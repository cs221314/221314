import os
import logging
import requests
import re
import json
from pyquery import PyQuery as pq
from datetime import datetime

# 配置日志格式
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

def send_wecom_message(content, user_info=None):
    """发送企业微信应用消息"""
    try:
        corpid = os.environ.get('WECOM_CORPID')
        secret = os.environ.get('WECOM_SECRET')
        agentid = os.environ.get('WECOM_AGENTID')
        
        if not all([corpid, secret, agentid]):
            logging.error("企业微信环境变量缺失")
            return False

        # 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={secret}"
        token_res = requests.get(token_url, timeout=10).json()
        if token_res.get('errcode') != 0:
            logging.error(f"Token获取失败: {token_res}")
            return False

        # 构建消息内容
        message = f"⏰ 皎月连签到通知\n🕒 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📢 状态：{content}"
        
        # 添加用户信息
        if user_info:
            message += f"\n\n👤 最新信息：" + "\n".join([
                f"\n├ 用户名：{user_info.get('username', 'N/A')}",
                f"├ 服务到期：{user_info.get('expire_time', 'N/A')}",
                f"└ 下次签到：{user_info.get('next_sign', 'N/A')}"
            ])

        # 构建消息体
        msg_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token_res['access_token']}"
        payload = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": agentid,
            "text": {
                "content": message
            }
        }

        # 发送消息
        msg_res = requests.post(msg_url, json=payload, timeout=10).json()
        if msg_res.get('errcode') == 0:
            logging.debug("微信通知发送成功")
            return True
        logging.error(f"消息发送失败: {msg_res}")
        return False
    except Exception as e:
        logging.error(f"推送异常: {str(e)}")
        return False

def get_login_session():
    """创建登录会话并获取Cookie"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    try:
        # 获取登录凭证
        username = os.environ.get('JYLZ')
        password = os.environ.get('JYLM')
        if not all([username, password]):
            raise ValueError("未配置登录凭证环境变量 JYLZ/JYLM")

        # 构造登录请求
        login_url = "https://www.natpierce.cn/pc/login/login.html"
        login_data = {
            "username": username,
            "password": password
        }
        
        # 精准请求头
        headers = {
            "Origin": "https://www.natpierce.cn",
            "Referer": "https://www.natpierce.cn/pc/login/login.html",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Priority": "u=1, i",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not:A-Brand";v="24", "Microsoft Edge";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }
        
        res = session.post(
            url=login_url,
            data=login_data,
            headers=headers
        )
        res.raise_for_status()
        
        # 解析登录结果
        login_result = res.json()
        logging.debug(f"登录响应：{login_result}")
        
        if login_result.get('code') != 200:
            raise ValueError(f"登录失败：{login_result.get('message', '未知错误')}")

        # 访问跳转URL确认登录状态
        session.get(login_result.get('url', 'https://www.natpierce.cn/pc/index/index.html'))
        
        logging.info("✅ 登录成功")
        return session
        
    except Exception as e:
        session.close()
        logging.error(f"🔑 登录流程异常: {str(e)}")
        raise

def parse_user_info(html):
    """解析用户信息"""
    try:
        doc = pq(html)
        info_div = doc('.d_hao')
        if not info_div:
            return None
        
        raw_text = info_div.html()
        raw_text = raw_text.replace('&nbsp;', ' ')
        raw_text = re.sub(r'<br\s*/?>', '\n', raw_text)
        
        info_dict = {}
        patterns = {
            'username': r'用户名：\s*([^\n]+)',
            'expire_time': r'服务到期时间：\s*([^\n]+)',
            'next_sign': r'下次可签到时间：\s*([^\n]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, raw_text)
            if match:
                info_dict[key] = match.group(1).strip()
        
        return info_dict if info_dict else None
        
    except Exception as e:
        logging.error(f"📝 用户信息解析失败: {str(e)}")
        return None

def check_sign_status(session):
    """检查签到状态"""
    try:
        res = session.get("https://www.natpierce.cn/pc/sign/index.html")
        res.raise_for_status()
        
        doc = pq(res.text)
        sign_btn = doc('#qiandao')
        service_text = doc('.d_qd').siblings('div').text()
        
        if "服务尚未到期" in service_text:
            return False, "服务未到期，无需签到"
            
        if not sign_btn:
            return False, "未找到签到按钮"
            
        return ("签到" in sign_btn.text()), sign_btn.text().strip()
        
    except Exception as e:
        return False, f"状态检查失败: {str(e)}"

def execute_sign(session):
    """执行签到并返回最新信息"""
    try:
        sign_url = "https://www.natpierce.cn/pc/sign/qiandao_bf.html"
        
        headers = {
            "Origin": "https://www.natpierce.cn",
            "Referer": "https://www.natpierce.cn/pc/sign/index.html",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Length": "0",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not:A-Brand";v="24", "Microsoft Edge";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }
        
        res = session.post(sign_url, headers=headers)
        res.raise_for_status()
        
        # 解析业务响应
        try:
            response_data = res.json()
            if response_data.get('code') == 200:
                msg = "🎉 签到成功"
            else:
                msg = f"❌ 业务错误: {response_data.get('message', '未知错误')}"
            success = response_data.get('code') == 200
        except json.JSONDecodeError:
            msg = f"📄 响应解析失败: {res.text[:100]}"
            success = False
        
        # 获取最新信息
        res = session.get("https://www.natpierce.cn/pc/sign/index.html")
        latest_info = parse_user_info(res.text)
        
        return success, msg, latest_info
            
    except requests.exceptions.HTTPError as e:
        return False, f"⚠️ 网络请求失败: {str(e)}", None
    except Exception as e:
        return False, f"⚠️ 系统异常: {str(e)}", None

def main():
    """主逻辑流程"""
    result_msg = "未知状态"
    user_info = None
    session = None
    
    try:
        # 获取登录会话
        session = get_login_session()
        
        # 检查签到状态
        can_sign, status_msg = check_sign_status(session)
        logging.info(f"📊 当前状态: {status_msg}")
        if not can_sign:
            result_msg = status_msg
            return result_msg, parse_user_info(session.get("https://www.natpierce.cn/pc/sign/index.html").text)

        # 执行签到
        sign_success, sign_msg, user_info = execute_sign(session)
        logging.info(f"📝 签到结果: {sign_msg}")
        result_msg = sign_msg if not sign_success else "🎉 签到成功"
        
        return result_msg, user_info

    except Exception as e:
        logging.error(f"🚨 流程异常: {str(e)}")
        return f"🚨 执行失败: {str(e)}", None
    finally:
        if session:
            session.close()
        send_wecom_message(result_msg, user_info)

if __name__ == "__main__":
    # 执行并获取结果
    final_result, final_info = main()
    logging.info(f"🏁 最终结果: {final_result}")
    
    # 返回退出码
    exit(0 if "成功" in final_result else 1)