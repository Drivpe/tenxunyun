import requests
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# 重要：请先运行get_cookies.py获取登录后的cookies，并确保cookies.json文件存在且格式正确
session = requests.Session()

ACTIVITY_ID = 164461404341040
SERVER_ACT_ID = 1897632168296710
SERVER_TYPE = "bundle_budget_mc_lg4_01"
# 镜像 ID 随活动刷新，以活动页 defaultGoodsParam.imageId 为准；
# 页面只给出 BlueprintId=LINUX_UNIX（Linux 纯净系统），未标注具体发行版，故不断言 Ubuntu。
SERVER_IMAGE_ID = "lhbp-eqora508"
REFERER_URL = "https://cloud.tencent.com/act/pro/featured-202607?fromSource=gwzcw.12786259.12786259.12786259&utm_medium=cpc&utm_id=gwzcw.12786259.12786259.12786259&msclkid=f99b232f8cf718f65fb449478f0cb94b#MS"
ACTIVITY_PAGE_URL = "https://cloud.tencent.com/act/pro/featured-202607"
REGION_NAMES = {1: "广州", 4: "上海", 8: "北京"}
BEIJING_TZ = timezone(timedelta(hours=8))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

# Cookie 改为可延迟加载：文件缺失时仍可 import（单元测试、场次解析都不依赖登录态）
def load_cookies(path="cookies.json"):
    """读取 cookies.json；不存在时返回空列表并提示，不阻断导入"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


cookies = load_cookies()


def install_cookies():
    """把 cookies.json 灌入 session，返回是否成功"""
    global cookies
    cookies = load_cookies()
    if not cookies:
        return False
    session.cookies.clear()
    for cookie in cookies:
        # 兼容Cookie字段缺失的情况
        session.cookies.set(
            cookie.get('name', ''),
            cookie.get('value', ''),
            domain=cookie.get('domain', ''),
            path=cookie.get('path', '/')  # 默认路径为/
        )
    return True


def get_cookie_value(name):
    values = [cookie.get("value", "") for cookie in cookies if cookie.get("name") == name and cookie.get("value")]
    return values[-1] if values else ""


def get_csrf_token():
    skey = get_cookie_value("skey") or get_cookie_value("p_skey")
    if skey:
        token = 5381
        for char in skey:
            token += (token << 5) + ord(char)
        return str(token & 0x7fffffff)
    return get_cookie_value("qcmainCSRFToken")


check_data = {
    "activity_id": ACTIVITY_ID,
    "goods": [
        {
            "act_id": SERVER_ACT_ID,
            "region_id": [1,4,8]
        }
    ],
    "preview": 0
}


headers = {
    "x-csrf-token": get_csrf_token(),
    "X-CSRF-TOKEN": get_csrf_token(),
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT,
    "referer": REFERER_URL,
    "origin": "https://cloud.tencent.com"
}


def refresh_csrf_headers():
    """登录态变化后重算 CSRF，避免沿用失效 Token"""
    token = get_csrf_token()
    headers["x-csrf-token"] = token
    headers["X-CSRF-TOKEN"] = token
    return token

# =================== 检查是否可抢购 =================== #

def check_available():
    """
    检查库存，返回有货的地域ID（无货返回None）
    """
    try:
        resp = session.post(
            "https://act-api.cloud.tencent.com/dianshi/check-available",
            json=check_data,
            headers=headers,
            timeout=10  # 新增超时控制
        )
        resp.raise_for_status()  # 抛出HTTP错误（4xx/5xx）
        result = resp.json()
    except Exception as e:
        print(f"❌ 库存检查接口调用失败：{str(e)}")
        return None

    # 校验接口返回是否正常
    if result.get("code") != 0 or result.get("msg") != "ok":
        print(f"❌ 库存检查接口返回异常：{json.dumps(result, ensure_ascii=False)}")
        return None

    # 校验商品基础权限（修复：逻辑反转）
    goods_data = result.get("data", [{}])[0]
    if goods_data.get("available") != 1 or goods_data.get("user_available") != 1:
        print("❌ 商品无购买权限/整体无货")
        return None

    # 安全获取地域库存（修复：避免KeyError）
    quota = goods_data.get("quota", {})
    for region_id, region_name in REGION_NAMES.items():
        # 逐层get，避免字段缺失报错
        available = quota.get(str(region_id), {})\
                        .get(SERVER_TYPE, {})\
                        .get("available", 0)
        if available > 0:
            print(f"✅ 检测到{region_name}（region_id={region_id}）有库存！")
            return region_id

    # 所有地域无货
    print("❌ 所有目标地域均无库存")
    return None


# =================== 立即购买（核心下单） =================== #
def buy_now(region_id):
    """
    调用do-goods接口完成购买
    :param region_id: 有货的地域ID
    """
    do_data = {
        "activity_id": ACTIVITY_ID,
        "agent_channel": {
            "fromChannel": "",
            "fromSales": "",
            "isAgentClient": False,
            "fromUrl": REFERER_URL
        },
        
        "business": {
            "id": 22755,
            "from": "lightningDeals"
        },
        "goods": [
            {
                "act_id": SERVER_ACT_ID,
                "type": SERVER_TYPE,
                "goods_param": {
                    "BlueprintId": "LINUX_UNIX",
                    "area": 1,
                    "ddocUnionConnect": 0,
                    "goodsNum": 1,
                    "imageId": SERVER_IMAGE_ID,
                    "scenario": "0",
                    "timeSpanUnit": "12m",
                    "zone": "",
                    "regionId": region_id,
                    "type": SERVER_TYPE
                }
            }
        ],
        
        "preview": 0
    }
    do_data["agent_channel"]["fromUrl"] = REFERER_URL
    try:
        # 修复：传do_data而非pay_data
        resp = session.post(
            "https://act-api.cloud.tencent.com/dianshi/do-goods",
            json=do_data,  # 关键修复：使用正确的购买参数
            headers=headers,
            timeout=10
        )
        print(f"🎯 核心购买接口返回：{resp.text}")
        return resp.json()
    except Exception as e:
        print(f"❌ 核心购买接口调用失败：{str(e)}")
        return None
    
def get_server_time():
    """获取服务器时间（绝对毫秒时间戳，与时区无关）"""
    response = requests.head(ACTIVITY_PAGE_URL, timeout=10)
    server_time = response.headers.get("Date")

    if not server_time:
        print("未获取到服务器时间")
        return None

    # HTTP Date 固定为 GMT，必须显式标注时区，否则跨时区机器会算错 8 小时
    dt = datetime.strptime(server_time, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
    beijing_time = dt.astimezone(BEIJING_TZ)
    timestamp_ms = int(dt.timestamp() * 1000)
    print(f"服务器时间(GMT): {dt:%Y-%m-%d %H:%M:%S}")
    print(f"北京时间: {beijing_time:%Y-%m-%d %H:%M:%S}")
    print(f"时间戳(毫秒): {timestamp_ms}")
    return timestamp_ms

def parse_seckill_sessions(html, activity_id=ACTIVITY_ID, target_act_id=SERVER_ACT_ID):
    """
    从活动页 HTML 解析目标商品的秒杀场次。

    返回按开始时间升序的列表：[{start_ms, end_ms, start_text}, ...]
    页面每个场次块都带 activity_id 与绝对毫秒 startTime，
    因此结果与时区无关，无需人工换算。
    """
    marker = f'"activity_id":{activity_id},"channel_tag"'
    blocks = html.split(marker)[1:]
    pattern = re.compile(
        r'"start_date":"(\d{4}-\d{2}-\d{2})","start_time":"(\d{2}:\d{2}:\d{2})"'
        r',"status":(\d+),"startTime":(\d{13}),"endTime":(\d{13})'
    )
    sessions = []
    for block in blocks:
        match = pattern.search(block)
        if not match:
            continue
        # 只保留包含目标商品的场次，避免误抢其它品类
        if str(target_act_id) not in block:
            continue
        start_ms = int(match.group(4))
        sessions.append(
            {
                "start_ms": start_ms,
                "end_ms": int(match.group(5)),
                "start_text": f"{match.group(1)} {match.group(2)}",
            }
        )
    return sorted(sessions, key=lambda item: item["start_ms"])


def fetch_seckill_sessions(timeout=20):
    """拉取活动页并解析场次；失败返回空列表"""
    try:
        resp = requests.get(
            ACTIVITY_PAGE_URL,
            headers={"User-Agent": headers["User-Agent"]},
            timeout=timeout,
        )
        resp.raise_for_status()
        return parse_seckill_sessions(resp.text)
    except Exception as e:
        print(f"❌ 场次解析失败：{e}")
        return []


def pick_next_session(sessions, now_ms):
    """
    返回第一个尚未结束的场次。

    包含两种情况：正在进行中的场次（主循环会立刻触发抢购），
    以及下一个还没开始的场次。全部已结束则返回 None。
    """
    for session_item in sessions:
        if session_item["end_ms"] > now_ms:
            return session_item
    return None


def buy_now_concurrent(region_ids):
    """并发抢购多个地域"""
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(buy_now, rid): rid for rid in region_ids}
        for future in future_map:
            rid = future_map[future]
            result = future.result()
            # 接口异常时 buy_now 返回 None，此处必须先判空，否则整个重试循环会崩溃
            if isinstance(result, dict) and result.get("code") == 0:
                print(f"🎉 抢购成功！地域: {REGION_NAMES.get(rid, rid)}")
                return result
            region_label = REGION_NAMES.get(rid, rid)
            if result is None:
                print(f"地域 {region_label} 抢购失败: 无响应（网络或接口异常）")
            else:
                print(f"地域 {region_label} 抢购失败: {result}")
    return None

# =================== 主程序 =================== #

# 明确不可重试的业务错误：账号资格不满足，重试毫无意义
# 1100106 = 活动仅对已激活账号开放；1100507 = 获取用户信息失败
FATAL_CODES = {1100106, 1100507}
# 限流：继续高频轰炸只会延长封禁，需要退避
RATE_LIMIT_CODES = {408}


def classify_result(result):
    """把接口返回归类：success / rate_limited / fatal / retryable"""
    if isinstance(result, dict):
        code = result.get("code")
        if code == 0:
            return "success"
        if code in RATE_LIMIT_CODES:
            return "rate_limited"
        if code in FATAL_CODES:
            return "fatal"
    return "retryable"


def prepare_eligibility_check():
    """
    调用 prepare-do 预检账号资格，返回 'passed' / 'blocked' / 'unknown'。

    为什么必须单独预检：check-available 的 user_available=1 只表示商品维度
    可用，并不校验账号激活状态；prepare-do 返回的 act_condition 才是账号
    真实状态。实测存在 user_available=1 却被 do-goods 以 1100507 拒绝的账号，
    没有这一步，只会在开抢瞬间才发现抢不到。

    'unknown' 表示接口给出其它原因（例如秒杀尚未开始），不能据此判定资格失败。
    """
    try:
        resp = session.post(
            "https://act-api.cloud.tencent.com/dianshi/prepare-do",
            json={"activity_id": ACTIVITY_ID, "act_id": SERVER_ACT_ID},
            headers=headers,
            timeout=10,
        )
        result = resp.json()
    except Exception as e:
        print(f"⚠️ 资格预检接口调用失败，跳过预检：{e}")
        return "unknown"

    code = result.get("code")
    if code == 0:
        print("✅ 资格预检通过")
        return "passed"

    if code in FATAL_CODES:
        detail = (result.get("data") or {}).get("detail") or {}
        act_condition = detail.get("act_condition") or {}
        missing = [key for key, value in act_condition.items() if value == 0 and key != "available"]
        print(f"⛔ 资格预检未通过：code={code} msg={result.get('msg')}")
        if missing:
            print(f"   账号未满足的条件：{', '.join(missing)}")
        if "activated" in missing:
            print("   该活动要求账号已完成开通（激活），请先在腾讯云控制台完成账号激活，")
            print("   否则本场及后续场次都会被 do-goods 直接拒绝。")
        return "blocked"

    print(f"ℹ️ 资格预检返回其它状态：code={code} msg={result.get('msg')}")
    return "unknown"


def buy_now_with_retry(
    region_ids,
    duration_seconds=60,
    interval_seconds=0.5,
    buy_func=buy_now_concurrent,
    time_func=time.monotonic,
    sleep_func=time.sleep,
    max_backoff_seconds=8.0,
):
    deadline = time_func() + duration_seconds
    attempt = 0
    last_result = None
    backoff = interval_seconds

    while True:
        attempt += 1
        print(f"retry attempt {attempt}")
        last_result = buy_func(region_ids)
        kind = classify_result(last_result)

        if kind == "success":
            return last_result

        if kind == "fatal":
            # 资格类硬错误重试不会改变结果，立刻停手，避免继续刷接口加重风控
            print("⛔ 账号资格校验未通过，停止重试")
            return last_result

        remaining_seconds = deadline - time_func()
        if remaining_seconds <= 0:
            print(f"retry window ended after {duration_seconds} seconds")
            return last_result

        if kind == "rate_limited":
            # 408 限流：指数退避，给网关冷却时间
            wait_seconds = min(max(backoff * 2, 1.0), max_backoff_seconds)
            backoff = wait_seconds
            print(f"⚠️ 触发限流(408)，退避 {wait_seconds:.1f} 秒")
        else:
            # 正常可重试（如秒杀尚未开始）：恢复基准节奏
            backoff = interval_seconds
            wait_seconds = interval_seconds

        sleep_func(min(wait_seconds, remaining_seconds))



def select_seckill_timestamp(manual_time_str="", now_ms=None):
    """
    决定本次抢购的绝对毫秒时间戳。

    manual_time_str 非空时按北京时间手工指定；
    否则从活动页自动解析当前进行中或下一个未结束的场次。
    无法确定时返回 None。
    """
    if manual_time_str:
        dt = datetime.strptime(manual_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING_TZ)
        return int(dt.timestamp() * 1000)

    sessions = fetch_seckill_sessions()
    if not sessions:
        print("❌ 未能从活动页解析到秒杀场次，可设置 SECKILL_TIME_STR 手工指定")
        return None

    # 用服务器时间选场次：本机时钟偏差过大时，本地时间可能误判当前场次已经结束
    if now_ms is None:
        now_ms = get_server_time()
    if now_ms is None:
        now_ms = time.time() * 1000

    # 选「尚未结束」的场次：若当前场次仍在进行中则立即开抢，否则等到下一场
    target = pick_next_session(sessions, now_ms)
    if target is None:
        print("❌ 当前没有未开始的场次，最近场次为：")
        for item in sessions:
            print(f"   {item['start_text']} -> {item['start_ms']}")
        return None

    print(f"📅 自动选中场次：{target['start_text']}（北京时间）")
    return target["start_ms"]


if __name__ == "__main__":
    print("🚀 启动腾讯云抢购脚本...")

    # 留空则自动从活动页解析下一个场次；需要强制指定时填 "YYYY-MM-DD HH:MM:SS"（北京时间）
    SECKILL_TIME_STR = ""
    # 提前触发的毫秒数，避免本机与服务器时钟差异导致请求偏晚
    EARLY_TRIGGER_MS = 3_000

    if not install_cookies():
        print("❌ 未找到 cookies.json，请先运行：python get_cookies.py")
        raise SystemExit(1)
    refresh_csrf_headers()

    region_ids = [1, 4, 8]
    check_only = "--check" in sys.argv

    # 资格预检必须在等待之前：抢不到库存和没资格抢，是两件事
    eligibility = prepare_eligibility_check()

    if check_only:
        # 诊断模式不做硬阻断：继续输出库存与场次，一条命令看全状态，
        # 资格被拦时仍以退出码 2 给出红色信号
        check_available()
        sessions = fetch_seckill_sessions()
        now_ms = get_server_time()
        target = pick_next_session(sessions, now_ms) if now_ms else None
        if target:
            minutes = (target["start_ms"] - now_ms) / 1000 / 60
            state = f"已开始 {abs(minutes):.0f} 分钟" if minutes <= 0 else f"距开抢 {minutes:.0f} 分钟"
            print(f"📅 场次 {target['start_text']}（北京时间），{state}，"
                  f"结束于 {datetime.fromtimestamp(target['end_ms'] / 1000, BEIJING_TZ):%H:%M}")
        else:
            print("❌ 当前没有未结束的场次")
        print("✅ 预检完成（未调用任何下单接口）")
        raise SystemExit(2 if eligibility == "blocked" else 0)

    if eligibility == "blocked":
        print("❌ 已停止：该账号不满足活动资格，重试与换场次都无法绕过。")
        raise SystemExit(2)
    if eligibility == "unknown":
        print("ℹ️ 未能确认可抢，将继续按原计划等待开抢。")

    seckill_timestamp = select_seckill_timestamp(SECKILL_TIME_STR)
    if seckill_timestamp is None:
        raise SystemExit(1)

    print(f"目标开抢时间戳(毫秒): {seckill_timestamp}")
    print(f"北京时间: {datetime.fromtimestamp(seckill_timestamp / 1000, BEIJING_TZ):%Y-%m-%d %H:%M:%S}")

    while True:
        current_time = get_server_time()
        if current_time is None:
            # 取不到服务器时间时不能直接比较，退避后重试
            time.sleep(1)
            continue
        if current_time >= seckill_timestamp - EARLY_TRIGGER_MS:
            print("秒杀开始！")
            buy_now_with_retry(region_ids, duration_seconds=60, interval_seconds=0.5)
            break
        else:
            remaining_seconds = (seckill_timestamp - current_time) / 1000
            print(f"⏳ 等待开抢，剩余 {remaining_seconds:.0f} 秒")
            # 距开抢较远时降低轮询频率，避免无意义地刷接口
            time.sleep(10 if remaining_seconds > 60 else 1)
