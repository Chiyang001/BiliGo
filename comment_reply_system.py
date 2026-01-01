"""
BiliGo 评论自动回复系统模块
独立的评论回复功能，与私信回复系统并行运行
"""

import json
import os
import threading
import time
import requests
from datetime import datetime
import logging
import hashlib
from collections import defaultdict

# 配置日志
logger = logging.getLogger(__name__)

class CommentReplySystem:
    def __init__(self):
        self.config = {
            'comment_reply_enabled': False,
            'default_comment_reply_enabled': False,
            'default_comment_reply_message': '感谢您的评论！',
            'default_comment_reply_type': 'text',
            'default_comment_reply_image': '',
            'comment_check_interval': 60,  # 评论检查间隔（秒），默认60秒
            'comment_send_delay': 3.0,  # 评论回复发送间隔（秒），默认3秒避免风控
            'only_reply_new_comments': True,  # 仅回复新评论
            'max_videos_to_check': 10,  # 最多检查的视频数量
            'max_comments_per_video': 20,  # 每个视频最多检查的评论数
        }
        
        self.rules = []  # 评论回复规则
        self.monitoring = False
        self.monitor_thread = None
        self.logs = []
        self.comment_cache = {}  # 评论缓存
        self.last_comment_times = defaultdict(int)
        self.last_send_time = 0
        self.program_start_time = int(time.time())
        
        # 配置文件路径
        self.config_file = None
        self.rules_file = None
        
        # B站API实例
        self.bili_api = None
        
    def get_config_file_path(self, filename):
        """获取配置文件路径，确保跨平台兼容"""
        app_root = self.get_app_root()
        return os.path.join(app_root, filename)
    
    def get_app_root(self):
        """获取应用根目录"""
        if hasattr(self, '_app_root'):
            return self._app_root
        
        # 尝试多种方式获取应用根目录
        possible_roots = [
            os.path.dirname(os.path.abspath(__file__)),
            os.getcwd(),
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ]
        
        for root in possible_roots:
            if os.path.exists(os.path.join(root, 'app.py')):
                self._app_root = root
                return root
        
        # 如果都找不到，使用当前目录
        self._app_root = os.getcwd()
        return self._app_root
    
    def init_config_paths(self):
        """初始化配置文件路径"""
        if self.config_file is None:
            self.config_file = self.get_config_file_path('comment_config.json')
        if self.rules_file is None:
            self.rules_file = self.get_config_file_path('comment_keywords.json')
    
    def load_config(self):
        """加载评论回复配置"""
        self.init_config_paths()
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
                logger.info("评论回复配置加载成功")
            else:
                logger.info("评论回复配置文件不存在，使用默认配置")
        except Exception as e:
            logger.error(f"加载评论回复配置失败: {e}")
    
    def save_config(self):
        """保存评论回复配置"""
        self.init_config_paths()
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("评论回复配置保存成功")
            return True
        except Exception as e:
            logger.error(f"保存评论回复配置失败: {e}")
            return False
    
    def load_rules(self):
        """加载评论回复规则"""
        self.init_config_paths()
        try:
            if os.path.exists(self.rules_file):
                with open(self.rules_file, 'r', encoding='utf-8') as f:
                    self.rules = json.load(f)
                logger.info(f"评论回复规则加载成功，共 {len(self.rules)} 条规则")
            else:
                self.rules = []
                logger.info("评论回复规则文件不存在，使用空规则列表")
        except Exception as e:
            logger.error(f"加载评论回复规则失败: {e}")
            self.rules = []
    
    def save_rules(self):
        """保存评论回复规则"""
        self.init_config_paths()
        try:
            os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
            with open(self.rules_file, 'w', encoding='utf-8') as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
            logger.info(f"评论回复规则保存成功，共 {len(self.rules)} 条规则")
            return True
        except Exception as e:
            logger.error(f"保存评论回复规则失败: {e}")
            return False
    
    def set_bili_api(self, bili_api):
        """设置B站API实例"""
        self.bili_api = bili_api
    
    def add_log(self, message, log_type='info'):
        """添加日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'message': f"[评论回复] {message}",
            'type': log_type
        }
        self.logs.append(log_entry)
        
        # 限制日志数量
        if len(self.logs) > 100:
            self.logs = self.logs[-50:]
        
        # 同时输出到控制台
        if log_type == 'error':
            logger.error(f"[评论回复] {message}")
        elif log_type == 'warning':
            logger.warning(f"[评论回复] {message}")
        else:
            logger.info(f"[评论回复] {message}")
    
    def get_logs(self):
        """获取日志"""
        return self.logs.copy()
    
    def clear_logs(self):
        """清空日志"""
        self.logs.clear()
    
    def match_comment_rule(self, comment_text):
        """匹配评论回复规则 - 改进版"""
        if not comment_text:
            return None
        
        comment_text_lower = comment_text.strip().lower()
        
        # 按优先级排序规则（可以根据规则的匹配度或创建时间排序）
        enabled_rules = [rule for rule in self.rules if rule.get('enabled', True)]
        
        for rule in enabled_rules:
            keywords_str = rule.get('keyword', '')
            if not keywords_str:
                continue
            
            # 支持中文逗号和英文逗号分隔
            keywords = [k.strip() for k in keywords_str.replace('，', ',').split(',')]
            
            for keyword in keywords:
                if not keyword:
                    continue
                
                keyword_lower = keyword.lower()
                
                # 精确匹配或包含匹配
                if keyword_lower in comment_text_lower:
                    self.add_log(f"匹配到关键词: '{keyword}' 在规则 '{rule.get('name', '未命名')}'", 'info')
                    return rule
        
        return None
    
    def get_my_videos(self, page=1, page_size=10):
        """获取我的视频列表 - 改进版"""
        if not self.bili_api:
            return None
        
        try:
            # 获取用户UID
            uid = self.bili_api.get_my_uid()
            if not uid:
                self.add_log("无法获取用户UID", 'error')
                return None
            
            # 使用更稳定的API接口
            url = 'https://api.bilibili.com/x/space/arc/search'
            params = {
                'mid': uid,
                'pn': page,
                'ps': page_size,
                'order': 'pubdate',  # 按发布时间排序
                'jsonp': 'jsonp'
            }
            
            response = self.bili_api.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                return result
            else:
                self.add_log(f"获取视频列表失败: {result.get('message', '未知错误')}", 'error')
                return None
                
        except Exception as e:
            self.add_log(f"获取视频列表异常: {e}", 'error')
            return None
    
    def get_video_comments(self, oid, page=1, page_size=20):
        """获取视频评论 - 改进版"""
        if not self.bili_api:
            return None
        
        try:
            url = 'https://api.bilibili.com/x/v2/reply'
            params = {
                'type': 1,  # 1表示视频评论
                'oid': oid,  # 视频的aid
                'pn': page,
                'ps': page_size,
                'sort': 2  # 2表示按时间排序，0表示按热度
            }
            
            response = self.bili_api.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                return result
            else:
                error_msg = result.get('message', '未知错误')
                # 只在非正常错误时记录日志
                if result.get('code') != 12002:  # 12002表示评论区已关闭
                    self.add_log(f"获取评论失败 (oid={oid}): {error_msg}", 'warning')
                return None
                
        except Exception as e:
            self.add_log(f"获取视频评论异常: {e}", 'error')
            return None
    
    def reply_to_comment(self, oid, root_rpid, message, reply_type='text', image_path=''):
        """回复评论"""
        if not self.bili_api:
            return False
        
        try:
            # 发送间隔控制
            current_time = time.time()
            send_interval = self.config.get('comment_send_delay', 2.0)
            if current_time - self.last_send_time < send_interval:
                wait_time = send_interval - (current_time - self.last_send_time)
                self.add_log(f"评论回复间隔控制，等待 {wait_time:.1f} 秒", 'info')
                time.sleep(wait_time)
            
            url = 'https://api.bilibili.com/x/v2/reply/add'
            data = {
                'type': 1,  # 视频评论
                'oid': oid,
                'root': root_rpid,
                'parent': root_rpid,
                'message': message,
                'csrf': self.bili_api.bili_jct
            }
            
            response = self.bili_api.session.post(url, data=data, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            # 更新最后发送时间
            self.last_send_time = time.time()
            
            if result.get('code') == 0:
                self.add_log(f"评论回复成功: {message[:50]}...", 'success')
                return True
            else:
                error_msg = result.get('message', '未知错误')
                self.add_log(f"评论回复失败: {error_msg}", 'error')
                return False
                
        except Exception as e:
            self.add_log(f"评论回复异常: {e}", 'error')
            return False
    
    def process_comments(self):
        """处理评论回复 - 完全重构版"""
        if not self.bili_api:
            self.add_log("B站API未初始化", 'error')
            return
        
        try:
            # 获取我的视频列表
            max_videos = self.config.get('max_videos_to_check', 10)
            videos_data = self.get_my_videos(page=1, page_size=max_videos)
            
            if not videos_data or videos_data.get('code') != 0:
                self.add_log("获取视频列表失败", 'warning')
                return
            
            videos = videos_data.get('data', {}).get('list', {}).get('vlist', [])
            if not videos:
                self.add_log("没有找到视频", 'info')
                return
            
            self.add_log(f"开始检查 {len(videos)} 个视频的评论", 'info')
            processed_count = 0
            replied_count = 0
            
            # 处理每个视频的评论
            for video in videos:
                if not self.monitoring:
                    break
                
                video_id = video.get('aid')
                video_title = video.get('title', '未知视频')
                
                # 获取视频评论
                max_comments = self.config.get('max_comments_per_video', 20)
                comments_data = self.get_video_comments(video_id, page=1, page_size=max_comments)
                
                if not comments_data or comments_data.get('code') != 0:
                    continue
                
                replies = comments_data.get('data', {}).get('replies', [])
                if not replies:
                    continue
                
                # 处理评论
                for reply in replies:
                    if not self.monitoring:
                        break
                    
                    try:
                        comment_id = reply.get('rpid')
                        comment_text = reply.get('content', {}).get('message', '')
                        comment_time = reply.get('ctime', 0)
                        commenter = reply.get('member', {})
                        commenter_name = commenter.get('uname', '未知用户')
                        commenter_uid = commenter.get('mid', 0)
                        
                        # 检查是否为新评论
                        if self.config.get('only_reply_new_comments', True):
                            if comment_time < self.program_start_time:
                                continue
                        
                        # 检查是否已处理过
                        cache_key = f"{video_id}_{comment_id}"
                        if cache_key in self.comment_cache:
                            continue
                        
                        # 标记为已处理
                        self.comment_cache[cache_key] = {
                            'time': comment_time,
                            'processed_at': int(time.time())
                        }
                        processed_count += 1
                        
                        # 不要回复自己的评论
                        my_uid = self.bili_api.get_my_uid()
                        if commenter_uid == my_uid:
                            continue
                        
                        self.add_log(f"检测到评论: {commenter_name} 在《{video_title}》: {comment_text[:30]}...", 'info')
                        
                        # 匹配回复规则
                        matched_rule = self.match_comment_rule(comment_text)
                        reply_message = None
                        reply_type = 'text'
                        reply_image = ''
                        
                        if matched_rule:
                            reply_message = matched_rule.get('reply', '')
                            reply_type = matched_rule.get('reply_type', 'text')
                            reply_image = matched_rule.get('reply_image', '')
                            self.add_log(f"匹配到规则: {matched_rule.get('name', '未命名规则')}", 'success')
                        elif self.config.get('default_comment_reply_enabled', False):
                            reply_message = self.config.get('default_comment_reply_message', '感谢您的评论！')
                            reply_type = self.config.get('default_comment_reply_type', 'text')
                            reply_image = self.config.get('default_comment_reply_image', '')
                            self.add_log("使用默认评论回复", 'info')
                        
                        # 发送回复
                        if reply_message:
                            success = self.reply_to_comment(
                                video_id, 
                                comment_id, 
                                reply_message, 
                                reply_type,
                                reply_image
                            )
                            
                            if success:
                                replied_count += 1
                                self.add_log(f"✅ 成功回复 {commenter_name}", 'success')
                            else:
                                self.add_log(f"❌ 回复 {commenter_name} 失败", 'error')
                        
                        # 短暂休息避免频率过高
                        time.sleep(1)
                        
                    except Exception as e:
                        self.add_log(f"处理评论时出错: {e}", 'error')
                        continue
                
                # 视频间休息
                time.sleep(2)
            
            # 清理过期缓存（保留最近1小时的）
            self.cleanup_comment_cache()
            
            if processed_count > 0:
                self.add_log(f"本轮检查完成: 处理 {processed_count} 条评论，回复 {replied_count} 条", 'info')
                
        except Exception as e:
            self.add_log(f"处理评论异常: {e}", 'error')
    
    def cleanup_comment_cache(self):
        """清理过期的评论缓存"""
        try:
            current_time = int(time.time())
            expired_keys = []
            
            for key, value in self.comment_cache.items():
                if isinstance(value, dict):
                    processed_at = value.get('processed_at', 0)
                    # 保留最近1小时的缓存
                    if current_time - processed_at > 3600:
                        expired_keys.append(key)
                else:
                    # 旧格式的缓存，也清理掉
                    if current_time - value > 3600:
                        expired_keys.append(key)
            
            for key in expired_keys:
                del self.comment_cache[key]
            
            if expired_keys:
                self.add_log(f"清理了 {len(expired_keys)} 条过期评论缓存", 'info')
                
        except Exception as e:
            logger.error(f"清理评论缓存失败: {e}")
    
    def monitor_comments(self):
        """评论监控主循环 - 改进版"""
        self.add_log("🚀 评论自动回复监控已启动", 'success')
        self.add_log(f"检查间隔: {self.config.get('comment_check_interval', 60)} 秒", 'info')
        self.add_log(f"回复间隔: {self.config.get('comment_send_delay', 3.0)} 秒", 'info')
        
        error_count = 0
        max_errors = 5
        
        while self.monitoring:
            try:
                self.process_comments()
                error_count = 0  # 成功后重置错误计数
                
                # 等待下次检查
                check_interval = self.config.get('comment_check_interval', 60)
                self.add_log(f"等待 {check_interval} 秒后进行下一轮检查...", 'info')
                
                for _ in range(check_interval):
                    if not self.monitoring:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                error_count += 1
                self.add_log(f"评论监控异常 ({error_count}/{max_errors}): {e}", 'error')
                
                if error_count >= max_errors:
                    self.add_log(f"连续错误次数过多，停止监控", 'error')
                    self.monitoring = False
                    break
                
                time.sleep(10)  # 出错后等待10秒再继续
        
        self.add_log("⏹️ 评论自动回复监控已停止", 'warning')
    
    def start_monitoring(self):
        """启动评论监控"""
        if self.monitoring:
            return False, "评论监控已在运行中"
        
        if not self.bili_api:
            return False, "B站API未初始化"
        
        try:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_comments, daemon=True)
            self.monitor_thread.start()
            return True, "评论监控启动成功"
        except Exception as e:
            self.monitoring = False
            return False, f"启动评论监控失败: {e}"
    
    def stop_monitoring(self):
        """停止评论监控"""
        if not self.monitoring:
            return False, "评论监控未在运行"
        
        try:
            self.monitoring = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5)
            return True, "评论监控停止成功"
        except Exception as e:
            return False, f"停止评论监控失败: {e}"
    
    def is_monitoring(self):
        """检查是否正在监控"""
        return self.monitoring
    
    def get_status(self):
        """获取系统状态"""
        return {
            'monitoring': self.monitoring,
            'rules_count': len(self.rules),
            'config': self.config.copy()
        }
    
    def import_from_message_config(self, message_config, message_rules):
        """从私信配置导入设置"""
        try:
            # 导入基础配置
            if message_config.get('default_reply_enabled'):
                self.config['default_comment_reply_enabled'] = True
                self.config['default_comment_reply_message'] = message_config.get('default_reply_message', '感谢您的评论！')
                self.config['default_comment_reply_type'] = message_config.get('default_reply_type', 'text')
                self.config['default_comment_reply_image'] = message_config.get('default_reply_image', '')
            
            # 导入规则
            imported_rules = []
            for rule in message_rules:
                comment_rule = {
                    'id': rule.get('id', int(time.time() * 1000)),
                    'name': f"[导入] {rule.get('name', '未命名规则')}",
                    'keyword': rule.get('keyword', ''),
                    'reply': rule.get('reply', ''),
                    'reply_type': rule.get('reply_type', 'text'),
                    'reply_image': rule.get('reply_image', ''),
                    'enabled': rule.get('enabled', True),
                    'created_at': datetime.now().isoformat()
                }
                imported_rules.append(comment_rule)
            
            self.rules.extend(imported_rules)
            
            # 保存配置和规则
            self.save_config()
            self.save_rules()
            
            self.add_log(f"成功导入私信配置，共导入 {len(imported_rules)} 条规则", 'success')
            return True, f"成功导入 {len(imported_rules)} 条规则"
            
        except Exception as e:
            self.add_log(f"导入私信配置失败: {e}", 'error')
            return False, f"导入失败: {e}"

# 全局评论回复系统实例
comment_reply_system = CommentReplySystem()