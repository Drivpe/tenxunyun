# 腾讯云轻量应用服务器抢购脚本

这是一个使用 Python 编写的腾讯云活动抢购脚本。脚本通过 Playwright 获取登录 Cookie，自动计算 CSRF Token，在设定时间到达后并发尝试广州、上海、北京三个地域，并在限定时间内持续重试。

![Tencent Cloud](image.png)

## 重要说明

运行 `snap_up_server.py` 会调用腾讯云真实购买接口。只要接口返回成功，就可能生成真实待付款订单。

- 脚本不能保证抢购成功，结果取决于库存、账号资格、网络延迟、接口拥塞和腾讯云风控。
- 当前脚本会并发请求三个地域。如果多个地域同时成功，可能生成多个待付款订单。
- 使用前请确认商品、镜像、价格、购买时长和地域符合你的需求。
- 请遵守腾讯云活动规则、账号协议和适用法律，不要以过高频率请求接口。
- `cookies.json` 包含登录凭据，禁止分享或提交到公开仓库。

## 当前默认配置

当前代码面向腾讯云 `featured-202607` 活动，默认参数如下：

| 配置 | 当前值 | 说明 |
| --- | --- | --- |
| 活动 ID | `164461404341040` | `ACTIVITY_ID` |
| 商品活动 ID | `1897632168296710` | `SERVER_ACT_ID` |
| 商品类型 | `bundle_budget_mc_lg4_01` | 4 核 4 GB 套餐标识 |
| 系统镜像 | `lhbp-eqora508` | 活动页当前默认镜像（`BlueprintId=LINUX_UNIX`，Linux 纯净系统） |
| 购买时长 | `12m` | 1 年 |
| 地域 | `1, 4, 8` | 广州、上海、北京 |
| 重试窗口 | 60 秒 | 开始抢购后持续时间 |
| 重试间隔 | 0.5 秒 | 每轮完成后的额外等待时间 |
| 提前触发 | 3000 毫秒 | 开抢前 3 秒开始请求 |

活动页只暴露 `BlueprintId=LINUX_UNIX`，不标注具体发行版，因此脚本不再声明镜像是 Ubuntu。需要特定系统时请在活动页确认。

地域 ID 来自当前活动页面：

| `region_id` | 城市 | 腾讯云地域标识 |
| --- | --- | --- |
| `1` | 广州 | `ap-guangzhou` |
| `4` | 上海 | `ap-shanghai` |
| `8` | 北京 | `ap-beijing` |

活动参数会变化。使用前应打开当前活动页面，确认活动 ID、商品 ID、套餐、镜像和地域仍然有效。

## 工作流程

1. `get_cookies.py` 打开 Chromium 并跳转到腾讯云登录页面。
2. 用户扫码并在手机端确认登录。
3. 登录完成后，Playwright 把 Cookie 保存到本地 `cookies.json`。
4. `snap_up_server.py` 加载 Cookie，并从 `skey` 或 `p_skey` 自动计算 CSRF Token。
5. 脚本抓取活动页，解析目标商品尚未结束的秒杀场次，得到开抢的绝对毫秒时间戳。
6. 脚本读取腾讯云页面响应头中的 HTTP `Date` 对时，到达提前触发时间后并发调用三个地域的真实购买接口。
7. 请求失败时继续重试，成功或重试窗口结束后退出。

主程序当前不会先等待库存查询结果，而是到点后直接调用购买接口。`check_available()` 主要用于人工诊断库存和账号资格。

## 环境要求

- Python 3.8 或更高版本
- Windows 10/11、Linux 或 macOS
- 可以访问腾讯云和 GitHub 的网络
- 腾讯云账号已完成活动要求的实名、资格或新用户认证
- 手机端可以扫码登录腾讯云

建议使用项目专用虚拟环境，避免系统 Python、Codex 临时 Python 或其他项目更新后导致依赖消失。

## 安装

### 获取项目

```bash
git clone https://github.com/kkkksad/tenxunyun.git
cd tenxunyun
```

### Windows PowerShell

创建并激活虚拟环境：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果系统没有 `py` 命令，可尝试：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装 Python 依赖和 Chromium：

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

如果 PowerShell 阻止激活脚本，可以不激活虚拟环境，直接使用：

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m playwright install chromium
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

部分 Linux 发行版需要额外安装浏览器系统依赖：

```bash
python -m playwright install --with-deps chromium
```

## 使用方法

### 1. 重新获取 Cookie

每次活动开始前都建议重新获取 Cookie：

```powershell
python .\get_cookies.py
```

Linux/macOS：

```bash
python get_cookies.py
```

浏览器打开后：

1. 使用微信或 QQ 扫描腾讯云登录二维码。
2. 在手机端确认授权。
3. 等待页面跳回 `featured-202607` 活动页。
4. 登录完成后脚本会等待约 8 秒，保存 Cookie 并自动关闭浏览器。

成功时会看到类似输出：

```text
Login succeeded. Saved 31 cookies to cookies.json.
```

不需要手动复制 CSRF Token。抢购脚本会读取 `cookies.json` 中的 `skey` 或 `p_skey`，自动计算并填写 `x-csrf-token`。

### 2. 检查抢购配置

打开 `snap_up_server.py`，确认文件顶部配置：

```python
ACTIVITY_ID = 164461404341040
SERVER_ACT_ID = 1897632168296710
SERVER_TYPE = "bundle_budget_mc_lg4_01"
SERVER_IMAGE_ID = "lhbp-eqora508"
REGION_NAMES = {1: "广州", 4: "上海", 8: "北京"}
```

秒杀时间默认自动获取，不需要手改。脚本会抓取活动页，解析目标商品尚未结束的场次：

```python
SECKILL_TIME_STR = ""  # 留空 = 自动解析场次
```

只有活动改版导致解析失败、或你明确要抢某一场时，才填北京时间强制指定：

```python
SECKILL_TIME_STR = "2026-10-22 10:00:00"
```

格式为 `年-月-日 时:分:秒`，按北京时间填写，脚本内部换算为绝对时间戳，与本机时区无关。

### 3. 预检资格（强烈建议每次开抢前执行）

```bash
python snap_up_server.py --check
```

只读模式，调用资格、库存、场次三个只读接口，**绝不下单**。输出示例：

```text
⛔ 资格预检未通过：code=1100106 msg=抱歉，当前活动仅针对已激活账号开放，欢迎了解其他活动。
   账号未满足的条件：activated, real_name
❌ 所有目标地域均无库存
📅 场次 2026-10-21 15:00:00（北京时间），已开始 13 分钟，结束于 18:00
```

资格被拦时退出码为 `2`。`check-available` 返回 `user_available=1` 不代表你能抢——它只校验商品维度；账号激活状态要用 `--check` 里的 `prepare-do` 预检确认。实测存在 `user_available=1` 却被下单接口以 `1100507` 全程拒绝的账号。

预检输出里 `1100136 已售罄` 与 `1100106/1100507 资格问题`含义完全不同：`prepare-do` 先校验账号资格、后看商品状态，能返回"售罄"就说明**资格已经没问题**，卡点只剩库存。此时直接运行主脚本会进入回流看守模式，无需人工干预。

### 4. 启动抢购脚本

建议提前几分钟启动，让脚本先完成 Python 加载、Cookie 读取和网络准备：

```powershell
python .\snap_up_server.py
```

Linux/macOS：

```bash
python snap_up_server.py
```

如果没有激活 Windows 虚拟环境：

```powershell
& '.\.venv\Scripts\python.exe' .\snap_up_server.py
```

不要只运行：

```powershell
.\snap_up_server.py
```

Windows 文件关联不完整时，这种方式可能立即返回且不显示任何输出。应明确使用 `python` 或虚拟环境中的 `python.exe`。

## 配置说明

### 提前触发

当前代码：

```python
EARLY_TRIGGER_MS = 3_000
if current_time >= seckill_timestamp - EARLY_TRIGGER_MS:
```

`3_000` 表示提前 3,000 毫秒，也就是提前 3 秒开始调用购买接口。例如官方时间为 `15:00:00`，脚本会从约 `14:59:57` 开始尝试。

如果希望提前 10 秒，可改为：

```python
EARLY_TRIGGER_MS = 10_000
```

提前请求时出现“秒杀尚未开始”是正常现象。不要把提前量设置得过大，以免产生大量无效请求或触发限流。

等待期间脚本按剩余时间自适应轮询对时请求：距开抢超过 60 秒时每 10 秒一次，进入最后 60 秒改为每 1 秒一次。取不到服务器时间时会退避重试而不是崩溃。

### 重试窗口和间隔

当前调用：

```python
buy_now_with_retry(
    region_ids,
    duration_seconds=60,
    interval_seconds=0.5,
)
```

- `duration_seconds=60`：整个重试阶段持续 60 秒。
- `interval_seconds=0.5`：每轮三个地域请求全部结束后，再等待 0.5 秒。

实际两轮请求的开始时间差还包含接口响应耗时，因此不一定严格等于 0.5 秒。腾讯云拥堵时，一轮可能持续数秒。

### 地域

主程序默认同时尝试三个地域：

```python
region_ids = [1, 4, 8]
```

如只接受上海，可改为：

```python
region_ids = [4]
```

同时请求多个地域会提高覆盖范围，但也存在多个地域同时生成待付款订单的可能。

### 镜像

当前镜像：

```python
SERVER_IMAGE_ID = "lhbp-eqora508"
```

该 ID 取自活动页 `defaultGoodsParam.imageId`，页面仅给出 `BlueprintId=LINUX_UNIX`（Linux 纯净系统），未标注具体发行版。镜像 ID 会随活动或商品变化，不能长期沿用；活动更新后应重新核对页面参数。

## 输出与结果判断

### 秒杀尚未开始

```text
{"code":1101001,"msg":"抱歉，秒杀尚未开始"}
```

提前触发阶段出现该结果是正常的，脚本会继续重试。

### CSRF 校验失败

```text
{"code":"CSRF-ERROR","msg":"CSRF 校验失败"}
```

通常表示 Cookie 已失效、不完整，或者登录会话发生变化。关闭正在运行的抢购脚本，重新运行 `get_cookies.py`，再重新启动抢购脚本。不要在代码中手填旧 Token。

### 售罄 1100136

```text
{"code":1100136,"msg":"抱歉，当前商品已售罄，欢迎选择其他商品"}
```

注意 `prepare-do` 先校验资格再看商品：返回售罄恰好证明**账号资格已通过**。场次进行中遇到该状态时，脚本会自动进入回流看守：每 5 秒用只读 `check-available` 轮询（静默，每 12 次报一行 `[watch N]`），检测到配额回流才定点下单，守到场次结束。这是实测结论——持续以 0.5 秒硬撞 `do-goods` 会换来成片 408，而同 session 的 `check-available` 始终正常。取消单通常在下单后 60 分钟支付时限到期时回流，15:00 场盯到 18:00 是合理的。

### 限流 408

```text
{"code":408,"msg":"系统访问频率过快，请稍后再试","data":{}}
```

三地域并发容易触发。脚本识别到 `408` 后会指数退避（1 秒起，逐轮翻倍，封顶 8 秒），而不是继续以 0.5 秒频率硬撞。限流是滑动窗口，持续高频只会延长封禁；同窗口内 `check-available` 通常仍可正常返回。

### 资格被拒（硬错误，重试无效）

```text
{"code":1100106,"msg":"抱歉，当前活动仅针对已激活账号开放，欢迎了解其他活动。"}
{"code":1100507,"msg":"获取用户信息失败，请确认该账号是否已完成注册"}
```

两类都属于账号资格问题，重试不会改变结果。脚本一旦识别到这两类错误码会立即停止重试，避免加重风控。用 `--check` 在开抢前确认。

`prepare-do` 返回的 `act_condition` 是账号实际状态，`user_condition` 是活动门槛（匿名页面同样暴露该字段）。常见卡点是 `activated=0` 与 `real_name=0`：账号未完成开通/实名认证，此时任何场次都无法成交。

### 未登录

返回 `NOT-LOGINED`、登录失效或购买资格异常时，重新获取 Cookie，并确认扫码登录的是目标腾讯云账号。

### 所有地域无库存

```text
所有目标地域均无库存
```

这表示库存查询接口正常、但广州、上海和北京的具体套餐配额都是 0。接口中的商品整体 `available=1` 仅代表活动商品有效，不代表每个地域有库存。

### 抢购成功

购买接口 `code=0` 才能视为接口成功。随后应立即登录腾讯云控制台检查待付款订单、地域、系统镜像、价格和有效期。

## 常见问题

### `ModuleNotFoundError: No module named 'requests'`

当前 Python 环境没有安装依赖，或者运行脚本时使用了另一套 Python：

```powershell
python -m pip install -r requirements.txt
python -c "import requests, playwright; print('dependencies ok')"
```

检查解释器路径：

```powershell
python -c "import sys; print(sys.executable)"
```

安装依赖和运行脚本必须使用同一个 Python。

### Playwright 提示找不到 Chromium

```powershell
python -m playwright install chromium
```

### `cookies.json` 不存在

先执行：

```powershell
python .\get_cookies.py
```

### `未能从活动页解析到秒杀场次`

自动场次解析依赖活动页的 JSON 内联数据。腾讯云改版页面结构后会失效，此时手动指定时间：

```python
SECKILL_TIME_STR = "2026-10-22 10:00:00"
```

判断是否为改版：打开活动页，搜索 `activity_id`，若场次块中不再同时出现 `start_date`、`start_time`、`startTime`，即为字段变更，需要更新 `parse_seckill_sessions()` 的正则。

### Linux 上 `python3 -m venv` 失败

提示 `ensurepip is not available` 时，安装对应发行版包：

```bash
sudo apt install python3-venv
```

若发行版暂无该包，可先建无 pip 的虚拟环境再引导：

```bash
python3 -m venv --without-pip .venv
curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
./.venv/bin/python /tmp/get-pip.py
./.venv/bin/python -m pip install -r requirements.txt
```

### Playwright 与已下载浏览器版本不匹配

`python -m playwright install chromium` 只安装当前 Python 包版本对应的构建。若之前用 Node 版 Playwright 装过浏览器，缓存目录里的版本号可能不同，直接补装即可：

```bash
python -m playwright install chromium
```

### 扫码后浏览器没有自动关闭

- 确认手机端已经点击授权。
- 确认浏览器最终进入 `cloud.tencent.com/act/pro/featured-202607`。
- 等待至少 8 秒。
- 仍无响应时关闭窗口并重新运行 `get_cookies.py`。

### 服务器时间看起来很奇怪

HTTP 响应头使用 GMT，因此日志可能同时显示 GMT、北京时间和毫秒时间戳。例如 GMT `07:00` 对应北京时间 `15:00`。

13 位数字是毫秒时间戳，仅用于程序比较，不是异常年份。网络请求、HTTP 时间仅精确到秒等因素可能造成数秒差异。

### 为什么提前运行还是抢不到

提前运行只能减少脚本启动和时间判断延迟，无法解决库存极少、账号资格、接口限流、网络拥塞或其他用户请求更早到达的问题。

## 安全说明

- `cookies.json` 已加入 `.gitignore`，不要使用 `git add -f cookies.json` 强制提交。
- 不要把 Cookie、`skey`、`p_skey`、CSRF Token 或完整请求头发给其他人。
- 如果怀疑 Cookie 泄露，请退出腾讯云登录、修改密码并重新建立会话。
- 公开日志前检查其中是否包含账号、订单或请求标识。
- 脚本请求的是未经公开稳定性承诺的活动接口，腾讯云更新页面后参数可能失效。

## 测试

运行单元测试：

```powershell
python -m unittest test_retry_window.py
```

编译检查：

```powershell
python -m py_compile get_cookies.py snap_up_server.py
```

测试覆盖重试窗口、地域映射、场次解析、场次选择、CSRF 推导和接口空响应，共 35 个用例，全部离线运行，不会调用真实购买接口。新增覆盖结果分类（success / rate_limited / fatal / retryable）、硬错误立即停止重试、408 指数退避与恢复基准节奏、prepare-do 资格预检四种分支。

## 项目结构

```text
tenxunyun/
├── .gitignore
├── README.md
├── requirements.txt
├── get_cookies.py
├── snap_up_server.py
├── test_retry_window.py
├── image.png
└── cookies.json          # 登录后本地生成，禁止提交
```

- `get_cookies.py`：打开浏览器登录并保存 Cookie。
- `snap_up_server.py`：加载会话、计算 CSRF、解析场次、校准时间并调用购买接口。
- `test_retry_window.py`：验证重试窗口、地域映射、场次解析与 CSRF。
- `requirements.txt`：Python 依赖列表。

## 免责声明

本项目仅用于个人学习和自动化流程研究，不提供任何抢购成功保证。使用者应自行核对商品参数、价格、地域、镜像、账号资格和活动规则，并自行承担运行脚本、生成订单、账号风控或其他后果。
