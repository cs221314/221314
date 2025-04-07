import requests
import os
import re
from bs4 import BeautifulSoup
import json

def send_wecom_message(corpid, secret, agentid, username, gold):
    token_url = f'https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={secret}'
    response = requests.get(token_url)
    token_data = response.json()
    if token_data.get('errcode') != 0:
        raise Exception(f"获取token失败: {token_data.get('errmsg')}")
    
    access_token = token_data['access_token']
    
    msg_url = f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}'
    message = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": agentid,
        "text": {
            "content": f"签到成功\n游戏藏宝湾单机社区\n用户名: {username}\n当前金币: {gold}"
        }
    }
    
    response = requests.post(msg_url, json=message)
    result = response.json()
    if result.get('errcode') != 0:
        raise Exception(f"消息发送失败: {result.get('errmsg')}")

def main():
    try:
        username = os.getenv('WYDJZ')
        password = os.getenv('WYDJM1')
        corpid = os.getenv('WECOM_CORPID')
        secret = os.getenv('WECOM_SECRET')
        agentid = os.getenv('WECOM_AGENTID')
        
        if not all([username, password, corpid, secret, agentid]):
            raise ValueError("请检查环境变量配置")

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.iopq.net/member.php?mod=logging&action=login'
        })
        
        # 获取登录页面
        login_page = session.get('https://www.iopq.net/member.php?mod=logging&action=login')
        login_page.encoding = 'gbk'
        soup = BeautifulSoup(login_page.text, 'html.parser')
        formhash = soup.find('input', {'name': 'formhash'})['value']
        
        # 构建登录参数
        login_data = {
            'formhash': formhash,
            'referer': 'https://www.iopq.net/thread-17134279-1-1.html',
            'username': username,
            'password': password,
            'questionid': '0',
            'answer': '',
            'cookietime': '2592000',
            'loginsubmit': 'true'
        }
        
        # 执行登录
        login_response = session.post(
            'https://www.iopq.net/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=LNmQo&inajax=1',
            data=login_data
        )
        login_response.encoding = 'gbk'
        
        # 验证登录状态
        if '欢迎您回来' not in login_response.text:
            raise Exception("登录失败")
        username_match = re.search(r'欢迎您回来，(.*?)，', login_response.text)
        logged_in_user = username_match.group(1) if username_match else username
        
        # 获取金币信息（修复后的逻辑）
        credit_page = session.get('https://www.iopq.net/home.php?mod=spacecp&ac=credit&showcredit=1')
        credit_page.encoding = 'gbk'
        soup = BeautifulSoup(credit_page.text, 'html.parser')
        
        # 新金币提取方式
        gold_element = soup.find('em', string=re.compile(r'^\s*金币:\s*$'))  # 精确匹配包含"金币:"的em标签
        if not gold_element:
            raise Exception("金币信息提取失败")
        
        # 提取父级<li>标签文本
        li_text = gold_element.find_parent('li').get_text(strip=True)
        gold_match = re.search(r'金币:\s*(\d+)', li_text)
        if not gold_match:
            raise Exception("金币数值提取失败")
        
        gold = gold_match.group(1)
        
        print(f"用户名: {logged_in_user}")
        print(f"当前金币: {gold}")
        
        # 企业微信推送
        send_wecom_message(corpid, secret, agentid, logged_in_user, gold)
        print("企业微信推送成功")
        
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()