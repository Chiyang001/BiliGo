"""SSH console regressions using isolated, synthetic credentials only."""
from pathlib import Path
from contextlib import closing
import hashlib
import base64
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / 'deploy/linux/terminal-auth.py'


class TerminalCredentialChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='biligo-ssh-auth-')
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)
        self.db = self.data / '.biligo_web_auth.sqlite3'

    def write_credentials(self, state, initial):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE credentials (id INTEGER PRIMARY KEY, password_state TEXT, '
                       'initial_password TEXT, password_hash TEXT)')
            db.execute('INSERT INTO credentials VALUES (1, ?, ?, ?)',
                       (state, initial, 'synthetic-secret-hash-never-display'))

    def run_console(self):
        before = hashlib.sha256(self.db.read_bytes()).digest() if self.db.exists() else None
        result = subprocess.run([sys.executable, str(CONSOLE), str(self.data)],
                                capture_output=True, text=True, timeout=10)
        if before is not None:
            self.assertEqual(hashlib.sha256(self.db.read_bytes()).digest(), before)
        self.assertNotIn('synthetic-secret-hash', result.stdout)
        return result

    def test_initial_password_shown_on_reconnect_without_mutation(self):
        self.write_credentials('initial', 'synthetic-initial-only')
        for _ in range(2):
            result = self.run_console()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('[INITIAL PASSWORD] synthetic-initial-only', result.stdout)

    def test_custom_password_never_displays_old_initial(self):
        self.write_credentials('custom', 'revoked-initial-must-not-appear')
        result = self.run_console()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Custom password is set', result.stdout)
        self.assertNotIn('revoked-initial', result.stdout)

    def test_missing_database_fails_without_creating_credentials(self):
        result = self.run_console()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.db.exists())

    def test_legacy_password_preserved(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE credentials (id INTEGER PRIMARY KEY, password_hash TEXT)')
            db.execute("INSERT INTO credentials VALUES (1, 'synthetic-secret-hash-never-display')")
        result = self.run_console()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Legacy password retained', result.stdout)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Server authorization checks require Linux')
class SshAuthorizationChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='biligo-authorize-')
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.ssh = self.home / '.ssh'
        self.authorized = self.ssh / 'authorized_keys'
        self.key = 'ssh-ed25519 c3ludGhldGlj'

    def authorize(self, key=None):
        encoded = base64.b64encode((key or self.key).encode()).decode()
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(['bash', str(ROOT / 'deploy/linux/authorize-ssh-key.sh'), encoded],
                              env=env, capture_output=True, text=True, timeout=10)

    def test_append_preserves_existing_key_and_handles_missing_final_newline(self):
        self.ssh.mkdir()
        previous = 'ssh-ed25519 ZXhpc3Rpbmc= previous-key'
        self.authorized.write_text(previous)
        result = self.authorize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.authorized.read_text().splitlines(), [previous, self.key + ' biligo-ssh'])
        self.assertEqual(self.ssh.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.authorized.stat().st_mode & 0o777, 0o600)
        self.assertEqual(sorted(p.name for p in self.ssh.iterdir()), ['authorized_keys'])

    def test_repeated_authorization_does_not_duplicate_or_remove_comment(self):
        self.ssh.mkdir()
        previous = self.key + ' my existing comment\n'
        self.authorized.write_text(previous)
        for _ in range(2):
            result = self.authorize()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.authorized.read_text(), previous)

    def test_invalid_public_key_creates_no_ssh_files(self):
        result = self.authorize('bad key; touch /tmp/should-never-execute')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.ssh.exists())

    def test_symlinked_authorized_keys_does_not_modify_target(self):
        self.ssh.mkdir()
        target = self.home / 'unrelated-file'
        target.write_text('retain this')
        self.authorized.symlink_to(target)
        result = self.authorize()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), 'retain this')


if __name__ == '__main__':
    unittest.main(verbosity=2)
