"""Path helpers for development and PyInstaller frozen builds."""
import os
import shutil
import sys

DEFAULT_CONFIG_FILES = (
    'config.json',
    'keywords.json',
    'comment_config.json',
    'comment_keywords.json',
    'comment_rules.json',
    'user_reply_stats.json',
)


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


def get_data_dir():
    env_data = os.environ.get('BILIGO_DATA_DIR', '').strip()
    if env_data:
        return os.path.abspath(env_data)
    return get_exe_dir()


def get_app_root():
    """Writable data directory for configs, exports, and user files."""
    return get_data_dir()


def get_static_root():
    """Directory containing bundled static assets (html/css/js)."""
    return get_resource_dir()


def ensure_data_files():
    """Copy default config templates to the data directory on first run."""
    data_dir = get_data_dir()
    resource_dir = get_resource_dir()
    for name in DEFAULT_CONFIG_FILES:
        dest = os.path.join(data_dir, name)
        src = os.path.join(resource_dir, name)
        if not os.path.exists(dest) and os.path.exists(src):
            shutil.copy2(src, dest)
