# -*- mode: python ; coding: utf-8 -*-
import json
import os
import sys

import playwright
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

sys.path.insert(0, SPECPATH)
from app_version import APP_VERSION, APP_VERSION_DATE, EXE_BASENAME, WINDOWS_VERSION

windows_version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=WINDOWS_VERSION, prodvers=WINDOWS_VERSION),
    kids=[
        StringFileInfo([StringTable('080404B0', [
            StringStruct('CompanyName', '炽阳001'),
            StringStruct('FileDescription', f'BiliGo {APP_VERSION}'),
            StringStruct('FileVersion', '.'.join(map(str, WINDOWS_VERSION))),
            StringStruct('InternalName', 'BiliGo'),
            StringStruct('LegalCopyright', 'Copyright © 2026 炽阳001'),
            StringStruct('OriginalFilename', EXE_BASENAME + '.exe'),
            StringStruct('ProductName', 'BiliGo'),
            StringStruct('ProductVersion', APP_VERSION),
            StringStruct('Comments', f'Security update · {APP_VERSION_DATE}'),
        ])]),
        VarFileInfo([VarStruct('Translation', [2052, 1200])]),
    ],
)


def collect_playwright_browser_datas():
    """Bundle Playwright Chromium into .local-browsers for frozen exe (PLAYWRIGHT_BROWSERS_PATH=0)."""
    ms_root = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ms-playwright')
    pkg_root = os.path.join(os.path.dirname(playwright.__file__), 'driver', 'package')
    with open(os.path.join(pkg_root, 'browsers.json'), encoding='utf-8') as f:
        browsers_meta = json.load(f)

    folder_names = {
        'chromium': 'chromium',
        'chromium-headless-shell': 'chromium_headless_shell',
        'ffmpeg': 'ffmpeg',
    }
    dest_base = os.path.join('playwright', 'driver', 'package', '.local-browsers')
    datas = []
    missing = []

    for item in browsers_meta.get('browsers', []):
        name = item.get('name')
        if name not in folder_names or not item.get('installByDefault'):
            continue
        folder = f"{folder_names[name]}-{item.get('revision')}"
        src_root = os.path.join(ms_root, folder)
        if not os.path.isdir(src_root):
            missing.append(folder)
            continue
        for root, _, files in os.walk(src_root):
            for fn in files:
                src_file = os.path.join(root, fn)
                rel_dir = os.path.dirname(os.path.relpath(src_file, src_root))
                dest_dir = os.path.normpath(os.path.join(dest_base, folder, rel_dir))
                datas.append((src_file, dest_dir))

    if missing:
        raise SystemExit(
            'Missing Playwright browsers: ' + ', '.join(missing) +
            '\nRun: python -m pip install playwright && playwright install chromium'
        )
    return datas


block_cipher = None

datas = [
    ('index.html', '.'),
    ('comment_reply.html', '.'),
    ('logs.html', '.'),
    ('docs.html', '.'),
    ('douyin_reply.html', '.'),
    ('xiaohongshu_reply.html', '.'),
    ('xianyu_reply.html', '.'),
    ('ai_reply.html', '.'),
    ('dashboard.html', '.'),
    ('style.css', '.'),
    ('comment_style.css', '.'),
    ('logs_style.css', '.'),
    ('docs_style.css', '.'),
    ('douyin_style.css', '.'),
    ('douyin_theme.css', '.'),
    ('xiaohongshu_theme.css', '.'),
    ('weibo_theme.css', '.'),
    ('xianyu_theme.css', '.'),
    ('channels_theme.css', '.'),
    ('ai_reply.css', '.'),
    ('dashboard.css', '.'),
    ('platform_tabs.css', '.'),
    ('script.js', '.'),
    ('comment_script.js', '.'),
    ('logs_script.js', '.'),
    ('docs_script.js', '.'),
    ('douyin_script.js', '.'),
    ('xiaohongshu_script.js', '.'),
    ('ai_mode.js', '.'),
    ('ai_reply.js', '.'),
    ('dashboard.js', '.'),
    ('platform_tabs.js', '.'),
    ('platform_import.js', '.'),
    ('platform_log_view.js', '.'),
    ('web_auth.js', '.'),
    ('web_auth.css', '.'),
    ('panel_login.html', '.'),
    ('panel_security.html', '.'),
    ('panel_auth.css', '.'),
    ('panel_login.js', '.'),
    ('panel_security.js', '.'),
    ('panel_theme.js', '.'),
    ('developer-avatar.png', '.'),
    ('tik-tok.png', '.'),
    ('xiaohongshu-seeklogo.png', '.'),
    ('sina-weibo-seeklogo.png', '.'),
    ('bilibili.png', '.'),
    ('openai.png', '.'),
    ('xianyu.jpg', '.'),
    ('weixin_channels.png', '.'),
    ('视频号.png', '.'),
    ('icons8-人-50.png', '.'),
    ('icons8-知识库-50.png', '.'),
    ('icons8-设置-50.png', '.'),
    ('docker/defaults/config.json', '.'),
    ('docker/defaults/keywords.json', '.'),
    ('docker/defaults/comment_config.json', '.'),
    ('docker/defaults/comment_keywords.json', '.'),
    ('docker/defaults/comment_rules.json', '.'),
    ('docker/defaults/user_reply_stats.json', '.'),
    ('docker/defaults/douyin_config.json', '.'),
    ('docker/defaults/douyin_keywords.json', '.'),
    ('docker/defaults/xiaohongshu_config.json', '.'),
    ('docker/defaults/xiaohongshu_keywords.json', '.'),
    ('docker/defaults/weibo_config.json', '.'),
    ('docker/defaults/weibo_keywords.json', '.'),
    ('docker/defaults/xianyu_config.json', '.'),
    ('docker/defaults/xianyu_keywords.json', '.'),
    ('docker/defaults/channels_config.json', '.'),
    ('docker/defaults/channels_keywords.json', '.'),
]
datas += collect_playwright_browser_datas()

hiddenimports = [
    'flask',
    'werkzeug',
    'jinja2',
    'click',
    'itsdangerous',
    'markupsafe',
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    'bili_wbi',
    'ai_handoff_store',
    'ai_conversation_store',
    'ai_reply_service',
    'dashboard_metrics',
    'comment_monitor_helpers',
    'comment_reply_system',
    'comment_playwright',
    'douyin_reply_system',
    'douyin_playwright',
    'xiaohongshu_reply_system',
    'xiaohongshu_playwright',
    'weibo_reply_system',
    'weibo_playwright',
    'xianyu_reply_system',
    'xianyu_playwright',
    'channels_reply_system',
    'channels_playwright',
    'playwright_runtime',
    'web_access',
    'web_files',
    'app_version',
    'playwright.sync_api',
]

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=EXE_BASENAME,
    version=windows_version_info,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
