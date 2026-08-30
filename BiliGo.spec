# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

datas = [
    ('index.html', '.'),
    ('comment_reply.html', '.'),
    ('logs.html', '.'),
    ('docs.html', '.'),
    ('style.css', '.'),
    ('comment_style.css', '.'),
    ('logs_style.css', '.'),
    ('docs_style.css', '.'),
    ('script.js', '.'),
    ('comment_script.js', '.'),
    ('logs_script.js', '.'),
    ('docs_script.js', '.'),
    ('config.json', '.'),
    ('keywords.json', '.'),
    ('comment_config.json', '.'),
    ('comment_keywords.json', '.'),
    ('comment_rules.json', '.'),
    ('user_reply_stats.json', '.'),
]

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
    'comment_monitor_helpers',
    'comment_reply_system',
    'comment_playwright',
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
    name='BiliGo',
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
