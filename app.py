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
    'reply_history_messages': False  # 是否回复历史消息
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
monitor_start_time = 0  # 监控启动时间，用于区分历史消息和新消息

# 配置文件路径 - 兼容Linux和Windows
CONFIG_FILE = os.path.join(os.getcwd(), 'config.json')
RULES_FILE = os.path.join(os.getcwd(), 'keywords.json')

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
        """发送私信（固定1秒间隔版）"""
        global last_send_time
        
        current_time = time.time()
        
        # 固定1秒发送间隔
        if current_time - last_send_time < 1.0:
            wait_time = 1.0 - (current_time - last_send_time)
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
                add_log(f"触发频率限制，但保持1秒间隔继续运行", 'warning')
            elif result.get('code') == -101:
                add_log("登录状态失效", 'error')
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

def add_log(message, log_type='info'):
    """添加日志"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = {
        'timestamp': timestamp,
        'message': message,
        'type': log_type
    }
    logs.append(log_entry)
    
    # 限制日志数量
    if len(logs) > 100:
        logs.pop(0)
    
    logger.info(f"[{log_type.upper()}] {message}")

def load_config():
    """加载配置"""
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")

def save_config():
    """保存配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存配置失败: {e}")

def load_rules():
    """加载关键词规则"""
    global rules
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                loaded_rules = json.load(f)
                if isinstance(loaded_rules, list):
                    rules = loaded_rules
                    precompile_rules()
                    enabled_count = len([r for r in rules if r.get('enabled', True)])
                    add_log(f"成功加载 {len(rules)} 条关键词规则，其中 {enabled_count} 条已启用", 'success')
                else:
                    rules = []
                    add_log("关键词文件格式错误，已重置", 'warning')
        except Exception as e:
            logger.error(f"加载关键词规则失败: {e}")
            add_log(f"加载关键词规则失败: {e}", 'error')
            rules = []
    else:
        rules = []
        add_log("关键词文件不存在，创建新文件", 'info')

def save_rules():
    """保存规则"""
    try:
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存规则失败: {e}")

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
    """极速关键词匹配"""
    message_lower = message.lower()
    
    for rule_id, rule_data in rule_matcher_cache.items():
        for keyword in rule_data['keywords']:
            if keyword in message_lower:
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
    
    # 更激进的缓存清理策略 - 只保留30分钟内的消息缓存
    old_cache = {}
    cleaned_count = 0
    for msg_id in list(message_cache.keys()):
        try:
            # 从消息ID中提取时间戳
            parts = msg_id.split('_')
            if len(parts) >= 2:
                msg_time = int(parts[1])
                if current_time - msg_time < 1800:  # 只保留30分钟内的
                    old_cache[msg_id] = message_cache[msg_id]
                else:
                    cleaned_count += 1
        except:
            # 无法解析的ID直接删除
            cleaned_count += 1
    
    message_cache = old_cache
    
    # 不清理时间记录，保持会话连续性
    # 但限制缓存大小，防止内存泄漏
    if len(message_cache) > 1000:
        # 如果缓存过大，只保留最新的500条
        sorted_items = sorted(message_cache.items(), key=lambda x: x[0])
        message_cache = dict(sorted_items[-500:])
        add_log("缓存过大，已清理到最新500条", 'warning')
    
    # 强制垃圾回收
    import gc
    gc.collect()
    
    add_log(f"缓存清理完成: 清理消息 {cleaned_count} 条，当前缓存 {len(message_cache)} 条，活跃会话 {len(last_message_times)} 个", 'info')

def process_single_session(api, my_uid, session):
    """处理单个会话的消息（只检测最后一条消息）"""
    global message_cache, last_message_times, monitor_start_time
    
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
        
        # 检查是否回复历史消息
        if not config.get('reply_history_messages', False):
            # 如果不回复历史消息，只处理监控启动后的新消息
            if msg_timestamp < monitor_start_time:
                # 更新最后处理时间，避免重复检查
                last_message_times[talker_id] = msg_timestamp
                add_log(f"用户{talker_id} 消息是历史消息，跳过回复（时间戳: {msg_timestamp} < 启动时间: {monitor_start_time}）", 'debug')
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
                    time.sleep(5)
                    continue
                else:
                    monitoring = False
                    return
            
            # 重置重试计数
            retry_count = 0
            
            add_log(f"监控已启动，用户UID: {my_uid}，固定1秒发送间隔 + 5秒无回复自动重启", 'success')
            
            # 预编译规则
            precompile_rules()
            
            # 初始化全局变量
            message_cache = {}
            last_message_times = defaultdict(int)
            last_send_time = 0
            monitor_start_time = int(time.time())  # 记录监控启动时间
            
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
                                time.sleep(1)
                    
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
                    
                    sessions = sessions_data.get('data', {}).get('session_list', [])
                    if not sessions:
                        time.sleep(0.5)
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
                    reply_count = 0
                    
                    for session in check_sessions:
                        if not monitoring:
                            break
                        
                        try:
                            results = process_single_session(api, my_uid, session)
                            
                            for result in results:
                                # 发送回复（固定1秒间隔 + 发送成功验证）
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
                                        # 验证发送是否真正成功
                                        time.sleep(0.5)  # 等待消息发送完成
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
                    
                    # 检查是否需要自动重启（5秒无回复）
                    current_time_check = int(time.time())
                    if current_time_check - last_reply_time >= 5:
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
                                            time.sleep(2)
                                    except Exception as api_e:
                                        add_log(f"API创建失败 {api_attempt + 1}/3: {api_e}", 'warning')
                                        time.sleep(2)
                                
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
                                            time.sleep(1)
                                    except Exception as uid_e:
                                        add_log(f"获取用户信息异常 {uid_attempt + 1}/3: {uid_e}", 'warning')
                                        time.sleep(1)
                                
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
                                    add_log(f"等待 {restart_attempts * 2} 秒后重试", 'info')
                                    time.sleep(restart_attempts * 2)
                        
                        # 如果重启失败，停止监控
                        if not restart_success:
                            add_log("❌ 多次重启失败，停止监控。请检查网络连接和登录状态", 'error')
                            monitoring = False
                            break
                    
                    # 固定循环间隔
                    elapsed = time.time() - loop_start
                    sleep_time = max(0.3, 0.5 - elapsed)  # 保持稳定的循环速度
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
                        time.sleep(5)
                    else:
                        time.sleep(2)
        
        except Exception as e:
            add_log(f"监控系统异常: {e}", 'error')
            retry_count += 1
            if retry_count < max_retries and monitoring:
                add_log(f"尝试重新启动监控系统 ({retry_count}/{max_retries})", 'warning')
                time.sleep(10)  # 等待更长时间再重试
            else:
                break
    
    # 确保监控状态正确设置
    monitoring = False
    add_log("监控已停止", 'warning')

# 路由定义
@app.route('/')
def index():
    return send_from_directory(os.getcwd(), 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    if '..' in filename or filename.startswith('/'):
        return "Access denied", 403
    return send_from_directory(os.getcwd(), filename)

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
    global monitoring, monitor_thread
    
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
    global message_cache, last_message_times, last_send_time, monitor_start_time
    message_cache = {}
    last_message_times = defaultdict(int)
    last_send_time = 0
    monitor_start_time = int(time.time())  # 记录监控启动时间
    
    # 启动新的监控线程
    monitoring = True
    monitor_thread = threading.Thread(target=monitor_messages)
    monitor_thread.daemon = True
    monitor_thread.start()
    
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

@app.route('/api/logs')
def get_logs():
    recent_logs = logs[-10:] if len(logs) > 10 else logs
    return jsonify({'logs': recent_logs})

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

if __name__ == '__main__':
    load_rules()
    
    print("BiliGo - B站私信自动回复系统启动中...")
    print("请在浏览器中访问: http://localhost:4999")
    
    app.run(host='0.0.0.0', port=4999, debug=False)
