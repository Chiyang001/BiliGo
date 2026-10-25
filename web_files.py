"""Explicit UI asset allowlist and filesystem boundaries for web file access."""
import os
from pathlib import Path

from flask import abort, send_from_directory

from app_paths import get_data_dir, get_static_root

PUBLIC_ASSETS = frozenset({
    'index.html', 'comment_reply.html', 'logs.html', 'docs.html', 'douyin_reply.html',
    'xiaohongshu_reply.html', 'xianyu_reply.html', 'ai_reply.html', 'dashboard.html',
    'style.css', 'comment_style.css', 'logs_style.css', 'docs_style.css', 'douyin_style.css',
    'douyin_theme.css', 'xiaohongshu_theme.css', 'weibo_theme.css', 'xianyu_theme.css',
    'channels_theme.css', 'ai_reply.css', 'dashboard.css', 'platform_tabs.css',
    'script.js', 'comment_script.js', 'logs_script.js', 'docs_script.js', 'douyin_script.js',
    'xiaohongshu_script.js', 'ai_mode.js', 'ai_reply.js', 'dashboard.js', 'platform_tabs.js',
    'platform_import.js', 'platform_log_view.js', 'web_auth.js', 'web_auth.css', 'panel_security.js',
    'tik-tok.png', 'xiaohongshu-seeklogo.png', 'sina-weibo-seeklogo.png', 'bilibili.png',
    'openai.png', 'xianyu.jpg', 'weixin_channels.png', '视频号.png',
    'icons8-人-50.png', 'icons8-知识库-50.png', 'icons8-设置-50.png',
})
IMAGE_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'})


def is_path_within(root, path):
    """Resolve symlinks/junctions before checking the directory boundary."""
    try:
        root = os.path.normcase(os.path.realpath(root))
        path = os.path.normcase(os.path.realpath(path))
        return os.path.commonpath([root, path]) == root
    except (OSError, ValueError):
        return False


def public_asset_path(filename):
    root = get_static_root()
    if filename not in PUBLIC_ASSETS or not is_path_within(root, os.path.join(root, filename)):
        abort(404)
    return os.path.join(root, filename)


def serve_public_asset(filename):
    path = public_asset_path(filename)
    return send_from_directory(os.path.dirname(path), os.path.basename(path))


def get_image_root():
    configured = os.environ.get('BILIGO_IMAGE_ROOT', '').strip()
    root = os.path.abspath(configured) if configured else os.path.join(get_data_dir(), 'images')
    os.makedirs(root, exist_ok=True)
    return os.path.realpath(root)


def resolve_image_path(value='', directory=False):
    root = get_image_root()
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('无效的图片路径')
    value = value.strip()
    if value.startswith(('\\\\', '//')) or '..' in value.replace('\\', '/').split('/'):
        raise ValueError('只能访问指定图片目录内的文件')
    _, tail = os.path.splitdrive(value)
    if ':' in tail:
        raise ValueError('无效的图片路径')
    path = os.path.realpath(value if os.path.isabs(value) else os.path.join(root, value))
    if not is_path_within(root, path):
        raise ValueError('只能访问指定图片目录内的文件')
    if directory:
        if not os.path.isdir(path):
            raise ValueError('图片文件夹不存在')
    elif not os.path.isfile(path) or Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError('请选择图片目录中的有效图片')
    return path


def image_mime(path):
    """Do not return arbitrary file contents merely because of an image suffix."""
    with open(path, 'rb') as handle:
        header = handle.read(16)
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if header.startswith(b'BM'):
        return 'image/bmp'
    if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        return 'image/webp'
    raise ValueError('文件内容不是支持的图片格式')
