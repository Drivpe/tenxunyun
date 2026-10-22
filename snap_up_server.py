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

class StockCheckError(Exception):
    """库存查询本身失败（网络异常 / 接口返回 code != 0）。

    与"确实无货"严格区分：check_available 返回 None 才表示无货，
    抛本异常表示这次查询没有结论。看守据此告警，而不是把限流或
    登录失效当成无货静默空转到场次结束。
    """


def check_available(quiet=False):
    """
    检查库存，返回有货的地域ID（无货返回None）

    quiet=True 供回流看守使用：除命中库存的 ✅ 提示外，所有打印全部静默，
    避免长时间轮询刷屏；告警由调用方按自己的节奏输出。

    查询本身失败（接口异常，或返回 code != 0 / msg != "ok"）时抛
    StockCheckError，并把原始原因带进异常消息；"无权限/无货/所有地域
    无货"仍返回 None。
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
        if not quiet:
            print(f"❌ 库存检查接口调用失败：{e}")
        # quiet 模式下由看守统一控制告警节奏，这里不打印
        raise StockCheckError(f"库存检查接口调用失败：{e}") from e

    # 校验接口返回是否正常
    if result.get("code") != 0 or result.get("msg") != "ok":
        detail = json.dumps(result, ensure_ascii=False)
        if not quiet:
            print(f"❌ 库存检查接口返回异常：{detail}")
        raise StockCheckError(f"库存检查接口返回异常：{detail}")

    # 校验商品基础权限（修复：逻辑反转）
    goods_data = result.get("data", [{}])[0]
    if goods_data.get("available") != 1 or goods_data.get("user_available") != 1:
        if not quiet:
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
    if not quiet:
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
    
def get_server_time(timeout=2):
    """获取服务器时间（绝对毫秒时间戳，与时区无关）

    失败一律返回 None（含网络异常）：调用方都按"对时不可用"降级处理，
    异常冒泡会直接崩掉主循环和 --check 诊断。

    timeout 必须小：该函数在主等待循环里被反复调用，实测 10 秒超时会在
    网络抖动时把开抢点整体拖后 8 秒（2026-10-22 10:00 场实测），
    秒杀场景下这等于直接放弃。
    """
    try:
        response = requests.head(ACTIVITY_PAGE_URL, timeout=timeout)
        server_time = response.headers.get("Date")
    except Exception as e:
        print(f"⚠️ 获取服务器时间失败：{type(e).__name__}")
        return None

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


def fetch_seckill_sessions(timeout=10, retries=3, backoff_seconds=2.0, total_budget_seconds=25.0):
    """
    拉取活动页并解析场次；失败返回空列表。

    必须重试：该页面在风控或灰度时会返回不含场次内联数据的精简版
    （实测同一 URL 出现过 1.4MB 完整页与仅数十字节 JS 挑战页两种响应），
    单次抓取失败不代表活动改版。

    必须限总时长：网络异常时单次 SSLError 实测就要 15 秒，3 次重试叠加
    退避会超过 60 秒，把 `--check` 这种诊断命令拖成"卡死"。因此整体
    预算 total_budget_seconds，超预算立即放弃并如实报告。
    """
    started = time.monotonic()
    for attempt in range(1, retries + 1):
        # 剩余预算不足一次请求的最低耗时就不再尝试
        remaining = total_budget_seconds - (time.monotonic() - started)
        if remaining <= 0:
            print(f"⚠️ 抓取活动页已超出 {total_budget_seconds:.0f} 秒总预算，停止重试")
            return []
        try:
            resp = requests.get(
                ACTIVITY_PAGE_URL,
                headers={"User-Agent": headers["User-Agent"]},
                timeout=min(timeout, remaining),
            )
            resp.raise_for_status()
            sessions = parse_seckill_sessions(resp.text)
            if sessions:
                return sessions
            print(f"⚠️ 第 {attempt} 次抓取未解析到场次（页面 {len(resp.text)} 字节，可能是风控精简页）")
        except Exception as e:
            print(f"⚠️ 第 {attempt} 次抓取活动页失败：{type(e).__name__}")
        if attempt < retries:
            pause = min(backoff_seconds * attempt, max(0.0, total_budget_seconds - (time.monotonic() - started)))
            if pause > 0:
                time.sleep(pause)
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


# 失败结果的优先级：fatal 必须让主循环立即停手；其次 sold_out（温和节奏）；
# 再次限流；最后才是其它可重试错误
_FAILURE_PRIORITY = {"fatal": 0, "sold_out": 1, "rate_limited": 2, "retryable": 3}


def buy_now_concurrent(region_ids, serial=False):
    """抢购多个地域；成功返回成交结果，全部失败返回最具信息量的失败结果

    serial=True 时改为串行尝试。实测 2026-10-22 10:00 场：三地域并发会触发
    `1100110 正在执行其他操作，请稍候再试`——同一账号的并发下单被服务端
    串行化，三个请求互相把对方顶掉，等于自相残杀。串行虽然单轮耗时更长，
    但每个请求都能真正进入下单流程。
    """
    failures = []
    success = {"hit": False}

    def attempt(rid):
        result = buy_now(rid)
        if classify_result(result) == "success":
            print(f"🎉 抢购成功！地域: {REGION_NAMES.get(rid, rid)}")
            success["hit"] = True
            success["result"] = result
            return True
        region_label = REGION_NAMES.get(rid, rid)
        if result is None:
            print(f"地域 {region_label} 抢购失败: 无响应（网络或接口异常）")
        else:
            print(f"地域 {region_label} 抢购失败: {result}")
            failures.append(result)
        return False

    if serial:
        for rid in region_ids:
            if attempt(rid):
                return success["result"]
    else:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_map = {executor.submit(buy_now, rid): rid for rid in region_ids}
            for future in future_map:
                rid = future_map[future]
                result = future.result()
                # 接口异常时 buy_now 返回 None，classify_result 对非 dict 归为 retryable
                if classify_result(result) == "success":
                    print(f"🎉 抢购成功！地域: {REGION_NAMES.get(rid, rid)}")
                    return result
                region_label = REGION_NAMES.get(rid, rid)
                if result is None:
                    print(f"地域 {region_label} 抢购失败: 无响应（网络或接口异常）")
                else:
                    print(f"地域 {region_label} 抢购失败: {result}")
                    failures.append(result)

    if not failures:
        return None
    # 按分类优先级返回，让 buy_now_with_retry 能识别 fatal / sold_out 并区别处理
    failures.sort(key=lambda item: _FAILURE_PRIORITY.get(classify_result(item), 9))
    return failures[0]

# =================== 主程序 =================== #

# 明确不可重试的业务错误：账号资格不满足，重试毫无意义
# 1100106 = 活动仅对已激活账号开放；1100507 = 获取用户信息失败
FATAL_CODES = {1100106, 1100507}
# 登录态中途失效（Cookie 约 6 小时过期）：重试不会恢复会话，必须停下来重新扫码。
# 单独定义是为了让资格预检能给出"重新扫码"这种可操作提示，而不是笼统的资格未通过；
# 它们同样属于不可重试，故并入 FATAL_CODES。
LOGIN_EXPIRED_CODES = {"NOT-LOGINED", "CSRF-ERROR"}
FATAL_CODES |= LOGIN_EXPIRED_CODES
# 限流：继续高频轰炸只会延长封禁，需要退避
RATE_LIMIT_CODES = {408}
# 1100136 = 当前商品已售罄。注意：prepare-do 先校验账号资格再看商品，
# 返回该码说明账号资格已通过，卡点是库存而非资格，等待取消回流即可再试
SOLD_OUT_CODE = 1100136


def classify_result(result):
    """把接口返回归类：success / rate_limited / fatal / sold_out / retryable"""
    if isinstance(result, dict):
        code = result.get("code")
        if code == 0:
            return "success"
        if code in RATE_LIMIT_CODES:
            return "rate_limited"
        if code in FATAL_CODES:
            return "fatal"
        if code == SOLD_OUT_CODE:
            return "sold_out"
    return "retryable"


def prepare_eligibility_check():
    """
    调用 prepare-do 预检账号资格，返回 'passed' / 'blocked' / 'sold_out' /
    'login_expired' / 'unknown'。

    为什么必须单独预检：check-available 的 user_available=1 只表示商品维度
    可用，并不校验账号激活状态；prepare-do 返回的 act_condition 才是账号
    真实状态。实测存在 user_available=1 却被 do-goods 以 1100507 拒绝的账号，
    没有这一步，只会在开抢瞬间才发现抢不到。

    prepare-do 的校验顺序是先账号资格、后商品状态：返回 1100136（售罄）
    即证明资格已通过，卡点是库存，等待取消回流即可。

    'login_expired' 表示登录态失效（NOT-LOGINED / CSRF-ERROR）：Cookie 过期
    或会话变化，重试不会恢复，必须重新扫码后再启动；调用方应直接停止，
    而不是继续等待开抢。

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

    # 登录态问题必须硬拦：脚本可能提前数小时启动，Cookie 中途过期后
    # 若放行等待，到点开抢只会连续失败，白等一场
    if code in LOGIN_EXPIRED_CODES:
        print(f"⛔ 登录态失效：code={code} msg={result.get('msg')}")
        print("   Cookie 已过期或会话变化，请重新运行 get_cookies.py 扫码后再启动本脚本。")
        return "login_expired"

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

    if code == SOLD_OUT_CODE:
        print("✅ 账号资格已通过（能走到售罄判断就说明资格没问题）")
        print("ℹ️ 当前商品已售罄（1100136），卡点是库存，不是资格。")
        return "sold_out"

    print(f"ℹ️ 资格预检返回其它状态：code={code} msg={result.get('msg')}")
    return "unknown"


def buy_now_with_retry(
    region_ids,
    duration_seconds=60,
    interval_seconds=0.5,
    buy_func=None,
    time_func=time.monotonic,
    sleep_func=time.sleep,
    max_backoff_seconds=8.0,
    sold_out_interval_seconds=3.0,
    opening_burst_seconds=15.0,
):
    """
    重试窗口。

    opening_burst_seconds：开抢瞬间的黄金期。实测 2026-10-22 10:00 场，
    开抢后前 5 轮全部 408，若按指数退避 1→2→4→8 秒，15 秒内只发出 5 次
    请求；而这段窗口正是库存可能仍在的唯一时段。因此黄金期内不退避，
    保持 interval_seconds 节奏硬打，过了黄金期才启用指数退避保护账号。

    buy_func 默认走串行：实测三地域并发会互相触发
    `1100110 正在执行其他操作`，同账号并发下单被服务端串行化。
    """
    if buy_func is None:
        buy_func = lambda ids: buy_now_concurrent(ids, serial=True)
    deadline = time_func() + duration_seconds
    burst_deadline = time_func() + opening_burst_seconds
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

        in_burst = time_func() < burst_deadline

        if kind == "rate_limited":
            if in_burst:
                # 黄金期不退避：408 多半是瞬时拥塞，退避等于把窗口让给别人
                backoff = interval_seconds
                wait_seconds = interval_seconds
                print(f"⚠️ 触发限流(408)，黄金期内不退避，{wait_seconds:.1f} 秒后重试")
            else:
                # 过了黄金期：指数退避，给网关冷却时间，避免账号被加重风控
                wait_seconds = min(max(backoff * 2, 1.0), max_backoff_seconds)
                backoff = wait_seconds
                print(f"⚠️ 触发限流(408)，退避 {wait_seconds:.1f} 秒")
        elif kind == "sold_out":
            # 已售罄：保持温和节奏轮询等待取消回流；高频硬撞只会换来 408
            backoff = interval_seconds
            wait_seconds = interval_seconds if in_burst else sold_out_interval_seconds
            print(f"ℹ️ 已售罄，{wait_seconds:.1f} 秒后重试")
        else:
            # 正常可重试（如秒杀尚未开始）：恢复基准节奏
            backoff = interval_seconds
            wait_seconds = interval_seconds

        sleep_func(min(wait_seconds, remaining_seconds))



def resolve_now_ms(now_ms=None):
    """
    取当前毫秒时间戳，返回 (now_ms, used_local)。

    优先用服务器时间：本机时钟偏差过大时会误判场次是否已结束。对时失败
    时退回本机时间，并把 used_local 置 True，让调用方在日志里说明，
    避免"对时失败"被静默当成"没有场次"。
    """
    if now_ms is not None:
        return now_ms, False
    server_ms = get_server_time()
    if server_ms is not None:
        return server_ms, False
    return int(time.time() * 1000), True


def select_seckill_session(manual_time_str="", now_ms=None):
    """
    决定本次抢购的场次，返回 {start_ms, end_ms, start_text}，无法确定返回 None。

    manual_time_str 非空时按北京时间手工指定（无 end_ms，为 None）；
    否则从活动页自动解析当前进行中或下一个未结束的场次。
    """
    if manual_time_str:
        dt = datetime.strptime(manual_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING_TZ)
        start_ms = int(dt.timestamp() * 1000)
        return {"start_ms": start_ms, "end_ms": None, "start_text": manual_time_str, "now_ms": None}

    sessions = fetch_seckill_sessions()
    if not sessions:
        print("❌ 未能从活动页解析到秒杀场次，可设置 SECKILL_TIME_STR 手工指定")
        return None

    now_ms, used_local = resolve_now_ms(now_ms)
    if used_local:
        print("⚠️ 未能获取服务器时间，已改用本机时间判断场次，结果可能有偏差")

    # 选「尚未结束」的场次：若当前场次仍在进行中则立即开抢，否则等到下一场
    target = pick_next_session(sessions, now_ms)
    if target is None:
        print("❌ 当前没有未结束的场次，最近场次为：")
        for item in sessions:
            print(f"   {item['start_text']} -> {item['start_ms']}")
        return None

    print(f"📅 自动选中场次：{target['start_text']}（北京时间）")
    # 携带对时结果，主流程不再重复请求服务器时间
    return {**target, "now_ms": now_ms}


def select_seckill_timestamp(manual_time_str="", now_ms=None):
    """兼容入口：只取开抢毫秒时间戳"""
    target = select_seckill_session(manual_time_str, now_ms)
    return target["start_ms"] if target else None


def watch_stock_and_buy(
    region_ids,
    end_ms,
    poll_seconds=5.0,
    check_func=None,
    buy_func=buy_now_concurrent,
    time_func=None,
    sleep_func=time.sleep,
    max_attempts=None,
    query_fail_threshold=5,
):
    """
    售罄回流看守。

    为什么用只读轮询而不是持续打 do-goods：实测 0.5 秒硬撞购买接口触发 408，
    而 check-available 连续请求仍正常返回 code=0。取消单回流的配额由
    check-available 侦测到后再定点下单，既不撞风控，又能守到场次结束。

    终止条件以场次 end_ms 为主（例如 15:00 场守到 18:00）；end_ms 为 None
    （手工指定时间）时必须给 max_attempts，否则返回 None 表示无法确定边界。

    查询异常（StockCheckError，例如限流或登录态失效）不终止看守，但会告警：
    首次失败打印一次原因，连续失败达到 query_fail_threshold 次后明确提示
    看守可能空转；查询成功一次即重置失败计数。

    成功返回成交结果；场次结束、资格硬错误或达到轮询上限返回 None。
    """
    if time_func is None:
        time_func = lambda: time.time() * 1000
    if check_func is None:
        # 静默轮询：无货是常态，刷屏到 18:00 会有上千行
        check_func = lambda: check_available(quiet=True)

    if end_ms is None and max_attempts is None:
        print("⚠️ 手工时间无法确定场次边界，请指定 max_attempts 后使用看守模式")
        return None

    attempt = 0
    fail_streak = 0
    while max_attempts is None or attempt < max_attempts:
        attempt += 1
        now_ms = time_func()
        if end_ms is not None and now_ms >= end_ms:
            print("⏱️ 本场次已结束，停止回流看守")
            return None

        try:
            region_id = check_func()
        except StockCheckError as e:
            # 查询失败不等于无货：不能当成 None 静默轮询，否则限流或
            # 登录失效时看守会一直空转到场次结束而毫无提示
            fail_streak += 1
            if fail_streak == 1:
                print(f"⚠️ 库存查询异常：{e}（将继续轮询）")
            elif fail_streak % query_fail_threshold == 0:
                print(f"🚨 库存查询已连续失败 {fail_streak} 次：可能被限流或登录态失效，"
                      f"看守可能空转到场次结束，请检查 Cookie 与网络")
            region_id = None
        else:
            # 查询成功一次就重置：连续失败计数只统计"无结论"的次数
            fail_streak = 0

        if region_id is not None:
            print(f"🔥 检测到回流库存（{REGION_NAMES.get(region_id, region_id)}），立即下单")
            result = buy_func([region_id])
            if classify_result(result) == "success":
                return result
            if classify_result(result) == "fatal":
                print("⛔ 资格校验未通过，停止看守")
                return None
        elif attempt % 12 == 1 and fail_streak == 0:
            print(f"[watch {attempt}] 暂无回流，每 {poll_seconds:.0f} 秒重查")

        sleep_func(poll_seconds)

    print("⏱️ 达到回流轮询上限，停止看守")
    return None


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
        try:
            check_available()
        except StockCheckError as e:
            # 诊断模式只报告，不让异常冒泡打断后面的场次信息
            print(f"⚠️ 库存查询失败：{e}")
        sessions = fetch_seckill_sessions()
        now_ms, used_local = resolve_now_ms()
        if used_local:
            # 对时失败不能直接判无场次（会误报），退回本地时间并说明
            print("⚠️ 未能获取服务器时间，已改用本机时间判断场次，结果可能有偏差")
        target = pick_next_session(sessions, now_ms)
        if target:
            minutes = (target["start_ms"] - now_ms) / 1000 / 60
            state = f"已开始 {abs(minutes):.0f} 分钟" if minutes <= 0 else f"距开抢 {minutes:.0f} 分钟"
            print(f"📅 场次 {target['start_text']}（北京时间），{state}，"
                  f"结束于 {datetime.fromtimestamp(target['end_ms'] / 1000, BEIJING_TZ):%H:%M}")
        elif not sessions:
            # 抓不到场次 ≠ 没有场次，必须分开报，否则会被误读成活动已结束
            print("⚠️ 未能从活动页解析到场次（可能是风控精简页或网络异常），场次状态未知")
        else:
            print("❌ 当前没有未结束的场次")
        print("✅ 预检完成（未调用任何下单接口）")
        raise SystemExit(2 if eligibility in ("blocked", "login_expired") else 0)

    if eligibility == "blocked":
        print("❌ 已停止：该账号不满足活动资格，重试与换场次都无法绕过。")
        raise SystemExit(2)
    if eligibility == "login_expired":
        print("❌ 已停止：现在重新获取 Cookie 后再启动脚本。")
        raise SystemExit(3)
    if eligibility == "unknown":
        print("ℹ️ 未能确认可抢，将继续按原计划等待开抢。")

    target = select_seckill_session(SECKILL_TIME_STR)
    if target is None:
        raise SystemExit(1)

    start_dt = datetime.fromtimestamp(target["start_ms"] / 1000, BEIJING_TZ)
    now_ms = target["now_ms"] or get_server_time() or int(time.time() * 1000)
    if target["end_ms"] is not None:
        end_dt = datetime.fromtimestamp(target["end_ms"] / 1000, BEIJING_TZ)
        print(f"当前北京时间: {datetime.fromtimestamp(now_ms / 1000, BEIJING_TZ):%H:%M:%S}，"
              f"本场窗口 {start_dt:%H:%M}–{end_dt:%H:%M}")
    else:
        print(f"目标开抢时间: {start_dt:%Y-%m-%d %H:%M:%S}（北京时间，手工指定）")

    # 场次已在进行中且当前售罄：进入只读回流看守，守到场次结束。
    # 注意必须排除"场次尚未开始"的情况：开抢前配额本就是 0，prepare-do 同样
    # 返回 1100136，若在这里直接进看守，就会跳过真正的开抢瞬间。
    if (eligibility == "sold_out"
            and target["end_ms"] is not None
            and target["start_ms"] <= now_ms < target["end_ms"]):
        end_text = datetime.fromtimestamp(target["end_ms"] / 1000, BEIJING_TZ).strftime("%H:%M")
        print(f"👀 场次进行中且当前售罄，进入回流看守直到 {end_text}")
        result = watch_stock_and_buy(region_ids, target["end_ms"])
        if classify_result(result) == "success":
            print("🎉 回流抢购成功，60 分钟内必须完成支付")
            raise SystemExit(0)
        raise SystemExit(1)

    if eligibility == "sold_out":
        # 开抢前售罄是正常状态，必须继续等待到点，不能提前退场
        print("ℹ️ 当前显示售罄属开抢前正常状态，继续等待开抢")

    # ===== 等待开抢 =====
    # 关键设计：只在开始等待时对一次时，算出"服务器时间 - 本机单调时钟"的偏移，
    # 之后全程用本机单调时钟推进。绝不在循环里反复发 HEAD 请求对时——
    # 2026-10-22 10:00 场实测：两次 ReadTimeout(10s) 把开抢点整体拖后 8 秒，
    # 等到真正发请求时库存已空。秒杀场景下，等待循环必须与网络解耦。
    def sync_offset():
        """返回 (offset_ms, ok)：offset = 服务器时间 - 本机时钟"""
        local_now_ms = time.time() * 1000
        server_now_ms = get_server_time(timeout=2)
        if server_now_ms is None:
            return None, False
        return server_now_ms - local_now_ms, True

    offset_ms, synced = sync_offset()
    if not synced:
        print("⚠️ 首次对时失败，改用本机时间；请确认本机时钟准确（NTP）")
        offset_ms = 0

    def server_now():
        return time.time() * 1000 + offset_ms

    remaining_ms = target["start_ms"] - server_now()
    print(f"⏳ 距开抢 {remaining_ms / 1000:.1f} 秒（"
          f"{'已对时' if synced else '本机时间'}，等待期间不再请求网络）")

    # 距开抢还早时，用长时间 sleep 分段推进；最后阶段用精确 sleep
    while True:
        remaining_ms = target["start_ms"] - EARLY_TRIGGER_MS - server_now()
        if remaining_ms <= 0:
            break
        # 距开抢超过 60 秒时，每 10 秒重新对一次时（此时网络抖动无代价），
        # 进入最后 60 秒后完全依赖已校准的偏移，不再发任何对时请求
        if remaining_ms > 60_000:
            time.sleep(min(remaining_ms / 1000 - 50, 10))
            new_offset, ok = sync_offset()
            if ok:
                offset_ms = new_offset
            continue
        # 最后 60 秒：单次 sleep 到点，避免循环抖动累积误差
        time.sleep(max(0.0, remaining_ms / 1000))
        break

    print("秒杀开始！")
    result = buy_now_with_retry(region_ids, duration_seconds=60, interval_seconds=0.5)
    if classify_result(result) == "success":
        print("🎉 抢购成功，60 分钟内必须完成支付")
        raise SystemExit(0)
    if classify_result(result) == "fatal":
        print("❌ 已停止：账号资格校验未通过，重试与换场次都无法绕过。")
        raise SystemExit(2)

    # 60 秒窗口内没抢到，不等于这场结束了：秒杀配额常在开抢瞬间清空，
    # 之后靠别人取消订单回流。原来这里直接 break 会让脚本在开抢 1 分钟
    # 后就退出，把剩余整个场次窗口（最长近 2 小时）白白丢掉。
    if target["end_ms"] is not None and server_now() < target["end_ms"]:
        end_text = datetime.fromtimestamp(target["end_ms"] / 1000, BEIJING_TZ).strftime("%H:%M")
        print(f"⏳ 60 秒内未抢到，转入回流看守直到 {end_text}")
        result = watch_stock_and_buy(region_ids, target["end_ms"])
        if classify_result(result) == "success":
            print("🎉 回流抢购成功，60 分钟内必须完成支付")
            raise SystemExit(0)
        print("❌ 本场次结束，仍未抢到")
        raise SystemExit(1)
