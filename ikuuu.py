#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
"""
cron: 0 7,19 * * *
name: 爱坤VPN
"""
def send_wecom_message(content):
    """发送企业微信应用消息"""
    corpid = os.environ.get('WECOM_CORPID')
    secret = os.environ.get('WECOM_SECRET')
    agentid = os.environ.get('WECOM_AGENTID')
    
    # 验证配置
    if not all([corpid, secret, agentid]):
        print("❌ 企业微信配置不完整，请设置以下环境变量：")
        print("WECOM_CORPID, WECOM_SECRET, WECOM_AGENTID")
        return False

    try:
        # 1. 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={secret}"
        token_resp = requests.get(token_url, timeout=10).json()
        if token_resp.get('errcode') != 0:
            print(f"❌ 获取企业微信token失败: {token_resp.get('errmsg')}")
            return False
        
        # 2. 发送消息
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token_resp['access_token']}"
        data = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": agentid,
            "text": {"content": content},
            "safe": 0
        }
        send_resp = requests.post(send_url, json=data, timeout=10).json()
        
        if send_resp.get('errcode') == 0:
            print("✅ 企业微信消息推送成功")
            return True
        else:
            print(f"❌ 企业微信推送失败: {send_resp.get('errmsg')}")
            return False
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

def main():
    # 基础配置
    host = os.environ.get('HOST', '').rstrip('/')
    username = os.environ.get('IKUUU_USER')
    password = os.environ.get('IKUUU_PASS')
    
    if not all([host, username, password]):
        error_msg = "❌ 错误：缺少必要环境变量（HOST/IKUUU_USER/IKUUU_PASS）"
        print(error_msg)
        send_wecom_message(error_msg)
        return

    # 初始化请求
    session = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36'}
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    base_msg = f"⏰ 当前时间：{timestamp}\n🌐 站点：{host}\n👤 账号：{username}\n"

    try:
        # 1. 登录
        login_resp = session.post(f"{host}/auth/login", headers=headers, data={"email": username, "passwd": password})
        if login_resp.status_code != 200 or login_resp.json().get('ret') != 1:
            raise Exception(f"❌ 登录失败：{login_resp.json().get('msg', '未知错误')}")

        # 2. 签到
        checkin_resp = session.post(f"{host}/user/checkin", headers=headers)
        checkin_data = checkin_resp.json()
        
        # 3. 获取用户信息
        user_resp = session.get(f"{host}/user")
        user_info = parse_user_info(user_resp.text)

        # 4. 处理签到结果
        if checkin_data.get('ret') == 1:
            status = "✅ 签到成功"
            traffic_gain = checkin_data.get('msg', '0B')  # 直接使用返回的消息
        elif "已经签到" in checkin_data.get('msg', ''):
            status = "ℹ️ 今日已签到"
            traffic_gain = "0B"
        else:
            status = f"❌ 签到失败：{checkin_data.get('msg', '未知错误')}"
            traffic_gain = "0B"

        # 5. 构建消息内容
        message = (
            f"[ikuuu签到通知]\n"
            f"{base_msg}"
            f"{status}\n"
            f"🎁 获得流量：{traffic_gain}\n"
            f"🎟️ 会员时长：{user_info['membership']}\n"
            f"📊 剩余流量：{user_info['traffic']}\n"
            f"📅 今日已用：{checkin_data.get('trafficInfo', '未知')}"
        )
        
        print(message)  # 控制台输出
        send_wecom_message(message)  # 发送企业微信通知

    except Exception as e:
        error_msg = f"{base_msg}{str(e)}"
        print(error_msg)
        send_wecom_message(f"[ikuuu异常告警]\n{error_msg}")

if __name__ == "__main__":
    main()
