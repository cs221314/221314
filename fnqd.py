#!/usr/bin/env python3
# coding: utf-8
"""
飞牛社区青龙面板自动签到脚本（企业微信版）
环境变量需配置：
- FN_COOKIE：完整的Cookie字符串（含pvRK_2132_saltkey和pvRK_2132_auth）
- fn_pvRK_2132_sign：签名参数
- WECOM_CORPID：企业ID
- WECOM_SECRET：应用Secret
- WECOM_AGENTID：应用AgentId
"""
"""
cron: 1 8 * * *
name: 飞牛签到
"""
import os
import requests
from bs4 import BeautifulSoup
import json

def parse_cookie(cookie_str: str) -> dict:
    """解析Cookie字符串为字典"""
    return {item.split('=')[0]: item.split('=')[1] 
            for item in cookie_str.split('; ') if '=' in item}

# 环境变量读取
COOKIE_STR = os.getenv('FN_COOKIE', '')
FN_SIGN = os.getenv('fn_pvRK_2132_sign', '')
CORPID = os.getenv('WECOM_CORPID')
SECRET = os.getenv('WECOM_SECRET')
AGENTID = os.getenv('WECOM_AGENTID')

# 解析关键Cookie参数
cookie_dict = parse_cookie(COOKIE_STR)
REQUIRED_COOKIES = {
    'pvRK_2132_saltkey': cookie_dict.get('pvRK_2132_saltkey'),
    'pvRK_2132_auth': cookie_dict.get('pvRK_2132_auth')
}

def get_wecom_token():
    """获取企业微信API凭证[6,7](@ref)"""
    try:
        resp = requests.get(
            f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORPID}&corpsecret={SECRET}",
            timeout=10
        )
        data = resp.json()
        if data.get('errcode') == 0:
            return data['access_token']
        raise Exception(f"Token获取失败: {data.get('errmsg')}")
    except Exception as e:
        raise Exception(f"API请求异常: {str(e)}")

def push_wecom(content: str):
    """企业微信消息推送[6,7](@ref)"""
    try:
        access_token = get_wecom_token()
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        
        payload = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": AGENTID,
            "text": {"content": content},
            "safe": 0
        }
        
        resp = requests.post(url, json=payload)
        result = resp.json()
        if result.get('errcode') != 0:
            print(f"❗ 推送失败：{result.get('errmsg')}")
    except Exception as e:
        print(f"🚨 推送异常：{str(e)}")

def sign_in():
    """执行签到核心逻辑[1,2](@ref)"""
    try:
        sign_url = f'https://club.fnnas.com/plugin.php?id=zqlj_sign&sign={FN_SIGN}'
        response = requests.get(sign_url, cookies=REQUIRED_COOKIES)

        if '恭喜您，打卡成功！' in response.text:
            print('✅ 签到成功')
            get_sign_info()
        elif '您今天已经打过卡了' in response.text:
            print('⏰ 今日已签到')
            get_sign_info()
        else:
            error_msg = '❌ 失败：Cookie可能失效'
            print(error_msg)
            push_wecom(f"飞牛签到失败\n{error_msg}")
            
    except Exception as e:
        error_msg = f'🚨 请求异常：{str(e)}'
        print(error_msg)
        push_wecom(f"飞牛签到异常\n{error_msg}")

def get_sign_info():
    """获取飞牛社区签到详情[1,5](@ref)"""
    try:
        response = requests.get('https://club.fnnas.com/plugin.php?id=zqlj_sign', 
                               cookies=REQUIRED_COOKIES)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        info_map = {
            '最近打卡': 'li:-soup-contains("最近打卡")',
            '本月打卡': 'li:-soup-contains("本月打卡")',
            '连续打卡': 'li:-soup-contains("连续打卡")',
            '累计打卡': 'li:-soup-contains("累计打卡")',
            '累计奖励': 'li:-soup-contains("累计奖励")',
            '当前等级': 'li:-soup-contains("当前打卡等级")'
        }
        
        result = []
        for name, selector in info_map.items():
            elem = soup.select_one(selector)
            if elem:
                value = elem.get_text().split('：')[-1].strip()
                result.append(f"{name}: {value}")
        
        if result:
            msg = "📊 签到详情\n" + "\n".join(result)
            print(msg)
            push_wecom(msg)
        else:
            raise Exception('页面结构已变更')
            
    except Exception as e:
        error_msg = f'详情获取失败：{str(e)}'
        print(error_msg)
        push_wecom(error_msg)

def validate_config():
    """配置校验[5,7](@ref)"""
    errors = []
    if not all(REQUIRED_COOKIES.values()):
        errors.append('Cookie缺少关键参数')
    if not FN_SIGN:
        errors.append('缺少签名参数')
    if not CORPID:
        errors.append('缺少企业ID')
    if not SECRET:
        errors.append('缺少应用Secret')
    if not AGENTID:
        errors.append('缺少应用AgentID')
    
    if errors:
        push_wecom("配置错误:\n" + "\n".join(errors))
        raise ValueError("配置校验失败")

if __name__ == '__main__':
    validate_config()
    print('🔍 配置校验通过')
    sign_in()
