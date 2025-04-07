import os
import requests
from pyquery import PyQuery as pq
import logging
import time
import random
import re
from datetime import datetime
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

class WooolcLoginSigner:
    def __init__(self, username, password):
        self.session = requests.Session()
        self.username = username
        self.password = password
        self._setup_headers()
        self._login()

    def _setup_headers(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.wooolc.com/forum.php",
            "Origin": "https://www.wooolc.com"
        }

    def _get_login_params(self):
        try:
            response = self.session.get(
                "https://www.wooolc.com/member.php?mod=logging&action=login",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            doc = pq(response.text)
            params = {
                "formhash": doc('input[name="formhash"]').attr("value"),
                "referer": doc('input[name="referer"]').attr("value") or "https://www.wooolc.com/forum.php",
                "loginhash": re.search(r"loginhash=(\w+)", response.text).group(1),
                "loginfield": doc('select[name="loginfield"] option[selected]').attr("value") or "username"
            }
            return params
        except Exception as e:
            logger.error(f"获取登录参数失败: {str(e)}")
            raise

    def _login(self):
        try:
            params = self._get_login_params()
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

            response = self.session.post(
                login_url,
                data=data,
                headers=self.headers,
                timeout=15
            )
            response.raise_for_status()

            # 解析XML响应
            root = ET.fromstring(response.text)
            cdata = root.text
            
            if "succeedhandle_" in cdata:
                redirect_url = re.search(r"window.location.href ='(.*?)';", cdata).group(1)
                self.session.get(redirect_url, headers=self.headers, timeout=10)
                logger.info("✅ 登录成功")
                return True
                
            if "<error>" in cdata:
                error_msg = re.search(r"<error>(.*?)</error>", cdata).group(1)
                logger.error(f"❌ 登录失败: {error_msg}")
                raise ValueError(error_msg)
                
            raise ValueError("未知登录响应")
        except Exception as e:
            logger.error(f"登录失败: {str(e)}")
            raise

    def check_login(self):
        try:
            response = self.session.get(
                "https://www.wooolc.com/home.php?mod=spacecp",
                headers=self.headers,
                timeout=10
            )
            return "个人资料" in response.text and "退出" in response.text
        except Exception as e:
            logger.error(f"登录状态检查失败: {str(e)}")
            return False

    def _get_formhash(self):
        try:
            response = self.session.get(
                "https://www.wooolc.com/plugin.php?id=k_misign:sign",
                headers=self.headers,
                timeout=10
            )
            doc = pq(response.text)
            return doc('input[name="formhash"]').attr("value")
        except Exception as e:
            logger.error(f"获取formhash失败: {str(e)}")
            return None

    def sign(self):
        if not self.check_login():
            return "login_failed"

        formhash = self._get_formhash()
        if not formhash:
            return "already_signed"

        try:
            time.sleep(random.uniform(1, 3))
            response = self.session.post(
                "https://www.wooolc.com/plugin.php?id=k_misign:sign",
                data={
                    "operation": "qiandao",
                    "formhash": formhash,
                    "format": "empty"
                },
                headers=self.headers,
                timeout=15
            )
            
            if "<root><![CDATA[]]></root>" in response.text:
                logger.info("🎉 签到成功")
                return "success"
            if "今日已签" in response.text or "已经签到" in response.text:
                logger.warning("⏰ 今日已签到")
                return "already_signed"
            if "login.php" in response.text:
                logger.error("❌ 登录失效")
                return "login_failed"
                
            logger.error(f"未知响应: {response.text[:200]}...")
            return "unknown_error"
        except Exception as e:
            logger.error(f"签到请求失败: {str(e)}")
            return "error"

    def get_wooolc_coin(self):
        try:
            response = self.session.get(
                "https://www.wooolc.com/home.php?mod=spacecp&ac=credit",
                headers=self.headers,
                timeout=10
            )
            doc = pq(response.text)
            for li in doc('li').items():
                if '传世币' in li.text():
                    match = re.search(r'传世币[：:]\s*(\d+)', li.text())
                    return match.group(1) if match else None
            return None
        except Exception as e:
            logger.error(f"获取传世币失败: {str(e)}")
            return None

def send_wecom_message(corpid, agentid, corpsecret, content):
    try:
        # 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}"
        token_res = requests.get(token_url, timeout=10)
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        
        if not access_token:
            return False

        # 发送消息
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        payload = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": agentid,
            "text": {"content": f"【传世单机社区签到】\n{content}"}
        }
        
        send_res = requests.post(send_url, json=payload, timeout=10)
        send_res.raise_for_status()
        return send_res.json().get("errcode") == 0
    except Exception as e:
        logger.error(f"企业微信通知失败: {str(e)}")
        return False

if __name__ == "__main__":
    username = os.getenv("WOOOLCZ")
    password = os.getenv("WOOOLM")
    
    if not username or not password:
        logger.error("❌ 请设置环境变量: WOOOLCZ(账号) 和 WOOOLM(密码)")
        exit(1)

    try:
        logger.info("=== 开始执行签到任务 ===")
        signer = WooolcLoginSigner(username, password)
        
        # 执行签到
        sign_result = signer.sign()
        status_map = {
            "success": "✅ 签到成功",
            "already_signed": "⏰ 今日已签到",
            "login_failed": "❌ 登录失效",
            "error": "🛑 请求异常",
            "unknown_error": "⚠️ 未知错误"
        }
        final_status = status_map.get(sign_result, "❓ 未知状态")
        
        # 获取传世币
        coin = signer.get_wooolc_coin() or "获取失败"

        # 企业微信通知
        wecom_corpid = os.getenv("WECOM_CORPID")
        wecom_agentid = os.getenv("WECOM_AGENTID")
        wecom_secret = os.getenv("WECOM_SECRET")
        
        if wecom_corpid and wecom_agentid and wecom_secret:
            content = (
                f"· 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"· 执行状态: {final_status}\n"
                f"· 用户账号: {username}\n"
                f"· 传世币余额: {coin}枚"
            )
            if send_wecom_message(wecom_corpid, wecom_agentid, wecom_secret, content):
                logger.info("✅ 通知发送成功")
            else:
                logger.warning("⚠️ 通知发送失败")
    except Exception as e:
        logger.exception("‼️ 程序执行异常")
        exit(1)