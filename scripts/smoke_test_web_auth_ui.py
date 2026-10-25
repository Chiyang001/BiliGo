"""Real-browser coverage for the password gate, remembered devices and settings."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

DATA = tempfile.TemporaryDirectory()
os.environ['BILIGO_DATA_DIR'] = DATA.name
os.environ['BILIGO_PANEL_PASSWORD'] = 'BiliGo-browser-test-password'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    password = os.environ['BILIGO_PANEL_PASSWORD']
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            device = browser.new_context(viewport={'width': 1280, 'height': 900}, color_scheme='light')
            page = device.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin + '/dashboard?from=bili_message', wait_until='networkidle')
            assert '/login?' in page.url
            assert page.title() == '登录面板 · BiliGo'
            assert page.get_by_role('checkbox').is_checked() is False
            assert device.request.get(origin + '/api/config').status == 401
            assert page.locator('html').get_attribute('data-theme-preference') == 'system'
            for removed in ('你的账号与配置，仅在登录后可见', '私密工作空间', '多平台协作 · 自动回复 · AI 客服'):
                assert removed not in page.locator('body').text_content()
            page.emulate_media(color_scheme='dark')
            expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
            page.locator('.login-card').evaluate('async (node) => Promise.all(node.getAnimations().map(animation => animation.finished))')
            page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-login-dark.png'))
            page.get_by_role('button', name='明亮模式', exact=True).click()
            assert page.locator('html').get_attribute('data-theme') == 'light'
            page.reload(wait_until='networkidle')
            assert page.locator('html').get_attribute('data-theme') == 'light', 'Manual choice must persist'
            page.get_by_role('button', name='黑暗模式', exact=True).click()
            page.emulate_media(color_scheme='light')
            assert page.locator('html').get_attribute('data-theme') == 'dark', 'Manual choice must override system'
            page.get_by_role('button', name='跟随系统', exact=True).click()
            assert page.locator('html').get_attribute('data-theme') == 'light'
            assert page.get_by_alt_text('炽阳001 的 GitHub 头像').evaluate('(image) => image.complete && image.naturalWidth > 0')
            page.locator('#panel-password').fill('visibility-check')
            page.get_by_role('button', name='显示密码', exact=True).click()
            assert page.locator('#panel-password').get_attribute('type') == 'text'
            assert page.locator('#toggle-password .eye-open').is_visible()
            assert page.locator('#toggle-password .eye-closed').is_hidden()
            page.get_by_role('button', name='隐藏密码', exact=True).click()
            assert page.locator('#panel-password').get_attribute('type') == 'password'
            assert page.locator('#toggle-password .eye-closed').is_visible()
            page.locator('#panel-password').fill('')
            page.get_by_role('button', name='忘记密码？').click()
            assert page.locator('#login-help-text').is_visible()
            page.get_by_role('button', name='忘记密码？').click()
            assert page.locator('#login-help-text').is_hidden()
            page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-login.png'))
            page.locator('#panel-password').fill('wrong-password')
            page.get_by_role('button', name='登录面板').click()
            page.get_by_role('alert').filter(has_text='面板密码错误').wait_for()
            page.locator('#panel-password').fill(password)
            page.get_by_role('checkbox').check()
            page.get_by_role('button', name='登录面板').click()
            page.wait_for_url(origin + '/dashboard?from=bili_message')
            page.get_by_role('link', name='面板安全').wait_for()
            cookie = next(item for item in device.cookies() if item['name'] == 'biligo_session')
            assert cookie['httpOnly'] and cookie['expires'] > 0
            state = device.storage_state()
            assert password not in json.dumps(state)
            assert all(item['name'] == 'biligo:auth-theme' for entry in state['origins'] for item in entry['localStorage']), 'Only appearance preferences may be stored in localStorage'

            # Restore just this browser's remembered cookie, without a new login.
            restored = browser.new_context(storage_state=state)
            restored_page = restored.new_page()
            restored_page.goto(origin + '/comment', wait_until='networkidle')
            assert restored_page.url.split('#')[0] == origin + '/comment', restored_page.url

            stranger = browser.new_context(viewport={'width': 390, 'height': 844}, color_scheme='light')
            stranger_page = stranger.new_page()
            stranger_page.goto(origin + '/comment', wait_until='networkidle')
            assert '/login?' in stranger_page.url
            assert stranger.request.get(origin + '/api/config').status == 401
            assert stranger_page.locator('#login-submit').is_visible()
            assert stranger_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            stranger_page.locator('.login-card').evaluate('async (node) => Promise.all(node.getAnimations().map(animation => animation.finished))')
            stranger_page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-login-mobile.png'), full_page=True)
            stranger_page.get_by_role('button', name='黑暗模式', exact=True).click()
            expect(stranger_page.get_by_role('button', name='黑暗模式', exact=True)).to_have_attribute('aria-pressed', 'true')
            stranger_page.locator('body').evaluate('async (node) => Promise.all(node.getAnimations({subtree: true}).filter(animation => animation.effect.getComputedTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {})))')
            stranger_page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-login-mobile-dark.png'), full_page=True)
            stranger_page.set_viewport_size({'width': 320, 'height': 720})
            assert stranger_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            stranger_page.emulate_media(reduced_motion='reduce')
            assert stranger_page.locator('.orbit-trail').evaluate('(node) => getComputedStyle(node).animationName') == 'none'

            page.goto(origin + '/', wait_until='domcontentloaded')
            page.set_viewport_size({'width': 1920, 'height': 1080})
            security_link = page.get_by_role('link', name='面板安全', exact=True)
            security_link.wait_for()
            expect(security_link).to_have_css('display', 'flex')
            security_box = security_link.bounding_box()
            status_box = page.locator('.header-actions .status-indicator').bounding_box()
            assert security_box['width'] < 170
            assert 0 <= security_box['x'] - (status_box['x'] + status_box['width']) <= 14
            page.locator('.header-actions').screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-panel-security-toolbar.png'))
            page.set_viewport_size({'width': 1280, 'height': 900})
            filename = "file'><img id=file-xss-marker src=x onerror=window.fileXss=true>.png"
            page.evaluate('items => displayFileList(items)', [{
                'name': filename, 'type': 'image', 'path': filename,
                'extension': 'PNG', 'size': '1 KB',
            }])
            assert page.locator('#file-list .file-name').text_content() == filename
            assert page.locator('#file-xss-marker').count() == 0
            assert page.evaluate('window.fileXss !== true')

            # All platform pages must load their JS and retain the panel controls.
            for path in ('/', '/comment', '/douyin', '/xiaohongshu', '/weibo', '/xianyu', '/channels', '/ai-reply', '/logs.html', '/docs.html'):
                response = page.goto(origin + path, wait_until='domcontentloaded')
                assert response.ok, path
                assert page.get_by_role('link', name='面板安全', exact=True).count() == 1, path
                assert page.locator('header').get_by_role('button', name='退出面板', exact=True).count() == 0, path

            page.goto(origin + '/panel-security', wait_until='networkidle')
            page.locator('.security-card').evaluate('async (node) => Promise.all(node.getAnimations().map(animation => animation.finished))')
            page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-password.png'), full_page=True)
            page.get_by_role('button', name='黑暗模式', exact=True).click()
            page.locator('body').evaluate('async (node) => Promise.all(node.getAnimations({subtree: true}).filter(animation => animation.effect.getComputedTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {})))')
            page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-password-dark.png'), full_page=True)
            page.get_by_role('button', name='跟随系统', exact=True).click()
            page.get_by_role('button', name='显示新密码', exact=True).click()
            assert page.locator('#new-password').get_attribute('type') == 'text'
            assert page.locator('[data-toggle-password="new-password"] .eye-open').is_visible()
            page.get_by_role('button', name='隐藏新密码', exact=True).click()
            assert page.locator('[data-toggle-password="new-password"] .eye-closed').is_visible()
            page.locator('#current-password').fill(password)
            page.locator('#new-password').fill('New-browser-test-password')
            page.locator('#confirm-password').fill('mismatched-password')
            page.locator('#password-submit').click()
            page.get_by_role('alert').filter(has_text='两次输入的新密码不一致').wait_for()
            page.locator('#current-password').fill('wrong-password')
            page.locator('#confirm-password').fill('New-browser-test-password')
            page.locator('#password-submit').click()
            page.get_by_role('alert').filter(has_text='当前面板密码错误').wait_for()
            assert page.url.endswith('/panel-security')
            page.locator('#current-password').fill(password)
            page.locator('#password-submit').click()
            page.wait_for_url(origin + '/login')
            assert restored.request.get(origin + '/api/config').status == 401
            assert device.request.get(origin + '/api/config').status == 401

            page.locator('#panel-password').fill('New-browser-test-password')
            page.get_by_role('button', name='登录面板').click()
            page.wait_for_url(origin + '/')
            page.get_by_role('link', name='面板安全', exact=True).click()
            page.locator('#panel-logout').click()
            page.wait_for_url(origin + '/login')
            page.go_back(wait_until='networkidle')
            assert '/login' in page.url

            # An initial password permits only setup, including with remember checked.
            store = app.extensions['biligo_web_auth']
            with patch.dict(os.environ, {'BILIGO_PANEL_PASSWORD': ''}), patch('builtins.print'):
                store.reset_to_initial_password()
            with store.connect() as db:
                initial = db.execute('SELECT initial_password FROM credentials').fetchone()[0]
            first_device = browser.new_context(viewport={'width': 480, 'height': 900})
            first_page = first_device.new_page()
            first_page.on('pageerror', lambda error: errors.append(str(error)))
            first_page.goto(origin + '/login', wait_until='networkidle')
            first_page.locator('#panel-password').fill(initial)
            first_page.get_by_role('checkbox').check()
            first_page.locator('#login-submit').click()
            first_page.wait_for_url(origin + '/panel-security?setup=1')
            first_page.get_by_role('heading', name='设置你的面板密码', exact=True).wait_for()
            assert first_page.locator('#security-back').is_hidden()
            assert first_device.request.get(origin + '/api/config').status == 428
            cookie = next(item for item in first_device.cookies() if item['name'] == 'biligo_session')
            assert cookie['expires'] == -1
            first_page.goto(origin + '/', wait_until='networkidle')
            assert '/panel-security?setup=1' in first_page.url
            first_page.locator('.security-card').evaluate('async (node) => Promise.all(node.getAnimations().map(animation => animation.finished))')
            first_page.screenshot(path=str(Path(__file__).resolve().parents[1] / '.codex-security-password-setup.png'), full_page=True)
            first_page.locator('#current-password').fill(initial)
            first_page.locator('#new-password').fill(initial)
            first_page.locator('#confirm-password').fill(initial)
            first_page.locator('#password-submit').click()
            first_page.get_by_role('alert').filter(has_text='新密码不能与当前密码相同').wait_for()
            first_page.locator('#new-password').fill('MyPass88')
            first_page.locator('#confirm-password').fill('MyPass88')
            first_page.locator('#password-submit').click()
            first_page.wait_for_url(origin + '/login')
            first_page.locator('#panel-password').fill('MyPass88')
            first_page.locator('#login-submit').click()
            first_page.wait_for_url(lambda url: url.split('#')[0] == origin + '/')
            assert first_device.request.get(origin + '/api/config').status == 200
            assert not errors, errors
            browser.close()
        print('Panel password browser smoke tests passed')
    finally:
        server.shutdown()
        server.server_close()
        DATA.cleanup()


if __name__ == '__main__':
    main()
