import os
import requests
import logging
import re
import time
import random
import hashlib
import json
from datetime import datetime
from bs4 import BeautifulSoup
from pyquery import PyQuery as pq
import xml.etree.ElementTree as ET

# 配置日志系统
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

setup_logging()
logger = logging.getLogger(__name__)

class BaseSigner:
    LAST_COINS_FILE = "last_coins.json"
    
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.result_template = (
            "· 执行时间: {time}\n"
            "· 执行状态: {status}\n"
            "· 用户账号: {username}\n"
            "· 当前金币: {coin}\n"
            "· 之前金币: {prev_coin}\n"
            "----------------------------"
        )
        self.current_coin = None
    
    @classmethod
    def load_last_coins(cls):
        try:
            with open(cls.LAST_COINS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    @classmethod
    def save_last_coins(cls, coins_data):
        with open(cls.LAST_COINS_FILE, 'w') as f:
            json.dump(coins_data, f, indent=2)
    
    def send_wecom_message(self, content):
        try:
            corpid = os.getenv("WECOM_CORPID")
            corpsecret = os.getenv("WECOM_SECRET")
            agentid = os.getenv("WECOM_AGENTID")
            
            if not all([corpid, corpsecret, agentid]):
                return False

            token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}"
            token_res = requests.get(token_url, timeout=10)
            token_res.raise_for_status()
            access_token = token_res.json().get("access_token")
            
            send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            payload = {
                "touser": "@all",
                "msgtype": "text",
                "agentid": agentid,
                "text": {"content": f"【全平台签到汇总】\n{content}"}
            }
            
            send_res = requests.post(send_url, json=payload, timeout=10)
            return send_res.json().get("errcode") == 0
        except Exception as e:
            logger.error(f"企业微信通知失败: {str(e)}")
            return False

class WooolcSigner(BaseSigner):
    def __init__(self):
        super().__init__()
        self.username = os.getenv("WOOOLCZ")
        self.password = os.getenv("WOOOLM")
        self.platform = "传世单机社区"
        self.logged_user = None
        
    def _login(self):
        try:
            response = self.session.get(
                "https://www.wooolc.com/member.php?mod=logging&action=login",
                headers=self.headers,
                timeout=10
            )
            doc = pq(response.text)
            params = {
                "formhash": doc('input[name="formhash"]').attr("value"),
                "referer": doc('input[name="referer"]').attr("value") or "https://www.wooolc.com/forum.php",
                "loginhash": re.search(r"loginhash=(\w+)", response.text).group(1),
                "loginfield": doc('select[name="loginfield"] option[selected]').attr("value") or "username"
            }
            
            login_url = f"https://www.wooolc.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={params['loginhash']}&inajax=1"
            data = {
                "formhash": params["formhash"],
                "referer": params["referer"],
                "loginfield": params["loginfield"],
                "username": self.username,
                "password": self.password,
                "questionid": "0",
                "answer": "",
                "cookietime": "2592000"
            }
            
            response = self.session.post(login_url, data=data, headers=self.headers)
            root = ET.fromstring(response.text)
            cdata = root.text
            
            if "succeedhandle_" in cdata:
                self.logged_user = self.username
                self.session.get(re.search(r"window.location.href ='(.*?)';", cdata).group(1))
                return True
            raise ValueError(re.search(r"<error>(.*?)</error>", cdata).group(1))
        except Exception as e:
            logger.error(f"登录失败: {str(e)}")
            return False
    
    def sign(self):
        try:
            start_time = datetime.now()
            status = ""
            coin = ""
            prev_coins = self.load_last_coins()
            prev_coin = prev_coins.get(self.platform, "未知")
            
            if not self._login():
                status = "❌ 登录失败"
            else:
                formhash = self._get_formhash()
                if not formhash:
                    status = "⏰ 今日已签到"
                else:
                    response = self.session.post(
                        "https://www.wooolc.com/plugin.php?id=k_misign:sign",
                        data={"operation": "qiandao", "formhash": formhash, "format": "empty"},
                        headers=self.headers
                    )
                    
                    if "<root><![CDATA[]]></root>" in response.text:
                        status = "✅ 签到成功"
                    else:
                        status = "⏰ 今日已签到"
                
                coin = self._get_coin() or "获取失败"
                self.current_coin = coin if coin != "获取失败" else None

            return self.result_template.format(
                time=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                status=status,
                username=self.logged_user or self.username,
                coin=f"{coin}枚",
                prev_coin=f"{prev_coin}枚" if prev_coin != "未知" else "未知"
            )
        except Exception as e:
            return f"‼️ 程序执行异常：{str(e)}"
    
    def _get_formhash(self):
        try:
            response = self.session.get("https://www.wooolc.com/plugin.php?id=k_misign:sign")
            return pq(response.text)('input[name="formhash"]').attr("value")
        except:
            return None
    
    def _get_coin(self):
        try:
            response = self.session.get("https://www.wooolc.com/home.php?mod=spacecp&ac=credit")
            for li in pq(response.text)('li').items():
                if '传世币' in li.text():
                    match = re.search(r'传世币[：:]\s*(\d+)', li.text())
                    return match.group(1) if match else None
            return None
        except Exception as e:
            logger.error(f"获取金币失败: {str(e)}")
            return None

class IopqSigner(BaseSigner):
    def __init__(self):
        super().__init__()
        self.username = os.getenv("WYDJZ")
        self.password = os.getenv("WYDJM1")
        self.platform = "游戏藏宝湾"
        self.logged_user = None
        
    def sign(self):
        try:
            start_time = datetime.now()
            status = ""
            coin = ""
            prev_coins = self.load_last_coins()
            prev_coin = prev_coins.get(self.platform, "未知")
            
            login_page = self.session.get('https://www.iopq.net/member.php?mod=logging&action=login')
            soup = BeautifulSoup(login_page.text, 'html.parser')
            formhash = soup.find('input', {'name': 'formhash'})['value']
            
            login_data = {
                'formhash': formhash,
                'referer': 'https://www.iopq.net/thread-17134279-1-1.html',
                'username': self.username,
                'password': self.password,
                'questionid': '0',
                'answer': '',
                'cookietime': '2592000',
                'loginsubmit': 'true'
            }
            
            response = self.session.post(
                'https://www.iopq.net/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=LNmQo&inajax=1',
                data=login_data
            )
            
            if '欢迎您回来' not in response.text:
                status = "❌ 登录失败"
            else:
                username_match = re.search(r'欢迎您回来，(.*?)，', response.text)
                self.logged_user = username_match.group(1) if username_match else self.username
                status = "✅ 签到成功"
                
                credit_page = self.session.get('https://www.iopq.net/home.php?mod=spacecp&ac=credit&showcredit=1')
                soup = BeautifulSoup(credit_page.text, 'html.parser')
                gold_element = soup.find('em', string=re.compile(r'^\s*金币:\s*$'))
                
                if gold_element:
                    li_text = gold_element.find_parent('li').get_text(strip=True)
                    match = re.search(r'金币:\s*(\d+)', li_text)
                    coin = match.group(1) if match else None
                else:
                    coin = None
                
                self.current_coin = coin if coin else None
                coin = coin or "获取失败"

            return self.result_template.format(
                time=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                status=status,
                username=self.logged_user,
                coin=f"{coin}枚",
                prev_coin=f"{prev_coin}枚" if prev_coin != "未知" else "未知"
            )
        except Exception as e:
            return f"‼️ 程序执行异常：{str(e)}"

class OduSigner(BaseSigner):
    def __init__(self):
        super().__init__()
        self.username = os.getenv("WYDJZ")
        self.password = os.getenv("WYDJM")
        self.platform = "零度网游单机"
        self.logged_user = None
        
    def sign(self):
        try:
            start_time = datetime.now()
            status = ""
            coin = ""
            prev_coins = self.load_last_coins()
            prev_coin = prev_coins.get(self.platform, "未知")
            
            login_page = self.session.get('https://www.0du.net/member.php?mod=logging&action=login')
            soup = BeautifulSoup(login_page.text, 'html.parser')
            formhash = soup.find('input', {'name': 'formhash'})['value']
            
            login_data = {
                'formhash': formhash,
                'referer': 'https://www.0du.net/forum.php',
                'username': self.username,
                'password': hashlib.md5(self.password.encode()).hexdigest(),
                'questionid': '0',
                'answer': '',
                'cookietime': '2592000',
                'loginsubmit': 'true'
            }
            
            response = self.session.post(
                'https://www.0du.net/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=LrtAc&inajax=1',
                data=login_data
            )
            
            username_match = re.search(r'欢迎您回来，(.+?)，', response.text)
            if not username_match:
                status = "❌ 登录失败"
            else:
                self.logged_user = username_match.group(1)
                status = "✅ 签到成功"
                
                profile_page = self.session.get('https://www.0du.net/home.php?mod=space')
                soup = BeautifulSoup(profile_page.text, 'html.parser')
                gold_element = soup.find('li', class_='nexmemberinfosthrees').find('p')
                coin = gold_element.text.strip() if gold_element else None
                self.current_coin = coin if coin else None
                coin = coin or "获取失败"

            return self.result_template.format(
                time=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                status=status,
                username=self.logged_user,
                coin=f"{coin}枚",
                prev_coin=f"{prev_coin}枚" if prev_coin != "未知" else "未知"
            )
        except Exception as e:
            return f"‼️ 程序执行异常：{str(e)}"

class RexuexiaSigner(BaseSigner):
    def __init__(self):
        super().__init__()
        self.username = os.getenv("WYDJZ")
        self.password = os.getenv("WYDJM")
        self.platform = "热血侠网游单机"
        self.logged_user = None
        
    def sign(self):
        try:
            start_time = datetime.now()
            status = ""
            coin = ""
            prev_coins = self.load_last_coins()
            prev_coin = prev_coins.get(self.platform, "未知")
            
            login_page = self.session.get('http://www.rexuexia.com/member.php?mod=logging&action=login')
            soup = BeautifulSoup(login_page.text, 'html.parser')
            formhash = soup.find('input', {'name': 'formhash'})['value']
            
            login_data = {
                'formhash': formhash,
                'referer': 'http://www.rexuexia.com/',
                'username': self.username,
                'password': self.password,
                'questionid': 0,
                'cookietime': 2592000,
                'loginsubmit': 'true'
            }
            
            response = self.session.post(
                'http://www.rexuexia.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=LDefault&inajax=1',
                data=login_data
            )
            
            credit_page = self.session.get('http://www.rexuexia.com/home.php?mod=spacecp&ac=credit&op=base')
            soup = BeautifulSoup(credit_page.text, 'html.parser')
            self.logged_user = soup.select_one('div.deanavartop a[title]')['title']
            
            gold_element = soup.find('li', class_='xi1')
            if gold_element:
                gold_text = gold_element.get_text(strip=True)
                coin = gold_text.split('金币:')[-1].split()[0]
                self.current_coin = coin
                status = "✅ 签到成功"
            else:
                coin = "获取失败"
                self.current_coin = None
                status = "⚠️ 金币获取失败"

            return self.result_template.format(
                time=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                status=status,
                username=self.logged_user,
                coin=f"{coin}枚",
                prev_coin=f"{prev_coin}枚" if prev_coin != "未知" else "未知"
            )
        except Exception as e:
            return f"‼️ 程序执行异常：{str(e)}"

def main():
    signers = [
        WooolcSigner(),
        IopqSigner(),
        OduSigner(),
        RexuexiaSigner()
    ]
    
    report = []
    current_coins = {}
    
    for signer in signers:
        try:
            if not signer.username or not signer.password:
                report.append(f"{signer.platform}: 未配置账号密码")
                continue
            
            logger.info(f"=== 开始执行 {signer.platform} 签到 ===")
            result = signer.sign()
            
            if hasattr(signer, 'platform') and hasattr(signer, 'current_coin'):
                current_coins[signer.platform] = signer.current_coin
            
            report.append(f"{signer.platform}签到结果：\n{result}")
            time.sleep(random.randint(1, 3))
        except Exception as e:
            report.append(f"{signer.platform}: 执行异常 {str(e)}")
            logger.error(f"{signer.platform} 执行异常: {str(e)}")
    
    last_coins = BaseSigner.load_last_coins()
    for platform, coin in current_coins.items():
        if coin and isinstance(coin, str) and coin.isdigit():
            last_coins[platform] = coin
    BaseSigner.save_last_coins(last_coins)
    
    final_content = "\n\n".join(report)
    logger.info("\n" + final_content)
    
    if BaseSigner().send_wecom_message(final_content):
        logger.info("通知发送成功")
    else:
        logger.warning("通知发送失败")

if __name__ == "__main__":
    main()