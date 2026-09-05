"""Persistent queue for AI messages that need a human reply."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from typing import Any, Dict, List, Optional

from app_paths import get_app_root


PLATFORM_NAMES = {
    'bili_message': 'B站私信',
    'bili_comment': 'B站评论',
    'douyin': '抖音私信',
    'xiaohongshu': '小红书私信',
    'weibo': '微博私信',
    'xianyu': '闲鱼消息',
}


class AiHandoffStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = os.path.join(get_app_root(), 'ai_handoffs.sqlite3')
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout = 10000')
        connection.execute('PRAGMA journal_mode = WAL')
        return connection

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            with closing(self._connect()) as connection, connection:
                connection.executescript('''
                    CREATE TABLE IF NOT EXISTS ai_handoffs (
                        id TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        external_key TEXT NOT NULL,
                        sender_name TEXT NOT NULL DEFAULT '',
                        sender_id TEXT NOT NULL DEFAULT '',
                        message_text TEXT NOT NULL,
                        reason TEXT NOT NULL DEFAULT '',
                        target_json TEXT NOT NULL DEFAULT '{}',
                        status TEXT NOT NULL DEFAULT 'pending',
                        reply_text TEXT NOT NULL DEFAULT '',
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        replied_at INTEGER,
                        UNIQUE(platform, external_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_handoffs_status_time
                        ON ai_handoffs(status, created_at DESC);
                ''')
            self._initialized = True

    def add(
        self, platform: str, external_key: str, sender_name: str,
        sender_id: str, message_text: str, reason: str,
        target: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if platform not in PLATFORM_NAMES or not str(external_key).strip() or not str(message_text).strip():
            return None
        self.initialize()
        item_id = uuid.uuid4().hex
        now = int(time.time())
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                '''INSERT OR IGNORE INTO ai_handoffs
                   (id, platform, external_key, sender_name, sender_id, message_text,
                    reason, target_json, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)''',
                (
                    item_id, platform, str(external_key), str(sender_name or '')[:120],
                    str(sender_id or '')[:160], str(message_text)[:4000],
                    str(reason or 'AI 无法确认可靠回复')[:240],
                    json.dumps(target or {}, ensure_ascii=False), now, now,
                ),
            )
            if cursor.rowcount:
                return item_id
            row = connection.execute(
                'SELECT id FROM ai_handoffs WHERE platform = ? AND external_key = ?',
                (platform, str(external_key)),
            ).fetchone()
            return str(row['id']) if row else None

    @staticmethod
    def _public(row: sqlite3.Row, include_target: bool = False) -> Dict[str, Any]:
        item = {
            'id': row['id'],
            'platform': row['platform'],
            'platform_name': PLATFORM_NAMES.get(row['platform'], row['platform']),
            'sender_name': row['sender_name'],
            'message_text': row['message_text'],
            'reason': row['reason'],
            'status': row['status'],
            'reply_text': row['reply_text'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'replied_at': row['replied_at'],
        }
        if include_target:
            try:
                item['_target'] = json.loads(row['target_json'] or '{}')
            except (TypeError, ValueError):
                item['_target'] = {}
            item['_sender_id'] = row['sender_id']
            item['_external_key'] = row['external_key']
        return item

    def list(self, status: str = 'pending', platform: str = '', limit: int = 200) -> List[Dict[str, Any]]:
        self.initialize()
        clauses, params = [], []
        if status in ('pending', 'replied', 'dismissed'):
            clauses.append('status = ?')
            params.append(status)
        if platform in PLATFORM_NAMES:
            clauses.append('platform = ?')
            params.append(platform)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        params.append(max(1, min(500, int(limit))))
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                f'SELECT * FROM ai_handoffs{where} ORDER BY created_at DESC LIMIT ?', params,
            ).fetchall()
        return [self._public(row) for row in rows]

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        self.initialize()
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute('SELECT * FROM ai_handoffs WHERE id = ?', (str(item_id),)).fetchone()
        return self._public(row, include_target=True) if row else None

    def resolve(self, item_id: str, status: str, reply_text: str = '') -> bool:
        if status not in ('replied', 'dismissed'):
            return False
        self.initialize()
        now = int(time.time())
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                '''UPDATE ai_handoffs SET status = ?, reply_text = ?, updated_at = ?, replied_at = ?
                   WHERE id = ? AND status IN ('pending', 'sending') ''',
                (status, str(reply_text or '')[:4000], now, now if status == 'replied' else None, str(item_id)),
            )
            return cursor.rowcount > 0

    def claim(self, item_id: str) -> bool:
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "UPDATE ai_handoffs SET status = 'sending', updated_at = ? WHERE id = ? AND status = 'pending'",
                (int(time.time()), str(item_id)),
            )
            return cursor.rowcount > 0

    def release(self, item_id: str) -> None:
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE ai_handoffs SET status = 'pending', updated_at = ? WHERE id = ? AND status = 'sending'",
                (int(time.time()), str(item_id)),
            )

    def pending_count(self) -> int:
        self.initialize()
        with self._lock, closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM ai_handoffs WHERE status = 'pending'").fetchone()[0])

    def clear_platform(self, platform: str) -> None:
        if platform not in PLATFORM_NAMES:
            return
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute('DELETE FROM ai_handoffs WHERE platform = ?', (platform,))

    def clear_all(self) -> None:
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute('DELETE FROM ai_handoffs')


ai_handoff_store = AiHandoffStore()
