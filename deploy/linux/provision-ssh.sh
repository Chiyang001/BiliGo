#!/usr/bin/env bash
# Invoked by deploy-ssh.ps1 as root. No VNC, Docker, backups or SSH/network rewrites.
set -Eeuo pipefail
umask 077
trap 'echo "[ERROR] Provisioning failed at line $LINENO. Fix the error above and rerun deployment; existing data is retained." >&2' ERR
source "$(dirname -- "${BASH_SOURCE[0]}")/download-sources.sh"

app=/opt/biligo-ssh
data=/var/lib/biligo-ssh
cache=/var/cache/biligo-ssh
config=/etc/biligo-ssh
unit=biligo-ssh.service
source_dir= port=4999 mirror=auto pip_index= browser_host= proxy=
while (( $# )); do
    case "$1" in
        --source|--port|--mirror|--pip-index|--browser-host|--proxy)
            (( $# >= 2 )) || { echo "Missing value for $1" >&2; exit 2; }
            case "$1" in
                --source) source_dir=$2 ;; --port) port=$2 ;; --mirror) mirror=$2 ;;
                --pip-index) pip_index=$2 ;; --browser-host) browser_host=$2 ;; --proxy) proxy=$2 ;;
            esac
            shift 2 ;;
        --help) echo 'Usage: sudo bash provision-ssh.sh --source DIR [--port 4999] [--mirror auto|official|china] [--pip-index HTTPS_URL] [--browser-host HTTPS_URL] [--proxy HTTP_URL]'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[[ $EUID == 0 ]] || { echo 'Root or passwordless sudo is required.' >&2; exit 1; }
[[ $port =~ ^[0-9]{4,5}$ ]] && (( 10#$port >= 1024 && 10#$port <= 65535 )) || { echo 'Invalid port.' >&2; exit 2; }
[[ $mirror == auto || $mirror == official || $mirror == china ]] || { echo 'Invalid mirror mode.' >&2; exit 2; }
for endpoint in "$pip_index" "$browser_host"; do
    [[ -z $endpoint || $endpoint =~ ^https://[^[:space:]\"\'\\]+$ ]] || { echo 'Download hosts must use HTTPS.' >&2; exit 2; }
done
[[ -z $proxy || $proxy =~ ^https?://[^[:space:]\"\'\\]+$ ]] || { echo 'Invalid proxy URL.' >&2; exit 2; }
[[ -f $source_dir/launcher.py && -f $source_dir/deploy/linux/ssh-session.sh ]] || { echo 'Invalid source directory.' >&2; exit 2; }
[[ -d /run/systemd/system ]] || { echo 'A Linux system with systemd is required.' >&2; exit 1; }
exec 9>/run/lock/biligo-ssh-deploy.lock
flock -n 9 || { echo 'Another BiliGo SSH deployment is in progress.' >&2; exit 1; }
source /etc/os-release
case "$ID:$VERSION_ID" in
    ubuntu:24.04|debian:12) ;;
    *) echo 'Supported targets: Ubuntu 24.04 and Debian 12. No system changes were made.' >&2; exit 1 ;;
esac
arch=$(dpkg --print-architecture)
[[ $arch == amd64 || $arch == arm64 ]] || { echo "Unsupported architecture: $arch" >&2; exit 1; }
# Refuse to overwrite an unrelated installation or user account.
if [[ -e $app && ! -f $config/managed ]]; then
    echo "Unmanaged $app already exists; refusing to overwrite it." >&2; exit 1
fi
if [[ ! -f $config/managed ]] && { id biligo-ssh >/dev/null 2>&1 || systemctl cat "$unit" >/dev/null 2>&1; }; then
    echo 'An unmanaged biligo-ssh user or service already exists.' >&2; exit 1
fi
if command -v ss >/dev/null && ss -H -ltn "sport = :$port" | read -r _; then
    # A repeat deployment may reuse only this service's existing port.
    if ! systemctl is-active --quiet "$unit" || [[ ! -f $config/service.env ]] ||
       ! grep -qx "PORT=$port" "$config/service.env"; then
        echo "Server port $port is occupied. Choose another -RemotePort." >&2; exit 1
    fi
fi

work=$(mktemp -d /tmp/biligo-provision.XXXXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
chmod 755 "$work"
install -d -m 755 "$config"
if [[ -n $proxy ]]; then
    export http_proxy=$proxy https_proxy=$proxy HTTP_PROXY=$proxy HTTPS_PROXY=$proxy
fi
export no_proxy=localhost,127.0.0.1,::1 NO_PROXY=localhost,127.0.0.1,::1
export DEBIAN_FRONTEND=noninteractive

write_apt_sources() {
    local selected=$1 base security
    if [[ $ID == ubuntu ]]; then
        if [[ $arch == arm64 ]]; then
            base=https://ports.ubuntu.com/ubuntu-ports
            security=$base
        else
            base=https://archive.ubuntu.com/ubuntu
            security=https://security.ubuntu.com/ubuntu
        fi
        if [[ $selected == china ]]; then
            base=https://mirrors.tuna.tsinghua.edu.cn/ubuntu
            [[ $arch != arm64 ]] || base=https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports
            security=$base
        fi
        printf 'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] %s noble main universe\ndeb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] %s noble-updates main universe\ndeb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] %s noble-security main universe\n' "$base" "$base" "$security" > "$work/sources.list"
    else
        base=https://deb.debian.org/debian
        security=https://security.debian.org/debian-security
        if [[ $selected == china ]]; then
            base=https://mirrors.tuna.tsinghua.edu.cn/debian
            security=https://mirrors.tuna.tsinghua.edu.cn/debian-security
        fi
        printf 'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] %s bookworm main\ndeb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] %s bookworm-updates main\ndeb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] %s bookworm-security main\n' "$base" "$base" "$security" > "$work/sources.list"
    fi
    chmod 644 "$work/sources.list"
}
# APT_CONFIG also applies to Playwright's child apt-get processes. Host sources stay intact.
cat > "$work/apt.conf" <<EOF
Dir::Etc::sourcelist "$work/sources.list";
Dir::Etc::sourceparts "-";
Acquire::Retries "1";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
APT::Update::Error-Mode "any";
EOF
chmod 644 "$work/apt.conf"
export APT_CONFIG="$work/apt.conf"
if [[ ! -s /etc/ssl/certs/ca-certificates.crt ]]; then
    # Minimal images may lack a CA store. Bootstrap only the CA package using
    # signed APT metadata/packages over HTTP, then restore HTTPS immediately.
    echo '[APT] Bootstrapping CA certificates using signed distribution packages.'
    biligo_update_apt_sources "$mirror" http
    apt-get install -y --no-install-recommends ca-certificates
fi
biligo_update_apt_sources "$mirror"
apt-get install -y --no-install-recommends ca-certificates curl python3 python3-venv iproute2
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
# Retry the port check after installing ss on minimal systems.
if ss -H -ltn "sport = :$port" | read -r _; then
    systemctl is-active --quiet "$unit" && [[ -f $config/service.env ]] &&
        grep -qx "PORT=$port" "$config/service.env" || { echo "Server port $port is occupied." >&2; exit 1; }
fi
if ! id biligo-ssh >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$data" --shell /usr/sbin/nologin biligo-ssh
fi
install -d -m 700 -o biligo-ssh -g biligo-ssh "$data" "$cache"
# This marker identifies the dedicated installation. No automatic backup/rollback copies.
printf 'BiliGo SSH deployment\n' > "$config/managed"
chmod 644 "$config/managed"
systemctl stop "$unit" 2>/dev/null || true
install -d -m 755 "$app"
find "$source_dir" -type d -exec chmod 755 {} +
find "$source_dir" -type f -exec chmod 644 {} +
cp -R --preserve=mode "$source_dir/." "$app/"
# Source and virtualenv are administrator-owned; runtime data belongs to the service user.
chown -R root:root "$app"
python3 -m venv "$app/.venv-linux"
py=$app/.venv-linux/bin/python
biligo_install_python_dependencies "$py" "$app/requirements.txt" "$mirror" "$pip_index"
"$py" -m playwright install-deps chromium
chmod -R a+rX "$app/.venv-linux"
biligo_install_chromium "$py" "$cache/ms-playwright" "$data" "$mirror" "$browser_host" "$proxy"
# Persist only deployment-scoped settings. Never write proxy settings into global profiles.
install -m 644 "$work/sources.list" "$config/apt.sources.list"
{
    printf 'PORT=%s\nBILIGO_BIND_HOST=127.0.0.1\nBILIGO_OPEN_BROWSER=0\n' "$port"
    printf 'PIP_INDEX_URL=%s\n' "$pip_index"
    [[ -z $browser_host ]] || printf 'PLAYWRIGHT_DOWNLOAD_HOST=%s\n' "$browser_host"
    if [[ -n $proxy ]]; then printf 'HTTP_PROXY=%s\nHTTPS_PROXY=%s\n' "$proxy" "$proxy"; fi
    printf 'NO_PROXY=localhost,127.0.0.1,::1\n'
} > "$config/service.env"
chmod 600 "$config/service.env"
cat > "/etc/systemd/system/$unit" <<EOF
[Unit]
Description=BiliGo managed over SSH
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=biligo-ssh
Group=biligo-ssh
WorkingDirectory=$app
Environment=HOME=$data
Environment=BILIGO_DATA_DIR=$data
Environment=BILIGO_VENV_DIR=$app/.venv-linux
Environment=PLAYWRIGHT_BROWSERS_PATH=$cache/ms-playwright
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$config/service.env
UMask=0077
NoNewPrivileges=true
ExecStart=/bin/bash $app/start.sh
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillMode=control-group
[Install]
WantedBy=multi-user.target
EOF
chmod 644 "/etc/systemd/system/$unit"
systemctl daemon-reload
systemctl enable --now "$unit"
for (( attempt=0; attempt<60; attempt++ )); do
    if curl --noproxy '*' --silent --fail --max-time 2 "http://127.0.0.1:$port/health" | grep -qx ok; then
        echo "[OK] BiliGo is healthy at server loopback port $port."
        echo '[INFO] SSH-only deployment. Interactive platform browser login requires an existing graphical session; VNC is not installed.'
        exit 0
    fi
    sleep 1
done
echo "[ERROR] Health check failed. Inspect: sudo journalctl -u $unit -n 80" >&2
exit 1
