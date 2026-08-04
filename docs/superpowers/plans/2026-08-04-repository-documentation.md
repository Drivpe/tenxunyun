# Repository Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the current Tencent Cloud seckill project with accurate, complete Chinese usage documentation and safe repository defaults.

**Architecture:** Keep the project as two executable Python scripts and one focused unit-test module. Use a single self-contained README as the user entry point, a minimal dependency manifest, and Git ignore rules that prevent authentication data and generated files from being published.

**Tech Stack:** Python 3.8+, requests, Playwright, unittest, Git, GitHub

---

### Task 1: Repository Hygiene and Dependencies

**Files:**
- Modify: `.gitignore`
- Create: `requirements.txt`

- [ ] **Step 1: Extend ignore rules**

Keep the existing secret rules and add:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
```

- [ ] **Step 2: Add the dependency manifest**

Create `requirements.txt` with:

```text
playwright
requests
```

- [ ] **Step 3: Verify secret and generated files are ignored**

Run:

```powershell
git check-ignore -v cookies.json __pycache__
```

Expected: both paths are reported as ignored.

### Task 2: Correct Region Display Metadata

**Files:**
- Modify: `snap_up_server.py`
- Modify: `test_retry_window.py`

- [ ] **Step 1: Add a failing mapping test**

Add:

```python
def test_region_names_match_activity_page(self):
    self.assertEqual(
        snap_up_server.REGION_NAMES,
        {1: "广州", 4: "上海", 8: "北京"},
    )
```

- [ ] **Step 2: Run the test and confirm the missing constant failure**

Run:

```powershell
python -m unittest test_retry_window.py
```

Expected: failure because `REGION_NAMES` does not exist.

- [ ] **Step 3: Add and use the authoritative mapping**

Add near the other constants:

```python
REGION_NAMES = {1: "广州", 4: "上海", 8: "北京"}
```

Replace the incorrect local `region_map` and iterate over
`REGION_NAMES.items()` in `check_available()`.

- [ ] **Step 4: Run the test and confirm it passes**

Run:

```powershell
python -m unittest test_retry_window.py
```

Expected: two tests pass.

### Task 3: Rewrite the User Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace obsolete instructions with one complete Chinese guide**

Use these top-level sections in order:

```markdown
# 腾讯云轻量应用服务器抢购脚本
## 重要说明
## 当前默认配置
## 工作流程
## 环境要求
## 安装
## 使用方法
## 配置说明
## 输出与结果判断
## 常见问题
## 安全说明
## 测试
## 项目结构
## 免责声明
```

Document exact Windows PowerShell and Linux/macOS commands for creating a
virtual environment, installing `requirements.txt`, installing Chromium,
running `get_cookies.py`, and running `snap_up_server.py`.

State explicitly that CSRF is derived from `skey` or `p_skey`; users do not
paste a token. Explain that `cookies.json` is sensitive and ignored. Describe
the current Ubuntu 24.04 LTS image ID, product type, activity IDs, valid region
IDs, official sale time, early offset, retry duration, and interval from the
current source.

Explain the real-order and possible multiple-pending-order behavior, HTTP Date
GMT display, Windows direct `.py` execution issue, missing dependency recovery,
cookie refresh, CSRF errors, not-started responses, no-stock responses, and the
fact that success cannot be guaranteed.

- [ ] **Step 2: Check documentation consistency**

Run searches that confirm obsolete manual-CSRF and incorrect region labels are
gone, while the automatic-CSRF and real-order warnings are present.

### Task 4: Verify the Publication Content

**Files:**
- Verify: `get_cookies.py`
- Verify: `snap_up_server.py`
- Verify: `test_retry_window.py`
- Verify: `README.md`
- Verify: `.gitignore`
- Verify: `requirements.txt`

- [ ] **Step 1: Compile scripts**

Run:

```powershell
python -m py_compile get_cookies.py snap_up_server.py
```

Expected: exit code 0.

- [ ] **Step 2: Run unit tests**

Run:

```powershell
python -m unittest test_retry_window.py
```

Expected: two tests pass.

- [ ] **Step 3: Inspect Git content**

Run `git diff --check`, inspect `git diff`, and verify that `cookies.json`,
`__pycache__`, and local credentials are absent from staged files.

No inventory or purchase endpoint is called during verification.

### Task 5: Commit and Publish

**Files:**
- Commit all approved source, test, documentation, dependency, and design files

- [ ] **Step 1: Preserve the source repository remote**

Rename the existing `origin` to `upstream`, then add:

```text
origin https://github.com/kkkksad/tenxunyun.git
```

- [ ] **Step 2: Ensure the branch name is main**

Run:

```powershell
git branch -M main
```

- [ ] **Step 3: Stage only approved files and commit**

Stage `.gitignore`, `README.md`, `requirements.txt`, `get_cookies.py`,
`snap_up_server.py`, `test_retry_window.py`, and this plan. Inspect the staged
diff, then commit with:

```text
docs: publish complete setup and usage guide
```

- [ ] **Step 4: Push without rewriting remote history**

Run:

```powershell
git push -u origin main
```

Expected: `main` is pushed and tracks `origin/main`. If the remote has
incompatible existing commits, stop rather than force-push.
