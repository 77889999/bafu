# 霸服论坛自动签到

基于 GitHub Actions 的 bfltttt.com 每日自动签到脚本。

## 使用方法

### 1. Fork 这个仓库到你自己的 GitHub

点右上角 Fork 按钮，复制一份到你账号下。

### 2. 添加 Secrets 账号密码

进入你 Fork 的仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，添加两个：

| Name | Secret |
|------|--------|
| `BAFU_USERNAME` | 你的论坛用户名 |
| `BAFU_PASSWORD` | 你的论坛密码 |

### 3. 启用 Actions

进入仓库的 **Actions** 页面，点击 "I understand my workflows, go ahead and enable them"。

然后找到 **"霸服论坛自动签到"** 这个 workflow，点 **"Enable workflow"**。

### 4. 手动测试一次

进入 Actions 页面 → 左边选 **"霸服论坛自动签到"** → 右边点 **"Run workflow"** → 绿色 Run 按钮。

跑完后点进去看日志，确认签到成功。

## 运行时间

默认每天 **北京时间早上 8:00** 自动运行一次。

想改时间的话，编辑 `.github/workflows/daily-signin.yml` 里的 cron 表达式（注意是 UTC 时间）：

| 北京时间 | UTC cron |
|---------|----------|
| 8:00    | `0 0 * * *` |
| 12:00   | `0 4 * * *` |
| 20:00   | `0 12 * * *` |

## 本地测试

```bash
pip install requests beautifulsoup4
export BAFU_USERNAME="你的用户名"
export BAFU_PASSWORD="你的密码"
python signin.py
```

## 文件说明

- `signin.py` — 签到主脚本
- `.github/workflows/daily-signin.yml` — GitHub Actions 定时配置
