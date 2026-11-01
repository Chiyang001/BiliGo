#!/usr/bin/env bash
# Executed over the first password-authenticated SSH connection, as the login user.
set -euo pipefail
umask 077
[[ $(uname -s) == Linux ]] || { echo 'SSH bootstrap requires a Linux server.' >&2; exit 1; }
[[ $# == 1 ]] || { echo 'Expected one encoded public key.' >&2; exit 2; }
key=$(printf '%s' "$1" | base64 -d)
[[ $key =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))\ [A-Za-z0-9+/]+={0,2}$ ]] || {
    echo 'Invalid OpenSSH public key.' >&2; exit 2;
}
ssh_dir=$HOME/.ssh
authorized=$ssh_dir/authorized_keys
[[ ! -L $ssh_dir && ! -L $authorized ]] || { echo 'Refusing to modify symbolic-linked SSH authorization paths.' >&2; exit 1; }
mkdir -p -- "$ssh_dir"
chmod 700 -- "$ssh_dir"
touch -- "$authorized"
chmod 600 -- "$authorized"
# Serialize bootstrap attempts, retaining existing keys and without creating backup copies.
exec 9>>"$authorized"
flock 9
blob=${key#* }
if ! grep -qF -- "$blob" "$authorized"; then
    # Leading newline also handles an existing file without a final newline.
    printf '\n%s biligo-ssh\n' "$key" >&9
    echo '[SSH] Public key added; existing authorized keys retained.'
else
    echo '[SSH] Public key is already present; no duplicate was added.'
fi
