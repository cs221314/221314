#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup

"""
cron: 0 7,19 * * *
name: 爱坤VPN多账号版
"""

def send_wecom_message(content):
    """发送企业微信应用消息"""
    corpid = os.environ.get('WECOM_CORPID')
    secret = os.environ.get('WECOM_SECRET')
    agentid = os.environ.get('WECOM_AGENTID')
    
    if not all([corpid, secret, agentid]):
        print("❌ 企业微信配置不完整")
        return False

    try:
        # 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={secret}"
        token_resp = requests.get(token_url, timeout=10).json()
        if token_resp.get('errcode') != 0:
            print(f"❌ 获取token失败: {token_resp.get('errmsg')}")
            return False
        
        # 发送消息
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token_resp['access_token']}"
        data = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": agentid,
            "text": {"content": content},
            "safe": 0
        }
        send_resp = requests.post(send_url, json=data, timeout=10).json()
        
        return send_resp.get('errcode') == 0
    except Exception as e:
        print(f"❌ 企业微信请求异常: {str(e)}")
        return False

def parse_user_info(html):
    """解析用户页面信息"""
    soup = BeautifulSoup(html, 'html.parser')
    info = {'membership': '未知', 'traffic': '未知'}
    
    try:
        # 解析会员时长
        membership_div = soup.find('h4', string='会员时长').parent.parent.find('div', class_='card-body')
        info['membership'] = membership_div.get_text(strip=True) if membership_div else '解析失败'
        
        # 解析剩余流量
        traffic_div = soup.find('h4', string='剩余流量').parent.parent.find('span', class_='counter')
        info['traffic'] = f"{traffic_div.get_text(strip=True)} GB" if traffic_div else '解析失败'
    except Exception as e:
        print(f"❌ 页面解析异常: {str(e)}")
    
    return info

def process_account(host, username, password):
    """处理单个账号签到"""
    session = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36'}
    result = {
        'username': username,
        'status': '❌ 未执行',
        'traffic_gain': '0B',
        'membership': '未知',
        'traffic': '未知',
        'traffic_used': '未知'
    }

    try:
        # 登录
        login_resp = session.post(f"{host}/auth/login", headers=headers, data={"email": username, "passwd": password})
        if login_resp.status_code != 200 or login_resp.json().get('ret') != 1:
            raise Exception(f"登录失败：{login_resp.json().get('msg', '未知错误')}")

        # 签到
        checkin_resp = session.post(f"{host}/user/checkin", headers=headers)
        checkin_data = checkin_resp.json()
        
        # 获取用户信息
        user_resp = session.get(f"{host}/user")
        user_info = parse_user_info(user_resp.text)

        # 处理结果
        if checkin_data.get('ret') == 1:
            result['status'] = "✅ 签到成功"
            result['traffic_gain'] = checkin_data.get('msg', '0B')
        elif "已经签到" in checkin_data.get('msg', ''):
            result['status'] = "ℹ️ 今日已签到"
        else:
            result['status'] = f"❌ 签到失败：{checkin_data.get('msg', '未知错误')}"

        result.update({
            'membership': user_info['membership'],
            'traffic': user_info['traffic'],
            'traffic_used': checkin_data.get('trafficInfo', '未知')
        })

    except Exception as e:
        result['status'] = f"❌ 处理异常：{str(e)}"
    
    return result

def main():
    # 基础配置
    host = os.environ.get('HOST', '').rstrip('/')
    usernames = os.environ.get('IKUUU_USER', '').split('|')
    passwords = os.environ.get('IKUUU_PASS', '').split('|')

    # 验证配置
    error_msg = ""
    if not host:
        error_msg = "❌ 错误：未配置HOST"
    elif len(usernames) != len(passwords):
        error_msg = f"❌ 账号密码数量不匹配（用户：{len(usernames)} 个，密码：{len(passwords)} 个）"
    elif len(usernames) == 0:
        error_msg = "❌ 未配置IKUUU_USER和IKUUU_PASS"

    if error_msg:
        print(error_msg)
        send_wecom_message(error_msg)
        return

    # 处理所有账号
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    report = [f"⏰ 当前时间：{timestamp}\n🌐 站点：{host}\n"]
    
    for i, (username, password) in enumerate(zip(usernames, passwords)):
        print(f"\n处理账号 {i+1}/{len(usernames)}：{username}")
        account_result = process_account(host, username.strip(), password.strip())
        
        # 构建单账号报告
        report.append(
            f"\n🔹 账号：{account_result['username']}\n"
            f"  状态：{account_result['status']}\n"
            f"  获得流量：{account_result['traffic_gain']}\n"
            f"  会员时长：{account_result['membership']}\n"
            f"  剩余流量：{account_result['traffic']}\n"
            f"  今日已用：{account_result['traffic_used']}"
        )

    # 合并推送消息
    full_message = f"[ikuuu多账号签到报告]\n{''.join(report)}"
    print("\n最终推送消息：\n" + full_message)
    
    if send_wecom_message(full_message):
        print("✅ 推送成功")
    else:
        print("❌ 推送失败")

if __name__ == "__main__":
    main()
