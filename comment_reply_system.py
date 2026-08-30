"""
BiliGo 评论自动回复系统模块 (20260830)
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

import bili_wbi
import comment_monitor_helpers
from app_paths import get_app_root

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
            'comment_check_interval': 5,  # 评论检查间隔（秒），默认5秒
            'comment_send_delay': 3.0,  # 评论回复发送间隔（秒），默认3秒避免风控
            'only_reply_new_comments': True,  # 仅回复新评论
            'max_videos_to_check': 50,
            'max_comments_per_video': 20,
            'comment_fetch_gap': 1.0,
            'comment_fetch_mode': 'wbi',
            'comment_monitor_sub_replies': True,
            'max_sub_pages_per_root': 15,
            'comment_main_sort_mode': 3,
            'comment_main_pages_max': 15,
            'video_list_strategy': 'both_ends',
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
        return get_app_root()
    
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
    
    @staticmethod
    def _merge_main_replies(reply_data):
        """合并 /x/v2/reply/main 返回的置顶与主列表"""
        if not reply_data:
            return []
        replies = list(reply_data.get('replies') or [])
        top_obj = reply_data.get('top')
        if isinstance(top_obj, dict):
            top_replies = top_obj.get('upper') or top_obj.get('top') or top_obj.get('admin')
            if isinstance(top_replies, dict):
                top_replies = [top_replies]
            if isinstance(top_replies, list):
                replies = top_replies + replies
        for tr in reply_data.get('top_replies') or []:
            if isinstance(tr, dict) and tr not in replies:
                replies.insert(0, tr)
        return replies

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
            
            # Web 端 arc/search 无 WBI 时返回空；改用 arc/list
            url = 'https://api.bilibili.com/x/space/arc/list'
            params = {
                'mid': uid,
                'pn': page,
                'ps': min(int(page_size), 50),
                'order': 'pubdate',
                'tid': 0,
            }
            
            response = self.bili_api.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') != 0:
                self.add_log(f"获取视频列表失败: {result.get('message', '未知错误')}", 'error')
                return None
            archives = result.get('data', {}).get('archives') or []
            vlist = []
            for a in archives:
                aid = a.get('aid')
                if not aid:
                    continue
                vlist.append({
                    'aid': aid,
                    'bvid': a.get('bvid', ''),
                    'title': a.get('title', '未知视频'),
                })
            return {
                'code': 0,
                'data': {'list': {'vlist': vlist}},
            }
                
        except Exception as e:
            self.add_log(f"获取视频列表异常: {e}", 'error')
            return None
    
    def get_video_comments(self, oid, page=1, page_size=20, bvid=None):
        """获取视频评论（与网页一致的 WBI 接口 /x/v2/reply/wbi/main）"""
        if not self.bili_api:
            return None
        
        mode = (self.config.get('comment_fetch_mode') or 'wbi').strip().lower()
        try:
            if mode == 'browser' and bvid:
                try:
                    from comment_playwright import fetch_reply_json_via_browser
                    br = fetch_reply_json_via_browser(
                        bvid,
                        self.bili_api.sessdata,
                        self.bili_api.bili_jct,
                    )
                    if br and br.get('code') == 0:
                        return bili_wbi.merge_reply_main_data(br.get('data') or {})
                except Exception as e:
                    self.add_log(f"浏览器拉取失败，改用 WBI: {e}", 'warning')
                # 浏览器未成功则继续走 WBI
            cache = getattr(self.bili_api, '_wbi_cache', None)
            if cache is None:
                self.bili_api._wbi_cache = {}
                cache = self.bili_api._wbi_cache
            main_mode = int(self.config.get('comment_main_sort_mode', 3) or 3)
            main_pages = int(self.config.get('comment_main_pages_max', 15) or 15)
            fg = float(self.config.get('comment_fetch_gap', 1.0) or 0)
            return bili_wbi.fetch_main_comment_replies_paged(
                self.bili_api.session,
                oid,
                min(int(page_size), 30),
                bvid,
                cache,
                mode=main_mode,
                max_pages=max(1, main_pages),
                fetch_gap=fg,
            )
        except Exception as e:
            self.add_log(f"获取视频评论异常: {e}", 'error')
            return None
    
    def reply_to_comment(self, oid, root_rpid, message, reply_type='text', image_path='', parent_rpid=None):
        """回复评论。楼中楼时 parent_rpid 为被回复的那条评论 rpid。"""
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
            
            parent = parent_rpid if parent_rpid is not None else root_rpid
            url = 'https://api.bilibili.com/x/v2/reply/add'
            data = {
                'type': 1,  # 视频评论
                'oid': oid,
                'root': root_rpid,
                'parent': parent,
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
            max_videos = int(self.config.get('max_videos_to_check', 50) or 50)
            my_uid = self.bili_api.get_my_uid()
            if not my_uid:
                self.add_log("无法获取用户 UID，跳过本轮", 'error')
                return
            strategy = (self.config.get('video_list_strategy') or 'both_ends').strip().lower()
            videos = comment_monitor_helpers.get_videos_for_monitor(
                self.bili_api.session, int(my_uid), max_videos, strategy
            )
            
            if not videos:
                self.add_log("没有找到视频", 'info')
                return
            
            self.add_log(f"开始检查 {len(videos)} 个视频的评论", 'info')
            processed_count = 0
            replied_count = 0
            
            monitor_sub = self.config.get('comment_monitor_sub_replies', True)
            max_sub_pages = int(self.config.get('max_sub_pages_per_root', 15) or 15)
            wbi_cache = getattr(self.bili_api, '_wbi_cache', None)
            if wbi_cache is None:
                self.bili_api._wbi_cache = {}
                wbi_cache = self.bili_api._wbi_cache
            
            fetch_gap = float(self.config.get('comment_fetch_gap', 1.0) or 0)
            for i, video in enumerate(videos):
                if not self.monitoring:
                    break
                if i > 0 and fetch_gap > 0:
                    time.sleep(fetch_gap)
                
                video_id = video.get('aid')
                video_title = video.get('title', '未知视频')
                vb = video.get('bvid') or None
                
                # 获取视频评论
                max_comments = self.config.get('max_comments_per_video', 20)
                top_list = self.get_video_comments(
                    video_id, page=1, page_size=max_comments, bvid=vb
                )
                
                if not top_list:
                    continue
                
                replies = comment_monitor_helpers.expand_video_comments_for_monitor(
                    self.bili_api.session,
                    wbi_cache,
                    video_id,
                    video_title,
                    vb,
                    top_list,
                    int(my_uid),
                    monitor_sub,
                    max_sub_pages,
                    fetch_gap,
                    sub_ps=20,
                )
                if not replies:
                    continue
                
                # 处理评论
                for reply in replies:
                    if not self.monitoring:
                        break
                    
                    try:
                        comment_id = reply.get('rpid')
                        reply_target = reply.get('reply_target_rpid') or comment_id
                        thread_root = reply.get('thread_root_rpid') or comment_id
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
                        cache_key = f"{video_id}_{reply_target}"
                        if cache_key in self.comment_cache:
                            continue
                        
                        # 标记为已处理
                        self.comment_cache[cache_key] = {
                            'time': comment_time,
                            'processed_at': int(time.time())
                        }
                        processed_count += 1
                        
                        # 不要回复自己的评论
                        if my_uid and commenter_uid == my_uid:
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
                                thread_root,
                                reply_message,
                                reply_type,
                                reply_image,
                                parent_rpid=reply_target,
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
        self.add_log(f"检查间隔: {self.config.get('comment_check_interval', 5)} 秒", 'info')
        self.add_log(f"回复间隔: {self.config.get('comment_send_delay', 3.0)} 秒", 'info')
        
        error_count = 0
        max_errors = 5
        
        while self.monitoring:
            try:
                self.process_comments()
                error_count = 0  # 成功后重置错误计数
                
                # 等待下次检查（支持小数秒；0 表示不等待；分段 sleep 便于及时停止）
                check_interval = float(self.config.get('comment_check_interval', 5))
                self.add_log(f"等待 {check_interval} 秒后进行下一轮检查...", 'info')
                if check_interval > 0 and self.monitoring:
                    end = time.monotonic() + check_interval
                    while self.monitoring and time.monotonic() < end:
                        time.sleep(min(1.0, end - time.monotonic()))
                    
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