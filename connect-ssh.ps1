<#
.SYNOPSIS
Reconnect to an existing SSH deployment without uploading or reinstalling anything.
.EXAMPLE
.\connect-ssh.ps1 -Server my-server
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [ValidateRange(0, 65535)][int]$Port = 0,
    [string]$IdentityFile,
    [string]$SshConfig,
    [ValidateRange(1024, 65535)][int]$LocalPort = 5500,
    [switch]$NoBrowser,
    [switch]$NoFollow,
    [switch]$ResetPanelPassword
)
. (Join-Path $PSScriptRoot 'deploy/ssh-common.ps1')
$options = @(Get-BiligoSshOptions $Server $Port $IdentityFile $SshConfig)
$result = @(Invoke-BiligoSsh $options $Server 'if test "$(id -u)" = 0; then bash /opt/biligo-ssh/deploy/linux/ssh-session.sh --port; else sudo -n bash /opt/biligo-ssh/deploy/linux/ssh-session.sh --port; fi')
$ports = @($result | Where-Object { $_ -match '^BILIGO_PORT=[0-9]+$' })
if ($ports.Count -ne 1) { throw 'Cannot read the deployed port. Run deploy-ssh.ps1 first.' }
$remotePort = [int]($ports[0].Split('=')[1])
if ($remotePort -lt 1024 -or $remotePort -gt 65535) { throw 'Invalid server port.' }
Start-BiligoConnection -Options $options -Server $Server -LocalPort $LocalPort -RemotePort $remotePort `
    -NoBrowser:$NoBrowser -NoFollow:$NoFollow -ResetPanelPassword:$ResetPanelPassword
