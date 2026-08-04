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
| 系统镜像 | `lhbp-1l4ptuvm` | Ubuntu 24.04 LTS 纯净系统 |
| 购买时长 | `12m` | 1 年 |
| 地域 | `1, 4, 8` | 广州、上海、北京 |
| 重试窗口 | 60 秒 | 开始抢购后持续时间 |
| 重试间隔 | 0.5 秒 | 每轮完成后的额外等待时间 |

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
5. 脚本读取腾讯云页面响应头中的 HTTP `Date`，用于等待官方秒杀时间。
6. 到达提前触发时间后，脚本并发调用三个地域的真实购买接口。
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
SERVER_IMAGE_ID = "lhbp-1l4ptuvm"  # Ubuntu 24.04 LTS
REGION_NAMES = {1: "广州", 4: "上海", 8: "北京"}
```

然后修改主程序中的官方秒杀时间：

```python
SECKILL_TIME_STR = "2026-08-04 15:00:00"
```

日期和时间必须改成当次活动的北京时间，格式为：

```text
年-月-日 时:分:秒
```

### 3. 启动抢购脚本

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
if current_time >= SECKILL_TIMESTAMP - 3_000:
```

`3_000` 表示提前 3,000 毫秒，也就是提前 3 秒开始调用购买接口。例如官方时间为 `15:00:00`，脚本会从约 `14:59:57` 开始尝试。

如果希望提前 10 秒，可改为：

```python
if current_time >= SECKILL_TIMESTAMP - 10_000:
```

提前请求时出现“秒杀尚未开始”是正常现象。不要把提前量设置得过大，以免产生大量无效请求或触发限流。

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
SERVER_IMAGE_ID = "lhbp-1l4ptuvm"
```

该 ID 对应 Ubuntu 24.04 LTS 64 位纯净系统镜像。镜像 ID 可能随活动或商品变化，不能只根据注释长期使用；活动更新后应重新核对页面参数。

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

测试不会调用真实购买接口。

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
- `snap_up_server.py`：加载会话、计算 CSRF、校准时间并调用购买接口。
- `test_retry_window.py`：验证重试窗口和地域映射。
- `requirements.txt`：Python 依赖列表。

## 免责声明

本项目仅用于个人学习和自动化流程研究，不提供任何抢购成功保证。使用者应自行核对商品参数、价格、地域、镜像、账号资格和活动规则，并自行承担运行脚本、生成订单、账号风控或其他后果。
