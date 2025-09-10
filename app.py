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

# 全局变量
config = {
    'default_reply_enabled': False,
    'default_reply_message': '您好，我现在不在，稍后会回复您的消息。',
    'default_reply_type': 'text',  # 'text' 或 'image'
    'default_reply_image': '',  # 默认回复图片路径
    'follow_reply_enabled': False,  # 关注后回复功能开关
    'follow_reply_message': '感谢您的关注！欢迎来到我的频道~',  # 关注后回复消息
    'follow_reply_type': 'text',  # 关注后回复类型：'text' 或 'image'
    'follow_reply_image': '',  # 关注后回复图片路径
    'unfollow_reply_enabled': False,  # 取消关注回复功能开关
    'unfollow_reply_message': '很遗憾看到您取消了关注，希望我们还有机会再见！',  # 取消关注回复消息
    'unfollow_reply_type': 'text',  # 取消关注回复类型：'text' 或 'image'
    'unfollow_reply_image': '',  # 取消关注回复图片路径
    'only_reply_new_messages': False,  # 是否仅回复新消息（程序启动后的消息）
    'follow_check_interval': 30,  # 检查关注者的间隔（秒）
    'message_check_interval': 0.05,  # 消息监测间隔（秒）
    'send_delay_interval': 1.0,  # 发送消息等待间隔（秒）
    'auto_restart_interval': 300  # 自动重启间隔（秒）
}
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

rules = []
monitoring = False
monitor_thread = None
logs = []
message_cache = {}
last_message_times = defaultdict(int)
rule_matcher_cache = {}
last_send_time = 0
# 关注者监控相关变量
followers_cache = set()  # 缓存已知关注者
welcome_sent_cache = set()  # 缓存已发送欢迎消息的关注者
last_follow_check = 0  # 上次检查关注者的时间
# 检查关注者的间隔将从配置中读取

# 取消关注监控相关变量
unfollowers_cache = set()  # 缓存已处理的取消关注者
last_unfollow_check = 0  # 上次检查取消关注的时间
follow_history = {}  # 关注历史记录 {uid: last_follow_time}

# 程序启动时间戳（用于仅回复新消息功能）
program_start_time = int(time.time())

# 配置文件路径 - 兼容Linux和Windows（延迟初始化）
CONFIG_FILE = None
RULES_FILE = None

def get_config_file_path(filename):
    """获取配置文件路径，确保跨平台兼容"""
    app_root = get_app_root()
    return os.path.join(app_root, filename)

def init_config_paths():
    """初始化配置文件路径"""
    global CONFIG_FILE, RULES_FILE
    if CONFIG_FILE is None:
        CONFIG_FILE = get_config_file_path('config.json')
    if RULES_FILE is None:
        RULES_FILE = get_config_file_path('keywords.json')

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
        """快速获取最新消息"""
        try:
            msgs_data = self.get_session_msgs(talker_id, size=1)
            if msgs_data and msgs_data.get('code') == 0:
                messages = msgs_data.get('data', {}).get('messages', [])
                return messages[0] if messages else None
            return None
        except:
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
                add_log(f"触发频率限制，但保持发送间隔继续运行", 'warning')
            elif result.get('code') == -101:
                add_log("登录状态失效，请重新配置登录信息", 'error')
            elif result.get('code') != 0:
                add_log(f"发送失败: {result.get('message', '未知错误')}", 'warning')
            
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

def add_log(message, log_type='info'):
    """添加日志"""
    timestamp = datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'message': message,
        'level': log_type  # 前端期望的字段名是 level 而不是 type
    }
    logs.append(log_entry)
    
    # 限制日志数量
    if len(logs) > 100:
        logs.pop(0)
    
    logger.info(f"[{log_type.upper()}] {message}")

def load_config():
    """加载配置"""
    global config
    init_config_paths()  # 确保路径已初始化
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                config.update(loaded_config)
            logger.info(f"成功加载配置文件: {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            add_log(f"加载配置失败: {e}", 'error')
    else:
        logger.info(f"配置文件不存在，使用默认配置: {CONFIG_FILE}")

def save_config():
    """保存配置"""
    try:
        init_config_paths()  # 确保路径已初始化
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存配置文件: {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        add_log(f"保存配置失败: {e}", 'error')

def load_rules():
    """加载关键词规则"""
    global rules
    init_config_paths()  # 确保路径已初始化
    logger.info(f"尝试加载关键词文件: {RULES_FILE}")
    
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                loaded_rules = json.load(f)
                if isinstance(loaded_rules, list):
                    rules = loaded_rules
                    precompile_rules()
                    enabled_count = len([r for r in rules if r.get('enabled', True)])
                    add_log(f"成功加载 {len(rules)} 条关键词规则，其中 {enabled_count} 条已启用", 'success')
                    logger.info(f"成功加载关键词规则: {len(rules)} 条")
                else:
                    rules = []
                    add_log("关键词文件格式错误，已重置", 'warning')
        except Exception as e:
            logger.error(f"加载关键词规则失败: {e}")
            add_log(f"加载关键词规则失败: {e}", 'error')
            rules = []
    else:
        rules = []
        add_log(f"关键词文件不存在: {RULES_FILE}，创建新文件", 'info')
        logger.warning(f"关键词文件不存在: {RULES_FILE}")

def save_rules():
    """保存规则"""
    try:
        init_config_paths()  # 确保路径已初始化
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存关键词规则: {RULES_FILE}")
    except Exception as e:
        logger.error(f"保存规则失败: {e}")
        add_log(f"保存规则失败: {e}", 'error')

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
        
        # 从配置中获取检查间隔，默认30秒避免触发风控
        check_interval = config.get('follow_check_interval', 30)
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
            
            # 3. 检测取消关注者（更可靠的验证）
            if config.get('unfollow_reply_enabled', False):
                # 获取所有新关注者的mid集合
                new_follower_mids = {f['mid'] for f in new_followers if f.get('mid')}
                
                # 找出之前在缓存中但现在不在当前关注者列表中的用户
                lost_followers = followers_cache - current_followers
                for unfollower_mid in lost_followers:
                    # 确保不是新关注者（避免误判）
                    if unfollower_mid not in new_follower_mids and unfollower_mid not in unfollowers_cache:
                        # 双重验证：检查该用户是否在最近获取的关注者列表中
                        # 通过重新获取关注者列表进行验证
                        try:
                            # 获取最新的关注者列表（限制为50个）
                            recent_followers = api.get_recent_followers(limit=50)
                            current_follower_mids = {f['mid'] for f in recent_followers if f.get('mid')}
                            
                            if unfollower_mid in current_follower_mids:
                                # 用户仍在关注列表中，跳过处理
                                continue
                                
                            # 确认用户确实取消关注
                            unfollowers.append({'mid': unfollower_mid})
                            unfollowers_cache.add(unfollower_mid)
                            add_log(f"💔 确认取消关注: UID {unfollower_mid}", 'warning')
                            # 从欢迎消息缓存中移除
                            if unfollower_mid in welcome_sent_cache:
                                welcome_sent_cache.remove(unfollower_mid)
                        except Exception as e:
                            add_log(f"验证取消关注状态失败: {e}", 'warning')
                            continue
            
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
        talker_id = session.get('talker_id')
        if not talker_id:
            return []
        
        # 获取最新的一条消息
        latest_msg = api.get_latest_message(talker_id)
        if not latest_msg:
            return []
        
        msg_timestamp = latest_msg.get('timestamp', 0)
        sender_uid = latest_msg.get('sender_uid')
        
        # 检查是否启用了"仅回复新消息"功能
        if config.get('only_reply_new_messages', False):
            # 如果消息时间早于程序启动时间，跳过处理
            if msg_timestamp < program_start_time:
                add_log(f"用户{talker_id} 消息时间早于程序启动时间，跳过回复（仅回复新消息模式）", 'debug')
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
            add_log(f"用户{talker_id} 最后一条消息是我发的，跳过回复", 'debug')
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
            add_log(f"✅ 检测到关键词匹配: 用户{talker_id} 消息'{message_text}' 匹配规则'{matched_rule['title']}'", 'info')
            return [{
                'talker_id': talker_id,
                'rule': matched_rule,
                'message': message_text,
                'timestamp': msg_timestamp
            }]
        else:
            # 如果启用了默认回复功能且没有匹配到关键词
            if config.get('default_reply_enabled', False):
                default_type = config.get('default_reply_type', 'text')
                
                if default_type == 'text' and config.get('default_reply_message'):
                    add_log(f"⚠️ 用户{talker_id} 消息'{message_text}' 未匹配关键词，使用默认文字回复", 'info')
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
                    add_log(f"⚠️ 用户{talker_id} 消息'{message_text}' 未匹配关键词，使用默认图片回复", 'info')
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
                add_log(f"❌ 用户{talker_id} 消息'{message_text}' 未匹配任何关键词", 'debug')
                return []
        
    except Exception as e:
        logger.error(f"处理会话 {session.get('talker_id')} 时出错: {e}")
        return []

def monitor_messages():
    """监控消息的主循环（增强稳定性版本）"""
    global monitoring, message_cache, last_message_times, last_send_time, monitor_thread
    
    if not config.get('sessdata') or not config.get('bili_jct'):
        add_log("未配置登录信息，无法启动监控", 'error')
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
                add_log("获取用户信息失败，请检查登录配置", 'error')
                retry_count += 1
                if retry_count < max_retries:
                    add_log(f"重试获取用户信息 ({retry_count}/{max_retries})", 'warning')
                    time.sleep(0.3)  # 进一步缩短用户信息重试等待时间
                    continue
                else:
                    monitoring = False
                    return
            
            # 重置重试计数
            retry_count = 0
            
            add_log(f"监控已启动，用户UID: {my_uid}", 'success')
            
            # 预编译规则
            precompile_rules()
            
            # 初始化全局变量
            message_cache = {}
            last_message_times = defaultdict(int)
            last_send_time = 0
            followers_cache = set()
            last_follow_check = 0
            
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
                    
                    # 心跳检测 - 每60秒输出一次状态
                    if current_time - last_heartbeat >= 60:
                        add_log(f"💓 系统运行正常: 处理{processed_count}条消息, 错误{error_count}次, 活跃会话{len(last_message_times)}个", 'info')
                        last_heartbeat = current_time
                    
                    # 每5分钟强制清理缓存（更频繁清理）
                    if current_time - last_cleanup > 300:
                        try:
                            cleanup_cache()
                            precompile_rules()
                            last_cleanup = current_time
                            add_log(f"定期维护: 已处理 {processed_count} 条消息，错误 {error_count} 次，活跃会话 {len(last_message_times)} 个", 'info')
                        except Exception as e:
                            add_log(f"缓存清理异常: {e}", 'warning')
                    
                    # 关注者检测已移至主循环，此处不再需要
                    
                    # 每30分钟重新创建API对象，防止连接问题
                    if current_time - last_api_reset > 1800:
                        try:
                            add_log("重新初始化API连接", 'info')
                            api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                            # 验证新API对象
                            test_uid = api.get_my_uid()
                            if test_uid:
                                last_api_reset = current_time
                                add_log("API重新初始化成功", 'success')
                            else:
                                add_log("API重新初始化失败，继续使用旧连接", 'warning')
                        except Exception as e:
                            add_log(f"API重新初始化异常: {e}", 'warning')
                    
                    # 获取会话列表 - 增加重试机制
                    sessions_data = None
                    for attempt in range(3):
                        try:
                            sessions_data = api.get_sessions()
                            if sessions_data:
                                break
                        except Exception as e:
                            add_log(f"获取会话列表尝试 {attempt+1}/3 失败: {e}", 'warning')
                            if attempt < 2:
                                time.sleep(0.3)  # 优化系统稳定等待时间
                    
                    if not sessions_data:
                        consecutive_errors += 1
                        if consecutive_errors > 5:
                            add_log("连续获取会话失败，重新初始化API", 'warning')
                            try:
                                api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                                consecutive_errors = 0
                            except Exception as e:
                                add_log(f"API重新初始化失败: {e}", 'error')
                        time.sleep(2)
                        continue
                    
                    if sessions_data.get('code') != 0:
                        error_msg = sessions_data.get('message', '未知错误')
                        add_log(f"API返回错误: {error_msg}", 'warning')
                        consecutive_errors += 1
                        
                        # 如果是认证相关错误，重新初始化
                        if sessions_data.get('code') in [-101, -111, -400, -403]:
                            add_log("认证错误，重新初始化API", 'warning')
                            try:
                                api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                            except Exception as e:
                                add_log(f"认证错误后API重新初始化失败: {e}", 'error')
                        
                        time.sleep(2)
                        continue
                    
                    consecutive_errors = 0  # 重置连续错误计数
                    
                    # 定期缓存清理，避免长时间运行内存负荷过大
                    if current_time % 300 == 0:  # 每5分钟清理一次
                        try:
                            cleanup_cache()
                            # 强制垃圾回收
                            import gc
                            gc.collect()
                            add_log("定期缓存清理完成，内存优化", 'info')
                        except Exception as e:
                            add_log(f"定期缓存清理异常: {e}", 'warning')
                    
                    # 初始化本轮回复计数
                    reply_count = 0
                    
                    # 🎯 实时检测关注者变化（新关注和取消关注）
                    if config.get('follow_reply_enabled', False) or config.get('unfollow_reply_enabled', False):
                        try:
                            followers_changes = check_followers_changes(api)
                            
                            # 处理新关注者
                            for follower in followers_changes['new_followers']:
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
                            for unfollower in followers_changes['unfollowers']:
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
                    
                    sessions = sessions_data.get('data', {}).get('session_list', [])
                    if not sessions:
                        time.sleep(0.2)
                        continue
                    
                    # 按最后消息时间排序
                    sessions.sort(key=lambda x: x.get('last_msg', {}).get('timestamp', 0), reverse=True)
                    
                    # 筛选需要检查的会话（扩大范围确保不遗漏）
                    check_sessions = []
                    debug_info = []
                    
                    for session in sessions[:30]:  # 检查前30个会话
                        talker_id = session.get('talker_id')
                        if not talker_id:
                            continue
                        
                        last_msg_time = session.get('last_msg', {}).get('timestamp', 0)
                        recorded_time = last_message_times.get(talker_id, 0)
                        
                        # 检查有新消息的会话
                        if last_msg_time > recorded_time:
                            check_sessions.append(session)
                            debug_info.append(f"用户{talker_id}: 新消息 {last_msg_time} > {recorded_time}")
                        # 或者最近5分钟内活跃的会话
                        elif current_time - last_msg_time < 300:
                            check_sessions.append(session)
                            debug_info.append(f"用户{talker_id}: 活跃会话 {current_time - last_msg_time}s前")
                        else:
                            debug_info.append(f"用户{talker_id}: 跳过 {last_msg_time} <= {recorded_time}")
                    
                    # 每30秒输出一次调试信息
                    if current_time % 30 == 0 and debug_info:
                        add_log(f"会话检查: {len(check_sessions)}/{len(sessions)} 个会话需要处理", 'debug')
                    
                    if not check_sessions:
                        time.sleep(0.2)
                        continue
                    
                    # 单线程顺序处理所有会话
                    # reply_count 已在循环开始时初始化
                    
                    for session in check_sessions:
                        if not monitoring:
                            break
                        
                        try:
                            results = process_single_session(api, my_uid, session)
                            
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
                                            add_log(f"✅ 已成功回复用户 {result['talker_id']} (规则: {result['rule']['title']}) 内容: {reply_content[:20]}...", 'success')
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
                                        add_log(f"❌ 回复用户 {result['talker_id']} 失败 [错误码:{error_code}]: {error_msg}", 'warning')
                                        error_count += 1
                                        
                                except Exception as e:
                                    add_log(f"💥 发送回复异常: {e}", 'error')
                                    error_count += 1
                        
                        except Exception as e:
                            add_log(f"处理会话异常: {e}", 'error')
                            error_count += 1
                    
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
                    current_time_check = int(time.time())
                    restart_interval = config.get('auto_restart_interval', 300)
                    if current_time_check - last_reply_time >= restart_interval:
                        add_log(f"🔄 已连续 {current_time_check - last_reply_time} 秒无回复消息，执行自动重启", 'warning')
                        
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
                    add_log(f"监控循环异常: {e}", 'error')
                    error_count += 1
                    consecutive_errors += 1
                    
                    # 如果连续错误太多，重新初始化
                    if consecutive_errors > 10:
                        add_log("连续错误过多，重新初始化系统", 'warning')
                        try:
                            api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                            consecutive_errors = 0
                        except Exception as init_e:
                            add_log(f"系统重新初始化失败: {init_e}", 'error')
                            break
                        time.sleep(0.3)  # 进一步缩短系统重新初始化后的等待时间
                    else:
                        time.sleep(0.2)  # 进一步缩短一般错误的等待时间
        
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
    add_log("监控已停止", 'warning')

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
        add_log("配置已更新", 'success')
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
        add_log("关键词规则已更新并预编译完成", 'success')
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
        add_log("开始监控私信（仅回复新消息模式）", 'success')
    else:
        add_log("开始监控私信", 'success')
    
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
def stop_monitoring():
    global monitoring, monitor_thread
    
    # 强制停止，不管当前状态
    monitoring = False
    add_log("停止监控私信", 'warning')
    
    # 等待线程结束
    if monitor_thread and monitor_thread.is_alive():
        monitor_thread.join(timeout=3)
        if monitor_thread.is_alive():
            add_log("监控线程未能在3秒内停止，但状态已重置", 'warning')
    
    # 清理线程引用
    monitor_thread = None
    
    return jsonify({'success': True})

@app.route('/api/status')
def get_status():
    global monitoring, monitor_thread
    
    # 检查实际状态，确保状态同步
    actual_monitoring = monitoring and monitor_thread and monitor_thread.is_alive()
    
    # 如果状态不一致，自动修正
    if monitoring and (not monitor_thread or not monitor_thread.is_alive()):
        monitoring = False
        monitor_thread = None
        add_log("检测到状态不一致，已自动修正", 'warning')
    
    return jsonify({
        'monitoring': actual_monitoring,
        'rules_count': len(rules),
        'config_set': bool(config.get('sessdata') and config.get('bili_jct'))
    })

@app.route('/api/logs', methods=['GET', 'DELETE'])
def handle_logs():
    global logs
    if request.method == 'GET':
        # 返回所有日志，让前端决定显示多少条
        return jsonify({'logs': logs})
    elif request.method == 'DELETE':
        # 清空日志
        logs.clear()
        add_log("日志已被手动清空", 'info')
        return jsonify({'success': True, 'message': '日志已清空'})

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
        
        save_config()
        add_log("仅回复新消息配置已更新", 'success')
        return jsonify({'success': True})
    else:
        # GET请求，返回当前配置
        return jsonify({
            'only_reply_new_messages': config.get('only_reply_new_messages', False)
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
                if interval < 5:
                    return jsonify({'success': False, 'error': '检查间隔不能少于5秒'})
                elif interval > 300:
                    return jsonify({'success': False, 'error': '检查间隔不能超过300秒（5分钟）'})
                
                old_value = config.get('follow_check_interval', 30)
                config['follow_check_interval'] = interval
                
                # 记录配置变更和风控提示
                if old_value != interval:
                    add_log(f"关注者检查间隔已更新: {old_value}秒 -> {interval}秒", 'success')
                    if interval < 30:
                        add_log(f"⚠️ 警告：检查间隔设置为{interval}秒，可能触发B站风控系统，建议设置为30秒以上", 'warning')
                    elif interval >= 30:
                        add_log(f"✅ 检查间隔设置为{interval}秒，有助于避免触发B站风控", 'success')
                
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '检查间隔必须是有效的数字'})
        
        save_config()
        add_log("关注者检查间隔配置已更新", 'success')
        return jsonify({'success': True})
    else:
        # GET请求，返回当前配置
        return jsonify({
            'follow_check_interval': config.get('follow_check_interval', 30)
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
comment_logs = []
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
    """加载评论回复配置"""
    global comment_config
    init_comment_config_paths()
    
    try:
        if os.path.exists(COMMENT_CONFIG_FILE):
            with open(COMMENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                comment_config.update(loaded_config)
    except Exception as e:
        logger.error(f"加载评论回复配置失败: {e}")

def save_comment_config():
    """保存评论回复配置"""
    init_comment_config_paths()
    
    try:
        with open(COMMENT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(comment_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存评论回复配置失败: {e}")

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
    global comment_logs
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = {
        'timestamp': timestamp,
        'message': message,
        'type': log_type
    }
    comment_logs.append(log_entry)
    
    # 保持日志数量在合理范围内
    if len(comment_logs) > 200:
        comment_logs = comment_logs[-100:]
    
    logger.info(f"[评论回复] {message}")

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
    """评论监控工作线程"""
    global comment_monitoring
    
    add_comment_log("开始监控评论回复", 'info')
    
    while comment_monitoring:
        try:
            if not comment_config.get('sessdata') or not comment_config.get('bili_jct'):
                add_comment_log("登录配置不完整，停止监控", 'error')
                comment_monitoring = False
                break
            
            api = CommentAPI(comment_config['sessdata'], comment_config['bili_jct'])
            my_uid = api.get_my_uid()
            
            if not my_uid:
                add_comment_log("获取用户信息失败，请检查登录配置", 'error')
                # 不要立即退出，等待下次检查
                time.sleep(30)
                continue
            
            # 获取所有评论（不分视频）
            max_videos = comment_config.get('max_videos_to_check', 20)
            comments_per_video = comment_config.get('comments_per_video', 10)
            all_comments = api.get_all_comments(my_uid, max_videos, comments_per_video)
            
            if not all_comments:
                add_comment_log("没有找到评论，等待下次检查", 'info')
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
                
                # 检查是否为新评论
                if comment_config.get('only_reply_new_comments', True):
                    if comment_time < comment_program_start_time:
                        add_comment_log(f"跳过旧评论: {commenter_name}", 'info')
                        continue
                
                # 检查是否已回复过
                cache_key = f"{video_id}_{comment_id}"
                if cache_key in comment_cache:
                    add_comment_log(f"已回复过: {commenter_name}", 'info')
                    continue
                
                # 匹配回复规则
                reply_message = ""
                reply_image = ""
                reply_type = "text"
                matched_rule = None
                
                # 检查关键词规则
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
                
                # 如果没有匹配规则，使用默认回复
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
            
            # 等待下次检查
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

if __name__ == '__main__':
    load_rules()
    load_comment_config()
    load_comment_rules()
    
    # 添加启动日志
    add_log("BiliGo - B站私信自动回复系统启动中...", 'info')
    add_log("系统初始化完成", 'success')
    add_log("Web服务器启动在端口 4999", 'info')
    add_log("请在浏览器中访问: http://localhost:4999", 'info')
    add_log("评论回复系统: http://localhost:4999/comment", 'info')
    
    print("BiliGo - B站私信自动回复系统启动中...")
    print("请在浏览器中访问: http://localhost:4999")
    print("评论回复系统: http://localhost:4999/comment")
    
    app.run(host='0.0.0.0', port=4999, debug=False)
