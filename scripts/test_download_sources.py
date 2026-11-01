"""Isolated mirror-policy tests; optional real wheel/browser download smoke check."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'deploy/linux/download-sources.sh'


@unittest.skipUnless(sys.platform.startswith('linux'), 'Download policy uses Linux Bash')
class DownloadSourceChecks(unittest.TestCase):
    def bash(self, script):
        return subprocess.run(['bash', '-c', 'set -euo pipefail; source "$1"; ' + script,
                               'biligo-download-test', str(HELPER)], capture_output=True, text=True, timeout=10)

    def test_auto_orders_all_domestic_sources_before_official(self):
        result = self.bash('biligo_apt_mirrors auto; biligo_pip_indexes auto; biligo_browser_hosts auto')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'china', 'official', 'https://pypi.tuna.tsinghua.edu.cn/simple', 'https://pypi.org/simple',
            'https://cdn.npmmirror.com/binaries/playwright', 'official'])

    def test_apt_fallback_changes_only_temporary_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '''
work=$2; calls=()
write_apt_sources() { printf 'deb https://%s.example test main\n' "$1" > "$work/sources.list"; }
apt-get() { calls+=("$selected"); [[ $selected == official ]]; }
biligo_update_apt_sources auto http
[[ $selected == official && ${calls[*]} == 'china official' ]]
grep -qx 'deb http://official.example test main' "$work/sources.list"
'''
            result = subprocess.run(['bash', '-c', 'set -euo pipefail; source "$1"; ' + script,
                                     'biligo-download-test', str(HELPER), directory],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_pip_prefers_china_even_if_apt_selected_official_and_records_fallback(self):
        result = self.bash('''
selected=official; calls=()
fake_python() { calls+=("$*"); [[ "$*" == *https://pypi.org/simple* ]]; }
biligo_install_python_dependencies fake_python requirements.txt auto
[[ ${#calls[@]} == 2 && ${calls[0]} == *pypi.tuna.tsinghua.edu.cn* && $pip_index == https://pypi.org/simple ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pip_success_stops_before_official(self):
        result = self.bash('''
calls=0
fake_python() { calls=$((calls + 1)); return 0; }
biligo_install_python_dependencies fake_python requirements.txt auto
[[ $calls == 1 && $pip_index == https://pypi.tuna.tsinghua.edu.cn/simple ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_browser_fallback_clears_download_host_and_preserves_proxy_and_cache(self):
        result = self.bash('''
calls=()
runuser() { calls+=("$*"); [[ "$*" != *PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com* ]]; }
biligo_install_chromium python '/test cache' '/test home' auto '' http://127.0.0.1:7890
[[ ${#calls[@]} == 2 && -z $browser_host ]]
[[ ${calls[0]} == *PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright* ]]
[[ ${calls[1]} == *'env -u PLAYWRIGHT_DOWNLOAD_HOST'* && ${calls[1]} != *PLAYWRIGHT_DOWNLOAD_HOST=https* ]]
[[ ${calls[1]} == *'-u PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST'* ]]
[[ ${calls[1]} == *'PLAYWRIGHT_BROWSERS_PATH=/test cache'* && ${calls[1]} == *HTTPS_PROXY=http://127.0.0.1:7890* ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_custom_overrides_do_not_silently_fall_back(self):
        result = self.bash('''
calls=0
fake_python() { calls=$((calls + 1)); [[ "$*" == *https://custom.example/simple* ]]; return 1; }
if biligo_install_python_dependencies fake_python requirements.txt auto https://custom.example/simple; then exit 9; fi
[[ $calls == 1 ]]
calls=0
runuser() { calls=$((calls + 1)); [[ "$*" == *PLAYWRIGHT_DOWNLOAD_HOST=https://custom.example/browser* ]]; return 1; }
if biligo_install_chromium python cache home auto https://custom.example/browser; then exit 9; fi
[[ $calls == 1 ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fixed_china_and_official_modes_have_no_other_sources(self):
        result = self.bash('biligo_apt_mirrors china; biligo_pip_indexes china; biligo_browser_hosts china; '
                           'biligo_apt_mirrors official; biligo_pip_indexes official; biligo_browser_hosts official')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'china', 'https://pypi.tuna.tsinghua.edu.cn/simple', 'https://cdn.npmmirror.com/binaries/playwright',
            'official', 'https://pypi.org/simple', 'official'])

    def test_all_failed_browser_sources_stop_installation(self):
        result = self.bash('''
calls=0
runuser() { calls=$((calls + 1)); return 1; }
if biligo_install_chromium python cache home auto; then exit 9; fi
[[ $calls == 2 ]]
''')
        self.assertEqual(result.returncode, 0, result.stderr)


def smoke_downloads():
    from importlib.metadata import version
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='biligo-mirror-smoke-') as directory:
        temporary = Path(directory)
        start = time.monotonic()
        with (temporary / 'downloads.log').open('w') as log:
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'download', '--no-deps', '--timeout', '20', '--retries', '1',
                '--index-url', 'https://pypi.tuna.tsinghua.edu.cn/simple', '--dest', str(temporary / 'wheels'),
                'playwright==' + version('playwright')], stdout=log, stderr=subprocess.STDOUT, timeout=180)
            if result.returncode:
                raise AssertionError((temporary / 'downloads.log').read_text())
            size = sum(path.stat().st_size for path in (temporary / 'wheels').iterdir())
            print(f'PASS: real Playwright wheel from Tsinghua ({size / 1e6:.1f} MB, {time.monotonic() - start:.1f}s).', flush=True)
            env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(temporary / 'browsers'),
                       PLAYWRIGHT_DOWNLOAD_HOST='https://cdn.npmmirror.com/binaries/playwright',
                       PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT='30000')
            env.pop('PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST', None)
            result = subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            if result.returncode:
                raise AssertionError((temporary / 'downloads.log').read_text())
        original = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        try:
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(temporary / 'browsers')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content('<title>Mirror smoke</title>')
                assert page.title() == 'Mirror smoke'
                browser.close()
            print('PASS: fresh Chromium, Headless Shell and FFmpeg from npmmirror; real headless browser launch.', flush=True)
        finally:
            if original is None:
                os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            else:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = original


if __name__ == '__main__':
    if sys.argv[1:] == ['--smoke-downloads']:
        smoke_downloads()
    else:
        unittest.main(verbosity=2)
