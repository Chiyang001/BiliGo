<#
.SYNOPSIS
Deploy BiliGo to Ubuntu 24.04 / Debian 12 using SSH, then open the local panel and stream logs.
.EXAMPLE
.\deploy-ssh.ps1 -Server my-server
.EXAMPLE
.\deploy-ssh.ps1 -Server user@server -Port 2222 -Mirror China -LocalPort 5501
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [ValidateRange(0, 65535)][int]$Port = 0,
    [string]$IdentityFile,
    [string]$SshConfig,
    [ValidateSet('Auto', 'Official', 'China')][string]$Mirror = 'Auto',
    [string]$PipIndex,
    [string]$BrowserDownloadHost,
    [string]$Proxy,
    [ValidateRange(1024, 65535)][int]$RemotePort = 4999,
    [ValidateRange(1024, 65535)][int]$LocalPort = 5500,
    [switch]$NoBrowser,
    [switch]$NonInteractive,
    [switch]$DeployOnly
)
. (Join-Path $PSScriptRoot 'deploy/ssh-common.ps1')
foreach ($command in @('ssh', 'scp')) { $null = Get-Command $command -CommandType Application -ErrorAction Stop }
foreach ($endpoint in @($PipIndex, $BrowserDownloadHost)) {
    if ($endpoint -and $endpoint -notmatch '^https://[^\s''"\\]+$') { throw 'Download/index overrides must be HTTPS URLs.' }
}
if ($Proxy -and $Proxy -notmatch '^https?://[^\s''"\\]+$') { throw '-Proxy must be an HTTP(S) proxy reachable from the server.' }
# Only the first key installation is interactive; subsequent deployment steps stay unattended.
Initialize-BiligoSshLogin -Server $Server -Port $Port -IdentityFile $IdentityFile -SshConfig $SshConfig -NonInteractive:$NonInteractive
$options = @(Get-BiligoSshOptions $Server $Port $IdentityFile $SshConfig)
# Fail before upload or package installation if the service prerequisites are missing.
Invoke-BiligoSsh $options $Server 'test "$(uname -s)" = Linux && (test "$(id -u)" = 0 || sudo -n true) && test -d /run/systemd/system'
$upload = $null
$archive = Join-Path ([IO.Path]::GetTempPath()) ('biligo-upload-' + [guid]::NewGuid().ToString('N') + '.tar.gz')
try {
    New-BiligoArchive $PSScriptRoot $archive
    $lines = @(Invoke-BiligoSsh $options $Server 'umask 077; mktemp -d /tmp/biligo-upload.XXXXXXXXXX')
    $upload = ($lines | Where-Object { $_ -match '^/tmp/biligo-upload\.[a-zA-Z0-9]+$' } | Select-Object -Last 1)
    if (-not $upload) { throw 'Server did not return a valid upload directory.' }
    $scpOptions = @($options)
    if ($Port) {
        # scp uses uppercase -P for its port.
        $scpOptions = @(Get-BiligoSshOptions $Server 0 $IdentityFile $SshConfig) + @('-P', "$Port")
    }
    & scp @scpOptions $archive "${Server}:$upload/source.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw 'Source upload failed.' }
    $hasher = [Security.Cryptography.SHA256]::Create()
    $archiveStream = [IO.File]::OpenRead($archive)
    try { $sha = [BitConverter]::ToString($hasher.ComputeHash($archiveStream)).Replace('-', '').ToLowerInvariant() }
    finally { $archiveStream.Dispose(); $hasher.Dispose() }
    $argsRemote = @('--source', "$upload/source", '--port', "$RemotePort", '--mirror', $Mirror.ToLowerInvariant())
    if ($PipIndex) { $argsRemote += @('--pip-index', $PipIndex) }
    if ($BrowserDownloadHost) { $argsRemote += @('--browser-host', $BrowserDownloadHost) }
    if ($Proxy) { $argsRemote += @('--proxy', $Proxy) }
    $encodedArgs = ($argsRemote | ForEach-Object { ConvertTo-BiligoShellLiteral $_ }) -join ' '
    # Expand only validated upload paths and a hexadecimal checksum; scripts never enter a shell via stdin.
    $installer = "bash source/deploy/linux/provision-ssh.sh $encodedArgs"
    $runInstaller = 'if test "$(id -u)" = 0; then ' + $installer + '; else sudo -n ' + $installer + '; fi'
    $remote = "set -eu; cd '$upload'; printf '%s  %s\n' '$sha' source.tar.gz | sha256sum -c -; mkdir source; tar -xzf source.tar.gz -C source; find source -name '*.sh' -type f -exec sed -i 's/\r$//' {} +; $runInstaller"
    Write-Host '[DEPLOY] Upload verified; installing server dependencies and service. No backups are created.'
    Invoke-BiligoSsh $options $Server $remote
} finally {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    if ($upload -and $upload -match '^/tmp/biligo-upload\.[a-zA-Z0-9]+$') {
        & ssh @options $Server "rm -rf -- '$upload'"
        if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot remove temporary upload directory $upload." }
    }
}
if (-not $DeployOnly) {
    & (Join-Path $PSScriptRoot 'connect-ssh.ps1') -Server $Server -Port $Port -IdentityFile $IdentityFile `
        -SshConfig $SshConfig -LocalPort $LocalPort -NoBrowser:$NoBrowser
}
