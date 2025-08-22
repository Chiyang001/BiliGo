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

app = Flask(__name__)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
config = {
    'default_reply_enabled': False,
    'default_reply_message': '您好，我现在不在，稍后会回复您的消息。'
}
rules = []
monitoring = False
monitor_thread = None
logs = []
message_cache = {}
last_message_times = defaultdict(int)
rule_matcher_cache = {}
last_send_time = 0

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
            'msg[content]': json.dumps({"content": content}),
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
    global message_cache, last_message_times
    
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
            if config.get('default_reply_enabled', False) and config.get('default_reply_message'):
                add_log(f"⚠️ 用户{talker_id} 消息'{message_text}' 未匹配关键词，使用默认回复", 'info')
                return [{
                    'talker_id': talker_id,
                    'rule': {
                        'title': '默认回复',
                        'reply': config.get('default_reply_message')
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
    """监控消息的主循环（带自动重启机制）"""
    global monitoring, message_cache, last_message_times, last_send_time
    
    if not config.get('sessdata') or not config.get('bili_jct'):
        add_log("未配置登录信息，无法启动监控", 'error')
        monitoring = False
        return
    
    try:
        api = BilibiliAPI(config['sessdata'], config['bili_jct'])
        my_uid = api.get_my_uid()
        
        if not my_uid:
            add_log("获取用户信息失败，请检查登录配置", 'error')
            monitoring = False
            return
        
        add_log(f"监控已启动，用户UID: {my_uid}，固定1秒发送间隔 + 5秒无回复自动重启", 'success')
        
        # 预编译规则
        precompile_rules()
        
        # 初始化全局变量
        message_cache = {}
        last_message_times = defaultdict(int)
        last_send_time = 0
        
        last_cleanup = int(time.time())
        last_api_reset = int(time.time())
        last_reply_time = int(time.time())  # 记录最后一次回复时间
        processed_count = 0
        error_count = 0
        consecutive_errors = 0
        
        while monitoring:
            try:
                loop_start = time.time()
                current_time = int(time.time())
                
                # 每5分钟强制清理缓存（更频繁清理）
                if current_time - last_cleanup > 300:
                    cleanup_cache()
                    precompile_rules()
                    last_cleanup = current_time
                    add_log(f"定期维护: 已处理 {processed_count} 条消息，错误 {error_count} 次，活跃会话 {len(last_message_times)} 个", 'info')
                
                # 每30分钟重新创建API对象，防止连接问题
                if current_time - last_api_reset > 1800:
                    add_log("重新初始化API连接", 'info')
                    api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                    last_api_reset = current_time
                
                # 获取会话列表
                sessions_data = api.get_sessions()
                if not sessions_data:
                    consecutive_errors += 1
                    if consecutive_errors > 5:
                        add_log("连续获取会话失败，重新初始化API", 'warning')
                        api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                        consecutive_errors = 0
                    time.sleep(1)
                    continue
                
                if sessions_data.get('code') != 0:
                    error_msg = sessions_data.get('message', '未知错误')
                    add_log(f"API返回错误: {error_msg}", 'warning')
                    consecutive_errors += 1
                    
                    # 如果是认证相关错误，重新初始化
                    if sessions_data.get('code') in [-101, -111, -400, -403]:
                        add_log("认证错误，重新初始化API", 'warning')
                        api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                    
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
                                reply_result = api.send_msg(result['talker_id'], content=result['rule']['reply'])
                                
                                if reply_result and reply_result.get('code') == 0:
                                    # 验证发送是否真正成功
                                    time.sleep(0.5)  # 等待消息发送完成
                                    verification_success = api.verify_message_sent(result['talker_id'], result['rule']['reply'])
                                    
                                    if verification_success:
                                        add_log(f"✅ 已成功回复用户 {result['talker_id']} (规则: {result['rule']['title']}) 内容: {result['rule']['reply'][:20]}...", 'success')
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
                    add_log(f"🔄 已处理{processed_count}条消息，执行缓存清理", 'info')
                    cleanup_cache()
                
                # 记录处理结果和更新最后回复时间
                if reply_count > 0:
                    last_reply_time = int(time.time())  # 更新最后回复时间
                    add_log(f"📊 本轮回复了 {reply_count} 条消息，总计处理 {processed_count} 条", 'info')
                
                # 检查是否需要自动重启（5秒无回复）
                current_time_check = int(time.time())
                if current_time_check - last_reply_time >= 5:
                    add_log(f"🔄 已连续 {current_time_check - last_reply_time} 秒无回复消息，执行自动重启", 'warning')
                    
                    # 重新初始化系统
                    message_cache = {}
                    last_message_times = defaultdict(int)
                    last_send_time = 0
                    last_reply_time = current_time_check
                    
                    # 重新创建API对象
                    api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                    my_uid = api.get_my_uid()
                    
                    if not my_uid:
                        add_log("重启后获取用户信息失败", 'error')
                        monitoring = False
                        break
                    
                    # 重新预编译规则
                    precompile_rules()
                    add_log("✅ 系统重启完成，继续监控", 'success')
                
                # 固定循环间隔
                elapsed = time.time() - loop_start
                sleep_time = max(0.3, 0.5 - elapsed)  # 保持稳定的循环速度
                time.sleep(sleep_time)
                
            except Exception as e:
                add_log(f"监控循环异常: {e}", 'error')
                error_count += 1
                consecutive_errors += 1
                
                # 如果连续错误太多，重新初始化
                if consecutive_errors > 10:
                    add_log("连续错误过多，重新初始化系统", 'warning')
                    api = BilibiliAPI(config['sessdata'], config['bili_jct'])
                    consecutive_errors = 0
                    time.sleep(5)
                else:
                    time.sleep(2)
    
    except Exception as e:
        add_log(f"监控系统异常: {e}", 'error')
    finally:
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
    
    if monitoring and monitor_thread and monitor_thread.is_alive():
        return jsonify({'success': False, 'error': '监控已在运行中'})
    
    # 确保之前的线程已停止
    if monitor_thread and monitor_thread.is_alive():
        monitoring = False
        monitor_thread.join(timeout=2)
    
    monitoring = True
    monitor_thread = threading.Thread(target=monitor_messages)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    add_log("开始监控私信", 'success')
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
def stop_monitoring():
    global monitoring, monitor_thread
    
    if not monitoring:
        return jsonify({'success': False, 'error': '监控未运行'})
    
    monitoring = False
    add_log("停止监控私信", 'warning')
    
    # 等待线程结束
    if monitor_thread and monitor_thread.is_alive():
        monitor_thread.join(timeout=3)
    
    return jsonify({'success': True})

@app.route('/api/status')
def get_status():
    return jsonify({
        'monitoring': monitoring,
        'rules_count': len(rules),
        'config_set': bool(config.get('sessdata') and config.get('bili_jct'))
    })

@app.route('/api/logs')
def get_logs():
    recent_logs = logs[-10:] if len(logs) > 10 else logs
    return jsonify({'logs': recent_logs})

if __name__ == '__main__':
    # 启动时加载配置和规则
    load_config()
    load_rules()
    
    print("BiliGo - B站私信自动回复系统启动中...")
    print("请在浏览器中访问: http://localhost:4999")
    
    app.run(host='0.0.0.0', port=4999, debug=False)
