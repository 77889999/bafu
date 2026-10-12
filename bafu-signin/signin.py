#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
霸服论坛 (bfltttt.com) 自动签到脚本
适用于 GitHub Actions 定时运行，支持 PushPlus 微信推送
针对不稳定站点优化：多重试 + 长超时
"""

import os
import re
import sys
import time
import requests
from datetime import datetime

# ============ 配置 ============
BASE_URL = "https://bfltttt.com"
LOGIN_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUSHPLUS_API = "http://www.pushplus.plus/send"
MAX_RETRY = 5
RETRY_DELAY = 10
TIMEOUT = 60


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def pushplus(title, content, token):
    if not token:
        return
    try:
        data = {"token": token, "title": title, "content": content, "template": "txt"}
        resp = requests.post(PUSHPLUS_API, data=data, timeout=10)
        result = resp.json()
        if result.get("code") == 200:
            log("PushPlus 推送成功")
        else:
            log(f"PushPlus 推送失败: {result}")
    except Exception as e:
        log(f"PushPlus 推送异常: {e}")


def request_with_retry(session, method, url, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    last_err = None
    for i in range(1, MAX_RETRY + 1):
        try:
            log(f"请求 {url}（第 {i}/{MAX_RETRY} 次）...")
            resp = session.request(method, url, **kwargs)
            resp.encoding = "utf-8"
            log(f"请求成功，状态码 {resp.status_code}")
            return resp
        except Exception as e:
            last_err = e
            log(f"第 {i} 次请求失败: {type(e).__name__}")
            if i < MAX_RETRY:
                log(f"等待 {RETRY_DELAY} 秒后重试...")
                time.sleep(RETRY_DELAY)
    raise last_err


def login(session, username, password):
    log("正在访问登录页获取 nonce...")
    login_page_url = f"{BASE_URL}/user-sign?tab=signin"
    resp = request_with_retry(session, "GET", login_page_url)

    nonce_match = re.search(r'name="_wpnonce"\s+value="([a-f0-9]+)"', resp.text)
    if not nonce_match:
        nonce_match = re.search(r'id="_wpnonce"\s+name="_wpnonce"\s+value="([a-f0-9]+)"', resp.text)

    if not nonce_match:
        log("无法提取 _wpnonce")
        return False

    wpnonce = nonce_match.group(1)
    log(f"获取登录 nonce: {wpnonce}")

    log("正在提交登录...")
    data = {
        "action": "user_signin",
        "username": username,
        "password": password,
        "remember": "forever",
        "_wpnonce": wpnonce,
        "redirect_to": BASE_URL + "/",
    }

    resp = request_with_retry(session, "POST", LOGIN_URL, data=data)

    try:
        result = resp.json()
    except Exception:
        log(f"登录返回非JSON: {resp.text[:200]}")
        return False

    log(f"登录返回: {result}")

    if result.get("error") == 0 or result.get("error") == False:
        log("登录成功")
        return True
    else:
        if "goto" in result or "url" in result or len(session.cookies) > 0:
            check = request_with_retry(session, "GET", BASE_URL + "/")
            if "退出登录" in check.text or "用户中心" in check.text:
                log("登录成功（页面验证）")
                return True
        log(f"登录失败: {result.get('msg', result)}")
        return False


def do_checkin(session):
    log("正在访问用户中心获取签到 nonce...")
    user_url = f"{BASE_URL}/user/"
    resp = request_with_retry(session, "GET", user_url)

    nonce = None
    m = re.search(r"user_upload_nonce['\"]?\s*[:=]\s*['\"]([a-f0-9]+)['\"]", resp.text)
    if m:
        nonce = m.group(1)
    if not nonce:
        m = re.search(r"nonce['\"]?\s*[:=]\s*['\"]([a-f0-9]{8,12})['\"]", resp.text)
        if m:
            nonce = m.group(1)

    if not nonce:
        log("无法提取签到 nonce")
        return "无法获取签到 nonce"

    log(f"获取签到 nonce: {nonce}")
    log("正在提交签到...")
    data = {"action": "user_checkin", "nonce": nonce}
    resp = request_with_retry(session, "POST", LOGIN_URL, data=data)

    try:
        result = resp.json()
    except Exception:
        return f"签到返回异常: {resp.text[:200]}"

    msg = result.get("msg", str(result))
    if result.get("error") == 0 or result.get("error") == False:
        log(f"签到成功！{msg}")
        return f"签到成功：{msg}"
    else:
        if "已签到" in msg:
            log(msg)
            return f"今日已签到：{msg}"
        else:
            log(f"签到返回: {result}")
            return f"签到异常：{msg}"


def main():
    username = os.environ.get("BAFU_USERNAME", "")
    password = os.environ.get("BAFU_PASSWORD", "")
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")

    if not username or not password:
        log("请设置环境变量 BAFU_USERNAME 和 BAFU_PASSWORD")
        sys.exit(1)

    log(f"账号: {username}")
    log(f"PushPlus: {'已配置' if pushplus_token else '未配置'}")
    log(f"重试: {MAX_RETRY} 次，超时: {TIMEOUT}s，间隔: {RETRY_DELAY}s")

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": BASE_URL + "/",
        "X-Requested-With": "XMLHttpRequest",
    })

    result_msg = ""
    try:
        login_ok = login(session, username, password)
        if not login_ok:
            result_msg = "登录失败"
        else:
            result_msg = do_checkin(session)
    except Exception as e:
        result_msg = f"运行异常: {type(e).__name__}: {e}"
        log(result_msg)

    log("=" * 50)
    log(f"最终结果: {result_msg}")
    log("=" * 50)

    pushplus(
        "霸服论坛签到结果",
        f"账号: {username}\n结果: {result_msg}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        pushplus_token
    )


if __name__ == "__main__":
    main()
