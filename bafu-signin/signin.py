#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
霸服论坛 (bfltttt.com) 自动签到脚本
适用于 GitHub Actions 定时运行
"""

import os
import re
import sys
import requests
from bs4 import BeautifulSoup

# ============ 配置 ============
BASE_URL = "https://bfltttt.com"
LOGIN_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def log(msg):
    """打印日志，带时间戳"""
    from datetime import datetime
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def get_nonce_from_page(session, url, pattern):
    """从页面HTML中提取 nonce"""
    resp = session.get(url, timeout=15)
    resp.encoding = "utf-8"
    html = resp.text
    m = re.search(pattern, html)
    if m:
        return m.group(1)
    return None


def login(session, username, password):
    """登录论坛，返回是否成功"""
    log("正在访问登录页获取 nonce...")

    # 1. 先访问登录页获取 _wpnonce
    login_page_url = f"{BASE_URL}/user-sign?tab=signin"
    resp = session.get(login_page_url, timeout=15)
    resp.encoding = "utf-8"

    # 提取登录表单的 _wpnonce
    nonce_match = re.search(r'name="_wpnonce"\s+value="([a-f0-9]+)"', resp.text)
    if not nonce_match:
        # 换一种匹配方式
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

    resp = session.post(LOGIN_URL, data=data, timeout=15)
    resp.encoding = "utf-8"

    try:
        result = resp.json()
    except Exception:
        log(f"❌ 登录返回非JSON: {resp.text[:200]}")
        return False

    log(f"登录返回: {result}")

    if result.get("error") == False or result.get("code") == 0:
        log("✅ 登录成功")
        return True
    else:
        # 有些主题登录成功返回的是跳转URL，不是error字段
        if "url" in result or "redirect" in result or len(session.cookies) > 0:
            # 再访问首页验证一下是否真的登录了
            check = session.get(BASE_URL + "/", timeout=15)
            check.encoding = "utf-8"
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
    resp = session.get(user_url, timeout=15)
    resp.encoding = "utf-8"

    # 提取签到用的 nonce - 从 user_upload_nonce 或者全局变量里找
    # 之前测试用的是 f8f639ebda 这个，实际应该动态提取
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

    resp = session.post(LOGIN_URL, data=data, timeout=15)
    resp.encoding = "utf-8"

    try:
        result = resp.json()
    except Exception:
        return f"签到返回异常: {resp.text[:200]}"

    msg = result.get("msg", str(result))

    if result.get("error") == False:
        log(f"🎉 签到成功！{msg}")
        return f"签到成功：{msg}"
    else:
        # error=true 但 msg 是"今日已签到"也算正常
        if "已签到" in msg:
            log(f"ℹ️ {msg}")
            return f"今日已签到：{msg}"
        else:
            log(f"⚠️ 签到返回: {result}")
            return f"签到异常：{msg}"


def main():
    # 从环境变量读取账号密码
    username = os.environ.get("BAFU_USERNAME", "")
    password = os.environ.get("BAFU_PASSWORD", "")

    if not username or not password:
        log("❌ 请设置环境变量 BAFU_USERNAME 和 BAFU_PASSWORD")
        sys.exit(1)

    log(f"账号: {username}")

    # 创建会话
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": BASE_URL + "/",
        "X-Requested-With": "XMLHttpRequest",
    })

    # 1. 登录
    if not login(session, username, password):
        sys.exit(1)

    # 2. 签到
    result = do_checkin(session)

    log("=" * 40)
    log(f"最终结果: {result}")
    log("=" * 40)


if __name__ == "__main__":
    main()
