from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import threading
import time
import requests
from datetime import datetime
import logging
import hashlib
from collections import defaultdict
import base64
import mimetypes
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量 - 私信回复系统
config = {
    'default_reply_enabled': False,
    'default_reply_message': '您好，我现在不在，稍后会回复您的消息。',
    'default_reply_type': 'text',  # 'text' 或 'image'
    'default_reply_image': '',  # 默认回复图片路径
    'separate_reply_by_follow': False,  # 是否区分已关注和未关注用户的默认回复
    'followed_reply_message': '您好，感谢您的关注！我现在不在，稍后会回复您的消息。',  # 已关注用户的默认回复
    'followed_reply_type': 'text',  # 已关注用户的回复类型
    'followed_reply_image': '',  # 已关注用户的回复图片
    'unfollowed_reply_message': '您好，我现在不在，稍后会回复您的消息。',  # 未关注用户的默认回复
    'unfollowed_reply_type': 'text',  # 未关注用户的回复类型
    'unfollowed_reply_image': '',  # 未关注用户的回复图片
    'follow_reply_enabled': False,  # 关注后回复功能开关
    'follow_reply_message': '感谢您的关注！欢迎来到我的频道~',  # 关注后回复消息
    'follow_reply_type': 'text',  # 关注后回复类型：'text' 或 'image'
    'follow_reply_image': '',  # 关注后回复图片路径
    'unfollow_reply_enabled': False,  # 取消关注回复功能开关
    'unfollow_reply_message': '很遗憾看到您取消了关注，希望我们还有机会再见！',  # 取消关注回复消息
    'unfollow_reply_type': 'text',  # 取消关注回复类型：'text' 或 'image'
    'unfollow_reply_image': '',  # 取消关注回复图片路径
    'only_reply_new_messages': False,  # 是否仅回复新消息（程序启动后的消息）
    'max_replies_per_user': 3,  # 单用户最大回复次数
    'follow_check_interval': 1800,  # 检查关注者的间隔（秒），默认30分钟避免触发风控
    'message_check_interval': 0.05,  # 消息监测间隔（秒）
    'send_delay_interval': 1.0,  # 发送消息等待间隔（秒）
    'auto_restart_interval': 300,  # 自动重启间隔（秒）
    'email_notification': {  # 邮件通知配置
        'enabled': False,
        'smtp_server': 'smtp.qq.com',
        'smtp_port': 587,
        'sender_email': '',
        'sender_password': '',
        'receiver_email': ''
    }
}

# 私信回复系统变量
rules = []
monitoring = False
monitor_thread = None
monitor_threads = {}  # 多账号监控线程字典 {account_name: thread}
message_logs = []  # 私信日志
message_cache = {}
last_message_times = defaultdict(int)
rule_matcher_cache = {}
last_send_time = 0

# 关注者监控相关变量
followers_cache = set()  # 缓存已知关注者
welcome_sent_cache = set()  # 缓存已发送欢迎消息的关注者
last_follow_check = 0  # 上次检查关注者的时间

# 取消关注监控相关变量
unfollowers_cache = set()  # 缓存已处理的取消关注者
last_unfollow_check = 0  # 上次检查取消关注的时间
follow_history = {}  # 关注历史记录 {uid: last_follow_time}

# 程序启动时间戳（用于仅回复新消息功能）
program_start_time = int(time.time())

# 错误追踪系统
error_tracker = {}  # 存储已发送邮件的错误 {error_hash: {'count': int, 'first_time': timestamp, 'last_time': timestamp, 'notified': bool}}
error_tracker_lock = threading.Lock()  # 线程锁，确保错误追踪的线程安全

# 配置文件路径 - 私信系统使用独立配置
CONFIG_FILE = None  # 私信配置文件路径
RULES_FILE = None   # 私信规则文件路径
USER_REPLY_STATS_FILE = None  # 用户回复统计文件路径

# 评论回复配置文件路径 - 完全独立
COMMENT_CONFIG_FILE = None  # 评论配置文件路径
COMMENT_RULES_FILE = None   # 评论规则文件路径

def get_config_file_path(filename):
    """获取配置文件路径，确保跨平台兼容"""
    app_root = get_app_root()
    return os.path.join(app_root, filename)

def init_config_paths():
    """初始化私信系统配置文件路径"""
    global CONFIG_FILE, RULES_FILE, USER_REPLY_STATS_FILE
    if CONFIG_FILE is None:
        CONFIG_FILE = get_config_file_path('config.json')  # 私信配置
    if RULES_FILE is None:
        RULES_FILE = get_config_file_path('keywords.json')  # 私信规则
    if USER_REPLY_STATS_FILE is None:
        USER_REPLY_STATS_FILE = get_config_file_path('user_reply_stats.json')  # 用户回复统计

def init_comment_config_paths():
    """初始化评论系统配置文件路径"""
    global COMMENT_CONFIG_FILE, COMMENT_RULES_FILE
    if COMMENT_CONFIG_FILE is None:
        COMMENT_CONFIG_FILE = get_config_file_path('comment_config.json')  # 评论配置
    if COMMENT_RULES_FILE is None:
        COMMENT_RULES_FILE = get_config_file_path('comment_rules.json')    # 评论规则

class BilibiliAPI:
    def __init__(self, sessdata, bili_jct):
        self.sessdata = sessdata
        self.bili_jct = bili_jct
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Cookie': f'SESSDATA={sessdata}; bili_jct={bili_jct}',
            'Referer': 'https://message.bilibili.com/'
        })
    
    @staticmethod
    def get_qrcode_login_url():
        """获取扫码登录的二维码URL"""
        try:
            url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://passport.bilibili.com/'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                data = result.get('data', {})
                return {
                    'success': True,
                    'url': data.get('url'),  # 二维码内容URL
                    'qrcode_key': data.get('qrcode_key')  # 用于轮询的key
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', '获取二维码失败')
                }
        except Exception as e:
            logger.error(f"获取扫码登录二维码失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def poll_qrcode_status(qrcode_key):
        """轮询扫码登录状态"""
        try:
            url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
            params = {
                'qrcode_key': qrcode_key
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://passport.bilibili.com/',
                'Origin': 'https://passport.bilibili.com'
            }
            
            # 创建session来保持cookie
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"扫码轮询响应: code={result.get('code')}, data={result.get('data')}")
            
            if result.get('code') == 0:
                data = result.get('data', {})
                code = data.get('code')
                
                # code: 86101-未扫码, 86090-已扫码未确认, 86038-二维码已失效, 0-成功
                if code == 0:
                    # 登录成功
                    logger.info("扫码登录成功，开始提取cookie")
                    
                    # 方法1: 从响应的Set-Cookie头中提取
                    sessdata = ''
                    bili_jct = ''
                    
                    # 检查响应头中的Set-Cookie
                    set_cookie_headers = response.headers.get('Set-Cookie', '')
                    logger.info(f"Set-Cookie头: {set_cookie_headers[:200] if set_cookie_headers else 'None'}")
                    
                    # 从session.cookies中提取
                    for cookie in session.cookies:
                        logger.info(f"Cookie: {cookie.name}={cookie.value[:20]}...")
                        if cookie.name == 'SESSDATA':
                            sessdata = cookie.value
                        elif cookie.name == 'bili_jct':
                            bili_jct = cookie.value
                    
                    # 方法2: 如果响应中有url，访问该url获取cookie
                    if (not sessdata or not bili_jct) and data.get('url'):
                        url_with_params = data.get('url')
                        logger.info(f"尝试从跳转URL获取cookie: {url_with_params[:100]}...")
                        try:
                            cookie_response = session.get(url_with_params, allow_redirects=True, timeout=10)
                            logger.info(f"跳转URL响应状态: {cookie_response.status_code}")
                            
                            for cookie in session.cookies:
                                if cookie.name == 'SESSDATA':
                                    sessdata = cookie.value
                                elif cookie.name == 'bili_jct':
                                    bili_jct = cookie.value
                        except Exception as e:
                            logger.error(f"访问跳转URL失败: {e}")
                    
                    # 方法3: 访问B站主页激活cookie
                    if not sessdata or not bili_jct:
                        logger.info("尝试访问B站主页激活cookie")
                        try:
                            home_response = session.get('https://www.bilibili.com', timeout=10)
                            logger.info(f"主页响应状态: {home_response.status_code}")
                            
                            for cookie in session.cookies:
                                if cookie.name == 'SESSDATA':
                                    sessdata = cookie.value
                                elif cookie.name == 'bili_jct':
                                    bili_jct = cookie.value
                        except Exception as e:
                            logger.error(f"访问主页失败: {e}")
                    
                    if sessdata and bili_jct:
                        logger.info(f"成功获取cookie - SESSDATA长度: {len(sessdata)}, bili_jct长度: {len(bili_jct)}")
                        return {
                            'success': True,
                            'status': 'success',
                            'sessdata': sessdata,
                            'bili_jct': bili_jct
                        }
                    else:
                        logger.warning(f"未能获取完整cookie - SESSDATA: {bool(sessdata)}, bili_jct: {bool(bili_jct)}")
                        logger.warning(f"完整响应数据: {data}")
                        
                        # 返回更详细的错误信息
                        missing = []
                        if not sessdata:
                            missing.append('SESSDATA')
                        if not bili_jct:
                            missing.append('bili_jct')
                        
                        return {
                            'success': False,
                            'status': 'error',
                            'message': f'获取登录凭证失败（缺少: {", ".join(missing)}），请尝试手动输入Cookie'
                        }
                elif code == 86101:
                    return {
                        'success': True,
                        'status': 'waiting',
                        'message': '等待扫码'
                    }
                elif code == 86090:
                    return {
                        'success': True,
                        'status': 'scanned',
                        'message': '已扫码，等待确认'
                    }
                elif code == 86038:
                    return {
                        'success': False,
                        'status': 'expired',
                        'message': '二维码已失效'
                    }
                else:
                    logger.warning(f"未知的扫码状态码: {code}, 消息: {data.get('message', '未知')}")
                    return {
                        'success': False,
                        'status': 'error',
                        'message': data.get('message', f'未知状态码: {code}')
                    }
            else:
                return {
                    'success': False,
                    'status': 'error',
                    'message': result.get('message', '轮询失败')
                }
        except Exception as e:
            logger.error(f"轮询扫码状态失败: {e}")
            return {
                'success': False,
                'status': 'error',
                'message': str(e)
            }
    
    def get_sessions(self):
        """获取私信会话列表（极速版）"""
        url = 'https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions'
        params = {
            'session_type': 1,
            'group_fold': 1,
            'unfollow_fold': 0,
            'sort_rule': 2,
            'build': 0,
            'mobi_app': 'web'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=1.5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            return None
    
    def get_session_msgs(self, talker_id, session_type=1, size=3):
        """获取指定会话的消息（极速版）"""
        url = 'https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs'
        params = {
            'sender_device_id': 1,
            'talker_id': talker_id,
            'session_type': session_type,
            'size': size,
            'build': 0,
            'mobi_app': 'web'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=0.8)
            response.raise_for_status()
            return response.json()
        except:
            return None
    
    def get_latest_message(self, talker_id):
        """快速获取最新消息（增强异常处理）"""
        try:
            msgs_data = self.get_session_msgs(talker_id, size=1)
            if msgs_data and msgs_data.get('code') == 0:
                messages = msgs_data.get('data', {}).get('messages', [])
                return messages[0] if messages else None
            elif msgs_data and msgs_data.get('code') != 0:
                # API返回错误，记录但不抛出异常
                logger.debug(f"获取消息失败 (用户{talker_id}): {msgs_data.get('message', '未知错误')}")
            return None
        except Exception as e:
            logger.debug(f"获取最新消息异常 (用户{talker_id}): {e}")
            return None
    
    def send_msg(self, receiver_id, msg_type=1, content=""):
        """发送私信（可配置间隔版）"""
        global last_send_time
        
        current_time = time.time()
        
        # 使用配置中的发送间隔
        send_interval = config.get('send_delay_interval', 1.0)
        if current_time - last_send_time < send_interval:
            wait_time = send_interval - (current_time - last_send_time)
            add_log(f"发送间隔控制，等待 {wait_time:.1f} 秒", 'info')
            time.sleep(wait_time)
        
        url = 'https://api.vc.bilibili.com/web_im/v1/web_im/send_msg'
        data = {
            'msg[sender_uid]': self.get_my_uid(),
            'msg[receiver_id]': receiver_id,
            'msg[receiver_type]': 1,
            'msg[msg_type]': msg_type,
            'msg[msg_status]': 0,
            'msg[content]': json.dumps({"content": content}) if msg_type == 1 else content,
            'msg[timestamp]': int(time.time()),
            'msg[new_face_version]': 0,
            'msg[dev_id]': 'B1994F2C-C5C9-4C0E-8F4C-F8E5F7E8F9E0',
            'build': 0,
            'mobi_app': 'web',
            'csrf': self.bili_jct
        }
        
        try:
            response = self.session.post(url, data=data, timeout=3.0)
            response.raise_for_status()
            result = response.json()
            
            # 更新最后发送时间
            last_send_time = time.time()
            
            # 简单的结果处理
            if result.get('code') == -412:
                add_log(f"触发频率限制，但保持发送间隔继续运行", 'warning',
                       error_details=f"错误码: -412\n接收者ID: {receiver_id}\n消息类型: {msg_type}",
                       context='发送私信消息')
            elif result.get('code') == -101:
                add_log("登录状态失效，请重新配置登录信息", 'error',
                       error_details=f"错误码: -101\n接收者ID: {receiver_id}\nSESSDATA可能已过期",
                       context='发送私信消息')
            elif result.get('code') != 0:
                add_log(f"发送失败: {result.get('message', '未知错误')}", 'warning',
                       error_details=f"错误码: {result.get('code')}\n错误消息: {result.get('message', '未知错误')}\n接收者ID: {receiver_id}\n消息类型: {msg_type}\nCSRF Token: {'已设置' if self.bili_jct else '未设置'}",
                       context='发送私信消息')
            
            return result
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            last_send_time = time.time()  # 即使失败也更新时间，避免卡住
            return None
    
    def upload_image(self, image_path):
        """模拟浏览器上传图片到B站"""
        try:
            if not os.path.exists(image_path):
                add_log(f"图片文件不存在: {image_path}", 'error')
                return None
            
            # 检查文件大小（B站限制通常为20MB）
            file_size = os.path.getsize(image_path)
            if file_size > 20 * 1024 * 1024:
                add_log(f"图片文件过大: {file_size / 1024 / 1024:.1f}MB", 'error')
                return None
            
            # 模拟浏览器完整的上传流程
            file_name = os.path.basename(image_path)
            mime_type = mimetypes.guess_type(image_path)[0] or 'image/png'
            
            # 第一步：获取上传凭证
            upload_info = self._get_upload_info()
            if not upload_info:
                add_log("获取上传凭证失败", 'error')
                return None
            
            # 第二步：上传到BFS服务器
            bfs_result = self._upload_to_bfs(image_path, upload_info)
            if not bfs_result:
                # 如果BFS上传失败，尝试直接上传
                return self._direct_upload_image(image_path)
            
            add_log(f"图片上传成功: {file_name}", 'success')
            return bfs_result
                    
        except Exception as e:
            add_log(f"图片上传异常: {e}", 'error')
            return None
    
    def _get_upload_info(self):
        """获取上传凭证信息"""
        try:
            url = 'https://member.bilibili.com/preupload'
            params = {
                'name': 'image.png',
                'size': 1024,
                'r': 'upos',
                'profile': 'ugcupos/bup',
                'ssl': '0',
                'version': '2.10.4',
                'build': '2100400'
            }
            
            response = self.session.get(url, params=params, timeout=10.0)
            if response.status_code == 200:
                result = response.json()
                if result.get('OK') == 1:
                    return result
            return None
        except:
            return None
    
    def _upload_to_bfs(self, image_path, upload_info):
        """上传到BFS服务器"""
        try:
            if not upload_info or 'upos_uri' not in upload_info:
                return None
            
            # 构造BFS上传URL
            upos_uri = upload_info['upos_uri']
            upload_url = f"https:{upos_uri}"
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # 模拟分片上传
            headers = {
                'Content-Type': 'application/octet-stream',
                'User-Agent': self.session.headers.get('User-Agent'),
                'Referer': 'https://message.bilibili.com/'
            }
            
            response = self.session.put(upload_url, data=image_data, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                # 返回图片信息
                return {
                    'image_url': upload_url.replace('upos-sz-mirrorks3.bilivideo.com', 'i0.hdslb.com'),
                    'image_width': 0,
                    'image_height': 0
                }
            
            return None
        except:
            return None
    
    def _direct_upload_image(self, image_path):
        """直接上传图片（备用方案）"""
        try:
            file_name = os.path.basename(image_path)
            
            # 尝试多个上传接口，模拟真实浏览器行为
            upload_configs = [
                {
                    'url': 'https://api.vc.bilibili.com/api/v1/drawImage/upload',
                    'data': {
                        'biz': 'im',
                        'category': 'daily',
                        'csrf': self.bili_jct
                    },
                    'headers': {
                        'Origin': 'https://message.bilibili.com',
                        'Referer': 'https://message.bilibili.com/',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                },
                {
                    'url': 'https://api.bilibili.com/x/dynamic/feed/draw/upload_bfs',
                    'data': {
                        'biz': 'new_dyn',
                        'category': 'daily',
                        'csrf': self.bili_jct
                    },
                    'headers': {
                        'Origin': 'https://t.bilibili.com',
                        'Referer': 'https://t.bilibili.com/',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                }
            ]
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            for config in upload_configs:
                try:
                    # 准备文件数据
                    files = {
                        'file_up': (file_name, image_data, mimetypes.guess_type(image_path)[0])
                    }
                    
                    # 更新session headers
                    original_headers = dict(self.session.headers)
                    self.session.headers.update(config['headers'])
                    
                    add_log(f"尝试直接上传到: {config['url']}", 'debug')
                    response = self.session.post(
                        config['url'], 
                        files=files, 
                        data=config['data'], 
                        timeout=15.0
                    )
                    
                    # 恢复原始headers
                    self.session.headers.clear()
                    self.session.headers.update(original_headers)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('code') == 0:
                            image_info = result.get('data', {})
                            add_log(f"直接上传成功: {file_name}", 'success')
                            return image_info
                        else:
                            add_log(f"接口返回错误: {result.get('message', '未知错误')}", 'debug')
                    else:
                        add_log(f"HTTP状态码: {response.status_code}", 'debug')
                        
                except Exception as e:
                    add_log(f"上传尝试失败: {e}", 'debug')
                    continue
            
            add_log("所有直接上传方法都失败", 'error')
            return None
            
        except Exception as e:
            add_log(f"直接上传异常: {e}", 'error')
            return None
    
    def send_image_msg(self, receiver_id, image_path):
        """发送图片消息"""
        try:
            # 先上传图片
            image_info = self.upload_image(image_path)
            if not image_info:
                return None
            
            # 构造图片消息内容
            image_content = {
                "url": image_info.get('image_url', ''),
                "height": image_info.get('image_height', 0),
                "width": image_info.get('image_width', 0),
                "imageType": "jpeg",
                "original": 1,
                "size": image_info.get('image_size', 0)
            }
            
            # 发送图片消息（msg_type=2表示图片消息）
            return self.send_msg(receiver_id, msg_type=2, content=json.dumps(image_content))
            
        except Exception as e:
            add_log(f"发送图片消息失败: {e}", 'error')
            return None
    
    def get_my_uid(self):
        """获取当前用户UID"""
        url = 'https://api.bilibili.com/x/web-interface/nav'
        try:
            response = self.session.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            if data['code'] == 0:
                return data['data']['mid']
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
        return None
    
    def check_user_relation(self, target_uid):
        """检查用户关系（是否关注了我）
        返回: True=已关注, False=未关注, None=检查失败
        """
        try:
            url = 'https://api.bilibili.com/x/relation'
            params = {
                'fid': target_uid
            }
            response = self.session.get(url, params=params, timeout=3)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                data = result.get('data', {})
                # attribute: 2=已关注我, 6=互相关注, 其他=未关注
                attribute = data.get('attribute', 0)
                return attribute in [2, 6]
            else:
                logger.warning(f"检查用户关系失败: {result.get('message', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"检查用户关系异常: {e}")
            return None
    
    def verify_message_sent(self, talker_id, expected_content):
        """验证消息是否真正发送成功"""
        try:
            # 获取最新消息验证是否发送成功
            msgs_data = self.get_session_msgs(talker_id, size=3)
            if not msgs_data or msgs_data.get('code') != 0:
                return False
            
            messages = msgs_data.get('data', {}).get('messages', [])
            if not messages:
                return False
            
            # 检查最新的几条消息中是否有我们刚发送的内容
            my_uid = self.get_my_uid()
            for msg in messages[-3:]:  # 检查最新3条消息
                if msg.get('sender_uid') == my_uid:
                    content_str = msg.get('content', '{}')
                    try:
                        content_obj = json.loads(content_str)
                        message_text = content_obj.get('content', '').strip()
                        if expected_content in message_text or message_text in expected_content:
                            return True
                    except:
                        if expected_content in content_str:
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"验证消息发送失败: {e}")
            return False
    
    def get_followers(self, page=1, page_size=50):
        """获取关注者列表"""
        try:
            my_uid = self.get_my_uid()
            if not my_uid:
                return None
            
            url = 'https://api.bilibili.com/x/relation/followers'
            params = {
                'vmid': my_uid,
                'pn': page,
                'ps': page_size,
                'order': 'desc',  # 按关注时间倒序
                'order_type': 'attention'
            }
            
            response = self.session.get(url, params=params, timeout=5.0)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {})
            else:
                add_log(f"获取关注者列表失败: {result.get('message', '未知错误')}", 'warning')
                return None
                
        except Exception as e:
            add_log(f"获取关注者列表异常: {e}", 'error')
            return None
    
    def get_recent_followers(self, limit=20):
        """获取最近的关注者（用于检测新关注）"""
        try:
            followers_data = self.get_followers(page=1, page_size=limit)
            if not followers_data:
                return []
            
            followers_list = followers_data.get('list', [])
            recent_followers = []
            
            for follower in followers_list:
                recent_followers.append({
                    'mid': follower.get('mid'),
                    'uname': follower.get('uname', ''),
                    'face': follower.get('face', ''),
                    'mtime': follower.get('mtime', 0),  # 关注时间
                    'attribute': follower.get('attribute', 0)  # 关注状态
                })
            
            return recent_followers
            
        except Exception as e:
            add_log(f"获取最近关注者异常: {e}", 'error')
            return []

def send_email_notification(subject, body, receiver_email=None):
    """发送邮件通知"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        email_config = config.get('email_notification', {})
        if not email_config.get('enabled', False):
            return False
        
        # 使用指定的接收邮箱或配置中的默认邮箱
        to_email = receiver_email or email_config.get('receiver_email', '')
        if not to_email:
            logger.warning("未配置接收邮箱，无法发送邮件通知")
            return False
        
        smtp_server = email_config.get('smtp_server', 'smtp.qq.com')
        smtp_port = email_config.get('smtp_port', 587)
        sender_email = email_config.get('sender_email', '')
        sender_password = email_config.get('sender_password', '')
        
        # 创建邮件
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        # 发送邮件
        server = None
        try:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
            logger.info(f"邮件通知已发送至: {to_email}")
            return True
            
        finally:
            # 安全关闭连接，忽略关闭时的错误
            if server:
                try:
                    server.quit()
                except:
                    pass  # 忽略关闭时的错误
        
    except Exception as e:
        logger.error(f"发送邮件通知失败: {e}")
        return False

def check_login_status(api):
    """检查登录状态是否有效"""
    try:
        uid = api.get_my_uid()
        return uid is not None
    except:
        return False

def send_login_expired_notification(account_name='', receiver_email=None):
    """发送登录掉线通知"""
    account_text = f"账号 {account_name}" if account_name else "您的账号"
    subject = f"BiliGo - {account_text}登录已失效"
    body = f"""
    <html>
    <body>
        <h2>BiliGo 登录状态提醒</h2>
        <p><strong>{account_text}</strong>的登录凭证已失效，请及时更新。</p>
        <p>失效时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>请登录 BiliGo 系统重新配置登录信息。</p>
        <hr>
        <p style="color: #666; font-size: 12px;">这是一封自动发送的邮件，请勿回复。</p>
    </body>
    </html>
    """
    return send_email_notification(subject, body, receiver_email)

def generate_error_hash(error_type, error_message, context=''):
    """生成错误的唯一哈希值"""
    error_string = f"{error_type}:{error_message}:{context}"
    return hashlib.md5(error_string.encode('utf-8')).hexdigest()

def track_and_notify_error(error_type, error_message, error_details='', context='', account_name='', receiver_email=None):
    """追踪错误并发送邮件通知（相同错误只发送一次）"""
    global error_tracker
    
    # 生成错误哈希
    error_hash = generate_error_hash(error_type, error_message, context)
    
    current_time = int(time.time())
    
    with error_tracker_lock:
        # 检查是否已经追踪过这个错误
        if error_hash in error_tracker:
            error_info = error_tracker[error_hash]
            error_info['count'] += 1
            error_info['last_time'] = current_time
            
            # 如果已经发送过通知，不再发送
            if error_info['notified']:
                logger.debug(f"错误已通知过，跳过邮件发送: {error_type} - {error_message}")
                return False
        else:
            # 新错误，创建追踪记录
            error_tracker[error_hash] = {
                'count': 1,
                'first_time': current_time,
                'last_time': current_time,
                'notified': False,
                'error_type': error_type,
                'error_message': error_message
            }
    
    # 发送邮件通知
    try:
        # 确定接收邮箱
        if not receiver_email:
            # 尝试从配置中获取邮箱
            email_config = config.get('email_notification', {})
            receiver_email = email_config.get('receiver_email', '')
            
            # 如果是多账号模式，尝试获取账号的邮箱
            if not receiver_email and account_name:
                accounts = config.get('accounts', [])
                for acc in accounts:
                    if acc.get('name') == account_name:
                        receiver_email = acc.get('email', '')
                        break
        
        if not receiver_email:
            logger.warning("未配置接收邮箱，无法发送错误通知")
            return False
        
        # 构造邮件内容
        account_text = f" [{account_name}]" if account_name else ""
        
        # 根据错误类型设置不同的标题和颜色
        if 'Warning' in error_type or 'warning' in error_type.lower():
            subject = f"BiliGo{account_text} - 系统警告通知"
            title_color = "#ff9800"
            title_icon = "⚠️"
            title_text = "BiliGo 系统警告通知"
        else:
            subject = f"BiliGo{account_text} - 系统错误通知"
            title_color = "#d9534f"
            title_icon = "❌"
            title_text = "BiliGo 系统错误通知"
        
        # 格式化错误详情
        error_details_html = error_details.replace('\n', '<br>').replace(' ', '&nbsp;')
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: {title_color}; border-bottom: 2px solid {title_color}; padding-bottom: 10px;">
                    {title_icon} {title_text}
                </h2>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #555;">错误信息</h3>
                    <p><strong>错误类型:</strong> {error_type}</p>
                    <p><strong>错误消息:</strong> {error_message}</p>
                    {f'<p><strong>上下文:</strong> {context}</p>' if context else ''}
                    {f'<p><strong>账号:</strong> {account_name}</p>' if account_name else ''}
                    <p><strong>发生时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                {f'''
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <h3 style="margin-top: 0; color: #856404;">详细信息</h3>
                    <pre style="background-color: #fff; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px;">{error_details_html}</pre>
                </div>
                ''' if error_details else ''}
                
                <div style="margin-top: 20px; padding: 15px; background-color: #e7f3ff; border-radius: 5px;">
                    <h3 style="margin-top: 0; color: #0056b3;">建议操作</h3>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>检查系统日志以获取更多详细信息</li>
                        <li>确认网络连接是否正常</li>
                        <li>验证账号登录凭证是否有效</li>
                        <li>如果问题持续，请考虑重启系统</li>
                    </ul>
                </div>
                
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    这是一封自动发送的邮件，请勿回复。<br>
                    相同的错误只会发送一次通知邮件。
                </p>
            </div>
        </body>
        </html>
        """
        
        # 发送邮件
        if send_email_notification(subject, body, receiver_email):
            # 标记为已通知
            with error_tracker_lock:
                if error_hash in error_tracker:
                    error_tracker[error_hash]['notified'] = True
            
            logger.info(f"错误通知邮件已发送至: {receiver_email}")
            add_log(f"错误通知邮件已发送: {error_type} - {error_message}", 'info')
            return True
        else:
            logger.error(f"发送错误通知邮件失败")
            return False
            
    except Exception as e:
        logger.error(f"发送错误通知时发生异常: {e}")
        return False

def cleanup_error_tracker():
    """清理错误追踪器中的旧记录（保留最近24小时的记录）"""
    global error_tracker
    
    current_time = int(time.time())
    cleanup_threshold = 24 * 3600  # 24小时
    
    with error_tracker_lock:
        old_errors = []
        for error_hash, error_info in error_tracker.items():
            if current_time - error_info['last_time'] > cleanup_threshold:
                old_errors.append(error_hash)
        
        for error_hash in old_errors:
            del error_tracker[error_hash]
        
        if old_errors:
            logger.info(f"清理了 {len(old_errors)} 条过期的错误追踪记录")

def load_user_reply_stats():
    """从JSON文件加载用户回复统计"""
    init_config_paths()
    if os.path.exists(USER_REPLY_STATS_FILE):
        try:
            with open(USER_REPLY_STATS_FILE, 'r', encoding='utf-8') as f:
                stats = json.load(f)
                # 转换为defaultdict
                return defaultdict(lambda: {'count': 0, 'last_reply_time': 0}, stats)
        except Exception as e:
            logger.error(f"加载用户回复统计失败: {e}")
    return defaultdict(lambda: {'count': 0, 'last_reply_time': 0})

def save_user_reply_stats(stats):
    """保存用户回复统计到JSON文件"""
    try:
        init_config_paths()
        # 转换defaultdict为普通dict以便JSON序列化
        stats_dict = {str(k): v for k, v in stats.items()}
        with open(USER_REPLY_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存用户回复统计失败: {e}")

def get_user_reply_count(user_id, stats):
    """获取用户的回复次数"""
    user_id_str = str(user_id)
    return stats.get(user_id_str, {}).get('count', 0)

def increment_user_reply_count(user_id, stats):
    """增加用户的回复次数"""
    user_id_str = str(user_id)
    if user_id_str not in stats:
        stats[user_id_str] = {'count': 0, 'last_reply_time': 0}
    stats[user_id_str]['count'] += 1
    stats[user_id_str]['last_reply_time'] = int(time.time())
    save_user_reply_stats(stats)
    return stats[user_id_str]['count']

def add_log(message, log_type='info', system='message', error_details='', context='', account_name=''):
    """添加日志 - 支持区分私信和评论系统，并在错误时发送邮件通知"""
    timestamp = datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'message': message,
        'level': log_type,
        'system': system  # 'message' 表示私信系统, 'comment' 表示评论系统
    }
    
    if system == 'message':
        message_logs.append(log_entry)
        # 限制私信日志数量
        if len(message_logs) > 100:
            message_logs.pop(0)
    elif system == 'comment':
        comment_logs.append(log_entry)
        # 限制评论日志数量
        if len(comment_logs) > 100:
            comment_logs.pop(0)
    
    # 系统日志输出
    system_prefix = "[私信]" if system == 'message' else "[评论]"
    logger.info(f"{system_prefix}[{log_type.upper()}] {message}")
    
    # 如果是错误或警告级别，发送邮件通知
    if log_type in ['error', 'warning']:
        try:
            # 异步发送邮件，避免阻塞主线程
            threading.Thread(
                target=track_and_notify_error,
                args=(
                    f"{system_prefix} {log_type.capitalize()}",
                    message,
                    error_details,
                    context,
                    account_name,
                    None  # receiver_email 将从配置中自动获取
                ),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"启动错误通知线程失败: {e}")

def load_config():
    """加载私信系统配置"""
    global config
    init_config_paths()  # 确保路径已初始化
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                config.update(loaded_config)
            logger.info(f"成功加载私信配置文件: {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"加载私信配置失败: {e}")
            add_log(f"加载私信配置失败: {e}", 'error', system='message')
    else:
        logger.info(f"私信配置文件不存在，使用默认配置: {CONFIG_FILE}")

def save_config():
    """保存私信系统配置"""
    try:
        init_config_paths()  # 确保路径已初始化
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存私信配置文件: {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"保存私信配置失败: {e}")
        add_log(f"保存私信配置失败: {e}", 'error', system='message')

def load_rules():
    """加载私信系统关键词规则"""
    global rules
    init_config_paths()  # 确保路径已初始化
    logger.info(f"尝试加载私信关键词文件: {RULES_FILE}")
    
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                loaded_rules = json.load(f)
                if isinstance(loaded_rules, list):
                    rules = loaded_rules
                    precompile_rules()
                    enabled_count = len([r for r in rules if r.get('enabled', True)])
                    add_log(f"成功加载 {len(rules)} 条私信关键词规则，其中 {enabled_count} 条已启用", 'success', system='message')
                    logger.info(f"成功加载私信关键词规则: {len(rules)} 条")
                else:
                    rules = []
                    add_log("私信关键词文件格式错误，已重置", 'warning', system='message')
        except Exception as e:
            logger.error(f"加载私信关键词规则失败: {e}")
            add_log(f"加载私信关键词规则失败: {e}", 'error', system='message')
            rules = []
    else:
        rules = []
        add_log(f"私信关键词文件不存在: {RULES_FILE}，创建新文件", 'info', system='message')
        logger.warning(f"私信关键词文件不存在: {RULES_FILE}")

def save_rules():
    """保存私信系统规则"""
    try:
        init_config_paths()  # 确保路径已初始化
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存私信关键词规则: {RULES_FILE}")
    except Exception as e:
        logger.error(f"保存私信规则失败: {e}")
        add_log(f"保存私信规则失败: {e}", 'error', system='message')

def load_rules_from_file(file_path):
    """从指定文件加载关键词规则"""
    try:
        if not os.path.exists(file_path):
            return None, "文件不存在"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_rules = json.load(f)
        
        if not isinstance(loaded_rules, list):
            return None, "文件格式错误：根元素必须是数组"
        
        # 验证规则格式
        valid_rules = []
        for i, rule in enumerate(loaded_rules):
            if not isinstance(rule, dict):
                continue
            
            # 检查必需字段
            if 'keyword' not in rule or 'name' not in rule:
                continue
            
            # 标准化规则格式
            standardized_rule = {
                'id': rule.get('id', i + 1),
                'name': rule.get('name', f'规则{i+1}'),
                'keyword': rule.get('keyword', ''),
                'reply': rule.get('reply', ''),
                'reply_type': rule.get('reply_type', 'text'),
                'reply_image': rule.get('reply_image', ''),
                'enabled': rule.get('enabled', True),
                'use_regex': rule.get('use_regex', False),
                'created_at': rule.get('created_at', datetime.now().isoformat())
            }
            valid_rules.append(standardized_rule)
        
        return valid_rules, None
        
    except json.JSONDecodeError as e:
        return None, f"JSON格式错误: {str(e)}"
    except Exception as e:
        return None, f"读取文件失败: {str(e)}"

def precompile_rules():
    """预编译规则，提高匹配速度"""
    global rule_matcher_cache
    rule_matcher_cache = {}
    
    for i, rule in enumerate(rules):
        if rule.get('enabled', True):
            # keywords.json 使用 'keyword' 字段，用逗号分隔多个关键词
            keyword_str = rule.get('keyword', '')
            keywords = [kw.lower().strip() for kw in keyword_str.split('，') if kw.strip()]
            # 也支持英文逗号分隔
            if not keywords:
                keywords = [kw.lower().strip() for kw in keyword_str.split(',') if kw.strip()]
            
            rule_matcher_cache[i] = {
                'keywords': keywords,
                'reply': rule.get('reply', ''),
                'reply_type': rule.get('reply_type', 'text'),  # 'text' 或 'image'
                'reply_image': rule.get('reply_image', ''),  # 图片路径
                'title': rule.get('name', f'规则{i+1}')  # keywords.json 使用 'name' 字段
            }

def check_keywords_fast(message):
    """极速关键词匹配（优化版）"""
    if not message or not rule_matcher_cache:
        return None
    
    message_lower = message.lower().strip()
    if not message_lower:
        return None
    
    # 使用更高效的匹配算法
    for rule_id, rule_data in rule_matcher_cache.items():
        keywords = rule_data['keywords']
        if not keywords:
            continue
            
        # 优先匹配较长的关键词，提高准确性
        for keyword in sorted(keywords, key=len, reverse=True):
            if keyword and keyword in message_lower:
                return rule_data
    return None

def get_random_image_from_folder(folder_path):
    """从指定文件夹随机获取一张图片"""
    try:
        if not os.path.exists(folder_path):
            add_log(f"图片文件夹不存在: {folder_path}", 'error')
            return None
        
        # 支持的图片格式
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        
        # 获取文件夹中所有图片文件
        image_files = []
        for file in os.listdir(folder_path):
            if os.path.splitext(file.lower())[1] in image_extensions:
                image_files.append(os.path.join(folder_path, file))
        
        if not image_files:
            add_log(f"文件夹中没有找到图片文件: {folder_path}", 'warning')
            return None
        
        # 随机选择一张图片
        import random
        selected_image = random.choice(image_files)
        add_log(f"随机选择图片: {os.path.basename(selected_image)}", 'info')
        return selected_image
        
    except Exception as e:
        add_log(f"获取随机图片失败: {e}", 'error')
        return None

def check_keywords(message, keywords):
    """检查消息是否包含关键词（兼容版本）"""
    message = message.lower()
    for keyword in keywords:
        if keyword.lower() in message:
            return True
    return False

def generate_message_id(talker_id, timestamp, content):
    """生成消息唯一ID"""
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
    return f"{talker_id}_{timestamp}_{content_hash}"

def cleanup_cache():
    """清理过期缓存（修复多轮对话版）"""
    global message_cache, last_message_times
    current_time = int(time.time())
    
    # 更激进的缓存清理策略 - 只保留15分钟内的消息缓存，提高内存效率
    old_cache = {}
    cleaned_count = 0
    for msg_id in list(message_cache.keys()):
        try:
            # 从消息ID中提取时间戳
            parts = msg_id.split('_')
            if len(parts) >= 2:
                msg_time = int(parts[1])
                if current_time - msg_time < 900:  # 只保留15分钟内的，减少内存占用
                    old_cache[msg_id] = message_cache[msg_id]
                else:
                    cleaned_count += 1
        except:
            # 无法解析的ID直接删除
            cleaned_count += 1
    
    message_cache = old_cache
    
    # 不清理时间记录，保持会话连续性
    # 但限制缓存大小，防止内存泄漏
    if len(message_cache) > 300:
        # 进一步减少消息缓存大小，只保留最新的200条，大幅提高内存效率
        sorted_items = sorted(message_cache.items(), key=lambda x: x[0])
        message_cache = dict(sorted_items[-200:])
        add_log("缓存过大，已清理到最新200条", 'warning')
    
    # 强制垃圾回收
    import gc
    gc.collect()
    
    add_log(f"缓存清理完成: 清理消息 {cleaned_count} 条，当前缓存 {len(message_cache)} 条，活跃会话 {len(last_message_times)} 个", 'info')

def check_followers_changes(api):
    """检测关注者变化（新关注和取消关注）- 完全重构版"""
    global followers_cache, last_follow_check, unfollowers_cache, follow_history
    
    try:
        current_time = int(time.time())
        
        # 从配置中获取检查间隔，默认300秒（5分钟）避免触发风控
        check_interval = config.get('follow_check_interval', 300)
        if current_time - last_follow_check < check_interval:
            return {'new_followers': [], 'unfollowers': []}
        
        last_follow_check = current_time
        
        # 如果关注相关功能都未启用，直接返回
        if not config.get('follow_reply_enabled', False) and not config.get('unfollow_reply_enabled', False):
            return {'new_followers': [], 'unfollowers': []}
        
        # 获取最近的关注者（进一步优化数量，减少API负担，提高响应速度）
        recent_followers = api.get_recent_followers(limit=15)
        if not recent_followers:
            return {'new_followers': [], 'unfollowers': []}
        
        # 使用线程锁确保原子操作
        lock = threading.Lock()
        with lock:
            new_followers = []
            unfollowers = []
            current_followers = set()
            
            # 1. 构建当前关注者集合
            for follower in recent_followers:
                follower_mid = follower.get('mid')
                if follower_mid:
                    current_followers.add(follower_mid)
            
            # 2. 检测新关注者（支持重复关注）
            if config.get('follow_reply_enabled', False):
                for follower in recent_followers:
                    follower_mid = follower.get('mid')
                    if not follower_mid:
                        continue
                    
                    follow_time = follower.get('mtime', 0)
                    
                    # 检查是否是最近90秒内的新关注
                    if current_time - follow_time <= 90:
                        # 检查是否需要发送欢迎消息
                        should_send_welcome = False
                        
                        # 检查是否是新关注者
                        is_new_follower = follower_mid not in followers_cache
                        # 检查是否是重复关注（之前取消过关注）
                        is_re_follow = follower_mid in followers_cache and follow_time > follow_history.get(follower_mid, 0)
                        
                        if (is_new_follower or is_re_follow) and follower_mid not in welcome_sent_cache:
                            should_send_welcome = True
                            log_type = "新关注者" if is_new_follower else "重复关注者"
                            add_log(f"⚡ 检测到{log_type}: {follower.get('uname', 'Unknown')} (UID: {follower_mid})", 'success')
                        
                        if should_send_welcome:
                            new_followers.append(follower)
                            # 更新关注历史
                            follow_history[follower_mid] = follow_time
            
            # 3. 检测取消关注者（优化版本，避免重复API调用）
            if config.get('unfollow_reply_enabled', False):
                # 获取所有新关注者的mid集合
                new_follower_mids = {f['mid'] for f in new_followers if f.get('mid')}
                
                # 找出之前在缓存中但现在不在当前关注者列表中的用户
                lost_followers = followers_cache - current_followers
                for unfollower_mid in lost_followers:
                    # 确保不是新关注者（避免误判）
                    if unfollower_mid not in new_follower_mids and unfollower_mid not in unfollowers_cache:
                        # 直接确认取消关注，不再重复调用API验证
                        # 因为我们已经从最新的关注者列表中获取了数据
                        unfollowers.append({'mid': unfollower_mid})
                        unfollowers_cache.add(unfollower_mid)
                        add_log(f"💔 检测到取消关注: UID {unfollower_mid}", 'warning')
                        # 从欢迎消息缓存中移除
                        if unfollower_mid in welcome_sent_cache:
                            welcome_sent_cache.remove(unfollower_mid)
            
            # 4. 更新关注者缓存（在所有检测完成后）
            followers_cache = current_followers.copy()
            
            # 优化缓存管理，减少内存占用并提高性能
            if len(followers_cache) > 200:
                # 只保留最新的150个关注者，减少内存占用
                followers_cache = set(list(followers_cache)[-150:])
            
            if len(unfollowers_cache) > 300:
                # 减少取消关注缓存大小
                unfollowers_cache = set(list(unfollowers_cache)[-200:])
            
            if len(follow_history) > 500:
                # 按时间排序，只保留最新的300条记录，减少内存占用
                sorted_history = sorted(follow_history.items(), key=lambda x: x[1], reverse=True)
                follow_history = dict(sorted_history[:300])
            
            return {'new_followers': new_followers, 'unfollowers': unfollowers}
        
    except Exception as e:
        add_log(f"检测关注者变化异常: {e}", 'error')
        return {'new_followers': [], 'unfollowers': []}

# 保持向后兼容性
def check_new_followers(api):
    """检测新关注者（向后兼容函数）"""
    result = check_followers_changes(api)
    return result['new_followers']

def send_follow_welcome_message(api, follower):
    """向新关注者发送欢迎消息"""
    try:
        follower_mid = follower.get('mid')
        follower_name = follower.get('uname', 'Unknown')
        
        if not follower_mid:
            return False
        
        # 获取回复配置
        reply_type = config.get('follow_reply_type', 'text')
        reply_message = config.get('follow_reply_message', '感谢您的关注！')
        reply_image = config.get('follow_reply_image', '')
        
        success = False
        
        if reply_type == 'image' and reply_image and os.path.exists(reply_image):
            # 发送图片欢迎消息
            add_log(f"向新关注者 {follower_name} 发送图片欢迎消息", 'info')
            result = api.send_image_msg(follower_mid, reply_image)
            if result and result.get('code') == 0:
                success = True
                add_log(f"✅ 成功向新关注者 {follower_name} 发送图片欢迎消息", 'success')
            else:
                # 图片发送失败，尝试发送文字消息
                add_log(f"图片发送失败，向 {follower_name} 发送文字欢迎消息", 'warning')
                result = api.send_msg(follower_mid, content=reply_message)
                if result and result.get('code') == 0:
                    success = True
                    add_log(f"✅ 成功向新关注者 {follower_name} 发送文字欢迎消息", 'success')
        else:
            # 发送文字欢迎消息
            add_log(f"向新关注者 {follower_name} 发送文字欢迎消息: {reply_message}", 'info')
            result = api.send_msg(follower_mid, content=reply_message)
            if result and result.get('code') == 0:
                success = True
                add_log(f"✅ 成功向新关注者 {follower_name} 发送欢迎消息", 'success')
        
        if not success:
            error_msg = result.get('message', '未知错误') if result else '网络错误'
            add_log(f"❌ 向新关注者 {follower_name} 发送欢迎消息失败: {error_msg}", 'warning')
        
        return success
        
    except Exception as e:
        add_log(f"发送关注欢迎消息异常: {e}", 'error')
        return False

def send_unfollow_goodbye_message(api, unfollower):
    """向取消关注者发送告别消息"""
    try:
        unfollower_mid = unfollower.get('mid')
        
        if not unfollower_mid:
            return False
        
        # 获取回复配置
        reply_type = config.get('unfollow_reply_type', 'text')
        reply_message = config.get('unfollow_reply_message', '很遗憾看到您取消了关注，希望我们还有机会再见！')
        reply_image = config.get('unfollow_reply_image', '')
        
        success = False
        
        if reply_type == 'image' and reply_image and os.path.exists(reply_image):
            # 发送图片告别消息
            add_log(f"向取消关注者 UID:{unfollower_mid} 发送图片告别消息", 'info')
            result = api.send_image_msg(unfollower_mid, reply_image)
            if result and result.get('code') == 0:
                success = True
                add_log(f"✅ 成功向取消关注者 UID:{unfollower_mid} 发送图片告别消息", 'success')
            else:
                # 图片发送失败，尝试发送文字消息
                add_log(f"图片发送失败，向 UID:{unfollower_mid} 发送文字告别消息", 'warning')
                result = api.send_msg(unfollower_mid, content=reply_message)
                if result and result.get('code') == 0:
                    success = True
                    add_log(f"✅ 成功向取消关注者 UID:{unfollower_mid} 发送文字告别消息", 'success')
        else:
            # 发送文字告别消息
            add_log(f"向取消关注者 UID:{unfollower_mid} 发送文字告别消息: {reply_message}", 'info')
            result = api.send_msg(unfollower_mid, content=reply_message)
            if result and result.get('code') == 0:
                success = True
                add_log(f"✅ 成功向取消关注者 UID:{unfollower_mid} 发送告别消息", 'success')
        
        if not success:
            error_msg = result.get('message', '未知错误') if result else '网络错误'
            add_log(f"❌ 向取消关注者 UID:{unfollower_mid} 发送告别消息失败: {error_msg}", 'warning')
        
        return success
        
    except Exception as e:
        add_log(f"发送取消关注告别消息异常: {e}", 'error')
        return False

def process_single_session(api, my_uid, session):
    """处理单个会话的消息（只检测最后一条消息）"""
    global message_cache, last_message_times, program_start_time
    
    try:
        # 安全检查：确保session是有效的字典
        if not session or not isinstance(session, dict):
            return []
            
        talker_id = session.get('talker_id')
        if not talker_id:
            return []
        
        # 从JSON文件读取用户回复统计
        user_reply_stats = load_user_reply_stats()
        max_replies = config.get('max_replies_per_user', 3)
        current_replies = get_user_reply_count(talker_id, user_reply_stats)
        
        # 只在首次达到限制时记录日志
        if current_replies >= max_replies:
            user_id_str = str(talker_id)
            if user_reply_stats.get(user_id_str, {}).get('logged', False) == False:
                add_log(f"用户{talker_id} 已达到最大回复次数限制 ({current_replies}/{max_replies})，后续消息将不再回复", 'info', system='message')
                user_reply_stats[user_id_str]['logged'] = True
                save_user_reply_stats(user_reply_stats)
            return []
        
        # 获取最新的一条消息
        latest_msg = api.get_latest_message(talker_id)
        if not latest_msg:
            return []
        
        msg_timestamp = latest_msg.get('timestamp', 0)
        sender_uid = latest_msg.get('sender_uid')
        
        # 检查是否启用了“仅回复新消息”功能
        if config.get('only_reply_new_messages', False):
            # 如果消息时间早于程序启动时间，跳过处理
            if msg_timestamp < program_start_time:
                add_log(f"用户{talker_id} 消息时间早于程序启动时间，跳过回复（仅回复新消息模式）", 'debug', system='message')
                # 仍然更新最后处理时间，避免重复检查
                last_message_times[talker_id] = msg_timestamp
                return []
        
        # 检查是否是新消息
        last_processed_time = last_message_times.get(talker_id, 0)
        if msg_timestamp <= last_processed_time:
            return []
        
        # 更新最后处理时间
        last_message_times[talker_id] = msg_timestamp
        
        # 如果最后一条消息是我发的，不回复
        if sender_uid == my_uid:
            add_log(f"用户{talker_id} 最后一条消息是我发的，跳过回复", 'debug', system='message')
            return []
        
        # 获取消息内容
        content_str = latest_msg.get('content', '{}')
        try:
            content_obj = json.loads(content_str)
            message_text = content_obj.get('content', '').strip()
        except:
            message_text = content_str.strip()
        
        if not message_text:
            return []
        
        # 生成消息ID并检查缓存
        msg_id = generate_message_id(talker_id, msg_timestamp, message_text)
        if msg_id in message_cache:
            return []
        
        # 更新缓存
        message_cache[msg_id] = True
        
        # 极速关键词匹配
        matched_rule = check_keywords_fast(message_text)
        
        if matched_rule:
            add_log(f"✅ 检测到关键词匹配: 用户{talker_id} 消息'{message_text}' 匹配规则'{matched_rule['title']}'", 'info', system='message')
            return [{
                'talker_id': talker_id,
                'rule': matched_rule,
                'message': message_text,
                'timestamp': msg_timestamp
            }]
        else:
            # 如果启用了默认回复功能且没有匹配到关键词
            if config.get('default_reply_enabled', False):
                # 检查是否启用了区分已关注/未关注用户的回复
                separate_by_follow = config.get('separate_reply_by_follow', False)
                
                if separate_by_follow:
                    # 检查用户是否关注了我
                    is_followed = api.check_user_relation(talker_id)
                    
                    if is_followed is True:
                        # 已关注用户的回复
                        reply_type = config.get('followed_reply_type', 'text')
                        reply_message = config.get('followed_reply_message', '您好，感谢您的关注！我现在不在，稍后会回复您的消息。')
                        reply_image = config.get('followed_reply_image', '')
                        user_type = '已关注'
                    elif is_followed is False:
                        # 未关注用户的回复
                        reply_type = config.get('unfollowed_reply_type', 'text')
                        reply_message = config.get('unfollowed_reply_message', '您好，我现在不在，稍后会回复您的消息。')
                        reply_image = config.get('unfollowed_reply_image', '')
                        user_type = '未关注'
                    else:
                        # 检查失败，使用默认回复
                        reply_type = config.get('default_reply_type', 'text')
                        reply_message = config.get('default_reply_message', '您好，我现在不在，稍后会回复您的消息。')
                        reply_image = config.get('default_reply_image', '')
                        user_type = '默认'
                    
                    if reply_type == 'text' and reply_message:
                        add_log(f"⚠️ 用户{talker_id}({user_type}) 消息'{message_text}' 未匹配关键词，使用{user_type}用户文字回复", 'info', system='message')
                        return [{
                            'talker_id': talker_id,
                            'rule': {
                                'title': f'默认回复({user_type}用户)',
                                'reply': reply_message,
                                'reply_type': 'text'
                            },
                            'message': message_text,
                            'timestamp': msg_timestamp
                        }]
                    elif reply_type == 'image' and reply_image:
                        add_log(f"⚠️ 用户{talker_id}({user_type}) 消息'{message_text}' 未匹配关键词，使用{user_type}用户图片回复", 'info', system='message')
                        return [{
                            'talker_id': talker_id,
                            'rule': {
                                'title': f'默认回复({user_type}用户)',
                                'reply': '[图片回复]',
                                'reply_type': 'image',
                                'reply_image': reply_image
                            },
                            'message': message_text,
                            'timestamp': msg_timestamp
                        }]
                else:
                    # 不区分用户类型，使用统一的默认回复
                    default_type = config.get('default_reply_type', 'text')
                    
                    if default_type == 'text' and config.get('default_reply_message'):
                        add_log(f"⚠️ 用户{talker_id} 消息'{message_text}' 未匹配关键词，使用默认文字回复", 'info', system='message')
                        return [{
                            'talker_id': talker_id,
                            'rule': {
                                'title': '默认回复',
                                'reply': config.get('default_reply_message'),
                                'reply_type': 'text'
                            },
                            'message': message_text,
                            'timestamp': msg_timestamp
                        }]
                    elif default_type == 'image' and config.get('default_reply_image'):
                        add_log(f"⚠️ 用户{talker_id} 消息'{message_text}' 未匹配关键词，使用默认图片回复", 'info', system='message')
                        return [{
                            'talker_id': talker_id,
                            'rule': {
                                'title': '默认回复',
                                'reply': '[图片回复]',
                                'reply_type': 'image',
                                'reply_image': config.get('default_reply_image')
                            },
                            'message': message_text,
                            'timestamp': msg_timestamp
                        }]
            else:
                add_log(f"❌ 用户{talker_id} 消息'{message_text}' 未匹配任何关键词", 'debug', system='message')
                return []
        
    except Exception as e:
        logger.error(f"处理会话 {session.get('talker_id')} 时出错: {e}")
        return []

def monitor_single_account(account_name, sessdata, bili_jct, account_uid, account_email=''):
    """监控单个账号的消息"""
    add_log(f"🚀 开始监控账号: {account_name} (UID: {account_uid})", 'success', system='message', account_name=account_name)
    
    max_retries = 3
    retry_count = 0
    login_failed_notified = False  # 标记是否已发送登录失效通知
    
    while monitoring and retry_count < max_retries:
        try:
            api = BilibiliAPI(sessdata, bili_jct)
            my_uid = api.get_my_uid()
            
            if not my_uid:
                error_msg = f"[{account_name}] 获取用户信息失败，登录可能已失效"
                error_details = f"账号: {account_name}\nUID: {account_uid}\n重试次数: {retry_count + 1}/{max_retries}"
                add_log(error_msg, 'error', system='message', 
                       error_details=error_details, 
                       context='账号登录验证', 
                       account_name=account_name)
                
                # 发送登录失效邮件通知（只发送一次）
                if not login_failed_notified and account_email:
                    if send_login_expired_notification(account_name, account_email):
                        add_log(f"[{account_name}] 已发送登录失效通知至 {account_email}", 'info', system='message', account_name=account_name)
                        login_failed_notified = True
                    else:
                        add_log(f"[{account_name}] 发送登录失效通知失败", 'warning', system='message', account_name=account_name)
                
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(0.3)
                    continue
                else:
                    return
            
            add_log(f"[{account_name}] 监控已启动，用户UID: {my_uid}", 'success', system='message')
            
            # 预编译规则
            precompile_rules()
            
            # 为每个账号创建独立的缓存（不包括user_reply_counts，使用JSON文件）
            local_cache = {
                'message_cache': {},
                'last_message_times': defaultdict(int),
                'last_send_time': 0,
                'followers_cache': set(),
                'welcome_sent_cache': set(),
                'last_follow_check': 0,
                'unfollowers_cache': set(),
                'follow_history': {}
            }
            
            # 执行监控循环（使用独立缓存）
            monitor_loop_core(api, my_uid, account_name, local_cache)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            add_log(f"[{account_name}] 监控异常: {e}", 'error', system='message',
                   error_details=error_details,
                   context='账号监控循环',
                   account_name=account_name)
            retry_count += 1
            if retry_count < max_retries and monitoring:
                time.sleep(1)
            else:
                break
    
    add_log(f"[{account_name}] 监控已停止", 'warning', system='message', account_name=account_name)

def monitor_loop_core(api, my_uid, account_prefix, cache):
    """监控循环核心逻辑（可用于单账号或多账号）"""
    # 从缓存中提取变量
    message_cache = cache['message_cache']
    last_message_times = cache['last_message_times']
    last_send_time = cache['last_send_time']
    followers_cache = cache['followers_cache']
    welcome_sent_cache = cache['welcome_sent_cache']
    last_follow_check = cache['last_follow_check']
    unfollowers_cache = cache['unfollowers_cache']
    follow_history = cache['follow_history']
    
    # 加载用户回复统计（从JSON文件）
    user_reply_stats = load_user_reply_stats()
    
    last_cleanup = int(time.time())
    last_api_reset = int(time.time())
    last_reply_time = int(time.time())
    last_heartbeat = int(time.time())
    processed_count = 0
    error_count = 0
    consecutive_errors = 0
    
    while monitoring:
        try:
            loop_start = time.time()
            current_time = int(time.time())
            
            # 心跳检测
            if current_time - last_heartbeat >= 60:
                add_log(f"[{account_prefix}] 💓 系统运行正常: 处理{processed_count}条消息, 错误{error_count}次", 'info', system='message')
                last_heartbeat = current_time
                
                # 健康检查
                if processed_count > 0 and error_count > processed_count * 0.5:
                    add_log(f"[{account_prefix}] ⚠️ 错误率过高，重新初始化API", 'warning', system='message')
                    try:
                        api = BilibiliAPI(api.sessdata, api.bili_jct)
                        error_count = 0
                        consecutive_errors = 0
                    except Exception as e:
                        add_log(f"[{account_prefix}] API重新初始化失败: {e}", 'error', system='message')
            
            # 定期清理缓存
            if current_time - last_cleanup > 300:
                try:
                    # 清理过期消息缓存
                    old_cache_size = len(message_cache)
                    cleaned_cache = {}
                    for msg_id in list(message_cache.keys()):
                        try:
                            parts = msg_id.split('_')
                            if len(parts) >= 2:
                                msg_time = int(parts[1])
                                if current_time - msg_time < 900:
                                    cleaned_cache[msg_id] = message_cache[msg_id]
                        except:
                            pass
                    message_cache.clear()
                    message_cache.update(cleaned_cache)
                    
                    import gc
                    gc.collect()
                    
                    # 同时清理错误追踪器
                    cleanup_error_tracker()
                    
                    add_log(f"[{account_prefix}] 缓存清理: {old_cache_size} -> {len(message_cache)}", 'info', system='message', account_name=account_prefix)
                    last_cleanup = current_time
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    add_log(f"[{account_prefix}] 缓存清理异常: {e}", 'warning', system='message',
                           error_details=error_details,
                           context='缓存清理',
                           account_name=account_prefix)
            
            # 获取会话列表
            sessions_data = None
            for attempt in range(3):
                try:
                    sessions_data = api.get_sessions()
                    if sessions_data:
                        break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(0.3)
            
            if not sessions_data or sessions_data.get('code') != 0:
                consecutive_errors += 1
                if consecutive_errors > 5:
                    add_log(f"[{account_prefix}] 连续获取会话失败，重新初始化API", 'warning', system='message')
                    try:
                        api = BilibiliAPI(api.sessdata, api.bili_jct)
                        consecutive_errors = 0
                    except Exception as e:
                        add_log(f"[{account_prefix}] API重新初始化失败: {e}", 'error', system='message')
                time.sleep(2)
                continue
            
            consecutive_errors = 0
            
            # 验证数据结构
            data = sessions_data.get('data')
            if not data or not isinstance(data, dict):
                time.sleep(1)
                continue
            
            # 处理会话
            sessions = data.get('session_list', [])
            if not sessions:
                time.sleep(0.2)
                continue
            
            # 过滤无效会话
            sessions = [s for s in sessions if s and isinstance(s, dict)]
            if not sessions:
                time.sleep(0.2)
                continue
            
            # 安全排序
            try:
                sessions.sort(key=lambda x: x.get('last_msg', {}).get('timestamp', 0) if x.get('last_msg') else 0, reverse=True)
            except Exception as sort_error:
                pass
            
            # 筛选需要检查的会话
            new_message_sessions = []
            active_sessions = []
            
            for session in sessions:
                if not session or not isinstance(session, dict):
                    continue
                
                talker_id = session.get('talker_id')
                if not talker_id:
                    continue
                
                last_msg = session.get('last_msg')
                if last_msg and isinstance(last_msg, dict):
                    last_msg_time = last_msg.get('timestamp', 0)
                else:
                    last_msg_time = 0
                
                recorded_time = last_message_times.get(talker_id, 0)
                
                if last_msg_time > recorded_time:
                    new_message_sessions.append(session)
                elif last_msg_time > 0 and current_time - last_msg_time < 300:
                    active_sessions.append(session)
            
            check_sessions = new_message_sessions + active_sessions
            
            if new_message_sessions:
                add_log(f"[{account_prefix}] 📬 检测到 {len(new_message_sessions)} 个新消息会话", 'info', system='message')
            
            if not check_sessions:
                time.sleep(0.2)
                continue
            
            # 处理会话
            reply_count = 0
            for session in check_sessions:
                if not monitoring:
                    break
                
                try:
                    session_talker_id = session.get('talker_id', 'unknown')
                    results = process_single_session_with_cache(api, my_uid, session, message_cache, last_message_times, user_reply_stats)
                    
                    if not results:
                        continue
                    
                    for result in results:
                        try:
                            reply_result = None
                            reply_content = result['rule']['reply']
                            reply_type = result['rule'].get('reply_type', 'text')
                            
                            if reply_type == 'image':
                                image_path = result['rule'].get('reply_image', '')
                                if image_path and os.path.exists(image_path):
                                    reply_result = api.send_image_msg(result['talker_id'], image_path)
                                    if not reply_result:
                                        fallback_message = config.get('default_reply_message', '您好，感谢您的消息！')
                                        reply_result = api.send_msg(result['talker_id'], fallback_message)
                                    reply_content = f"[图片] {os.path.basename(image_path)}"
                                else:
                                    continue
                            else:
                                reply_result = api.send_msg(result['talker_id'], content=result['rule']['reply'])
                            
                            if reply_result and reply_result.get('code') == 0:
                                # 使用JSON文件统计增加回复次数
                                current_count = increment_user_reply_count(result['talker_id'], user_reply_stats)
                                max_count = config.get('max_replies_per_user', 3)
                                add_log(f"[{account_prefix}] ✅ 已回复用户 {result['talker_id']} (第{current_count}/{max_count}次)", 'success', system='message')
                                reply_count += 1
                                processed_count += 1
                                last_reply_time = current_time
                            elif reply_result and reply_result.get('code') == -101:
                                add_log(f"[{account_prefix}] 🔐 登录状态失效", 'error', system='message')
                                return  # 退出监控
                            else:
                                error_count += 1
                        except Exception as e:
                            error_count += 1
                
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    add_log(f"[{account_prefix}] 处理会话 {session_talker_id} 异常: {e}", 'error', system='message',
                           error_details=error_detail,
                           context=f'处理会话 {session_talker_id}',
                           account_name=account_prefix)
                    logger.error(f"会话处理详细错误:\n{error_detail}")
                    error_count += 1
                    continue
            
            # 更新缓存（不再需要user_reply_counts）
            cache['message_cache'] = message_cache
            cache['last_message_times'] = last_message_times
            cache['last_send_time'] = last_send_time
            
            # 循环间隔
            elapsed = time.time() - loop_start
            check_interval = config.get('message_check_interval', 0.05)
            sleep_time = max(0.01, check_interval - elapsed)
            time.sleep(sleep_time)
            
        except KeyboardInterrupt:
            add_log(f"[{account_prefix}] 收到停止信号", 'warning', system='message', account_name=account_prefix)
            return
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            add_log(f"[{account_prefix}] 监控循环异常: {e}", 'error', system='message',
                   error_details=error_detail,
                   context='监控循环主逻辑',
                   account_name=account_prefix)
            logger.error(f"详细错误信息:\n{error_detail}")
            error_count += 1
            consecutive_errors += 1
            
            if consecutive_errors > 5:
                add_log(f"[{account_prefix}] 连续错误过多，执行系统重置", 'warning', system='message')
                try:
                    message_cache.clear()
                    last_message_times.clear()
                    import gc
                    gc.collect()
                    api = BilibiliAPI(api.sessdata, api.bili_jct)
                    consecutive_errors = 0
                    last_reply_time = current_time
                except Exception as init_e:
                    add_log(f"[{account_prefix}] 系统重置失败: {init_e}", 'error', system='message')
                    if consecutive_errors > 15:
                        return
                time.sleep(2)
            else:
                time.sleep(1)

def process_single_session_with_cache(api, my_uid, session, message_cache, last_message_times, user_reply_stats):
    """处理单个会话（使用传入的缓存和统计）"""
    try:
        if not session or not isinstance(session, dict):
            return []
        
        talker_id = session.get('talker_id')
        if not talker_id:
            return []
        
        # 从JSON统计文件读取用户回复次数
        max_replies = config.get('max_replies_per_user', 3)
        current_replies = get_user_reply_count(talker_id, user_reply_stats)
        
        # 只在首次达到限制时记录日志，避免重复输出
        if current_replies >= max_replies:
            user_id_str = str(talker_id)
            if user_reply_stats.get(user_id_str, {}).get('logged', False) == False:
                add_log(f"用户{talker_id} 已达到最大回复次数限制 ({current_replies}/{max_replies})，后续消息将不再回复", 'info', system='message')
                user_reply_stats[user_id_str]['logged'] = True
                save_user_reply_stats(user_reply_stats)
            return []
        
        # 获取最新消息
        latest_msg = api.get_latest_message(talker_id)
        if not latest_msg:
            return []
        
        msg_timestamp = latest_msg.get('timestamp', 0)
        sender_uid = latest_msg.get('sender_uid')
        
        # 检查是否仅回复新消息
        if config.get('only_reply_new_messages', False):
            if msg_timestamp < program_start_time:
                last_message_times[talker_id] = msg_timestamp
                return []
        
        # 检查是否是新消息
        last_processed_time = last_message_times.get(talker_id, 0)
        if msg_timestamp <= last_processed_time:
            return []
        
        # 更新最后处理时间
        last_message_times[talker_id] = msg_timestamp
        
        # 如果是自己发的消息，跳过
        if sender_uid == my_uid:
            return []
        
        # 获取消息内容
        content_str = latest_msg.get('content', '{}')
        try:
            content_obj = json.loads(content_str)
            message_text = content_obj.get('content', '').strip()
        except:
            message_text = content_str.strip()
        
        if not message_text:
            return []
        
        # 生成消息ID并检查缓存
        msg_id = generate_message_id(talker_id, msg_timestamp, message_text)
        if msg_id in message_cache:
            return []
        
        # 更新缓存
        message_cache[msg_id] = True
        
        # 关键词匹配
        matched_rule = check_keywords_fast(message_text)
        
        if matched_rule:
            return [{
                'talker_id': talker_id,
                'rule': matched_rule,
                'message': message_text,
                'timestamp': msg_timestamp
            }]
        elif config.get('default_reply_enabled', False):
            # 检查是否启用了区分已关注/未关注用户的回复
            separate_by_follow = config.get('separate_reply_by_follow', False)
            
            if separate_by_follow:
                # 检查用户是否关注了我
                is_followed = api.check_user_relation(talker_id)
                
                if is_followed is True:
                    # 已关注用户的回复
                    reply_type = config.get('followed_reply_type', 'text')
                    reply_message = config.get('followed_reply_message', '您好，感谢您的关注！我现在不在，稍后会回复您的消息。')
                    reply_image = config.get('followed_reply_image', '')
                    user_type = '已关注'
                elif is_followed is False:
                    # 未关注用户的回复
                    reply_type = config.get('unfollowed_reply_type', 'text')
                    reply_message = config.get('unfollowed_reply_message', '您好，我现在不在，稍后会回复您的消息。')
                    reply_image = config.get('unfollowed_reply_image', '')
                    user_type = '未关注'
                else:
                    # 检查失败，使用默认回复
                    reply_type = config.get('default_reply_type', 'text')
                    reply_message = config.get('default_reply_message', '您好，我现在不在，稍后会回复您的消息。')
                    reply_image = config.get('default_reply_image', '')
                    user_type = '默认'
                
                if reply_type == 'text' and reply_message:
                    return [{
                        'talker_id': talker_id,
                        'rule': {
                            'title': f'默认回复({user_type}用户)',
                            'reply': reply_message,
                            'reply_type': 'text'
                        },
                        'message': message_text,
                        'timestamp': msg_timestamp
                    }]
                elif reply_type == 'image' and reply_image:
                    return [{
                        'talker_id': talker_id,
                        'rule': {
                            'title': f'默认回复({user_type}用户)',
                            'reply': '[图片回复]',
                            'reply_type': 'image',
                            'reply_image': reply_image
                        },
                        'message': message_text,
                        'timestamp': msg_timestamp
                    }]
            else:
                # 不区分用户类型，使用统一的默认回复
                default_type = config.get('default_reply_type', 'text')
                if default_type == 'text' and config.get('default_reply_message'):
                    return [{
                        'talker_id': talker_id,
                        'rule': {
                            'title': '默认回复',
                            'reply': config.get('default_reply_message'),
                            'reply_type': 'text'
                        },
                        'message': message_text,
                        'timestamp': msg_timestamp
                    }]
                elif default_type == 'image' and config.get('default_reply_image'):
                    return [{
                        'talker_id': talker_id,
                        'rule': {
                            'title': '默认回复',
                            'reply': '[图片回复]',
                            'reply_type': 'image',
                            'reply_image': config.get('default_reply_image')
                        },
                        'message': message_text,
                        'timestamp': msg_timestamp
                    }]
        
        return []
        
    except Exception as e:
        logger.error(f"处理会话 {session.get('talker_id')} 时出错: {e}")
        return []

def monitor_messages():
    """监控消息的主循环（增强稳定性版本）- 支持多账号"""
    global monitoring, message_cache, last_message_times, last_send_time, monitor_thread
    global followers_cache, welcome_sent_cache, last_follow_check
    global unfollowers_cache, follow_history, monitor_threads
    
    # 检查是否启用多账号模式
    if config.get('multi_account_mode', False):
        accounts = config.get('accounts', [])
        enabled_accounts = [acc for acc in accounts if acc.get('enabled', True)]
        
        if not enabled_accounts:
            add_log("多账号模式已启用，但没有可用的账号", 'error', system='message')
            monitoring = False
            return
        
        add_log(f"🎯 多账号模式：将监控 {len(enabled_accounts)} 个账号", 'success', system='message')
        
        # 为每个账号创建独立的监控线程
        monitor_threads = {}
        for account in enabled_accounts:
            account_name = account.get('name')
            sessdata = account.get('sessdata')
            bili_jct = account.get('bili_jct')
            account_uid = account.get('uid')
            account_email = account.get('email', '')
            
            if not sessdata or not bili_jct:
                add_log(f"账号 {account_name} 配置不完整，跳过", 'warning', system='message')
                continue
            
            # 创建并启动账号监控线程
            thread = threading.Thread(
                target=monitor_single_account,
                args=(account_name, sessdata, bili_jct, account_uid, account_email),
                daemon=True
            )
            thread.start()
            monitor_threads[account_name] = thread
            add_log(f"✅ 账号 {account_name} 监控线程已启动", 'info', system='message')
        
        # 等待所有线程结束
        while monitoring:
            time.sleep(1)
            # 检查是否所有线程都已结束
            all_stopped = all(not thread.is_alive() for thread in monitor_threads.values())
            if all_stopped:
                break
        
        add_log("所有账号监控已停止", 'warning', system='message')
        return
    
    # 单账号模式（向后兼容）
    if not config.get('sessdata') or not config.get('bili_jct'):
        add_log("未配置登录信息，无法启动监控", 'error', system='message')
        monitoring = False
        return
    
    # 增加重试机制和异常恢复
    max_retries = 3
    retry_count = 0
    
    while monitoring and retry_count < max_retries:
        try:
            api = BilibiliAPI(config['sessdata'], config['bili_jct'])
            my_uid = api.get_my_uid()
            
            if not my_uid:
                add_log("获取用户信息失败，请检查登录配置", 'error', system='message')
                retry_count += 1
                if retry_count < max_retries:
                    add_log(f"重试获取用户信息 ({retry_count}/{max_retries})", 'warning', system='message')
                    time.sleep(0.3)  # 进一步缩短用户信息重试等待时间
                    continue
                else:
                    monitoring = False
                    return
            
            # 重置重试计数
            retry_count = 0
            
            add_log(f"监控已启动，用户UID: {my_uid}", 'success', system='message')
            
            # 预编译规则
            precompile_rules()
            
            # 初始化全局变量（不再使用内存中的user_reply_counts）
            message_cache = {}
            last_message_times = defaultdict(int)
            last_send_time = 0
            followers_cache = set()
            welcome_sent_cache = set()
            last_follow_check = 0
            unfollowers_cache = set()
            follow_history = {}
            
            last_cleanup = int(time.time())
            last_api_reset = int(time.time())
            last_reply_time = int(time.time())  # 记录最后一次回复时间
            last_heartbeat = int(time.time())  # 心跳检测
            processed_count = 0
            error_count = 0
            consecutive_errors = 0
            
            while monitoring:
                try:
                    loop_start = time.time()
                    current_time = int(time.time())
                    
                    # 心跳检测 - 每60秒输出一次状态并进行健康检查
                    if current_time - last_heartbeat >= 60:
                        add_log(f"💓 系统运行正常: 处理{processed_count}条消息, 错误{error_count}次, 活跃会话{len(last_message_times)}个", 'info', system='message')
                        last_heartbeat = current_time
                        
                        # 健康检查：如果错误率过高，重新初始化API
                        if processed_count > 0 and error_count > processed_count * 0.5:
                            add_log(f"⚠️ 错误率过高 ({error_count}/{processed_count})，重新初始化API", 'warning', system='message')
                            try:
                                api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                                error_count = 0  # 重置错误计数
                                consecutive_errors = 0
                            except Exception as e:
                                add_log(f"健康检查后API重新初始化失败: {e}", 'error', system='message')
                    
                    # 每5分钟强制清理缓存（更频繁清理）
                    if current_time - last_cleanup > 300:
                        try:
                            cleanup_cache()
                            precompile_rules()
                            last_cleanup = current_time
                            add_log(f"定期维护: 已处理 {processed_count} 条消息，错误 {error_count} 次，活跃会话 {len(last_message_times)} 个", 'info', system='message')
                        except Exception as e:
                            add_log(f"缓存清理异常: {e}", 'warning', system='message')
                    
                    # 关注者检测已移至主循环，此处不再需要
                    
                    # 每30分钟重新创建API对象，防止连接问题
                    if current_time - last_api_reset > 1800:
                        try:
                            add_log("重新初始化API连接", 'info', system='message')
                            api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                            # 验证新API对象
                            test_uid = api.get_my_uid()
                            if test_uid:
                                last_api_reset = current_time
                                add_log("API重新初始化成功", 'success', system='message')
                            else:
                                add_log("API重新初始化失败，继续使用旧连接", 'warning', system='message')
                        except Exception as e:
                            add_log(f"API重新初始化异常: {e}", 'warning', system='message')
                    
                    # 获取会话列表 - 增加重试机制
                    sessions_data = None
                    for attempt in range(3):
                        try:
                            sessions_data = api.get_sessions()
                            if sessions_data:
                                break
                        except Exception as e:
                            add_log(f"获取会话列表尝试 {attempt+1}/3 失败: {e}", 'warning', system='message')
                            if attempt < 2:
                                time.sleep(0.3)  # 优化系统稳定等待时间
                    
                    if not sessions_data:
                        consecutive_errors += 1
                        if consecutive_errors > 5:
                            add_log("连续获取会话失败，重新初始化API", 'warning', system='message')
                            try:
                                api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                                consecutive_errors = 0
                            except Exception as e:
                                add_log(f"API重新初始化失败: {e}", 'error', system='message')
                        time.sleep(2)
                        continue
                    
                    if sessions_data.get('code') != 0:
                        error_msg = sessions_data.get('message', '未知错误')
                        add_log(f"API返回错误: {error_msg}", 'warning', system='message')
                        consecutive_errors += 1
                        
                        # 如果是认证相关错误，重新初始化
                        if sessions_data.get('code') in [-101, -111, -400, -403]:
                            add_log("认证错误，重新初始化API", 'warning', system='message')
                            try:
                                api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                            except Exception as e:
                                add_log(f"认证错误后API重新初始化失败: {e}", 'error', system='message')
                        
                        time.sleep(2)
                        continue
                    
                    consecutive_errors = 0  # 重置连续错误计数
                    
                    # 验证返回的数据结构
                    data = sessions_data.get('data')
                    if not data or not isinstance(data, dict):
                        add_log("API返回数据格式异常，跳过本轮", 'warning', system='message')
                        time.sleep(1)
                        continue
                    
                    # 定期缓存清理，避免长时间运行内存负荷过大
                    if current_time % 300 == 0:  # 每5分钟清理一次
                        try:
                            cleanup_cache()
                            # 强制垃圾回收
                            import gc
                            gc.collect()
                            add_log("定期缓存清理完成，内存优化", 'info', system='message')
                        except Exception as e:
                            add_log(f"定期缓存清理异常: {e}", 'warning', system='message')
                    
                    # 初始化本轮回复计数
                    reply_count = 0
                    
                    # 🎯 实时检测关注者变化（新关注和取消关注）
                    if config.get('follow_reply_enabled', False) or config.get('unfollow_reply_enabled', False):
                        try:
                            followers_changes = check_followers_changes(api)
                            
                            # 处理新关注者
                            for follower in followers_changes.get('new_followers', []):
                                if not monitoring:  # 检查是否仍在监控中
                                    break
                                try:
                                    # 发送欢迎消息（会自动应用发送间隔控制）
                                    if send_follow_welcome_message(api, follower):
                                        welcome_sent_cache.add(follower['mid'])
                                    reply_count += 1  # 计入回复统计
                                    processed_count += 1
                                except Exception as e:
                                    add_log(f"处理新关注者异常: {e}", 'error')
                                    error_count += 1
                            
                            # 处理取消关注者
                            for unfollower in followers_changes.get('unfollowers', []):
                                if not monitoring:  # 检查是否仍在监控中
                                    break
                                try:
                                    # 发送告别消息（会自动应用发送间隔控制）
                                    send_unfollow_goodbye_message(api, unfollower)
                                    reply_count += 1  # 计入回复统计
                                    processed_count += 1
                                except Exception as e:
                                    add_log(f"处理取消关注者异常: {e}", 'error')
                                    error_count += 1
                                    
                        except Exception as e:
                            add_log(f"实时检测关注者变化异常: {e}", 'warning')
                            error_count += 1
                            # 异常后继续运行，不中断监控循环
                    
                    sessions = sessions_data.get('data', {}).get('session_list', [])
                    if not sessions:
                        time.sleep(0.2)
                        continue
                    
                    # 过滤掉无效的会话（None 或空对象）
                    sessions = [s for s in sessions if s and isinstance(s, dict)]
                    if not sessions:
                        time.sleep(0.2)
                        continue
                    
                    # 按最后消息时间排序（安全版本）
                    try:
                        sessions.sort(key=lambda x: x.get('last_msg', {}).get('timestamp', 0) if x.get('last_msg') else 0, reverse=True)
                    except Exception as sort_error:
                        add_log(f"会话排序异常: {sort_error}，使用原始顺序", 'warning', system='message')
                        # 如果排序失败，继续使用原始顺序
                    
                    # 筛选需要检查的会话（扩大范围确保不遗漏）
                    check_sessions = []
                    new_message_sessions = []  # 有新消息的会话（优先处理）
                    active_sessions = []  # 活跃会话（次要处理）
                    
                    # 检查所有会话，不限制数量，避免漏回复
                    for session in sessions:
                        # 安全检查：确保session是有效的字典
                        if not session or not isinstance(session, dict):
                            continue
                            
                        talker_id = session.get('talker_id')
                        if not talker_id:
                            continue
                        
                        # 安全获取最后消息时间
                        last_msg = session.get('last_msg')
                        if last_msg and isinstance(last_msg, dict):
                            last_msg_time = last_msg.get('timestamp', 0)
                        else:
                            last_msg_time = 0
                        
                        recorded_time = last_message_times.get(talker_id, 0)
                        
                        # 检查有新消息的会话（优先级最高）
                        if last_msg_time > recorded_time:
                            new_message_sessions.append(session)
                        # 或者最近5分钟内活跃的会话（次要优先级）
                        elif last_msg_time > 0 and current_time - last_msg_time < 300:
                            active_sessions.append(session)
                    
                    # 合并会话列表：新消息优先，然后是活跃会话
                    check_sessions = new_message_sessions + active_sessions
                    
                    # 记录检查统计
                    if new_message_sessions:
                        add_log(f"📬 检测到 {len(new_message_sessions)} 个新消息会话，{len(active_sessions)} 个活跃会话", 'info', system='message')
                    
                    if not check_sessions:
                        time.sleep(0.2)
                        continue
                    
                    # 单线程顺序处理所有会话
                    # reply_count 已在循环开始时初始化
                    
                    for session in check_sessions:
                        if not monitoring:
                            break
                        
                        try:
                            # 获取会话ID用于日志
                            session_talker_id = session.get('talker_id', 'unknown')
                            
                            results = process_single_session(api, my_uid, session)
                            
                            if not results:
                                continue
                            
                            for result in results:
                                # 发送回复（带发送成功验证）
                                try:
                                    reply_result = None
                                    reply_content = result['rule']['reply']
                                    
                                    # 检查回复类型
                                    reply_type = result['rule'].get('reply_type', 'text')
                                    
                                    if reply_type == 'image':
                                        # 发送图片回复
                                        image_path = result['rule'].get('reply_image', '')
                                        if image_path and os.path.exists(image_path):
                                            add_log(f"发送图片回复给用户 {result['talker_id']}: {os.path.basename(image_path)}", 'info')
                                            reply_result = api.send_image_msg(result['talker_id'], image_path)
                                            
                                            # 如果图片发送失败，尝试发送备用文字回复
                                            if not reply_result:
                                                # 使用默认文字回复或通用回复
                                                fallback_message = config.get('default_reply_message', '您好，感谢您的消息！')
                                                add_log(f"图片发送失败，发送备用文字回复给用户 {result['talker_id']}: {fallback_message}", 'warning')
                                                reply_result = api.send_msg(result['talker_id'], fallback_message)
                                            reply_content = f"[图片] {os.path.basename(image_path)}"
                                        else:
                                            add_log(f"图片文件不存在，跳过回复用户 {result['talker_id']}", 'warning')
                                            continue
                                    else:
                                        # 发送文字回复
                                        reply_result = api.send_msg(result['talker_id'], content=result['rule']['reply'])
                                    
                                    if reply_result and reply_result.get('code') == 0:
                                        # 验证发送是否真正成功（优化等待时间）
                                        verification_wait = config.get('message_check_interval', 0.05) * 0.5
                                        time.sleep(max(0.01, verification_wait))  # 动态调整验证等待时间
                                        try:
                                            verification_success = api.verify_message_sent(result['talker_id'], reply_content)
                                        except Exception as e:
                                            add_log(f"验证消息发送状态异常: {e}", 'warning')
                                            verification_success = True  # 假设发送成功，避免卡住
                                        
                                        if verification_success:
                                            # 成功发送后，使用JSON文件统计增加回复次数
                                            user_reply_stats = load_user_reply_stats()
                                            current_count = increment_user_reply_count(result['talker_id'], user_reply_stats)
                                            max_count = config.get('max_replies_per_user', 3)
                                            
                                            add_log(f"✅ 已成功回复用户 {result['talker_id']} (规则: {result['rule']['title']}) 内容: {reply_content[:20]}... (第{current_count}/{max_count}次)", 'success')
                                            reply_count += 1
                                            processed_count += 1
                                        else:
                                            add_log(f"⚠️ 用户 {result['talker_id']} 发送验证失败，消息可能未送达", 'warning')
                                            error_count += 1
                                        
                                    elif reply_result and reply_result.get('code') == -412:
                                        add_log(f"🚫 用户 {result['talker_id']} 触发频率限制: {reply_result.get('message', '')}", 'warning')
                                        error_count += 1
                                        
                                    elif reply_result and reply_result.get('code') == -101:
                                        add_log("🔐 登录状态失效，请重新配置登录信息", 'error')
                                        monitoring = False
                                        break
                                        
                                    else:
                                        error_msg = reply_result.get('message', '未知错误') if reply_result else '网络错误'
                                        error_code = reply_result.get('code', 'N/A') if reply_result else 'N/A'
                                        error_details = f"错误码: {error_code}\n错误消息: {error_msg}\n用户ID: {result['talker_id']}\n消息内容: {result['message']}\n回复类型: {reply_type}\n完整响应: {reply_result}"
                                        add_log(f"❌ 回复用户 {result['talker_id']} 失败 [错误码:{error_code}]: {error_msg}", 'warning',
                                               error_details=error_details,
                                               context='回复用户消息')
                                        error_count += 1
                                        
                                except Exception as e:
                                    add_log(f"💥 发送回复异常: {e}", 'error')
                                    error_count += 1
                        
                        except Exception as e:
                            import traceback
                            error_detail = traceback.format_exc()
                            add_log(f"处理会话 {session_talker_id} 异常: {e}", 'error')
                            logger.error(f"会话处理详细错误:\n{error_detail}")
                            error_count += 1
                            # 继续处理下一个会话，不中断循环
                            continue
                    
                    # 每处理10轮后，强制清理一次缓存
                    if processed_count > 0 and processed_count % 10 == 0:
                        try:
                            add_log(f"🔄 已处理{processed_count}条消息，执行缓存清理", 'info')
                            cleanup_cache()
                        except Exception as e:
                            add_log(f"缓存清理异常: {e}", 'warning')
                    
                    # 记录处理结果和更新最后回复时间
                    if reply_count > 0:
                        last_reply_time = int(time.time())  # 更新最后回复时间
                        add_log(f"📊 本轮回复了 {reply_count} 条消息，总计处理 {processed_count} 条", 'info')
                    
                    # 检查是否需要自动重启（可配置间隔）
                    # 只有在有错误或异常情况下才触发自动重启
                    current_time_check = int(time.time())
                    restart_interval = config.get('auto_restart_interval', 300)
                    time_since_last_reply = current_time_check - last_reply_time
                    
                    # 自动重启条件：长时间无回复 且 有连续错误
                    should_restart = (time_since_last_reply >= restart_interval and consecutive_errors > 3)
                    
                    if should_restart:
                        add_log(f"🔄 已连续 {time_since_last_reply} 秒无回复消息且有 {consecutive_errors} 个连续错误，执行自动重启", 'warning')
                        
                        # 增强的重启机制
                        restart_success = False
                        restart_attempts = 0
                        max_restart_attempts = 3
                        
                        while not restart_success and restart_attempts < max_restart_attempts:
                            restart_attempts += 1
                            try:
                                add_log(f"尝试重启 ({restart_attempts}/{max_restart_attempts})", 'info')
                                
                                # 清理所有缓存和状态
                                message_cache.clear()
                                last_message_times.clear()
                                last_send_time = 0
                                followers_cache.clear()
                                welcome_sent_cache.clear()
                                last_follow_check = 0
                                unfollowers_cache.clear()
                                follow_history.clear()
                                
                                # 强制垃圾回收
                                import gc
                                gc.collect()
                                
                                # 等待一下让系统稳定
                                time.sleep(1)
                                
                                # 重新创建API对象，增加重试机制
                                api_created = False
                                for api_attempt in range(3):
                                    try:
                                        api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                                        # 测试API连接
                                        test_sessions = api.get_sessions()
                                        if test_sessions and test_sessions.get('code') == 0:
                                            api_created = True
                                            break
                                        else:
                                            add_log(f"API测试失败，尝试 {api_attempt + 1}/3", 'warning')
                                            time.sleep(0.2)  # 进一步缩短API测试失败等待时间
                                    except Exception as api_e:
                                        add_log(f"API创建失败 {api_attempt + 1}/3: {api_e}", 'warning')
                                        time.sleep(0.2)  # 进一步缩短API创建失败等待时间
                                
                                if not api_created:
                                    raise Exception("无法创建有效的API连接")
                                
                                # 获取用户信息，增加重试
                                my_uid = None
                                for uid_attempt in range(3):
                                    try:
                                        my_uid = api.get_my_uid()
                                        if my_uid:
                                            break
                                        else:
                                            add_log(f"获取用户信息失败，尝试 {uid_attempt + 1}/3", 'warning')
                                            time.sleep(0.1)  # 进一步缩短获取用户信息失败等待时间
                                    except Exception as uid_e:
                                        add_log(f"获取用户信息异常 {uid_attempt + 1}/3: {uid_e}", 'warning')
                                        time.sleep(0.1)  # 进一步缩短获取用户信息异常等待时间
                                
                                if not my_uid:
                                    raise Exception("无法获取用户信息，可能是登录状态失效")
                                
                                # 重新预编译规则
                                precompile_rules()
                                
                                # 重置时间戳
                                last_reply_time = current_time_check
                                last_cleanup = current_time_check
                                last_api_reset = current_time_check
                                last_heartbeat = current_time_check
                                
                                restart_success = True
                                add_log(f"✅ 系统重启成功 (用户UID: {my_uid})，继续监控", 'success')
                                
                            except Exception as e:
                                add_log(f"重启尝试 {restart_attempts} 失败: {e}", 'error')
                                if restart_attempts < max_restart_attempts:
                                    add_log(f"等待 {restart_attempts} 秒后重试", 'info')
                                    time.sleep(min(restart_attempts * 0.5, 2))  # 大幅缩短重启等待时间，最多2秒
                        
                        # 如果重启失败，停止监控
                        if not restart_success:
                            add_log("❌ 多次重启失败，停止监控。请检查网络连接和登录状态", 'error')
                            monitoring = False
                            break
                    
                    # 可配置循环间隔 - 实现快速响应
                    elapsed = time.time() - loop_start
                    check_interval = config.get('message_check_interval', 0.05)
                    sleep_time = max(0.01, check_interval - elapsed)
                    time.sleep(sleep_time)
                    
                except KeyboardInterrupt:
                    add_log("收到停止信号", 'warning')
                    monitoring = False
                    break
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    add_log(f"监控循环异常: {e}", 'error',
                           error_details=error_detail,
                           context='单账号监控循环',
                           account_name='')
                    logger.error(f"详细错误信息:\n{error_detail}")
                    error_count += 1
                    consecutive_errors += 1
                    
                    # 如果连续错误太多，执行完整的系统重置
                    if consecutive_errors > 5:
                        add_log(f"连续错误 {consecutive_errors} 次，执行系统重置", 'warning')
                        try:
                            # 清理所有缓存
                            message_cache.clear()
                            last_message_times.clear()
                            
                            # 强制垃圾回收
                            import gc
                            gc.collect()
                            
                            # 重新创建API对象
                            api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                            
                            # 测试API连接
                            test_uid = api.get_my_uid()
                            if test_uid:
                                add_log(f"系统重置成功，用户UID: {test_uid}", 'success')
                                consecutive_errors = 0
                                last_reply_time = int(time.time())  # 重置最后回复时间
                            else:
                                add_log("系统重置失败：无法获取用户信息", 'error')
                                if consecutive_errors > 15:
                                    add_log("连续错误超过15次，停止监控", 'error')
                                    monitoring = False
                                    break
                        except Exception as init_e:
                            add_log(f"系统重置失败: {init_e}", 'error')
                            if consecutive_errors > 15:
                                add_log("连续错误超过15次，停止监控", 'error')
                                monitoring = False
                                break
                        time.sleep(2)  # 重置后等待2秒
                    else:
                        time.sleep(1)  # 一般错误等待1秒
        
        except Exception as e:
            add_log(f"监控系统异常: {e}", 'error')
            retry_count += 1
            if retry_count < max_retries and monitoring:
                add_log(f"尝试重新启动监控系统 ({retry_count}/{max_retries})", 'warning')
                time.sleep(1)  # 大幅缩短监控系统重启等待时间
            else:
                break
    
    # 确保监控状态正确设置
    monitoring = False

# 获取应用根目录
def get_app_root():
    """获取应用根目录，确保跨平台兼容"""
    if hasattr(get_app_root, '_cached_root'):
        return get_app_root._cached_root
    
    # 尝试多种方式获取应用根目录
    possible_roots = [
        os.getcwd(),  # 当前工作目录
        os.path.dirname(os.path.abspath(__file__)),  # 脚本所在目录
        os.path.dirname(os.path.realpath(__file__))  # 脚本真实路径目录
    ]
    
    for root in possible_roots:
        index_path = os.path.join(root, 'index.html')
        if os.path.exists(index_path) and os.path.isfile(index_path):
            get_app_root._cached_root = root
            logger.info(f"应用根目录: {root}")
            return root
    
    # 如果都找不到，使用当前工作目录
    get_app_root._cached_root = os.getcwd()
    logger.warning(f"未找到index.html，使用默认目录: {get_app_root._cached_root}")
    return get_app_root._cached_root

# 路由定义
@app.route('/')
def index():
    """主页路由"""
    try:
        app_root = get_app_root()
        index_path = os.path.join(app_root, 'index.html')
        
        logger.info(f"尝试访问主页，根目录: {app_root}")
        logger.info(f"index.html路径: {index_path}")
        logger.info(f"文件是否存在: {os.path.exists(index_path)}")
        
        if os.path.exists(index_path) and os.path.isfile(index_path):
            return send_from_directory(app_root, 'index.html')
        else:
            error_msg = f"index.html not found in {app_root}"
            logger.error(error_msg)
            # 列出目录内容用于调试
            try:
                files = os.listdir(app_root)
                logger.info(f"目录内容: {files}")
                return f"{error_msg}<br>目录内容: {', '.join(files)}", 404
            except Exception as list_e:
                logger.error(f"无法列出目录内容: {list_e}")
                return error_msg, 404
                
    except Exception as e:
        logger.error(f"访问主页失败: {e}")
        return f"Error loading index.html: {str(e)}", 500

@app.route('/<path:filename>')
def static_files(filename):
    """静态文件服务路由"""
    try:
        # 安全检查
        if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            logger.warning(f"拒绝访问不安全路径: {filename}")
            return "Access denied", 403
        
        app_root = get_app_root()
        # 规范化文件名，兼容Linux和Windows
        safe_filename = os.path.normpath(filename)
        file_path = os.path.join(app_root, safe_filename)
        
        logger.debug(f"请求文件: {filename}, 完整路径: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.warning(f"文件不存在: {file_path}")
            return f"File not found: {filename}", 404
        
        # 检查是否为文件
        if not os.path.isfile(file_path):
            logger.warning(f"路径不是文件: {file_path}")
            return f"Not a file: {filename}", 404
        
        # 发送文件
        return send_from_directory(app_root, safe_filename)
        
    except Exception as e:
        logger.error(f"静态文件服务错误 {filename}: {e}")
        return f"Error serving file: {str(e)}", 500

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        config.update(data)
        save_config()
        add_log("私信系统配置已更新", 'success', system='message')
        return jsonify({'success': True})
    else:
        return jsonify(config)

@app.route('/api/rules', methods=['GET', 'POST'])
def handle_rules():
    global rules
    
    if request.method == 'POST':
        data = request.get_json()
        rules = data.get('rules', [])
        save_rules()
        precompile_rules()
        add_log("私信关键词规则已更新并预编译完成", 'success', system='message')
        return jsonify({'success': True})
    else:
        return jsonify({'rules': rules})

@app.route('/api/start', methods=['POST'])
def start_monitoring():
    global monitoring, monitor_thread, program_start_time
    
    # 检查配置
    if not config.get('sessdata') or not config.get('bili_jct'):
        return jsonify({'success': False, 'error': '请先配置登录信息'})
    
    # 强制重置状态，确保可以重新启动
    if monitor_thread and monitor_thread.is_alive():
        add_log("强制停止旧的监控线程", 'warning')
        monitoring = False
        monitor_thread.join(timeout=3)
        if monitor_thread.is_alive():
            add_log("旧线程未能正常停止，但继续启动新线程", 'warning')
    
    # 重置所有状态
    monitoring = False  # 先设为False，避免竞态条件
    monitor_thread = None
    
    # 清理全局状态
    global message_cache, last_message_times, last_send_time, followers_cache, last_follow_check, unfollowers_cache, follow_history
    message_cache = {}
    last_message_times = defaultdict(int)
    last_send_time = 0
    followers_cache = set()
    last_follow_check = 0
    unfollowers_cache = set()
    follow_history = {}
    
    # 重置程序启动时间（用于仅回复新消息功能）
    program_start_time = int(time.time())
    
    # 启动新的监控线程
    monitoring = True
    monitor_thread = threading.Thread(target=monitor_messages)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # 根据配置显示不同的启动消息
    if config.get('only_reply_new_messages', False):
        add_log("开始监控私信（仅回复新消息模式）", 'success', system='message')
    else:
        add_log("开始监控私信", 'success', system='message')
    
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
def stop_monitoring():
    global monitoring, monitor_thread
    
    # 强制停止，不管当前状态
    monitoring = False
    add_log("停止监控私信", 'warning', system='message')
    
    # 等待线程结束
    if monitor_thread and monitor_thread.is_alive():
        monitor_thread.join(timeout=3)
        if monitor_thread.is_alive():
            add_log("监控线程未能在3秒内停止，但状态已重置", 'warning', system='message')
    
    # 清理线程引用
    monitor_thread = None
    
    return jsonify({'success': True})

@app.route('/api/status')
def get_status():
    """获取系统状态 - 分离私信和评论监控状态"""
    global monitoring, monitor_thread, comment_monitoring, comment_monitor_thread
    
    # 检查私信监控实际状态，确保状态同步
    actual_monitoring = monitoring and monitor_thread and monitor_thread.is_alive()
    
    # 如果状态不一致，自动修正
    if monitoring and (not monitor_thread or not monitor_thread.is_alive()):
        monitoring = False
        monitor_thread = None
        add_log("检测到私信监控状态不一致，已自动修正", 'warning', system='message')
    
    # 检查评论监控实际状态
    actual_comment_monitoring = comment_monitoring and comment_monitor_thread and comment_monitor_thread.is_alive()
    
    # 如果评论监控状态不一致，自动修正
    if comment_monitoring and (not comment_monitor_thread or not comment_monitor_thread.is_alive()):
        comment_monitoring = False
        comment_monitor_thread = None
        add_log("检测到评论监控状态不一致，已自动修正", 'warning', system='comment')
    
    # 系统整体运行状态：只要有一个监控在运行就算运行中
    system_running = actual_monitoring or actual_comment_monitoring
    
    return jsonify({
        'message_monitoring': actual_monitoring,  # 私信监控状态
        'comment_monitoring': actual_comment_monitoring,  # 评论监控状态
        'system_running': system_running,  # 整体运行状态
        'message_rules_count': len(rules),  # 私信规则数量
        'comment_rules_count': len(comment_rules),  # 评论规则数量
        'message_config_set': bool(config.get('sessdata') and config.get('bili_jct')),  # 私信配置状态
        'comment_config_set': bool(comment_config.get('sessdata') and comment_config.get('bili_jct')),  # 评论配置状态
        # 保持向后兼容
        'monitoring': actual_monitoring,
        'rules_count': len(rules),
        'config_set': bool(config.get('sessdata') and config.get('bili_jct'))
    })
    
    return jsonify({
        'message_monitoring': actual_monitoring,  # 私信监控状态
        'comment_monitoring': actual_comment_monitoring,  # 评论监控状态
        'system_running': system_running,  # 整体运行状态
        'message_rules_count': len(rules),  # 私信规则数量
        'comment_rules_count': len(comment_rules),  # 评论规则数量
        'message_config_set': bool(config.get('sessdata') and config.get('bili_jct')),  # 私信配置状态
        'comment_config_set': bool(comment_config.get('sessdata') and comment_config.get('bili_jct')),  # 评论配置状态
        # 保持向后兼容
        'monitoring': actual_monitoring,
        'rules_count': len(rules),
        'config_set': bool(config.get('sessdata') and config.get('bili_jct'))
    })

@app.route('/api/logs', methods=['GET', 'DELETE'])
def handle_logs():
    """处理日志接口 - 支持分类获取"""
    global message_logs, comment_logs
    
    if request.method == 'GET':
        # 获取日志类型参数
        log_type = request.args.get('type', 'all')  # all, message, comment
        
        if log_type == 'message':
            logs_data = message_logs
        elif log_type == 'comment':
            logs_data = comment_logs
        else:  # all - 合并所有日志
            all_logs = []
            
            # 添加私信日志
            for log in message_logs:
                log_copy = log.copy()
                if 'system' not in log_copy:
                    log_copy['system'] = 'message'
                all_logs.append(log_copy)
            
            # 添加评论日志
            for log in comment_logs:
                log_copy = log.copy()
                if 'system' not in log_copy:
                    log_copy['system'] = 'comment'
                all_logs.append(log_copy)
            
            # 按时间排序
            all_logs.sort(key=lambda x: x['timestamp'])
            logs_data = all_logs
        
        return jsonify({'logs': logs_data, 'type': log_type})
    
    elif request.method == 'DELETE':
        # 清空指定类型日志
        log_type = request.args.get('type', 'all')
        
        if log_type == 'message':
            message_logs.clear()
            add_log("私信日志已被手动清空", 'info', system='message')
            message = '私信日志已清空'
        elif log_type == 'comment':
            comment_logs.clear()
            add_log("评论日志已被手动清空", 'info', system='comment')
            message = '评论日志已清空'
        else:  # all
            message_logs.clear()
            comment_logs.clear()
            message = '所有日志已清空'
        
        return jsonify({'success': True, 'message': message})

@app.route('/api/image-config', methods=['GET', 'POST'])
def handle_image_config():
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 更新图片回复配置
        if 'image_reply_enabled' in data:
            config['image_reply_enabled'] = data['image_reply_enabled']
        
        if 'image_folder_path' in data:
            folder_path = data['image_folder_path'].strip()
            if folder_path and not os.path.exists(folder_path):
                return jsonify({'success': False, 'error': '指定的图片文件夹不存在'})
            config['image_folder_path'] = folder_path
        
        save_config()
        add_log("图片回复配置已更新", 'success')
        return jsonify({'success': True})
    else:
        return jsonify({
            'image_reply_enabled': config.get('image_reply_enabled', False),
            'image_folder_path': config.get('image_folder_path', '')
        })

@app.route('/api/browse-images', methods=['POST'])
def browse_images():
    """浏览指定目录下的图片文件"""
    data = request.get_json()
    folder_path = data.get('folder_path', '').strip()
    
    # 如果没有提供路径，使用用户主目录
    if not folder_path:
        folder_path = os.path.expanduser('~')
    
    # 规范化路径，兼容Windows和Linux
    folder_path = os.path.normpath(os.path.abspath(folder_path))
    
    # 调试日志
    add_log(f"浏览路径: {folder_path}", 'debug')
    
    if not os.path.exists(folder_path):
        add_log(f"路径不存在: {folder_path}", 'error')
        return jsonify({'success': False, 'error': f'文件夹不存在: {folder_path}'})
    
    if not os.path.isdir(folder_path):
        add_log(f"路径不是文件夹: {folder_path}", 'error')
        return jsonify({'success': False, 'error': '路径不是文件夹'})
    
    try:
        # 支持的图片格式
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        
        items = []
        
        # 添加上级目录选项（除非是根目录）
        parent_dir = os.path.dirname(folder_path)
        if parent_dir != folder_path:  # 不是根目录
            items.append({
                'name': '..',
                'type': 'directory',
                'path': os.path.normpath(parent_dir)
            })
        
        # 列出当前目录内容
        try:
            for item in sorted(os.listdir(folder_path)):
                item_path = os.path.normpath(os.path.join(folder_path, item))
                
                try:
                    if os.path.isdir(item_path):
                        items.append({
                            'name': item,
                            'type': 'directory',
                            'path': item_path
                        })
                    elif os.path.isfile(item_path):
                        ext = os.path.splitext(item.lower())[1]
                        if ext in image_extensions:
                            # 获取文件大小
                            size = os.path.getsize(item_path)
                            size_str = format_file_size(size)
                            
                            items.append({
                                'name': item,
                                'type': 'image',
                                'path': item_path,
                                'size': size_str,
                                'extension': ext[1:].upper()
                            })
                except (OSError, IOError) as e:
                    # 跳过无法访问的文件/文件夹
                    add_log(f"跳过无法访问的项目 {item}: {e}", 'warning')
                    continue
        except (OSError, IOError) as e:
            add_log(f"读取目录内容失败 {folder_path}: {e}", 'error')
            return jsonify({'success': False, 'error': f'读取目录失败: {str(e)}'})
        
        return jsonify({
            'success': True,
            'current_path': folder_path,
            'items': items
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'读取文件夹失败: {str(e)}'})

def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

@app.route('/api/get-home-directory', methods=['GET'])
def get_home_directory():
    """获取用户主目录路径"""
    try:
        home_dir = os.path.normpath(os.path.expanduser('~'))
        # 常用的图片目录
        common_dirs = []
        
        # Windows系统
        if os.name == 'nt':
            pictures_dir = os.path.normpath(os.path.join(home_dir, 'Pictures'))
            desktop_dir = os.path.normpath(os.path.join(home_dir, 'Desktop'))
            if os.path.exists(pictures_dir):
                common_dirs.append({'name': '图片', 'path': pictures_dir})
            if os.path.exists(desktop_dir):
                common_dirs.append({'name': '桌面', 'path': desktop_dir})
        else:
            # Linux/Mac系统
            pictures_dir = os.path.normpath(os.path.join(home_dir, 'Pictures'))
            desktop_dir = os.path.normpath(os.path.join(home_dir, 'Desktop'))
            if os.path.exists(pictures_dir):
                common_dirs.append({'name': 'Pictures', 'path': pictures_dir})
            if os.path.exists(desktop_dir):
                common_dirs.append({'name': 'Desktop', 'path': desktop_dir})
        
        add_log(f"获取主目录成功: {home_dir}", 'debug')
        
        return jsonify({
            'success': True,
            'home_directory': home_dir,
            'common_directories': common_dirs
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'获取主目录失败: {str(e)}'})

@app.route('/api/follow-reply-config', methods=['GET', 'POST'])
def handle_follow_reply_config():
    """处理关注后回复配置"""
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 更新关注后回复配置
        if 'follow_reply_enabled' in data:
            config['follow_reply_enabled'] = data['follow_reply_enabled']
        
        if 'follow_reply_message' in data:
            config['follow_reply_message'] = data['follow_reply_message'].strip()
        
        if 'follow_reply_type' in data:
            reply_type = data['follow_reply_type']
            if reply_type in ['text', 'image']:
                config['follow_reply_type'] = reply_type
        
        if 'follow_reply_image' in data:
            image_path = data['follow_reply_image'].strip()
            if image_path and not os.path.exists(image_path):
                return jsonify({'success': False, 'error': '指定的图片文件不存在'})
            config['follow_reply_image'] = image_path
        
        save_config()
        add_log("关注后回复配置已更新", 'success')
        return jsonify({'success': True})
    else:
        return jsonify({
            'follow_reply_enabled': config.get('follow_reply_enabled', False),
            'follow_reply_message': config.get('follow_reply_message', '感谢您的关注！欢迎来到我的频道~'),
            'follow_reply_type': config.get('follow_reply_type', 'text'),
            'follow_reply_image': config.get('follow_reply_image', '')
        })

@app.route('/api/unfollow-reply-config', methods=['GET', 'POST'])
def handle_unfollow_reply_config():
    """处理取消关注回复配置"""
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 更新取消关注回复配置
        if 'unfollow_reply_enabled' in data:
            config['unfollow_reply_enabled'] = data['unfollow_reply_enabled']
        
        if 'unfollow_reply_message' in data:
            config['unfollow_reply_message'] = data['unfollow_reply_message'].strip()
        
        if 'unfollow_reply_type' in data:
            reply_type = data['unfollow_reply_type']
            if reply_type in ['text', 'image']:
                config['unfollow_reply_type'] = reply_type
        
        if 'unfollow_reply_image' in data:
            image_path = data['unfollow_reply_image'].strip()
            if image_path and not os.path.exists(image_path):
                return jsonify({'success': False, 'error': '指定的图片文件不存在'})
            config['unfollow_reply_image'] = image_path
        
        save_config()
        add_log("取消关注回复配置已更新", 'success')
        return jsonify({'success': True})
    else:
        # GET请求，返回当前配置
        return jsonify({
            'unfollow_reply_enabled': config.get('unfollow_reply_enabled', False),
            'unfollow_reply_message': config.get('unfollow_reply_message', '很遗憾看到您取消了关注，希望我们还有机会再见！'),
            'unfollow_reply_type': config.get('unfollow_reply_type', 'text'),
            'unfollow_reply_image': config.get('unfollow_reply_image', '')
        })

@app.route('/api/test-follow-detection', methods=['POST'])
def test_follow_detection():
    """测试关注者检测功能"""
    try:
        if not config.get('sessdata') or not config.get('bili_jct'):
            return jsonify({'success': False, 'error': '请先配置登录信息'})
        
        api = BilibiliAPI(config['sessdata'], config['bili_jct'])
        
        # 测试获取关注者列表
        recent_followers = api.get_recent_followers(limit=10)
        
        if recent_followers:
            followers_info = []
            for follower in recent_followers[:5]:  # 只显示前5个
                followers_info.append({
                    'uname': follower.get('uname', 'Unknown'),
                    'mid': follower.get('mid'),
                    'mtime': follower.get('mtime', 0)
                })
            
            add_log(f"测试获取关注者成功，共 {len(recent_followers)} 个最近关注者", 'success')
            return jsonify({
                'success': True,
                'message': f'成功获取到 {len(recent_followers)} 个最近关注者',
                'followers': followers_info
            })
        else:
            add_log("测试获取关注者失败或无关注者", 'warning')
            return jsonify({
                'success': False,
                'error': '无法获取关注者列表，请检查登录状态和权限设置'
            })
            
    except Exception as e:
        add_log(f"测试关注者检测异常: {e}", 'error')
        return jsonify({'success': False, 'error': f'测试失败: {str(e)}'})

@app.route('/api/new-message-config', methods=['GET', 'POST'])
def handle_new_message_config():
    """处理仅回复新消息配置"""
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 更新仅回复新消息配置
        if 'only_reply_new_messages' in data:
            old_value = config.get('only_reply_new_messages', False)
            new_value = data['only_reply_new_messages']
            config['only_reply_new_messages'] = new_value
            
            # 记录配置变更
            if old_value != new_value:
                if new_value:
                    add_log("已启用仅回复新消息模式，只会回复程序启动后的消息", 'success')
                else:
                    add_log("已关闭仅回复新消息模式，会回复所有未处理的消息", 'success')
        
        # 更新单用户最大回复次数配置
        if 'max_replies_per_user' in data:
            old_max = config.get('max_replies_per_user', 3)
            new_max = data['max_replies_per_user']
            
            # 验证输入值
            if isinstance(new_max, int) and 1 <= new_max <= 100:
                config['max_replies_per_user'] = new_max
                
                # 记录配置变更
                if old_max != new_max:
                    add_log(f"单用户最大回复次数已设置为 {new_max} 次", 'success')
                    
                    # 如果减少了限制，清理现有计数
                    if new_max < old_max:
                        # 重置所有用户的回复计数（清空JSON文件），让新配置立即生效
                        save_user_reply_stats({})
                        add_log("已清理用户回复计数，新配置立即生效", 'info')
            else:
                return jsonify({'success': False, 'error': '单用户最大回复次数必须在1-100之间'})
        
        save_config()
        add_log("消息设置配置已更新", 'success')
        return jsonify({'success': True})
    else:
        # GET请求，返回当前配置
        return jsonify({
            'only_reply_new_messages': config.get('only_reply_new_messages', False),
            'max_replies_per_user': config.get('max_replies_per_user', 3)
        })

@app.route('/api/follow-check-interval-config', methods=['GET', 'POST'])
def handle_follow_check_interval_config():
    """处理关注者检查间隔配置"""
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 更新关注者检查间隔配置
        if 'follow_check_interval' in data:
            interval = data['follow_check_interval']
            
            # 验证间隔值的合理性
            try:
                interval = int(interval)
                if interval < 300:
                    return jsonify({'success': False, 'error': '检查间隔不能少于300秒（5分钟），避免触发B站风控'})
                elif interval > 3600:
                    return jsonify({'success': False, 'error': '检查间隔不能超过3600秒（1小时）'})
                
                old_value = config.get('follow_check_interval', 300)
                config['follow_check_interval'] = interval
                
                # 记录配置变更和风控提示
                if old_value != interval:
                    add_log(f"关注者检查间隔已更新: {old_value}秒 -> {interval}秒", 'success')
                    if interval < 600:
                        add_log(f"⚠️ 提示：检查间隔设置为{interval}秒（{interval//60}分钟），建议设置为10分钟以上更安全", 'warning')
                    else:
                        add_log(f"✅ 检查间隔设置为{interval}秒（{interval//60}分钟），有助于避免触发B站风控", 'success')
                
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '检查间隔必须是有效的数字'})
        
        save_config()
        add_log("关注者检查间隔配置已更新", 'success')
        return jsonify({'success': True})
    else:
        # GET请求，返回当前配置
        return jsonify({
            'follow_check_interval': config.get('follow_check_interval', 300)
        })

@app.route('/api/timing-config', methods=['GET', 'POST'])
def handle_timing_config():
    """处理时间间隔配置"""
    global config
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 验证和更新消息监测间隔
        if 'message_check_interval' in data:
            try:
                interval = float(data['message_check_interval'])
                if interval < 0.01:
                    return jsonify({'success': False, 'error': '消息监测间隔不能少于0.01秒'})
                elif interval > 5.0:
                    return jsonify({'success': False, 'error': '消息监测间隔不能超过5秒'})
                
                old_value = config.get('message_check_interval', 0.05)
                config['message_check_interval'] = interval
                
                if old_value != interval:
                    add_log(f"消息监测间隔已更新: {old_value}秒 -> {interval}秒", 'success')
                    
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '消息监测间隔必须是有效的数字'})
        
        # 验证和更新发送等待间隔
        if 'send_delay_interval' in data:
            try:
                interval = float(data['send_delay_interval'])
                if interval < 0.1:
                    return jsonify({'success': False, 'error': '发送等待间隔不能少于0.1秒'})
                elif interval > 10.0:
                    return jsonify({'success': False, 'error': '发送等待间隔不能超过10秒'})
                
                old_value = config.get('send_delay_interval', 1.0)
                config['send_delay_interval'] = interval
                
                if old_value != interval:
                    add_log(f"发送等待间隔已更新: {old_value}秒 -> {interval}秒", 'success')
                    if interval < 1.0:
                        add_log(f"⚠️ 警告：发送间隔设置为{interval}秒，可能触发B站风控系统", 'warning')
                    
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '发送等待间隔必须是有效的数字'})
        
        # 验证和更新自动重启间隔
        if 'auto_restart_interval' in data:
            try:
                interval = int(data['auto_restart_interval'])
                if interval < 60:
                    return jsonify({'success': False, 'error': '自动重启间隔不能少于60秒'})
                elif interval > 3600:
                    return jsonify({'success': False, 'error': '自动重启间隔不能超过3600秒（1小时）'})
                
                old_value = config.get('auto_restart_interval', 300)
                config['auto_restart_interval'] = interval
                
                if old_value != interval:
                    add_log(f"自动重启间隔已更新: {old_value}秒 -> {interval}秒", 'success')
                    
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '自动重启间隔必须是有效的数字'})
        
        save_config()
        add_log("时间间隔配置已更新", 'success')
        return jsonify({'success': True})
    else:
        # GET请求，返回当前配置
        return jsonify({
            'message_check_interval': config.get('message_check_interval', 0.05),
            'send_delay_interval': config.get('send_delay_interval', 1.0),
            'auto_restart_interval': config.get('auto_restart_interval', 300)
        })

@app.route('/api/accounts', methods=['GET', 'POST', 'DELETE'])
def handle_accounts():
    """处理多账号管理"""
    global config
    
    if request.method == 'GET':
        # 返回账号列表（隐藏敏感信息）
        accounts = config.get('accounts', [])
        safe_accounts = []
        for acc in accounts:
            safe_accounts.append({
                'name': acc.get('name', ''),
                'enabled': acc.get('enabled', True),
                'sessdata_preview': acc.get('sessdata', '')[:10] + '...' if acc.get('sessdata') else '',
                'uid': acc.get('uid', '')
            })
        return jsonify({
            'success': True,
            'accounts': safe_accounts,
            'multi_account_mode': config.get('multi_account_mode', False)
        })
    
    elif request.method == 'POST':
        data = request.get_json()
        action = data.get('action')
        
        if action == 'add':
            # 添加新账号
            name = data.get('name', '').strip()
            sessdata = data.get('sessdata', '').strip()
            bili_jct = data.get('bili_jct', '').strip()
            email = data.get('email', '').strip()
            
            if not name:
                return jsonify({'success': False, 'error': '账号名称不能为空'})
            if not sessdata or not bili_jct:
                return jsonify({'success': False, 'error': '请填写完整的登录信息'})
            
            # 检查账号名是否重复
            accounts = config.get('accounts', [])
            if any(acc.get('name') == name for acc in accounts):
                return jsonify({'success': False, 'error': f'账号名称 "{name}" 已存在'})
            
            # 验证账号有效性
            try:
                api = BilibiliAPI(sessdata, bili_jct)
                uid = api.get_my_uid()
                if not uid:
                    return jsonify({'success': False, 'error': '无法获取用户信息，请检查登录凭证是否正确'})
                
                # 添加账号
                new_account = {
                    'name': name,
                    'sessdata': sessdata,
                    'bili_jct': bili_jct,
                    'uid': uid,
                    'email': email,
                    'enabled': True,
                    'created_at': datetime.now().isoformat()
                }
                accounts.append(new_account)
                config['accounts'] = accounts
                save_config()
                
                add_log(f"✅ 成功添加账号: {name} (UID: {uid})", 'success')
                return jsonify({'success': True, 'message': f'成功添加账号: {name}', 'uid': uid})
                
            except Exception as e:
                return jsonify({'success': False, 'error': f'验证账号失败: {str(e)}'})
        
        elif action == 'update':
            # 更新账号状态
            name = data.get('name', '').strip()
            enabled = data.get('enabled', True)
            
            accounts = config.get('accounts', [])
            found = False
            for acc in accounts:
                if acc.get('name') == name:
                    acc['enabled'] = enabled
                    found = True
                    break
            
            if not found:
                return jsonify({'success': False, 'error': f'账号 "{name}" 不存在'})
            
            config['accounts'] = accounts
            save_config()
            
            status = "启用" if enabled else "禁用"
            add_log(f"账号 {name} 已{status}", 'info')
            return jsonify({'success': True, 'message': f'账号已{status}'})
        
        elif action == 'toggle_mode':
            # 切换多账号模式
            multi_mode = data.get('enabled', False)
            config['multi_account_mode'] = multi_mode
            save_config()
            
            mode_text = "多账号模式" if multi_mode else "单账号模式"
            add_log(f"已切换到{mode_text}", 'info')
            return jsonify({'success': True, 'message': f'已切换到{mode_text}'})
        
        else:
            return jsonify({'success': False, 'error': '未知操作'})
    
    elif request.method == 'DELETE':
        # 删除账号
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'error': '账号名称不能为空'})
        
        accounts = config.get('accounts', [])
        original_count = len(accounts)
        accounts = [acc for acc in accounts if acc.get('name') != name]
        
        if len(accounts) == original_count:
            return jsonify({'success': False, 'error': f'账号 "{name}" 不存在'})
        
        config['accounts'] = accounts
        save_config()
        
        add_log(f"已删除账号: {name}", 'warning')
        return jsonify({'success': True, 'message': f'已删除账号: {name}'})

if __name__ == '__main__':
    # 启动时加载配置和规则
    load_config()
@app.route('/api/preview-image', methods=['POST'])
def preview_image():
    """获取图片预览数据"""
    try:
        data = request.get_json()
        image_path = data.get('image_path', '').strip()
        
        if not image_path:
            return jsonify({'success': False, 'error': '图片路径为空'})
        
        # 规范化路径
        image_path = os.path.normpath(image_path)
        
        if not os.path.exists(image_path):
            return jsonify({'success': False, 'error': '图片文件不存在'})
        
        if not os.path.isfile(image_path):
            return jsonify({'success': False, 'error': '路径不是文件'})
        
        # 检查文件大小（限制预览大小为5MB）
        file_size = os.path.getsize(image_path)
        if file_size > 5 * 1024 * 1024:
            return jsonify({
                'success': False, 
                'error': f'文件过大 ({file_size / 1024 / 1024:.1f}MB)，无法预览'
            })
        
        # 检查是否为图片文件
        mime_type = mimetypes.guess_type(image_path)[0]
        if not mime_type or not mime_type.startswith('image/'):
            return jsonify({'success': False, 'error': '不是有效的图片文件'})
        
        # 读取图片数据并转换为base64
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # 格式化文件大小
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / 1024 / 1024:.1f} MB"
        
        return jsonify({
            'success': True,
            'image_data': base64_data,
            'mime_type': mime_type,
            'file_size': size_str,
            'file_name': os.path.basename(image_path)
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'预览失败: {str(e)}'})

@app.route('/api/import-config', methods=['POST'])
def import_config():
    """导入完整配置包"""
    global rules
    try:
        init_config_paths()
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        # 检查文件类型
        if not file.filename.lower().endswith('.json'):
            return jsonify({'success': False, 'error': '只支持JSON格式文件'})
        
        # 检查文件大小 (5MB)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'success': False, 'error': '文件大小不能超过5MB'})
        
        # 读取文件内容
        try:
            content = file.read().decode('utf-8')
            imported_data = json.loads(content)
        except UnicodeDecodeError:
            return jsonify({'success': False, 'error': '文件编码错误，请使用UTF-8编码'})
        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'error': f'JSON格式错误: {str(e)}'})
        
        # 获取导入模式
        import_mode = request.form.get('import_mode', 'replace')
        
        # 统一处理：优先处理完整配置文件格式，兼容旧版本仅规则格式
        imported_config = {}
        imported_rules = []
        
        if 'config' in imported_data and 'rules' in imported_data:
            # 完整配置文件格式
            imported_config = imported_data.get('config', {})
            imported_rules = imported_data.get('rules', [])
        elif isinstance(imported_data, list):
            # 兼容旧版本：仅关键词规则文件
            imported_rules = imported_data
        else:
            return jsonify({'success': False, 'error': '不支持的文件格式，请使用包含config和rules的完整配置文件'})
        
        # 验证和更新配置
        global config, rules
        
        # 备份当前配置
        backup_config = config.copy()
        backup_rules = rules.copy()
        
        try:
            # 更新配置（如果有的话）
            config_updated = False
            if imported_config:
                if import_mode == 'replace':
                    # 只更新存在的配置项，保持默认值
                    for key, value in imported_config.items():
                        if key in config:
                            config[key] = value
                            config_updated = True
                else:  # append模式对配置也是替换
                    for key, value in imported_config.items():
                        if key in config:
                            config[key] = value
                            config_updated = True
            
            # 处理规则
            valid_rules = []
            invalid_count = 0
            
            for i, rule in enumerate(imported_rules):
                if not isinstance(rule, dict):
                    invalid_count += 1
                    continue
                
                # 检查必需字段
                if 'keyword' not in rule or not rule.get('keyword', '').strip():
                    invalid_count += 1
                    continue
                
                # 标准化规则格式
                standardized_rule = {
                    'id': rule.get('id', int(time.time() * 1000) + i),
                    'name': rule.get('name', f'导入规则{i+1}'),
                    'keyword': rule.get('keyword', '').strip(),
                    'reply': rule.get('reply', ''),
                    'reply_type': rule.get('reply_type', 'text'),
                    'reply_image': rule.get('reply_image', ''),
                    'enabled': rule.get('enabled', True),
                    'use_regex': rule.get('use_regex', False),
                    'created_at': rule.get('created_at', datetime.now().isoformat())
                }
                valid_rules.append(standardized_rule)
            
            # 更新规则
            if import_mode == 'replace':
                rules = valid_rules
                rules_message = f'替换导入 {len(valid_rules)} 条规则'
            else:  # append
                existing_keywords = {rule['keyword'] for rule in rules}
                new_rules = [rule for rule in valid_rules if rule['keyword'] not in existing_keywords]
                rules.extend(new_rules)
                rules_message = f'追加导入 {len(new_rules)} 条新规则'
            
            # 保存配置和规则
            if config_updated:
                save_config()
            save_rules()
            precompile_rules()
            
            # 记录日志
            success_msg = f"成功导入配置包: {rules_message}"
            if config_updated:
                success_msg += "，配置项已更新"
            if invalid_count > 0:
                success_msg += f"，跳过 {invalid_count} 条无效规则"
            
            add_log(success_msg, 'success')
            
            return jsonify({
                'success': True,
                'message': success_msg,
                'imported_rules': len(valid_rules),
                'invalid_count': invalid_count,
                'total_rules': len(rules),
                'config_updated': config_updated
            })
            
        except Exception as e:
            # 恢复备份
            config = backup_config
            rules = backup_rules
            raise e
        

        
    except Exception as e:
        error_msg = f"导入失败: {str(e)}"
        add_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/validate-config-file', methods=['POST'])
def validate_config_file():
    """验证配置文件格式"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        # 检查文件类型
        if not file.filename.lower().endswith('.json'):
            return jsonify({'success': False, 'error': '只支持JSON格式文件'})
        
        # 检查文件大小
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'success': False, 'error': '文件大小不能超过5MB'})
        
        # 读取文件内容
        try:
            content = file.read().decode('utf-8')
            data = json.loads(content)
        except UnicodeDecodeError:
            return jsonify({'success': False, 'error': '文件编码错误，请使用UTF-8编码'})
        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'error': f'JSON格式错误: {str(e)}'})
        
        # 统一验证文件格式：优先支持完整配置格式，兼容旧版本
        config_data = {}
        rules_data = []
        file_type = 'unknown'
        
        if 'config' in data and 'rules' in data:
            # 完整配置文件格式（推荐）
            config_data = data.get('config', {})
            rules_data = data.get('rules', [])
            file_type = 'complete_config'
        elif isinstance(data, list):
            # 兼容旧版本：仅关键词规则文件
            rules_data = data
            file_type = 'rules_only'
        else:
            return jsonify({'success': False, 'error': '不支持的文件格式，推荐使用包含config和rules的完整配置文件'})
        
        # 验证配置项
        valid_config_keys = []
        if config_data:
            for key in config_data.keys():
                if key in config:  # 检查是否是有效的配置项
                    valid_config_keys.append(key)
        
        # 验证规则
        valid_rules = 0
        invalid_rules = 0
        sample_rules = []
        
        for rule in rules_data[:5]:  # 只显示前5条作为示例
            if isinstance(rule, dict) and 'keyword' in rule and rule.get('keyword', '').strip():
                valid_rules += 1
                sample_rules.append({
                    'name': rule.get('name', '未命名'),
                    'keyword': rule.get('keyword', ''),
                    'reply': rule.get('reply', '')[:50] + ('...' if len(rule.get('reply', '')) > 50 else '')
                })
            else:
                invalid_rules += 1
        
        # 统计剩余规则
        for rule in rules_data[5:]:
            if isinstance(rule, dict) and 'keyword' in rule and rule.get('keyword', '').strip():
                valid_rules += 1
            else:
                invalid_rules += 1
        
        return jsonify({
            'success': True,
            'file_type': file_type,
            'file_size': f"{file_size / 1024:.1f} KB",
            'config_items': len(valid_config_keys),
            'valid_config_keys': valid_config_keys,
            'total_rules': len(rules_data),
            'valid_rules': valid_rules,
            'invalid_rules': invalid_rules,
            'sample_rules': sample_rules
        })
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'验证失败: {str(e)}'})

@app.route('/api/export-config', methods=['GET'])
def export_config():
    """导出完整配置包（包含config.json和keywords.json）"""
    try:
        init_config_paths()
        
        # 创建export目录
        app_root = get_app_root()
        export_dir = os.path.join(app_root, 'export')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 准备配置数据
        config_data = {
            'version': '1.0',
            'export_time': datetime.now().isoformat(),
            'app_name': 'BiliGo',
            'config': config.copy(),
            'rules': rules.copy()
        }
        
        # 导出文件路径
        export_filename = f'biligo_config_{timestamp}.json'
        export_path = os.path.join(export_dir, export_filename)
        
        # 写入文件
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        add_log(f'导出完整配置: {len(rules)} 条规则, 配置文件已保存到 export/{export_filename}', 'success')
        
        # 返回文件下载
        return send_from_directory(
            export_dir, 
            export_filename,
            as_attachment=True,
            download_name=export_filename,
            mimetype='application/json'
        )
        
    except Exception as e:
        error_msg = f"导出配置失败: {str(e)}"
        add_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/export-keywords', methods=['GET'])
def export_keywords():
    """导出完整配置包（包含config和keywords，统一格式）"""
    try:
        init_config_paths()
        
        # 创建export目录
        app_root = get_app_root()
        export_dir = os.path.join(app_root, 'export')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 准备配置数据（统一格式：包含config和keywords）
        config_data = {
            'version': '1.0',
            'export_time': datetime.now().isoformat(),
            'app_name': 'BiliGo',
            'config': config.copy(),
            'rules': rules.copy()
        }
        
        # 导出文件路径
        export_filename = f'biligo_config_{timestamp}.json'
        export_path = os.path.join(export_dir, export_filename)
        
        # 写入文件
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        add_log(f'导出完整配置: {len(rules)} 条规则和配置项，文件已保存到 export/{export_filename}', 'success')
        
        # 返回文件下载
        return send_from_directory(
            export_dir, 
            export_filename,
            as_attachment=True,
            download_name=export_filename,
            mimetype='application/json'
        )
        
    except Exception as e:
        error_msg = f"导出失败: {str(e)}"
        add_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/validate-keywords-file', methods=['POST'])
def validate_keywords_file():
    """验证配置文件格式（统一使用validate-config-file接口）"""
    # 重定向到统一的配置文件验证接口
    return validate_config_file()

# ==================== 评论回复系统 API ====================

# 评论回复系统全局变量
comment_config = {
    'sessdata': '',
    'bili_jct': '',
    'default_comment_reply_enabled': False,
    'default_comment_reply_message': '感谢您的评论！',
    'default_comment_reply_type': 'text',
    'default_comment_reply_image': '',
    'comment_check_interval': 30,
    'max_videos_to_check': 20,  # 检查的最大视频数量
    'comments_per_video': 10,   # 每个视频获取的评论数量
    'comment_send_delay': 2.0,
    'only_reply_new_comments': True
}

comment_rules = []
comment_monitoring = False
comment_monitor_thread = None
comment_logs = []  # 评论系统独立日志
comment_cache = {}
comment_last_send_time = 0
comment_program_start_time = int(time.time())

# 评论回复配置文件路径
COMMENT_CONFIG_FILE = None
COMMENT_RULES_FILE = None

def init_comment_config_paths():
    """初始化评论回复配置文件路径"""
    global COMMENT_CONFIG_FILE, COMMENT_RULES_FILE
    if COMMENT_CONFIG_FILE is None:
        COMMENT_CONFIG_FILE = get_config_file_path('comment_config.json')
    if COMMENT_RULES_FILE is None:
        COMMENT_RULES_FILE = get_config_file_path('comment_rules.json')

def load_comment_config():
    """加载评论回复系统配置"""
    global comment_config
    init_comment_config_paths()
    
    try:
        if os.path.exists(COMMENT_CONFIG_FILE):
            with open(COMMENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                comment_config.update(loaded_config)
            logger.info(f"成功加载评论回复配置: {COMMENT_CONFIG_FILE}")
        else:
            logger.info(f"评论回复配置文件不存在，使用默认配置: {COMMENT_CONFIG_FILE}")
    except Exception as e:
        logger.error(f"加载评论回复配置失败: {e}")
        add_log(f"加载评论回复配置失败: {e}", 'error', system='comment')

def save_comment_config():
    """保存评论回复系统配置"""
    init_comment_config_paths()
    
    try:
        with open(COMMENT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(comment_config, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存评论回复配置: {COMMENT_CONFIG_FILE}")
    except Exception as e:
        logger.error(f"保存评论回复配置失败: {e}")
        add_log(f"保存评论回复配置失败: {e}", 'error', system='comment')

def load_comment_rules():
    """加载评论回复规则"""
    global comment_rules
    init_comment_config_paths()
    
    try:
        if os.path.exists(COMMENT_RULES_FILE):
            with open(COMMENT_RULES_FILE, 'r', encoding='utf-8') as f:
                comment_rules = json.load(f)
    except Exception as e:
        logger.error(f"加载评论回复规则失败: {e}")
        comment_rules = []

def save_comment_rules():
    """保存评论回复规则"""
    init_comment_config_paths()
    
    try:
        with open(COMMENT_RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(comment_rules, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存评论回复规则失败: {e}")

def add_comment_log(message, log_type='info'):
    """添加评论回复日志"""
    # 使用统一的日志系统，设置system='comment'
    add_log(message, log_type, system='comment')

class CommentAPI:
    """评论回复API类"""
    def __init__(self, sessdata, bili_jct):
        self.sessdata = sessdata
        self.bili_jct = bili_jct
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Cookie': f'SESSDATA={sessdata}; bili_jct={bili_jct}',
            'Referer': 'https://www.bilibili.com/'
        })
    
    def get_my_uid(self):
        """获取当前用户UID"""
        try:
            url = 'https://api.bilibili.com/x/web-interface/nav'
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return data.get('data', {}).get('mid')
            return None
        except Exception as e:
            add_comment_log(f"获取用户UID失败: {e}", 'error')
            return None
    
    def get_user_videos(self, uid, page=1, page_size=30):
        """获取用户视频列表"""
        try:
            url = 'https://api.bilibili.com/x/space/arc/search'
            params = {
                'mid': uid,
                'pn': page,
                'ps': page_size,
                'order': 'pubdate'
            }
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return data.get('data', {}).get('list', {}).get('vlist', [])
            return []
        except Exception as e:
            add_comment_log(f"获取视频列表失败: {e}", 'error')
            return []
    
    def get_video_comments(self, oid, page=1, page_size=20):
        """获取视频评论"""
        try:
            url = 'https://api.bilibili.com/x/v2/reply'
            params = {
                'type': 1,
                'oid': oid,
                'pn': page,
                'ps': page_size,
                'sort': 2  # 按时间排序
            }
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return data.get('data', {}).get('replies', [])
            return []
        except Exception as e:
            add_comment_log(f"获取评论失败: {e}", 'error')
            return []
    
    def get_all_comments(self, uid, max_videos=20, comments_per_video=10):
        """获取用户所有视频的评论（不分视频）"""
        all_comments = []
        try:
            # 获取用户最新视频
            videos = self.get_user_videos(uid, page=1, page_size=max_videos)
            add_comment_log(f"获取到 {len(videos)} 个视频，开始获取所有评论", 'info')
            
            for video in videos:
                video_id = video.get('aid')
                video_title = video.get('title', '未知视频')
                
                # 获取该视频的评论
                comments = self.get_video_comments(video_id, page=1, page_size=comments_per_video)
                
                # 为每个评论添加视频信息
                for comment in comments:
                    comment['video_id'] = video_id
                    comment['video_title'] = video_title
                    all_comments.append(comment)
            
            # 按评论时间排序（最新的在前）
            all_comments.sort(key=lambda x: x.get('ctime', 0), reverse=True)
            add_comment_log(f"总共获取到 {len(all_comments)} 条评论", 'info')
            
            return all_comments
        except Exception as e:
            add_comment_log(f"获取所有评论失败: {e}", 'error')
            return []
    
    def reply_comment(self, oid, root_rpid, message="", image_path=""):
        """回复评论"""
        global comment_last_send_time
        
        current_time = time.time()
        send_interval = comment_config.get('comment_send_delay', 2.0)
        
        if current_time - comment_last_send_time < send_interval:
            wait_time = send_interval - (current_time - comment_last_send_time)
            add_comment_log(f"发送间隔控制，等待 {wait_time:.1f} 秒", 'info')
            time.sleep(wait_time)
        
        try:
            url = 'https://api.bilibili.com/x/v2/reply/add'
            
            data = {
                'type': 1,
                'oid': oid,
                'root': root_rpid,
                'parent': root_rpid,
                'message': message,
                'csrf': self.bili_jct
            }
            
            # 如果是图片回复
            if image_path and os.path.exists(image_path):
                # 这里需要实现图片上传逻辑，暂时使用文字回复
                data['message'] = message or '[图片回复]'
            
            response = self.session.post(url, data=data, timeout=10)
            comment_last_send_time = time.time()
            
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 0:
                    add_comment_log(f"评论回复成功", 'success')
                    return True
                else:
                    add_comment_log(f"评论回复失败: {result.get('message', '未知错误')}", 'error')
                    return False
            else:
                add_comment_log(f"评论回复请求失败: HTTP {response.status_code}", 'error')
                return False
                
        except Exception as e:
            add_comment_log(f"评论回复异常: {e}", 'error')
            comment_last_send_time = time.time()
            return False

def comment_monitor_worker():
    """评论监控工作线程 - 完全独立的评论系统"""
    global comment_monitoring
    
    add_comment_log("开始监控评论回复", 'info')
    
    while comment_monitoring:
        try:
            # 使用独立的评论配置，不依赖私信配置
            if not comment_config.get('sessdata') or not comment_config.get('bili_jct'):
                add_comment_log("评论系统登录配置不完整，停止监控", 'error')
                comment_monitoring = False
                break
            
            # 使用评论系统独立的API实例
            api = CommentAPI(comment_config['sessdata'], comment_config['bili_jct'])
            my_uid = api.get_my_uid()
            
            if not my_uid:
                add_comment_log("获取评论系统用户信息失败，请检查登录配置", 'error')
                # 不要立即退出，等待下次检查
                time.sleep(30)
                continue
            
            # 获取所有评论（不分视频） - 使用评论系统独立配置
            max_videos = comment_config.get('max_videos_to_check', 20)
            comments_per_video = comment_config.get('comments_per_video', 10)
            all_comments = api.get_all_comments(my_uid, max_videos, comments_per_video)
            
            if not all_comments:
                add_comment_log("没有找到评论，等待下次检查", 'info')
                # 使用评论系统独立的检查间隔
                time.sleep(comment_config.get('comment_check_interval', 30))
                continue
            
            for comment in all_comments:
                if not comment_monitoring:
                    break
                
                comment_id = comment.get('rpid')
                comment_content = comment.get('content', {}).get('message', '')
                comment_time = comment.get('ctime', 0)
                commenter_name = comment.get('member', {}).get('uname', '未知用户')
                video_id = comment.get('video_id')
                video_title = comment.get('video_title', '未知视频')
                
                add_comment_log(f"检查评论: {commenter_name} 在《{video_title}》- {comment_content[:30]}...", 'info')
                
                # 检查是否为新评论 - 使用评论系统独立的配置
                if comment_config.get('only_reply_new_comments', True):
                    if comment_time < comment_program_start_time:
                        add_comment_log(f"跳过旧评论: {commenter_name}", 'info')
                        continue
                
                # 检查是否已回复过 - 使用评论系统独立的缓存
                cache_key = f"{video_id}_{comment_id}"
                if cache_key in comment_cache:
                    add_comment_log(f"已回复过: {commenter_name}", 'info')
                    continue
                
                # 匹配回复规则 - 使用评论系统独立的规则
                reply_message = ""
                reply_image = ""
                reply_type = "text"
                matched_rule = None
                
                # 检查关键词规则 - 使用comment_rules而不是rules
                for rule in comment_rules:
                    if not rule.get('enabled', True):
                        continue
                    
                    keywords = rule.get('keyword', '').split(',')
                    for keyword in keywords:
                        keyword = keyword.strip()
                        if keyword and keyword in comment_content:
                            reply_message = rule.get('reply', '')
                            reply_image = rule.get('reply_image', '')
                            reply_type = rule.get('reply_type', 'text')
                            matched_rule = rule.get('name', '未命名规则')
                            break
                    
                    if matched_rule:
                        break
                
                # 如果没有匹配规则，使用默认回复 - 使用评论系统独立配置
                if not matched_rule and comment_config.get('default_comment_reply_enabled', False):
                    reply_message = comment_config.get('default_comment_reply_message', '')
                    reply_image = comment_config.get('default_comment_reply_image', '')
                    reply_type = comment_config.get('default_comment_reply_type', 'text')
                    matched_rule = "默认回复"
                
                # 发送回复
                if reply_message or reply_image:
                    if reply_type == 'image' and reply_image:
                        success = api.reply_comment(video_id, comment_id, reply_message, reply_image)
                    else:
                        success = api.reply_comment(video_id, comment_id, reply_message)
                    
                    if success:
                        comment_cache[cache_key] = True
                        add_comment_log(f"已回复 {commenter_name} 在《{video_title}》的评论 (规则: {matched_rule})", 'success')
                    else:
                        add_comment_log(f"回复 {commenter_name} 在《{video_title}》的评论失败", 'error')
            
            # 等待下次检查 - 使用评论系统独立配置
            check_interval = comment_config.get('comment_check_interval', 30)
            time.sleep(check_interval)
            
        except Exception as e:
            add_comment_log(f"评论监控异常: {e}", 'error')
            time.sleep(10)
    
    add_comment_log("评论监控已停止", 'warning')

@app.route('/comment')
def comment_page():
    """评论回复页面"""
    return send_from_directory('.', 'comment_reply.html')

@app.route('/logs.html')
def logs_page():
    """系统日志页面"""
    return send_from_directory('.', 'logs.html')

@app.route('/api/comment-config', methods=['GET', 'POST'])
def handle_comment_config():
    """处理评论回复配置"""
    if request.method == 'GET':
        load_comment_config()
        return jsonify(comment_config)
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            comment_config.update(data)
            save_comment_config()
            add_comment_log("评论回复配置已更新", 'success')
            return jsonify({'success': True})
        except Exception as e:
            error_msg = f"保存评论回复配置失败: {str(e)}"
            add_comment_log(error_msg, 'error')
            return jsonify({'success': False, 'error': error_msg})

@app.route('/api/comment-rules', methods=['GET', 'POST'])
def handle_comment_rules():
    """处理评论回复规则"""
    if request.method == 'GET':
        load_comment_rules()
        return jsonify({'rules': comment_rules})
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if 'rules' in data:
                comment_rules.clear()
                comment_rules.extend(data['rules'])
                save_comment_rules()
                add_comment_log(f"评论回复规则已更新，共 {len(comment_rules)} 条", 'success')
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': '无效的规则数据'})
        except Exception as e:
            error_msg = f"保存评论回复规则失败: {str(e)}"
            add_comment_log(error_msg, 'error')
            return jsonify({'success': False, 'error': error_msg})

@app.route('/api/comment-start', methods=['POST'])
def start_comment_monitoring():
    """开始评论监控"""
    global comment_monitoring, comment_monitor_thread
    
    if comment_monitoring:
        return jsonify({'success': False, 'error': '评论监控已在运行中'})
    
    if not comment_config.get('sessdata') or not comment_config.get('bili_jct'):
        return jsonify({'success': False, 'error': '请先配置登录信息'})
    
    try:
        comment_monitoring = True
        comment_monitor_thread = threading.Thread(target=comment_monitor_worker, daemon=True)
        comment_monitor_thread.start()
        
        add_comment_log("评论监控已启动", 'success')
        return jsonify({'success': True})
    except Exception as e:
        comment_monitoring = False
        error_msg = f"启动评论监控失败: {str(e)}"
        add_comment_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/comment-stop', methods=['POST'])
def stop_comment_monitoring():
    """停止评论监控"""
    global comment_monitoring
    
    comment_monitoring = False
    add_comment_log("评论监控已停止", 'warning')
    return jsonify({'success': True})

@app.route('/api/comment-status')
def get_comment_status():
    """获取评论监控状态"""
    return jsonify({
        'monitoring': comment_monitoring,
        'rules_count': len(comment_rules)
    })

@app.route('/api/comment-logs')
def get_comment_logs():
    """获取评论回复日志"""
    # 返回所有日志，按时间倒序
    return jsonify({
        'logs': list(reversed(comment_logs)),
        'total': len(comment_logs),
        'monitoring': comment_monitoring
    })

@app.route('/api/import-from-message-config', methods=['POST'])
def import_from_message_config():
    """从私信配置导入到评论配置"""
    try:
        load_config()
        load_rules()
        
        # 导入基本配置
        comment_config['sessdata'] = config.get('sessdata', '')
        comment_config['bili_jct'] = config.get('bili_jct', '')
        comment_config['default_comment_reply_enabled'] = config.get('default_reply_enabled', False)
        comment_config['default_comment_reply_message'] = config.get('default_reply_message', '感谢您的评论！')
        comment_config['default_comment_reply_type'] = config.get('default_reply_type', 'text')
        comment_config['default_comment_reply_image'] = config.get('default_reply_image', '')
        
        # 导入规则
        imported_rules = []
        for rule in rules:
            comment_rule = {
                'id': rule.get('id', int(time.time() * 1000)),
                'name': rule.get('name', '导入的规则'),
                'keyword': rule.get('keyword', ''),
                'reply': rule.get('reply', ''),
                'reply_type': rule.get('reply_type', 'text'),
                'reply_image': rule.get('reply_image', ''),
                'enabled': rule.get('enabled', True),
                'created_at': rule.get('created_at', datetime.now().isoformat())
            }
            imported_rules.append(comment_rule)
        
        comment_rules.clear()
        comment_rules.extend(imported_rules)
        
        # 保存配置
        save_comment_config()
        save_comment_rules()
        
        message = f"成功导入 {len(imported_rules)} 条规则和基本配置"
        add_comment_log(message, 'success')
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        error_msg = f"导入失败: {str(e)}"
        add_comment_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/export-comment-config', methods=['GET'])
def export_comment_config():
    """导出评论回复配置"""
    try:
        load_comment_config()
        load_comment_rules()
        
        # 创建export目录
        app_root = get_app_root()
        export_dir = os.path.join(app_root, 'export')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 准备导出数据
        export_data = {
            'version': '1.0',
            'export_time': datetime.now().isoformat(),
            'app_name': 'BiliGo - 评论回复系统',
            'config': comment_config.copy(),
            'rules': comment_rules.copy()
        }
        
        # 导出文件路径
        export_filename = f'biligo_comment_config_{timestamp}.json'
        export_path = os.path.join(export_dir, export_filename)
        
        # 写入文件
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        add_comment_log(f'导出评论回复配置: {len(comment_rules)} 条规则，文件已保存到 export/{export_filename}', 'success')
        
        # 返回文件下载
        return send_from_directory(
            export_dir, 
            export_filename,
            as_attachment=True,
            download_name=export_filename,
            mimetype='application/json'
        )
        
    except Exception as e:
        error_msg = f"导出评论回复配置失败: {str(e)}"
        add_comment_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/import-comment-config', methods=['POST'])
def import_comment_config():
    """导入评论回复配置"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        import_mode = request.form.get('import_mode', 'merge')
        
        # 读取文件内容
        content = file.read().decode('utf-8')
        data = json.loads(content)
        
        # 验证文件格式
        if 'config' not in data and 'rules' not in data:
            return jsonify({'success': False, 'error': '无效的配置文件格式'})
        
        imported_count = 0
        
        # 导入配置
        if 'config' in data:
            if import_mode == 'replace':
                comment_config.clear()
            comment_config.update(data['config'])
            save_comment_config()
        
        # 导入规则
        if 'rules' in data:
            if import_mode == 'replace':
                comment_rules.clear()
            
            for rule in data['rules']:
                # 确保规则有必要的字段
                if 'keyword' in rule and 'reply' in rule:
                    if import_mode == 'merge':
                        # 检查是否已存在相同关键词的规则
                        existing = any(r.get('keyword') == rule.get('keyword') for r in comment_rules)
                        if not existing:
                            comment_rules.append(rule)
                            imported_count += 1
                    else:
                        comment_rules.append(rule)
                        imported_count += 1
            
            save_comment_rules()
        
        message = f"成功导入 {imported_count} 条评论回复规则"
        add_comment_log(message, 'success')
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        error_msg = f"导入评论回复配置失败: {str(e)}"
        add_comment_log(error_msg, 'error')
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/validate-comment-keywords-file', methods=['POST'])
def validate_comment_keywords_file():
    """验证评论回复配置文件"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        # 读取文件内容
        content = file.read().decode('utf-8')
        data = json.loads(content)
        
        # 验证文件格式
        if 'rules' not in data and not isinstance(data, list):
            return jsonify({'success': False, 'error': '无效的配置文件格式'})
        
        # 统计有效规则
        rules_data = data.get('rules', data) if isinstance(data, dict) else data
        valid_rules = 0
        
        for rule in rules_data:
            if isinstance(rule, dict) and 'keyword' in rule and 'reply' in rule:
                valid_rules += 1
        
        return jsonify({
            'success': True,
            'valid_rules': valid_rules,
            'total_rules': len(rules_data)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'文件验证失败: {str(e)}'})

@app.route('/api/save_email_config', methods=['POST'])
def save_email_config():
    """保存邮件配置"""
    try:
        global config
        data = request.get_json()
        
        # 更新邮件配置
        config['email_notification'] = {
            'enabled': data.get('enabled', False),
            'smtp_server': data.get('smtp_server', 'smtp.qq.com'),
            'smtp_port': data.get('smtp_port', 587),
            'sender_email': data.get('sender_email', ''),
            'sender_password': data.get('sender_password', ''),
            'receiver_email': data.get('receiver_email', '')
        }
        
        # 保存配置到文件
        save_config()
        
        return jsonify({'success': True, 'message': '邮件配置保存成功'})
        
    except Exception as e:
        error_msg = f"保存邮件配置失败: {str(e)}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/get_email_config', methods=['GET'])
def get_email_config():
    """获取邮件配置"""
    try:
        global config
        email_config = config.get('email_notification', {
            'enabled': False,
            'smtp_server': 'smtp.qq.com',
            'smtp_port': 587,
            'sender_email': '',
            'sender_password': '',
            'receiver_email': ''
        })
        
        return jsonify({'success': True, 'config': email_config})
        
    except Exception as e:
        error_msg = f"获取邮件配置失败: {str(e)}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/test_email', methods=['POST'])
def test_email():
    """发送测试邮件"""
    try:
        data = request.get_json()
        sender_email = data.get('sender_email', '')
        sender_password = data.get('sender_password', '')
        receiver_email = data.get('receiver_email', '')
        
        if not sender_email or not sender_password or not receiver_email:
            return jsonify({'success': False, 'error': '邮件配置信息不完整'})
        
        # 临时设置邮件配置用于测试
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # 创建测试邮件
        subject = "BiliGo - 邮件配置测试"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #00a1d6; border-bottom: 2px solid #00a1d6; padding-bottom: 10px;">
                    ✅ BiliGo 邮件配置测试成功
                </h2>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #555;">测试信息</h3>
                    <p><strong>发送邮箱:</strong> {sender_email}</p>
                    <p><strong>接收邮箱:</strong> {receiver_email}</p>
                    <p><strong>测试时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div style="background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #28a745;">
                    <h3 style="margin-top: 0; color: #155724;">配置成功</h3>
                    <p>恭喜！您的邮件配置已经成功设置。当系统出现错误或登录失效时，您将收到详细的邮件通知。</p>
                </div>
                
                <div style="margin-top: 20px; padding: 15px; background-color: #e7f3ff; border-radius: 5px;">
                    <h3 style="margin-top: 0; color: #0056b3;">功能说明</h3>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>系统错误自动通知</li>
                        <li>登录状态失效提醒</li>
                        <li>详细的错误信息和建议操作</li>
                        <li>相同错误只发送一次通知</li>
                    </ul>
                </div>
                
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    这是一封测试邮件，请勿回复。<br>
                    如果您收到此邮件，说明邮件配置已成功设置。
                </p>
            </div>
        </body>
        </html>
        """
        
        # 创建邮件对象
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        # 发送邮件
        server = None
        try:
            server = smtplib.SMTP('smtp.qq.com', 587, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
            logger.info(f"测试邮件已发送至: {receiver_email}")
            
            # 成功发送后返回成功，不管关闭连接时是否有错误
            return jsonify({'success': True, 'message': '测试邮件发送成功'})
            
        finally:
            # 安全关闭连接，忽略关闭时的错误
            if server:
                try:
                    server.quit()
                except:
                    pass  # 忽略关闭时的错误
        
    except smtplib.SMTPAuthenticationError:
        return jsonify({'success': False, 'error': '邮箱认证失败，请检查邮箱地址和授权码是否正确'})
    except smtplib.SMTPException as e:
        error_msg = str(e)
        # 如果错误信息包含特定的无害错误，仍然返回成功
        if 'b\'\\x00\\x00\\x00\'' in error_msg or '(-1,' in error_msg:
            logger.info(f"测试邮件已发送至: {receiver_email} (忽略关闭连接错误)")
            return jsonify({'success': True, 'message': '测试邮件发送成功'})
        return jsonify({'success': False, 'error': f'SMTP错误: {error_msg}'})
    except Exception as e:
        error_msg = f"发送测试邮件失败: {str(e)}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/reset_all_data', methods=['POST'])
def reset_all_data():
    """清除所有数据，恢复初始设置"""
    try:
        global config, rules, message_logs, message_cache, last_message_times
        global followers_cache, welcome_sent_cache, unfollowers_cache, follow_history
        global monitoring, monitor_thread
        
        # 停止监控
        if monitoring:
            monitoring = False
            if monitor_thread and monitor_thread.is_alive():
                monitor_thread.join(timeout=5)
        
        # 重置全局配置为默认值
        config = {
            'default_reply_enabled': False,
            'default_reply_message': '您好，我现在不在，稍后会回复您的消息。',
            'default_reply_type': 'text',
            'default_reply_image': '',
            'separate_reply_by_follow': False,
            'followed_reply_message': '您好，感谢您的关注！我现在不在，稍后会回复您的消息。',
            'followed_reply_type': 'text',
            'followed_reply_image': '',
            'unfollowed_reply_message': '您好，我现在不在，稍后会回复您的消息。',
            'unfollowed_reply_type': 'text',
            'unfollowed_reply_image': '',
            'follow_reply_enabled': False,
            'follow_reply_message': '感谢您的关注！欢迎来到我的频道~',
            'follow_reply_type': 'text',
            'follow_reply_image': '',
            'unfollow_reply_enabled': False,
            'unfollow_reply_message': '很遗憾看到您取消了关注，希望我们还有机会再见！',
            'unfollow_reply_type': 'text',
            'unfollow_reply_image': '',
            'only_reply_new_messages': False,
            'max_replies_per_user': 3,
            'follow_check_interval': 1800,
            'message_check_interval': 0.05,
            'send_delay_interval': 1.0,
            'auto_restart_interval': 300,
            'email_notification': {
                'enabled': False,
                'smtp_server': 'smtp.qq.com',
                'smtp_port': 587,
                'sender_email': '',
                'sender_password': '',
                'receiver_email': ''
            },
            'sessdata': '',
            'bili_jct': ''
        }
        
        # 清空规则
        rules = []
        
        # 清空缓存和统计
        message_cache = {}
        last_message_times = defaultdict(int)
        followers_cache = set()
        welcome_sent_cache = set()
        unfollowers_cache = set()
        follow_history = {}
        
        # 清空日志
        message_logs = []
        
        # 保存清空后的配置
        init_config_paths()
        save_config()
        save_rules()
        
        # 删除用户回复统计文件
        if os.path.exists(USER_REPLY_STATS_FILE):
            os.remove(USER_REPLY_STATS_FILE)
        
        # 清空评论系统数据
        from comment_reply_system import comment_reply_system
        
        # 停止评论监控
        if comment_reply_system.is_monitoring():
            comment_reply_system.stop_monitoring()
        
        # 重置评论系统配置
        comment_reply_system.config = {
            'comment_reply_enabled': False,
            'default_comment_reply_enabled': False,
            'default_comment_reply_message': '感谢您的评论！',
            'default_comment_reply_type': 'text',
            'default_comment_reply_image': '',
            'comment_check_interval': 60,
            'comment_send_delay': 3.0,
            'only_reply_new_comments': True,
            'max_videos_to_check': 10,
            'max_comments_per_video': 20,
        }
        
        # 清空评论规则
        comment_reply_system.rules = []
        
        # 清空评论缓存和日志
        comment_reply_system.comment_cache = {}
        comment_reply_system.logs = []
        
        # 保存评论系统配置
        comment_reply_system.save_config()
        comment_reply_system.save_rules()
        
        logger.info("所有数据已清除，恢复初始设置")
        add_log("所有数据已清除，系统已恢复初始设置", 'warning')
        
        return jsonify({
            'success': True,
            'message': '所有数据已清除，系统已恢复初始设置'
        })
        
    except Exception as e:
        error_msg = f"清除数据失败: {str(e)}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/qrcode-login/generate', methods=['GET'])
def generate_qrcode():
    """生成扫码登录二维码"""
    try:
        result = BilibiliAPI.get_qrcode_login_url()
        return jsonify(result)
    except Exception as e:
        error_msg = f"生成二维码失败: {str(e)}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg})

@app.route('/api/qrcode-login/poll', methods=['POST'])
def poll_qrcode():
    """轮询扫码登录状态"""
    try:
        data = request.get_json()
        qrcode_key = data.get('qrcode_key')
        
        if not qrcode_key:
            return jsonify({'success': False, 'error': '缺少qrcode_key参数'})
        
        result = BilibiliAPI.poll_qrcode_status(qrcode_key)
        
        # 如果登录成功，自动保存配置
        if result.get('success') and result.get('status') == 'success':
            global config
            config['sessdata'] = result.get('sessdata')
            config['bili_jct'] = result.get('bili_jct')
            save_config()
            add_log('扫码登录成功，配置已自动保存', 'success')
        
        return jsonify(result)
    except Exception as e:
        error_msg = f"轮询扫码状态失败: {str(e)}"
        logger.error(error_msg)
        return jsonify({'success': False, 'error': error_msg})

# 确保在系统启动时添加一些初始日志，方便测试
if __name__ == '__main__':
    # 首先确保日志数组已初始化
    if 'message_logs' not in globals():
        message_logs = []
    if 'comment_logs' not in globals():
        comment_logs = []
        
    # 首先加载配置和规则
    load_rules()
    load_comment_config()
    load_comment_rules()
    
    # 添加启动日志到私信系统
    add_log("BiliGo - B站私信自动回复系统启动中...", 'info', system='message')
    add_log("系统初始化完成", 'success', system='message')
    add_log("Web服务器启动在端口 4999", 'info', system='message')
    add_log("请在浏览器中访问: http://localhost:4999", 'info', system='message')
    add_log("评论回复系统: http://localhost:4999/comment", 'info', system='message')
    add_log("日志系统已就绪", 'success', system='message')
    
    # 添加启动日志到评论系统
    add_log("评论回复系统已初始化", 'info', system='comment')
    add_log("评论监控功能就绪", 'success', system='comment')
    add_log("评论日志系统已就绪", 'success', system='comment')
    
    print("BiliGo - B站私信自动回复系统启动中...")
    print("请在浏览器中访问: http://localhost:4999")
    print("评论回复系统: http://localhost:4999/comment")
    
    app.run(host='0.0.0.0', port=4999, debug=False)
