"""Linux entry-point isolation and optional real service startup checks."""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import playwright_runtime as runtime  # noqa: E402


def bash_path():
    git_bash = Path('C:/Program Files/Git/bin/bash.exe')
    return str(git_bash) if os.name == 'nt' and git_bash.is_file() else shutil.which('bash')


def shell_path(path):
    value = path.as_posix()
    if os.name == 'nt' and len(value) > 2 and value[1] == ':':
        return '/' + value[0].lower() + value[2:]
    return value


class LinuxRuntimeChecks(unittest.TestCase):
    def test_interactive_login_requires_display_but_headless_does_not(self):
        with patch.object(runtime.sys, 'platform', 'linux'), patch.dict(os.environ, {'DISPLAY': ''}):
            runtime.ensure_browser_display(True)
            with self.assertRaisesRegex(runtime.BrowserRuntimeError, 'DISPLAY'):
                runtime.ensure_browser_display(False)
        with patch.object(runtime.sys, 'platform', 'linux'), patch.dict(os.environ, {'DISPLAY': ':1'}):
            runtime.ensure_browser_display(False)
        with patch.object(runtime.sys, 'platform', 'win32'), patch.dict(os.environ, {'DISPLAY': ''}):
            runtime.ensure_browser_display(False)

    def test_browser_repair_does_not_install_system_packages_without_opt_in(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runtime.subprocess, 'check_call') as command, \
                patch.object(runtime, 'is_frozen', return_value=False), \
                patch.dict(os.environ, {'BILIGO_PLAYWRIGHT_WITH_DEPS': ''}):
            runtime._install_chromium(directory)
            self.assertNotIn('--with-deps', command.call_args.args[0])
            os.environ['BILIGO_PLAYWRIGHT_WITH_DEPS'] = '1'
            runtime._install_chromium(directory)
            self.assertIn('--with-deps', command.call_args.args[0])


@unittest.skipUnless(bash_path(), 'Bash is required for entry-point checks')
class LinuxEntryPointChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='biligo linux paths ')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.project = self.root / 'project with spaces'
        (self.project / 'deploy' / 'linux').mkdir(parents=True)
        for name in ('start.sh', 'install_linux.sh', 'deploy/linux/environment.sh'):
            shutil.copyfile(ROOT / name, self.project / name)
        self.venv = self.project / '.venv-linux'
        (self.venv / 'bin').mkdir(parents=True)
        self.capture = self.root / 'invocation.txt'
        fake_python = self.venv / 'bin' / 'python'
        fake_python.write_text(
            '#!/usr/bin/env bash\n'
            'printf "%s\\n" "$BILIGO_DATA_DIR" "$PLAYWRIGHT_BROWSERS_PATH" '
            '"$BILIGO_OPEN_BROWSER" "$PWD" "$(umask)" "$@" > "$BILIGO_TEST_CAPTURE"\n',
            encoding='utf-8', newline='\n',
        )
        fake_python.chmod(0o755)
        self.env = os.environ.copy()
        for name in ('BILIGO_DATA_DIR', 'BILIGO_VENV_DIR', 'PLAYWRIGHT_BROWSERS_PATH',
                     'BILIGO_OPEN_BROWSER', 'DISPLAY'):
            self.env.pop(name, None)
        self.env.update(
            XDG_DATA_HOME=shell_path(self.root / 'xdg data'),
            XDG_CACHE_HOME=shell_path(self.root / 'xdg cache'),
            BILIGO_TEST_CAPTURE=self.capture.as_posix(),
        )

    def start(self):
        # Emulate uname only on the Windows development host; Linux runs natively.
        script = 'exec bash "$@"'
        if os.name == 'nt':
            script = 'uname() { echo Linux; }; export -f uname; ' + script
        return subprocess.run(
            [bash_path(), '-c', script, 'biligo-test',
             (self.project / 'start.sh').as_posix(), '--version'],
            env=self.env, cwd=self.root, capture_output=True, text=True, timeout=15,
        )

    def test_start_from_other_directory_with_spaces_uses_separate_xdg_data(self):
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.capture.read_text(encoding='utf-8').splitlines()
        # Git Bash represents Windows paths as /c/...; compare suffixes there.
        self.assertTrue(values[0].endswith('/xdg data/biligo-linux'), values)
        self.assertTrue(values[1].endswith('/xdg cache/biligo-linux/ms-playwright'), values)
        self.assertEqual(values[2], '0')
        self.assertTrue(values[3].endswith('/project with spaces'), values)
        self.assertEqual(values[4], '0077')
        self.assertTrue(values[5].endswith('/project with spaces/launcher.py'), values)
        self.assertEqual(values[6:], ['--version'])
        self.assertTrue((self.root / 'xdg data' / 'biligo-linux').is_dir())
        self.assertFalse((self.project / 'config.json').exists())

    def test_explicit_paths_and_browser_preference_survive_desktop_start(self):
        self.env.update(BILIGO_DATA_DIR='custom data', PLAYWRIGHT_BROWSERS_PATH='custom cache',
                        DISPLAY=':1', BILIGO_OPEN_BROWSER='0')
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.capture.read_text(encoding='utf-8').splitlines()
        self.assertTrue(values[0].endswith('/project with spaces/custom data'), values)
        self.assertTrue(values[1].endswith('/project with spaces/custom cache'), values)
        self.assertEqual(values[2], '0')
        self.env.pop('BILIGO_OPEN_BROWSER')
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.capture.read_text(encoding='utf-8').splitlines()[2], '1')

    def test_missing_environment_fails_before_starting_application(self):
        (self.venv / 'bin' / 'python').unlink()
        result = self.start()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('install_linux.sh', result.stderr)
        self.assertFalse(self.capture.exists())


def smoke_server():
    if not sys.platform.startswith('linux'):
        raise SystemExit('The real Linux startup smoke check must run on Linux.')
    with tempfile.TemporaryDirectory(prefix='biligo-linux-startup-') as directory:
        data = Path(directory) / 'data'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        env.update(BILIGO_DATA_DIR=str(data), BILIGO_OPEN_BROWSER='0', PORT=str(port))
        env.pop('BILIGO_PANEL_PASSWORD', None)
        # Keep the generated initial password out of CI output.
        with (Path(directory) / 'server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(['bash', str(ROOT / 'start.sh')], cwd=directory,
                                       env=env, stdout=log, stderr=log, start_new_session=True)
            try:
                deadline = time.monotonic() + 45
                while True:
                    if process.poll() is not None:
                        raise AssertionError(f'Linux entry point exited early: {process.returncode}')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                            assert response.read().strip() == b'ok'
                        break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() >= deadline:
                            raise AssertionError('Linux server did not become healthy within 45 seconds')
                        time.sleep(0.2)
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/api/config', timeout=3)
                except urllib.error.HTTPError as exc:
                    assert exc.code == 401, exc.code
                else:
                    raise AssertionError('Configuration API was accessible without panel login')
                assert (data / '.biligo_web_auth.sqlite3').is_file()
                assert (data / 'config.json').is_file()
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    raise AssertionError('Linux service did not stop after SIGTERM')
        print('Linux entry point: health, password gate, isolated data and shutdown passed.')


if __name__ == '__main__':
    if '--smoke-server' in sys.argv:
        smoke_server()
    else:
        unittest.main(verbosity=2)
