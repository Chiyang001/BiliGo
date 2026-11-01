#!/usr/bin/env bash
# Deployment-scoped download policy. Sourced by provision-ssh.sh; no global configuration writes.

biligo_apt_mirrors() {
    case "$1" in
        auto) printf '%s\n' china official ;;
        china|official) printf '%s\n' "$1" ;;
        *) echo 'Invalid mirror policy.' >&2; return 2 ;;
    esac
}

biligo_pip_indexes() {
    if [[ -n ${2:-} ]]; then printf '%s\n' "$2"; return; fi
    case "$1" in
        auto) printf '%s\n' https://pypi.tuna.tsinghua.edu.cn/simple https://pypi.org/simple ;;
        china) printf '%s\n' https://pypi.tuna.tsinghua.edu.cn/simple ;;
        official) printf '%s\n' https://pypi.org/simple ;;
        *) echo 'Invalid mirror policy.' >&2; return 2 ;;
    esac
}

biligo_browser_hosts() {
    if [[ -n ${2:-} ]]; then printf '%s\n' "$2"; return; fi
    case "$1" in
        auto) printf '%s\n' https://cdn.npmmirror.com/binaries/playwright official ;;
        china) printf '%s\n' https://cdn.npmmirror.com/binaries/playwright ;;
        official) printf '%s\n' official ;;
        *) echo 'Invalid mirror policy.' >&2; return 2 ;;
    esac
}

# Uses write_apt_sources and the temporary APT_CONFIG provided by the installer.
biligo_update_apt_sources() {
    local mode=$1 scheme=${2:-https} candidate
    local -a candidates
    mapfile -t candidates < <(biligo_apt_mirrors "$mode")
    for candidate in "${candidates[@]}"; do
        selected=$candidate
        write_apt_sources "$selected"
        [[ $scheme != http ]] || sed -i 's|https://|http://|g' "$work/sources.list"
        echo "[APT] Trying $selected sources (host source files are preserved)."
        if apt-get update; then return 0; fi
        echo "[APT] $selected source failed." >&2
    done
    echo '[ERROR] No selected APT source could be updated.' >&2
    return 1
}

biligo_install_python_dependencies() {
    local python=$1 requirements=$2 mode=$3 override=${4:-} candidate
    local -a candidates
    mapfile -t candidates < <(biligo_pip_indexes "$mode" "$override")
    for candidate in "${candidates[@]}"; do
        if [[ -n $override ]]; then echo '[PIP] Trying the custom package index.'
        else echo "[PIP] Trying $candidate"; fi
        if "$python" -m pip install --disable-pip-version-check --timeout 20 --retries 1 \
            --index-url "$candidate" -r "$requirements"; then
            pip_index=$candidate
            return 0
        fi
        echo '[PIP] Package installation failed on this source.' >&2
    done
    echo '[ERROR] No selected Python package source succeeded.' >&2
    return 1
}

biligo_install_chromium() {
    local python=$1 browser_cache=$2 service_home=$3 mode=$4 override=${5:-} download_proxy=${6:-} candidate
    local -a candidates browser_env
    mapfile -t candidates < <(biligo_browser_hosts "$mode" "$override")
    for candidate in "${candidates[@]}"; do
        browser_env=("HOME=$service_home" "PLAYWRIGHT_BROWSERS_PATH=$browser_cache" "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=30000")
        if [[ $candidate != official ]]; then browser_env+=("PLAYWRIGHT_DOWNLOAD_HOST=$candidate"); fi
        if [[ -n $download_proxy ]]; then browser_env+=("HTTPS_PROXY=$download_proxy" "HTTP_PROXY=$download_proxy"); fi
        if [[ -n $override ]]; then echo '[BROWSER] Trying the custom Chromium download host.'
        else echo "[BROWSER] Trying $candidate (no graphical desktop/VNC)."; fi
        if runuser -u biligo-ssh -- env -u PLAYWRIGHT_DOWNLOAD_HOST -u PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST "${browser_env[@]}" \
            "$python" -m playwright install chromium; then
            browser_host=$candidate
            [[ $browser_host != official ]] || browser_host=
            return 0
        fi
        echo '[BROWSER] Download failed; keeping completed browser files for the next attempt.' >&2
    done
    echo '[ERROR] No selected Chromium download source succeeded.' >&2
    return 1
}
