#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $EUID == 0 ]] || { echo 'Passwordless sudo is required for the managed SSH session.' >&2; exit 1; }
config=/etc/biligo-ssh
app=/opt/biligo-ssh
data=/var/lib/biligo-ssh
unit=biligo-ssh.service
[[ -f $config/managed && -f $config/service.env ]] || { echo 'Deploy with deploy-ssh.ps1 first.' >&2; exit 1; }
port=$(sed -n 's/^PORT=\([0-9]*\)$/\1/p' "$config/service.env")
[[ $port =~ ^[0-9]{4,5}$ ]] && (( 10#$port >= 1024 && 10#$port <= 65535 )) || { echo 'Invalid configured port.' >&2; exit 1; }
follow=1 reset=0
for arg in "$@"; do
    case "$arg" in
        --port) printf 'BILIGO_PORT=%s\n' "$port"; exit 0 ;;
        --no-follow) follow=0 ;;
        --reset-panel-password) reset=1 ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done
systemctl is-active --quiet "$unit" || { echo 'BiliGo is stopped. Run: sudo systemctl start biligo-ssh' >&2; exit 1; }
if (( reset )); then
    # Explicit opt-in only. Do not restart or reset credentials on normal reconnects.
    runuser -u biligo-ssh -- env HOME="$data" BILIGO_DATA_DIR="$data" \
        "$app/.venv-linux/bin/python" "$app/web_access.py" --reset-initial-password
else
    runuser -u biligo-ssh -- "$app/.venv-linux/bin/python" "$app/deploy/linux/terminal-auth.py" "$data"
fi
echo '[INFO] SSH tunnel and live logs are active. The server continues running after disconnect.'
echo '[INFO] Browser-based platform verification needs a graphical session; this deployment uses no VNC.'
if (( follow )); then
    # Only new records: replaying old startup logs could display a revoked initial password.
    # Close the journal process when ssh closes stdin, even on a non-PTY connection.
    journalctl -u "$unit" -n 0 -f --no-pager -o cat &
    journal_pid=$!
    trap 'kill "$journal_pid" 2>/dev/null || true; wait "$journal_pid" 2>/dev/null || true' EXIT
    cat >/dev/null
else
    echo '[INFO] --no-follow: keeping the tunnel open without streaming journal records.'
    cat >/dev/null
fi
