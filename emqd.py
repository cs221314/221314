/**
 * @cron 0 7-19/6 * * *
 * @description MEFRP签到
 */
import os
import requests
import logging
import time
from urllib.parse import urljoin

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class MefrpMultiSign:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.mefrp.com"
        self.api_url = "https://api.mefrp.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": f"{self.base_url}/"
        }

        # 从环境变量获取多账号配置
        self.usernames = os.environ.get('Mez', '').split('|')
        self.passwords = os.environ.get('Mem', '').split('|')
        self.corpid = os.environ.get('WECOM_CORPID')
        self.secret = os.environ.get('WECOM_SECRET')
        self.agentid = os.environ.get('WECOM_AGENTID')

        # 验证配置
        if not all([self.usernames, self.passwords]):
            raise ValueError("未配置账号密码环境变量 Mez/Mem")
        if len(self.usernames) != len(self.passwords):
            raise ValueError("账号密码数量不匹配")
        if not all([self.corpid, self.secret, self.agentid]):
            raise ValueError("未配置企业微信环境变量")

    def _get_access_token(self):
        """获取企业微信access_token"""
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.corpid}&corpsecret={self.secret}"
        try:
            response = requests.get(url, timeout=10)
            if response.json().get('errcode') == 0:
                return response.json()['access_token']
            logging.error(f"获取token失败: {response.text}")
        except Exception as e:
            logging.error(f"获取token异常: {str(e)}")
        return None

    def login(self, username, password):
        """执行登录操作"""
        login_url = urljoin(self.api_url, "/api/public/login")
        data = {"username": username, "password": password}
        
        try:
            response = self.session.post(login_url, json=data, headers=self.headers)
            if response.json().get("code") == 200:
                token = response.json()["data"]["token"]
                self.headers.update({"Authorization": f"Bearer {token}"})
                logging.info(f"账号 {username} 登录成功")
                return True
            logging.error(f"账号 {username} 登录失败: {response.text}")
        except Exception as e:
            logging.error(f"账号 {username} 登录请求异常: {str(e)}")
        return False

    def sign_in(self):
        """执行签到操作"""
        sign_url = urljoin(self.api_url, "/api/auth/user/sign")
        try:
            response = self.session.get(sign_url, headers=self.headers)
            res = response.json()
            
            if res.get("code") == 200:
                return {
                    "success": True,
                    "traffic": res["data"]["extraTraffic"],
                    "message": "签到成功"
                }
            elif res.get("code") == 403 and "已签到" in res.get("message", ""):
                return {
                    "success": True,
                    "traffic": 0,
                    "message": res["message"]
                }
            else:
                logging.error(f"签到失败: {response.text}")
                return {
                    "success": False,
                    "message": res.get("message", "未知错误")
                }
        except Exception as e:
            logging.error(f"签到请求异常: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }

    def get_user_info(self):
        """通过API获取用户信息"""
        info_url = urljoin(self.api_url, "/api/auth/user/info")
        try:
            response = self.session.get(info_url, headers=self.headers)
            res = response.json()
            
            if res.get("code") == 200:
                data = res["data"]
                username = data.get("username", "未知用户")
                # 将MB转换为GB并保留2位小数
                traffic_mb = data.get('traffic', 0)
                traffic_gb = round(traffic_mb / 1024, 2)
                traffic = f"{traffic_gb} GB"
                return username, traffic
            else:
                logging.error(f"获取用户信息失败: {response.text}")
                return None, None
        except Exception as e:
            logging.error(f"获取用户信息异常: {str(e)}")
            return None, None

    def wx_push(self, results):
        """企业微信应用消息推送（合并所有账号结果）"""
        access_token = self._get_access_token()
        if not access_token:
            return

        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        
        # 构建合并消息内容
        content = "【MEFRP多账号签到通知】\n\n"
        for result in results:
            content += f"账号：{result['username']}\n"
            content += f"签到状态：{result['sign_result']['message']}\n"
            if result['sign_result'].get('traffic', 0) > 0:
                content += f"本次获得：{result['sign_result']['traffic']}GB\n"
            content += f"剩余流量：{result['traffic']}\n"
            content += "----------------\n"

        data = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": self.agentid,
            "text": {"content": content},
            "safe": 0
        }

        try:
            response = requests.post(url, json=data)
            if response.json().get('errcode') == 0:
                logging.info("企业微信推送成功")
            else:
                logging.error(f"推送失败: {response.text}")
        except Exception as e:
            logging.error(f"推送请求异常: {str(e)}")

    def process_account(self, username, password):
        """处理单个账号的签到流程"""
        result = {
            "username": username,
            "success": False,
            "sign_result": None,
            "traffic": None
        }
        
        if not self.login(username, password):
            return result
            
        sign_result = self.sign_in()
        if not sign_result['success']:
            return result
            
        username, traffic = self.get_user_info()
        if username and traffic:
            result.update({
                "success": True,
                "sign_result": sign_result,
                "traffic": traffic
            })
        
        return result

    def main(self):
        start_time = time.time()
        logging.info(f"开始执行多账号签到... {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
        
        results = []
        success_count = 0
        
        # 遍历所有账号
        for username, password in zip(self.usernames, self.passwords):
            username = username.strip()
            password = password.strip()
            if not username or not password:
                continue
                
            logging.info(f"正在处理账号: {username}")
            result = self.process_account(username, password)
            results.append(result)
            if result['success']:
                success_count += 1
            # 每个账号处理完后稍作延迟
            time.sleep(3)
        
        # 发送合并通知
        if results:
            self.wx_push([r for r in results if r['success']])
        
        end_time = time.time()
        logging.info(f"执行结束，共处理 {len(results)} 个账号，成功 {success_count} 个")
        logging.info(f"总耗时: {int(end_time - start_time)} 秒")

if __name__ == "__main__":
    try:
        signer = MefrpMultiSign()
        signer.main()
    except ValueError as e:
        logging.error(str(e))
    except Exception as e:
        logging.error(f"程序运行异常: {str(e)}")
