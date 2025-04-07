"""
天翼云盘自动签到脚本
支持多账号签到并通过企业微信通知
"""
import time
import re
import json
import base64
import hashlib
import urllib.parse
import hmac
import rsa
import requests
import random
import os
"""
cron: 0 7,19 * * *
name: 天翼云盘签到
"""
BI_RM = list("0123456789abcdefghijklmnopqrstuvwxyz")

B64MAP = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

# 企业微信应用配置
WECOM_CORPID = os.getenv('WECOM_CORPID', '')
WECOM_SECRET = os.getenv('WECOM_SECRET', '')
WECOM_AGENTID = os.getenv('WECOM_AGENTID', '')

if not WECOM_CORPID or not WECOM_SECRET or not WECOM_AGENTID:
    print("企业微信应用配置不完整，签到结果将不会通过企业微信发送")

def int2char(a):
    return BI_RM[a]

def b64tohex(a):
    d = ""
    e = 0
    c = 0
    for i in range(len(a)):
        if list(a)[i] != "=":
            v = B64MAP.index(list(a)[i])
            if 0 == e:
                e = 1
                d += int2char(v >> 2)
                c = 3 & v
            elif 1 == e:
                e = 2
                d += int2char(c << 2 | v >> 4)
                c = 15 & v
            elif 2 == e:
                e = 3
                d += int2char(c)
                d += int2char(v >> 2)
                c = 3 & v
            else:
                e = 0
                d += int2char(c << 2 | v >> 4)
                d += int2char(15 & v)
    if e == 1:
        d += int2char(c << 2)
    return d

def rsa_encode(j_rsakey, string):
    rsa_key = f"-----BEGIN PUBLIC KEY-----\n{j_rsakey}\n-----END PUBLIC KEY-----"
    pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(rsa_key.encode())
    result = b64tohex((base64.b64encode(rsa.encrypt(f'{string}'.encode(), pubkey))).decode())
    return result

def login(username, password):
    url = ""
    urlToken = "https://m.cloud.189.cn/udb/udb_login.jsp?pageId=1&pageKey=default&clientType=wap&redirectURL=https://m.cloud.189.cn/zhuanti/2021/shakeLottery/index.html"
    s = requests.Session()
    r = s.get(urlToken)
    pattern = r"https?://[^\s'\"]+"
    match = re.search(pattern, r.text)
    if match:
        url = match.group()
    else:
        print("没有找到url")

    r = s.get(url)
    pattern = r"<a id=\"j-tab-login-link\"[^>]*href=\"([^\"]+)\""
    match = re.search(pattern, r.text)
    if match:
        href = match.group(1)
    else:
        print("没有找到href链接")

    r = s.get(href)
    captchaToken = re.findall(r"captchaToken' value='(.+?)'", r.text)[0]
    lt = re.findall(r'lt = "(.+?)"', r.text)[0]
    returnUrl = re.findall(r"returnUrl= '(.+?)'", r.text)[0]
    paramId = re.findall(r'paramId = "(.+?)"', r.text)[0]
    j_rsakey = re.findall(r'j_rsaKey" value="(\S+)"', r.text, re.M)[0]
    s.headers.update({"lt": lt})

    username = rsa_encode(j_rsakey, username)
    password = rsa_encode(j_rsakey, password)
    url = "https://open.e.189.cn/api/logbox/oauth2/loginSubmit.do"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/76.0',
        'Referer': 'https://open.e.189.cn/',
    }
    data = {
        "appKey": "cloud",
        "accountType": '01',
        "userName": f"{{RSA}}{username}",
        "password": f"{{RSA}}{password}",
        "validateCode": "",
        "captchaToken": captchaToken,
        "returnUrl": returnUrl,
        "mailSuffix": "@189.cn",
        "paramId": paramId
    }
    r = s.post(url, data=data, headers=headers, timeout=5)
    if (r.json()['result'] == 0):
        print(r.json()['msg'])
    else:
        print(r.json()['msg'])
    redirect_url = r.json()['toUrl']
    r = s.get(redirect_url)
    return s

def get_wecom_access_token():
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECOM_CORPID}&corpsecret={WECOM_SECRET}"
    response = requests.get(url)
    return response.json().get('access_token')

def send_wecom_message(content):
    if not WECOM_CORPID or not WECOM_SECRET or not WECOM_AGENTID:
        print("企业微信配置不完整，跳过消息推送")
        return
    
    access_token = get_wecom_access_token()
    if not access_token:
        print("获取企业微信access_token失败")
        return
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    data = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": WECOM_AGENTID,
        "text": {
            "content": content
        },
        "safe": 0
    }
    
    response = requests.post(url, json=data)
    result = response.json()
    if result.get('errcode') == 0:
        print("企业微信消息推送成功")
    else:
        print(f"企业微信消息推送失败: {result.get('errmsg')}")

def process_account(username, password):
    result = []
    try:
        s = login(username, password)
        rand = str(round(time.time() * 1000))
        surl = f'https://api.cloud.189.cn/mkt/userSign.action?rand={rand}&clientType=TELEANDROID&version=8.6.3&model=SM-G930K'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.136 Mobile Safari/537.36 Ecloud/8.6.3 Android/22 clientId/355325117317828 clientModel/SM-G930K imsi/460071114317824 clientChannelId/qq proVersion/1.0.6',
            "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
            "Host": "m.cloud.189.cn",
            "Accept-Encoding": "gzip, deflate",
        }
        
        # 签到
        response = s.get(surl, headers=headers)
        netdiskBonus = response.json()['netdiskBonus']
        if response.json()['isSign'] == "false":
            res = f"账号 {username[:3]}****{username[-4:]} 签到成功，获得 {netdiskBonus}M 空间"
        else:
            res = f"账号 {username[:3]}****{username[-4:]} 已签到，获得 {netdiskBonus}M 空间"
        result.append(res)
        print(res)
        
    except Exception as e:
        error_msg = f"账号 {username[:3]}****{username[-4:]} 签到失败: {str(e)}"
        result.append(error_msg)
        print(error_msg)
    
    return result

def main():
    # 从环境变量获取多账号
    usernames = os.getenv('ty_username', '').split('&')
    passwords = os.getenv('ty_password', '').split('&')
    
    if not usernames or not passwords or len(usernames) != len(passwords):
        print("账号密码配置错误，请检查环境变量 ty_username 和 ty_password")
        return
    
    all_results = []
    for i in range(len(usernames)):
        username = usernames[i].strip()
        password = passwords[i].strip()
        if not username or not password:
            continue
            
        print(f"\n正在处理账号 {username[:3]}****{username[-4:]}")
        account_results = process_account(username, password)
        all_results.extend(account_results)
    
    # 发送汇总通知
    if all_results and WECOM_CORPID and WECOM_SECRET and WECOM_AGENTID:
        message = "天翼云签到结果汇总:\n" + "\n".join(all_results)
        send_wecom_message(message)

def lambda_handler(event, context):  # aws default
    main()

def main_handler(event, context):  # tencent default
    main()

def handler(event, context):  # aliyun default
    main()

if __name__ == "__main__":
    main()
