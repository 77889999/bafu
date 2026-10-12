#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
霸服论坛 (bfltttt.com) 自动签到脚本
适用于 GitHub Actions 定时运行，支持 PushPlus 微信推送
带网络重试机制
"""

import os
import re
import sys
import time
import json
import requests
from datetime import datetime

# ============ 配置 ============
BASE_URL = "https://bfltttt.com"
LOGIN_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUSHPLUS_API = "http://www.pushplus.plus/send"
MAX_RETRY = 3        # 最大重试次数
RETRY_DELAY = 5      # 重试间隔（秒）
TIMEOUT = 30         # 单次请求超时（秒）


def log(msg):
    """打印日志，带时间戳"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def pushplus(title, content, token):
    """通过 PushPlus 推送消息到微信"""
    if not token:
        log("未配置 PushPlus token，跳过推送")
        return

    try:
        data = {
            "token": token,
            "title": title,
            "content": content,
            "template": "txt",
        }
        resp = requests.post(PUSHPLUS_API, data=data, timeout=10)
        result = resp.json()
        if result.get("code") == 200:
            log("✅ PushPlus 推送成功")
        else:
            log(f"⚠️ PushPlus 推送失败: {result}")
    except Exception as e:
        log(f"⚠️ PushPlus 推送异常: {e}")


def request_with_retry(session, method, url, **kwargs):
    """带重试的请求"""
    kwargs.setdefault("timeout", TIMEOUT)
    last_err = None

    for i in range(1, MAX_RETRY + 1):
        try:
            log(f"请求 {url}（第 {i}/{MAX_RETRY} 次）...")
            resp = session.request(method, url, **kwargs)
            resp.encoding = "utf-8"
            return resp
        except Exception as e:
            last_err = e
            log(f"⚠️ 请求失败: {e}")
            if i < MAX_RETRY:
                log(f"等待 {RETRY_DELAY} 秒后重试...")
                time.sleep(RETRY_DELAY)

    raise last_err


def login(session, username, password):
    """登录论坛，返回是否成功"""
    log("正在访问登录页获取 nonce...")

    # 1. 先访问登录页获取 _wpnonce
    login_page_url = f"{BASE_URL}/user-sign?tab=signin"
    resp = request_with_retry(session, "GET", login_page_url)

    # 提取登录表单的 _wpnonce
    nonce_match = re.search(r'name="_wpnonce"\s+value="([a-f0-9]+)"', resp.text)
    if not nonce_match:
        nonce_match = re.search(r'id="_wpnonce"\s+name="_wpnonce"\s+value="([a-f0-9]+)"', resp.text)

    if not nonce_match:
        log("❌ 无法从登录页提取 _wpnonce")
        return False

    wpnonce = nonce_match.group(1)
    log(f"✅ 获取登录 nonce: {wpnonce}")

    # 2. 提交登录请求
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
        log(f"❌ 登录返回非JSON: {resp.text[:200]}")
        return False

    log(f"登录返回: {result}")

    if result.get("error") == 0 or result.get("error") == False:
        log("✅ 登录成功")
        return True
    else:
        if "goto" in result or "url" in result or len(session.cookies) > 0:
            check = request_with_retry(session, "GET", BASE_URL + "/")
            if "退出登录" in check.text or "用户中心" in check.text:
                log("✅ 登录成功（通过页面验证）")
                return True

        log(f"❌ 登录失败: {result.get('msg', result)}")
        return False


def do_checkin(session):
    """执行签到，返回结果消息"""
    log("正在访问用户中心获取签到 nonce...")

    # 访问用户中心页
    user_url = f"{BASE_URL}/user/"
    resp = request_with_retry(session, "GET", user_url)

    # 提取签到用的 nonce
    nonce = None

    # 方式1: 找 user_upload_nonce
    m = re.search(r"user_upload_nonce['\"]?\s*[:=]\s*['\"]([a-f0-9]+)['\"]", resp.text)
    if m:
        nonce = m.group(1)

    # 方式2: 找所有 nonce 变量
    if not nonce:
        m = re.search(r"nonce['\"]?\s*[:=]\s*['\"]([a-f0-9]{8,12})['\"]", resp.text)
        if m:
            nonce = m.group(1)

    if not nonce:
        log("❌ 无法提取签到 nonce")
        return "无法获取签到 nonce"

    log(f"✅ 获取签到 nonce: {nonce}")

    # 提交签到请求
    log("正在提交签到...")
    data = {
        "action": "user_checkin",
        "nonce": nonce,
    }

    resp = request_with_retry(session, "POST", LOGIN_URL, data=data)

    try:
        result = resp.json()
    except Exception:
        return f"签到返回异常: {resp.text[:200]}"

    msg = result.get("msg", str(result))

    if result.get("error") == 0 or result.get("error") == False:
        log(f"🎉 签到成功！{msg}")
        return f"签到成功：{msg}"
    else:
        if "已签到" in msg:
            log(f"ℹ️ {msg}")
            return f"今日已签到：{msg}"
        else:
            log(f"⚠️ 签到返回: {result}")
            return f"签到异常：{msg}"


def main():
    # 从环境变量读取配置
    username = os.environ.get("BAFU_USERNAME", "")
    password = os.environ.get("BAFU_PASSWORD", "")
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")

    if not username or not password:
        log("❌ 请设置环境变量 BAFU_USERNAME 和 BAFU_PASSWORD")
        sys.exit(1)

    log(f"账号: {username}")
    log(f"PushPlus: {'已配置' if pushplus_token else '未配置（跳过推送）'}")

    # 创建会话
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": BASE_URL + "/",
        "X-Requested-With": "XMLHttpRequest",
    })

    result_msg = ""
    try:
        # 1. 登录
        login_ok = login(session, username, password)

        if not login_ok:
            result_msg = "登录失败"
        else:
            # 2. 签到
            result_msg = do_checkin(session)

    except Exception as e:
        result_msg = f"运行异常: {e}"
        log(f"❌ {result_msg}")

    log("=" * 40)
    log(f"最终结果: {result_msg}")
    log("=" * 40)

    # 3. PushPlus 推送（不管成功失败都推）
    pushplus(
        "霸服论坛签到结果",
        f"账号: {username}\n结果: {result_msg}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        pushplus_token
    )


if __name__ == "__main__":
    main()
