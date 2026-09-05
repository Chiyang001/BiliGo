"""Privacy-preserving operational metrics for the unified dashboard."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app_paths import get_app_root


PLATFORMS = ('bili_message', 'bili_comment', 'douyin', 'xiaohongshu', 'weibo', 'xianyu')
EVENT_TYPES = ('inbound', 'reply_success', 'reply_failure')
PLATFORM_NAMES = {
    'bili_message': 'B站私信',
    'bili_comment': 'B站评论',
    'douyin': '抖音私信',
    'xiaohongshu': '小红书私信',
    'weibo': '微博私信',
    'xianyu': '闲鱼消息',
}


class DashboardMetrics:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = os.path.join(get_app_root(), 'dashboard_metrics.sqlite3')
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
                    CREATE TABLE IF NOT EXISTS dashboard_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS dashboard_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        occurred_at INTEGER NOT NULL,
                        day TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_key_hash TEXT NOT NULL,
                        contact_hash TEXT,
                        reply_mode TEXT NOT NULL DEFAULT '',
                        UNIQUE(platform, event_type, event_key_hash)
                    );
                    CREATE INDEX IF NOT EXISTS idx_dashboard_events_day
                        ON dashboard_events(day, platform, event_type);
                    CREATE INDEX IF NOT EXISTS idx_dashboard_events_time
                        ON dashboard_events(occurred_at);
                    CREATE TABLE IF NOT EXISTS dashboard_legacy (
                        platform TEXT PRIMARY KEY,
                        reply_count INTEGER NOT NULL DEFAULT 0,
                        contact_count INTEGER NOT NULL DEFAULT 0
                    );
                ''')
                salt_row = connection.execute(
                    "SELECT value FROM dashboard_meta WHERE key = 'hash_salt'"
                ).fetchone()
                if salt_row:
                    self._salt = salt_row['value']
                else:
                    self._salt = secrets.token_hex(24)
                    connection.execute(
                        "INSERT INTO dashboard_meta(key, value) VALUES('hash_salt', ?)",
                        (self._salt,),
                    )
                migrated = connection.execute(
                    "SELECT value FROM dashboard_meta WHERE key = 'legacy_migrated'"
                ).fetchone()
                if not migrated:
                    self._migrate_legacy(connection)
                    connection.execute(
                        "INSERT INTO dashboard_meta(key, value) VALUES('legacy_migrated', ?)",
                        (str(int(time.time())),),
                    )
            self._initialized = True

    def _migrate_legacy(self, connection: sqlite3.Connection) -> None:
        files = {
            'bili_message': 'user_reply_stats.json',
            'douyin': 'douyin_user_reply_stats.json',
            'xiaohongshu': 'xiaohongshu_user_reply_stats.json',
            'weibo': 'weibo_user_reply_stats.json',
            'xianyu': 'xianyu_user_reply_stats.json',
        }
        for platform in PLATFORMS:
            records: Dict[str, Any] = {}
            filename = files.get(platform)
            if filename:
                try:
                    with open(os.path.join(get_app_root(), filename), 'r', encoding='utf-8') as stream:
                        loaded = json.load(stream)
                        records = loaded if isinstance(loaded, dict) else {}
                except (OSError, ValueError, TypeError):
                    records = {}
            reply_count = sum(max(0, int((row or {}).get('count') or 0)) for row in records.values())
            connection.execute(
                'INSERT OR REPLACE INTO dashboard_legacy(platform, reply_count, contact_count) VALUES(?, ?, ?)',
                (platform, reply_count, len(records)),
            )

    def _hash(self, value: str) -> str:
        return hashlib.sha256(f'{self._salt}|{value}'.encode('utf-8')).hexdigest()

    def record(
        self,
        platform: str,
        event_type: str,
        event_key: str,
        contact_id: str = '',
        reply_mode: str = '',
        occurred_at: Optional[int] = None,
    ) -> bool:
        if platform not in PLATFORMS or event_type not in EVENT_TYPES or not str(event_key):
            return False
        self.initialize()
        timestamp = int(occurred_at or time.time())
        event_hash = self._hash(f'{platform}|{event_type}|{event_key}')
        contact_hash = self._hash(f'{platform}|contact|{contact_id}') if str(contact_id) else None
        day = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                '''INSERT OR IGNORE INTO dashboard_events
                   (occurred_at, day, platform, event_type, event_key_hash, contact_hash, reply_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (timestamp, day, platform, event_type, event_hash, contact_hash, str(reply_mode or '')),
            )
            return cursor.rowcount > 0

    def clear_platform(self, platform: str) -> None:
        if platform not in PLATFORMS:
            return
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute('DELETE FROM dashboard_events WHERE platform = ?', (platform,))
            connection.execute(
                'UPDATE dashboard_legacy SET reply_count = 0, contact_count = 0 WHERE platform = ?',
                (platform,),
            )

    def clear_all(self) -> None:
        self.initialize()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute('DELETE FROM dashboard_events')
            connection.execute('UPDATE dashboard_legacy SET reply_count = 0, contact_count = 0')

    @staticmethod
    def _range_start(range_key: str) -> Optional[str]:
        days = {'7d': 7, '30d': 30, '90d': 90}.get(range_key)
        if not days:
            return None
        return (datetime.now().date() - timedelta(days=days - 1)).isoformat()

    def snapshot(self, range_key: str, statuses: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        self.initialize()
        if range_key not in ('7d', '30d', '90d', 'all'):
            range_key = '30d'
        start_day = self._range_start(range_key)
        today = datetime.now().date()
        with self._lock, closing(self._connect()) as connection, connection:
            if range_key == 'all':
                first = connection.execute('SELECT MIN(day) AS day FROM dashboard_events').fetchone()['day']
                start_day = first or today.isoformat()
            params = (start_day,) if start_day else ()
            where = 'WHERE day >= ?' if start_day else ''
            rows = connection.execute(
                f'''SELECT day, platform,
                    SUM(CASE WHEN event_type = 'inbound' THEN 1 ELSE 0 END) AS inbound,
                    SUM(CASE WHEN event_type = 'reply_success' THEN 1 ELSE 0 END) AS success,
                    SUM(CASE WHEN event_type = 'reply_failure' THEN 1 ELSE 0 END) AS failure
                    FROM dashboard_events {where}
                    GROUP BY day, platform ORDER BY day''', params,
            ).fetchall()
            contact_rows = connection.execute(
                f'''SELECT platform, COUNT(DISTINCT contact_hash) AS contacts
                    FROM dashboard_events {where} AND contact_hash IS NOT NULL
                    GROUP BY platform''' if where else
                '''SELECT platform, COUNT(DISTINCT contact_hash) AS contacts
                   FROM dashboard_events WHERE contact_hash IS NOT NULL GROUP BY platform''',
                params,
            ).fetchall()
            last_rows = connection.execute(
                'SELECT platform, MAX(occurred_at) AS last_activity FROM dashboard_events GROUP BY platform'
            ).fetchall()
            legacy_rows = connection.execute('SELECT * FROM dashboard_legacy').fetchall()

        contacts = {row['platform']: int(row['contacts']) for row in contact_rows}
        last_activity = {row['platform']: int(row['last_activity'] or 0) for row in last_rows}
        legacy = {row['platform']: int(row['reply_count']) for row in legacy_rows}
        per_platform = {key: {'inbound': 0, 'success': 0, 'failure': 0} for key in PLATFORMS}
        by_day: Dict[str, Dict[str, int]] = {}
        for row in rows:
            values = {name: int(row[name] or 0) for name in ('inbound', 'success', 'failure')}
            by_day.setdefault(row['day'], {'inbound': 0, 'success': 0, 'failure': 0})
            for name, value in values.items():
                by_day[row['day']][name] += value
                per_platform[row['platform']][name] += value

        start_date = datetime.strptime(start_day or today.isoformat(), '%Y-%m-%d').date()
        series = []
        cursor = start_date
        while cursor <= today:
            day = cursor.isoformat()
            series.append({'date': day, **by_day.get(day, {'inbound': 0, 'success': 0, 'failure': 0})})
            cursor += timedelta(days=1)

        platforms = []
        alerts = []
        for key in PLATFORMS:
            metrics = per_platform[key]
            status = dict(statuses.get(key) or {})
            attempts = metrics['success'] + metrics['failure']
            success_rate = round(metrics['success'] * 100 / attempts, 1) if attempts else 0
            state = status.get('state', 'unknown')
            if state in ('session_expired', 'not_configured', 'unknown'):
                alerts.append({'platform': key, 'level': 'warning', 'message': status.get('message') or f'{PLATFORM_NAMES[key]}状态异常'})
            elif attempts >= 5 and success_rate < 80:
                alerts.append({'platform': key, 'level': 'error', 'message': f'{PLATFORM_NAMES[key]}近期回复成功率偏低'})
            platforms.append({
                'id': key,
                'name': PLATFORM_NAMES[key],
                'state': state,
                'state_label': status.get('state_label', '状态未知'),
                'message': status.get('message', ''),
                'rules_count': int(status.get('rules_count') or 0),
                'account_count': int(status.get('account_count') or 0),
                'inbound': metrics['inbound'],
                'success': metrics['success'],
                'failure': metrics['failure'],
                'contacts': contacts.get(key, 0),
                'success_rate': success_rate,
                'last_activity': last_activity.get(key),
                'legacy_replies': legacy.get(key, 0),
            })

        total_inbound = sum(item['inbound'] for item in per_platform.values())
        total_success = sum(item['success'] for item in per_platform.values())
        total_failure = sum(item['failure'] for item in per_platform.values())
        total_attempts = total_success + total_failure
        return {
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'range': {'key': range_key, 'start': start_day, 'end': today.isoformat()},
            'summary': {
                'total_replies': sum(legacy.values()) + self._all_recorded_success(),
                'period_inbound': total_inbound,
                'period_success': total_success,
                'period_failure': total_failure,
                'success_rate': round(total_success * 100 / total_attempts, 1) if total_attempts else 0,
                'running_platforms': sum(1 for value in statuses.values() if value.get('state') == 'running'),
            },
            'series': series,
            'platforms': platforms,
            'alerts': alerts,
        }

    def _all_recorded_success(self) -> int:
        with self._lock, closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM dashboard_events WHERE event_type = 'reply_success'"
            ).fetchone()
            return int(row['count'] or 0)


dashboard_metrics = DashboardMetrics()


def record_dashboard_event(
    platform: str,
    event_type: str,
    event_key: str,
    contact_id: str = '',
    reply_mode: str = '',
    occurred_at: Optional[int] = None,
) -> bool:
    """Non-throwing instrumentation hook for monitor threads."""
    try:
        return dashboard_metrics.record(platform, event_type, event_key, contact_id, reply_mode, occurred_at)
    except Exception:
        return False
