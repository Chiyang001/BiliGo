"""Regression checks for browser revisions and session-error classification."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

DATA = tempfile.TemporaryDirectory(prefix='biligo-runtime-tests-')
os.environ['BILIGO_DATA_DIR'] = DATA.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import playwright  # noqa: E402
import playwright_runtime as runtime  # noqa: E402
from douyin_playwright import DouyinBrowserWorker  # noqa: E402
from douyin_reply_system import DouyinReplySystem  # noqa: E402
from weibo_reply_system import WeiboReplySystem  # noqa: E402
from channels_reply_system import ChannelsReplySystem  # noqa: E402


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        package = self.root / 'fake-playwright'
        (package / 'driver' / 'package').mkdir(parents=True)
        (package / 'driver' / 'package' / 'browsers.json').write_text(json.dumps({'browsers': [
            {'name': 'chromium', 'revision': '7777'},
            {'name': 'chromium-headless-shell', 'revision': '7777'},
        ]}), encoding='utf-8')
        self.cache = self.root / 'browsers'
        for manager in (patch.object(playwright, '__file__', str(package / '__init__.py')),
                        patch.object(runtime, '_CONFIGURED', False),
                        patch.object(runtime, 'get_exe_dir', return_value=str(self.root)),
                        patch.object(runtime, 'is_frozen', return_value=False),
                        patch.dict(os.environ, {'PLAYWRIGHT_BROWSERS_PATH': str(self.cache)})):
            manager.start()
            self.addCleanup(manager.stop)

    def install_fixture(self, root=None, revision='7777', shell=True):
        root = Path(root or self.cache)
        chrome = root / ('chromium-' + revision) / 'bin' / 'chrome.exe'
        chrome.parent.mkdir(parents=True, exist_ok=True)
        chrome.write_bytes(b'fixture browser')
        if shell:
            headless = root / ('chromium_headless_shell-' + revision) / 'bin' / 'chrome-headless-shell.exe'
            headless.parent.mkdir(parents=True, exist_ok=True)
            headless.write_bytes(b'fixture headless browser')

    def test_reject_old_revision_and_missing_or_empty_headless_executable(self):
        self.install_fixture(revision='6666')
        self.assertFalse(runtime._chromium_installed(str(self.cache)))
        self.install_fixture(shell=False)
        self.assertFalse(runtime._chromium_installed(str(self.cache)))
        self.install_fixture()
        self.assertTrue(runtime._chromium_installed(str(self.cache)))
        shell = self.cache / 'chromium_headless_shell-7777' / 'bin' / 'chrome-headless-shell.exe'
        shell.write_bytes(b'')
        self.assertFalse(runtime._chromium_installed(str(self.cache)))

    def test_select_matching_system_cache_but_honor_explicit_directory(self):
        local = self.root / 'playwright-browsers'
        self.install_fixture(local, revision='6666')
        self.install_fixture()
        with patch.object(runtime, '_system_browser_cache', return_value=str(self.cache)):
            self.assertEqual(runtime.get_playwright_browsers_dir(), str(self.cache))
            runtime.configure_playwright_env()
            self.assertEqual(os.environ['PLAYWRIGHT_BROWSERS_PATH'], str(self.cache))
            self.install_fixture(local)
            self.assertEqual(runtime.get_playwright_browsers_dir(), str(local))
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(self.root / 'explicit')
            with patch.object(runtime, '_CONFIGURED', False):
                runtime.configure_playwright_env()
            self.assertEqual(os.environ['PLAYWRIGHT_BROWSERS_PATH'], str(self.root / 'explicit'))

    def test_install_missing_matching_runtime_once_under_concurrency(self):
        self.install_fixture(revision='6666')
        with patch.object(runtime, '_install_chromium', side_effect=lambda _: self.install_fixture()) as install:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: runtime.ensure_playwright_ready(), range(12)))
            self.assertTrue(all(results))
            install.assert_called_once_with(str(self.cache))
        shell = self.cache / 'chromium_headless_shell-7777' / 'bin' / 'chrome-headless-shell.exe'
        shell.unlink()
        with patch.object(runtime, '_install_chromium') as install:
            with self.assertLogs('playwright_runtime', level='ERROR'):
                self.assertFalse(runtime.ensure_playwright_ready())
            install.assert_called_once()

    def test_frozen_missing_runtime_never_invokes_exe_as_python_installer(self):
        resources = self.root / 'resources'
        with patch.object(runtime, 'is_frozen', return_value=True), \
                patch.object(runtime, 'get_resource_dir', return_value=str(resources)), \
                patch.object(runtime, '_CONFIGURED', False), \
                patch.dict(os.environ, {'PLAYWRIGHT_BROWSERS_PATH': '0'}), \
                patch.object(runtime.subprocess, 'check_call') as command:
            with self.assertLogs('playwright_runtime', level='ERROR'):
                self.assertFalse(runtime.ensure_playwright_ready())
            command.assert_not_called()
            self.install_fixture(resources / 'playwright' / 'driver' / 'package' / '.local-browsers')
            self.assertTrue(runtime.ensure_playwright_ready())
            command.assert_not_called()

    def test_installer_uses_current_interpreter_and_preserves_other_revisions(self):
        with patch.object(runtime.subprocess, 'check_call') as command:
            runtime._install_chromium(str(self.cache))
        args, kwargs = command.call_args
        self.assertEqual(args[0][:5], [sys.executable, '-m', 'playwright', 'install', 'chromium'])
        self.assertEqual(kwargs['env']['PLAYWRIGHT_BROWSERS_PATH'], str(self.cache))
        self.assertEqual(kwargs['env']['PLAYWRIGHT_SKIP_BROWSER_GC'], '1')


class WorkerFailureChecks(unittest.TestCase):
    def make_worker(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        worker = DouyinBrowserWorker(str(Path(directory.name) / 'storage.json'))
        worker._playwright = MagicMock()
        return worker

    def test_missing_browser_is_repaired_then_retried_without_touching_storage(self):
        worker = self.make_worker()
        context = MagicMock()
        context.pages = [MagicMock()]
        launch = worker._playwright.chromium.launch_persistent_context
        launch.side_effect = [RuntimeError('Chrome not installed'),
                              RuntimeError("Executable doesn't exist at missing/chrome.exe"), context]
        with patch('douyin_playwright.ensure_playwright_ready', return_value=True) as repair:
            worker._ensure_browser()
        repair.assert_called_once()
        self.assertEqual(launch.call_count, 3)
        self.assertIs(worker._context, context)
        self.assertFalse(Path(worker.storage_path).exists())

    def test_failed_repair_is_an_operational_error_not_logged_out(self):
        worker = self.make_worker()
        worker._playwright.chromium.launch_persistent_context.side_effect = RuntimeError("Executable doesn't exist")
        with patch('douyin_playwright.ensure_playwright_ready', return_value=False), \
                self.assertRaises(runtime.BrowserRuntimeError):
            worker._ensure_browser()
        with patch.object(worker, '_call', side_effect=runtime.BrowserRuntimeError('missing browser')):
            with self.assertRaises(runtime.BrowserRuntimeError):
                worker.check_session_valid()
        with patch.object(worker, '_call', return_value=False):
            self.assertFalse(worker.check_session_valid())

    def test_unrelated_launch_failure_does_not_trigger_download(self):
        worker = self.make_worker()
        worker._playwright.chromium.launch_persistent_context.side_effect = RuntimeError('Profile in use')
        with patch('douyin_playwright.ensure_playwright_ready') as repair, self.assertRaisesRegex(RuntimeError, 'Profile in use'):
            worker._ensure_browser()
        repair.assert_not_called()

    def test_runtime_error_type_survives_worker_queue(self):
        worker = self.make_worker()
        fake_context = MagicMock()
        with patch('playwright.sync_api.sync_playwright', return_value=fake_context), \
                patch.object(worker, '_dispatch', side_effect=runtime.BrowserRuntimeError('missing browser')), \
                self.assertLogs('douyin_playwright', level='ERROR'):
            try:
                with self.assertRaises(runtime.BrowserRuntimeError):
                    worker.check_session_valid()
            finally:
                worker.stop_worker()

    def test_verification_errors_preserve_login_state_on_all_affected_platforms(self):
        for cls in (DouyinReplySystem, WeiboReplySystem, ChannelsReplySystem):
            with self.subTest(platform=cls.__name__), tempfile.TemporaryDirectory() as directory:
                system = cls()
                system.storage_file = str(Path(directory) / 'storage.json')
                Path(system.storage_file).write_text('{"cookies": []}', encoding='utf-8')
                system.config.update(logged_in=True, session_expired=False)
                browser = MagicMock()
                browser.check_session_valid.side_effect = runtime.BrowserRuntimeError('matching browser unavailable')
                with patch.object(system, '_ensure_browser', return_value=browser), \
                        patch.object(system, '_storage_has_session_cookies', return_value=False), \
                        patch.object(system, 'save_config') as save, patch.object(system, 'add_log'), \
                        self.assertLogs(level='WARNING') if cls is DouyinReplySystem else nullcontext():
                    system.verify_session(background=False)
                self.assertTrue(system.config['logged_in'])
                self.assertFalse(system.config['session_expired'])
                save.assert_not_called()
                self.assertEqual(Path(system.storage_file).read_text(), '{"cookies": []}')


    def test_actual_authentication_rejection_still_marks_session_expired(self):
        for cls in (DouyinReplySystem, WeiboReplySystem, ChannelsReplySystem):
            with self.subTest(platform=cls.__name__), tempfile.TemporaryDirectory() as directory:
                system = cls()
                system.storage_file = str(Path(directory) / 'storage.json')
                Path(system.storage_file).write_text('{"cookies": []}', encoding='utf-8')
                system.config.update(logged_in=True, session_expired=False)
                browser = MagicMock()
                browser.check_session_valid.return_value = False
                with patch.object(system, '_ensure_browser', return_value=browser), \
                        patch.object(system, '_storage_has_session_cookies', return_value=False), \
                        patch.object(system, '_has_persistent_profile', return_value=False, create=True), \
                        patch.object(system, 'save_config') as save, patch.object(system, 'add_log'):
                    system.verify_session(background=False)
                self.assertFalse(system.config['logged_in'])
                self.assertTrue(system.config['session_expired'])
                save.assert_called()


def real_browser_smoke():
    from playwright.sync_api import sync_playwright
    runtime.configure_playwright_env()
    assert runtime.ensure_playwright_ready(), 'Browser runtime is not ready'
    with tempfile.TemporaryDirectory(prefix='biligo-browser-smoke-') as profile, sync_playwright() as api:
        context = api.chromium.launch_persistent_context(profile, headless=True)
        try:
            page = context.new_page()
            page.set_content('<title>BiliGo runtime smoke</title><p>Local browser test</p>')
            assert page.title() == 'BiliGo runtime smoke'
            print('Headless browser launch passed:', context.browser.version, flush=True)
        finally:
            context.close()


if __name__ == '__main__':
    try:
        if '--smoke-browser' in sys.argv:
            real_browser_smoke()
        else:
            unittest.main(verbosity=2)
    finally:
        DATA.cleanup()
