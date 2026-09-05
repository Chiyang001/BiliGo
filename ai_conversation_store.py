"""Persistent, platform-isolated conversation memory for AI replies."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from typing import Optional

from app_paths import get_app_root


PLATFORMS = ('bili_message', 'bili_comment', 'douyin', 'xiaohongshu', 'weibo', 'xianyu')


class AiConversationStore:
    """Store only the conversation text required to provide per-user AI context.

    Contact and event identifiers are irreversibly hashed with a local random salt.
    Each exchange is idempotent so monitor retries cannot duplicate the context.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = os.path.join(get_app_root(), 'ai_conversations.sqlite3')
        self._initialized = False
        self._salt = ''

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
                    CREATE TABLE IF NOT EXISTS ai_conversation_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS ai_conversation_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        contact_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        UNIQUE(platform, contact_hash, event_hash, role)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_conversation_contact
                        ON ai_conversation_messages(platform, contact_hash, id DESC);
                ''')
                row = connection.execute(
                    "SELECT value FROM ai_conversation_meta WHERE key = 'hash_salt'"
                ).fetchone()
                if row:
                    self._salt = str(row['value'])
                else:
                    self._salt = secrets.token_hex(24)
                    connection.execute(
                        "INSERT INTO ai_conversation_meta(key, value) VALUES('hash_salt', ?)",
                        (self._salt,),
                    )
            self._initialized = True

    def _hash(self, value: str) -> str:
        return hashlib.sha256(f'{self._salt}|{value}'.encode('utf-8')).hexdigest()

    def _contact_hash(self, platform: str, contact_id: str) -> str:
        return self._hash(f'{platform}|contact|{contact_id}')

    def build_context(self, platform: str, contact_id: str, max_chars: int) -> str:
        if platform not in PLATFORMS or not str(contact_id).strip() or max_chars <= 0:
            return ''
        self.initialize()
        contact_hash = self._contact_hash(platform, str(contact_id).strip())
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                '''SELECT role, content FROM ai_conversation_messages
                   WHERE platform = ? AND contact_hash = ?
                   ORDER BY id DESC LIMIT 100''',
                (platform, contact_hash),
            ).fetchall()
        if not rows:
            return ''
        selected = []
        used = 0
        for row in rows:
            label = '用户' if row['role'] == 'user' else '助手'
            line = f"{label}：{str(row['content']).strip()}"
            if not line.strip('：'):
                continue
            if used + len(line) + 1 > max_chars:
                remaining = max_chars - used - len(label) - 2
                if remaining > 40:
                    selected.append(f'{label}：…{str(row["content"])[-remaining:]}')
                break
            selected.append(line)
            used += len(line) + 1
        selected.reverse()
        return '以下是与当前用户此前已确认发送成功的对话，请保持上下文连贯：\n' + '\n'.join(selected)

    def record_exchange(
        self,
        platform: str,
        contact_id: str,
        user_message: str,
        assistant_message: str,
        event_key: str,
        occurred_at: Optional[int] = None,
    ) -> bool:
        if (
            platform not in PLATFORMS or not str(contact_id).strip()
            or not str(user_message).strip() or not str(assistant_message).strip()
            or not str(event_key).strip()
        ):
            return False
        self.initialize()
        contact_hash = self._contact_hash(platform, str(contact_id).strip())
        event_hash = self._hash(f'{platform}|event|{event_key}')
        timestamp = int(occurred_at or time.time())
        values = (
            ('user', str(user_message).strip()[:8000]),
            ('assistant', str(assistant_message).strip()[:8000]),
        )
        inserted = False
        with self._lock, closing(self._connect()) as connection, connection:
            for role, content in values:
                cursor = connection.execute(
                    '''INSERT OR IGNORE INTO ai_conversation_messages
                       (platform, contact_hash, event_hash, role, content, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (platform, contact_hash, event_hash, role, content, timestamp),
                )
                inserted = inserted or cursor.rowcount > 0
            # Bound local storage without breaking the newest exchanges.
            connection.execute(
                '''DELETE FROM ai_conversation_messages
                   WHERE platform = ? AND contact_hash = ? AND id NOT IN (
                       SELECT id FROM ai_conversation_messages
                       WHERE platform = ? AND contact_hash = ?
                       ORDER BY id DESC LIMIT 100
                   )''',
                (platform, contact_hash, platform, contact_hash),
            )
        return inserted

    def clear_platform(self, platform: str) -> None:
        if platform not in PLATFORMS:
            return
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute('DELETE FROM ai_conversation_messages WHERE platform = ?', (platform,))

    def clear_all(self) -> None:
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute('DELETE FROM ai_conversation_messages')


ai_conversation_store = AiConversationStore()
