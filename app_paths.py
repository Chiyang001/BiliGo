"""Path helpers for development and PyInstaller frozen builds."""
import logging
import os
import shutil
import sys

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILES = (
    'config.json',
    'keywords.json',
    'comment_config.json',
    'comment_keywords.json',
    'comment_rules.json',
    'user_reply_stats.json',
    'douyin_config.json',
    'douyin_keywords.json',
    'xiaohongshu_config.json',
    'xiaohongshu_keywords.json',
    'weibo_config.json',
    'weibo_keywords.json',
    'xianyu_config.json',
    'xianyu_keywords.json',
    'channels_config.json',
    'channels_keywords.json',
)

LEGACY_DATA_DIRS = (
    'ai_knowledge',
    'export',
    'douyin_browser_profile',
    'xiaohongshu_browser_profile',
    'weibo_browser_profile',
    'xianyu_browser_profile',
    'channels_browser_profile',
    'douyin_media',
)

LEGACY_DATA_FILES = (
    'douyin_storage.json',
    'ai_conversations.sqlite3',
    'ai_handoffs.sqlite3',
    '.biligo_web_token',
)

MIGRATION_MARKER = '.legacy_exe_dir_migrated'


def is_frozen():
    return getattr(sys, 'frozen', False)


def get_exe_dir():
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir():
    if is_frozen():
        return sys._MEIPASS
    return get_exe_dir()


def _default_persistent_data_dir():
    """Packaged builds store user data outside the EXE and PyInstaller temp dir."""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'BiliGo')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'BiliGo')
    return os.path.join(os.path.expanduser('~'), '.local', 'share', 'BiliGo')


def get_data_dir():
    env_data = os.environ.get('BILIGO_DATA_DIR', '').strip()
    if env_data:
        return os.path.abspath(env_data)
    if is_frozen():
        return _default_persistent_data_dir()
    return get_exe_dir()


def get_app_root():
    """Writable data directory for configs, exports, and user files."""
    return get_data_dir()


def get_static_root():
    """Directory containing bundled static assets (html/css/js)."""
    return get_resource_dir()


def _copy_if_missing(src, dest):
    if os.path.exists(dest) or not os.path.exists(src):
        return False
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    return True


def migrate_legacy_data_dir():
    """Copy user data from the EXE directory into the persistent data directory."""
    if not is_frozen():
        return
    if os.environ.get('BILIGO_DATA_DIR', '').strip():
        return

    data_dir = get_data_dir()
    exe_dir = get_exe_dir()
    if os.path.normcase(os.path.abspath(data_dir)) == os.path.normcase(os.path.abspath(exe_dir)):
        return

    os.makedirs(data_dir, exist_ok=True)
    migrated_any = False

    for name in DEFAULT_CONFIG_FILES:
        src = os.path.join(exe_dir, name)
        dest = os.path.join(data_dir, name)
        if _copy_if_missing(src, dest):
            migrated_any = True
            logger.info('已迁移配置文件: %s -> %s', src, dest)

    for name in LEGACY_DATA_FILES:
        src = os.path.join(exe_dir, name)
        dest = os.path.join(data_dir, name)
        if _copy_if_missing(src, dest):
            migrated_any = True
            logger.info('已迁移数据文件: %s -> %s', src, dest)

    for name in LEGACY_DATA_DIRS:
        src = os.path.join(exe_dir, name)
        dest = os.path.join(data_dir, name)
        if _copy_if_missing(src, dest):
            migrated_any = True
            logger.info('已迁移数据目录: %s -> %s', src, dest)

    marker = os.path.join(data_dir, MIGRATION_MARKER)
    if migrated_any or not os.path.exists(marker):
        with open(marker, 'w', encoding='utf-8') as marker_file:
            marker_file.write(exe_dir)
        logger.info('用户数据目录: %s (原 EXE 目录: %s)', data_dir, exe_dir)


def ensure_data_files():
    """Copy default config templates to the data directory on first run."""
    migrate_legacy_data_dir()
    data_dir = get_data_dir()
    resource_dir = get_resource_dir()
    for name in DEFAULT_CONFIG_FILES:
        dest = os.path.join(data_dir, name)
        src = os.path.join(resource_dir, name)
        if not os.path.exists(dest) and os.path.exists(src):
            shutil.copy2(src, dest)
