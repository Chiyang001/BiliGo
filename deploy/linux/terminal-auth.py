"""Read current panel credential status for an authenticated SSH console, without mutation."""
from pathlib import Path
from contextlib import closing
import sqlite3
import sys


def show_status(data_dir):
    database = Path(data_dir) / '.biligo_web_auth.sqlite3'
    # mode=ro prevents a reconnect from creating/resetting the authentication database.
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(credentials)')}
        if not {'password_state', 'initial_password'} <= columns:
            print('[PASSWORD] Legacy password retained; sign in to set a custom password.', flush=True)
            return
        row = db.execute('SELECT password_state, initial_password FROM credentials WHERE id=1').fetchone()
    if row and row[0] == 'initial' and row[1]:
        print(f'[INITIAL PASSWORD] {row[1]}', flush=True)
        print('[PASSWORD] Sign in and set your own password before using the panel.', flush=True)
    elif row and row[0] == 'custom':
        print('[PASSWORD] Custom password is set. It cannot be recovered from its hash.', flush=True)
    else:
        print('[PASSWORD] Existing password retained. Use -ResetPanelPassword only if needed.', flush=True)


if __name__ == '__main__':
    show_status(sys.argv[1])
