"""Release metadata shared by the server, launcher and Windows EXE builder."""

VERSION = '3.2.1'
APP_VERSION = f'V{VERSION} Ultra'
APP_VERSION_DATE = '2026-10-25'
WINDOWS_VERSION = tuple(int(part) for part in VERSION.split('.')) + (0,)
EXE_BASENAME = f'BiliGo_V{VERSION}_Ultra'
