"""Bootstrap Playwright for portable dev, Docker, and frozen builds."""
import json
import logging
import os
import subprocess
import sys
import threading

from app_paths import get_exe_dir, get_resource_dir, is_frozen

logger = logging.getLogger(__name__)

_CONFIGURED = False
_READY = False
_LOCK = threading.Lock()


class BrowserRuntimeError(RuntimeError):
    """The browser runtime is unavailable; this is not an expired login session."""


def ensure_browser_display(headless: bool) -> None:
    """Interactive Chromium needs an X11 display on Linux, including VNC/XWayland."""
    if sys.platform.startswith('linux') and not headless and not os.environ.get('DISPLAY', '').strip():
        raise BrowserRuntimeError(
            'Linux 图形登录需要可访问的桌面显示（DISPLAY）。'
            '请在 Linux 桌面或 VNC 会话中启动 BiliGo，并在该桌面的浏览器窗口完成登录；'
            '仅通过 SSH 或网页面板无法操作服务器浏览器。已有登录态可继续使用无头监控。'
        )


def _system_browser_cache():
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    elif sys.platform == 'darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Caches')
    else:
        base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'ms-playwright')


def get_playwright_browsers_dir():
    """Return PLAYWRIGHT_BROWSERS_PATH value for the current runtime."""
    if is_frozen():
        return '0'
    local = os.path.join(get_exe_dir(), 'playwright-browsers')
    # Different Python environments may require different Chromium revisions.
    # Reuse a matching system cache rather than selecting an older local build.
    if _chromium_installed(local):
        return local
    system_cache = _system_browser_cache()
    if _chromium_installed(system_cache):
        return system_cache
    return local


def configure_playwright_env():
    """Set browser lookup path before importing playwright."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', get_playwright_browsers_dir())
    _CONFIGURED = True


def _chromium_installed(browsers_dir: str) -> bool:
    """Require both actual executables for the currently imported Playwright."""
    if browsers_dir == '0':
        browsers_dir = os.path.join(
            get_resource_dir(),
            'playwright',
            'driver',
            'package',
            '.local-browsers',
        )
    if not os.path.isdir(browsers_dir):
        return False
    try:
        import playwright
        package = os.path.join(os.path.dirname(playwright.__file__), 'driver', 'package')
        with open(os.path.join(package, 'browsers.json'), encoding='utf-8') as handle:
            browsers = {item['name']: item for item in json.load(handle)['browsers']}
        executables = {
            'chromium': {'chrome.exe', 'chrome', 'Chromium', 'Google Chrome for Testing'},
            'chromium-headless-shell': {'chrome-headless-shell.exe', 'headless_shell.exe',
                                        'chrome-headless-shell', 'headless_shell'},
        }
        for name, filenames in executables.items():
            item = browsers.get(name)
            if not item:
                return False
            folder = os.path.join(browsers_dir, f"{name.replace('-', '_')}-{item['revision']}")
            if not os.path.isdir(folder):
                return False
            if not any(os.path.isfile(os.path.join(root, file)) and os.path.getsize(os.path.join(root, file)) > 0
                       for root, _, files in os.walk(folder) for file in files if file in filenames):
                return False
        return True
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        return False


def _ensure_playwright_package() -> None:
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        if is_frozen():
            raise BrowserRuntimeError('EXE 未包含 Playwright，请重新构建完整安装包')
        logger.info('正在安装 playwright Python 包...')
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', 'playwright'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import playwright  # noqa: F401


def _install_chromium(browsers_dir: str) -> None:
    env = os.environ.copy()
    env['PLAYWRIGHT_SKIP_BROWSER_GC'] = '1'
    if browsers_dir and browsers_dir != '0':
        env['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir
        os.makedirs(browsers_dir, exist_ok=True)
    logger.info('正在下载 Playwright Chromium 到 %s ...', browsers_dir or 'default')
    cmd = [sys.executable, '-m', 'playwright', 'install', 'chromium']
    # System packages belong to provisioning, not an unattended web service.
    # An administrator can opt in explicitly; install_linux.sh --with-deps is
    # the normal Linux installation path.
    with_deps = os.environ.get('BILIGO_PLAYWRIGHT_WITH_DEPS', '').strip().lower() in ('1', 'true', 'yes')
    if with_deps and not is_frozen():
        cmd.append('--with-deps')
    subprocess.check_call(cmd, env=env, timeout=180)


def ensure_playwright_ready(force_install: bool = False) -> bool:
    """Ensure playwright package and Chromium are available."""
    global _READY
    with _LOCK:
        configure_playwright_env()
        try:
            _ensure_playwright_package()
        except Exception as exc:
            logger.error('安装 playwright 失败: %s', exc)
            return False

        browsers_dir = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
        if force_install or not _chromium_installed(browsers_dir):
            _READY = False
            if is_frozen():
                logger.error('EXE 缺少匹配版本的 Chromium 或 Headless Shell，请重新打包完整浏览器运行时')
                return False
            try:
                _install_chromium(browsers_dir)
            except Exception as exc:
                logger.error('安装 Playwright Chromium 失败: %s', exc)
                return False
            if not _chromium_installed(browsers_dir):
                logger.error('浏览器安装后校验失败：当前 Playwright 对应的 Chromium 和 Headless Shell 仍不完整')
                return False

        _READY = True
        return True
