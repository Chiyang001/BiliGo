# Shared by the Windows PowerShell 5.1 / PowerShell 7 entry points.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-BiligoDefaultIdentity {
    $sshDirectory = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.ssh'
    foreach ($name in @('id_ed25519', 'id_rsa', 'id_ecdsa')) {
        $candidate = Join-Path $sshDirectory $name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return (Join-Path $sshDirectory 'id_ed25519')
}

function Get-BiligoSshOptions {
    param([string]$Server, [int]$Port, [string]$IdentityFile, [string]$SshConfig)
    if ($Server -notmatch '^[\p{L}\p{N}_@.:[\]-]+$' -or $Server.StartsWith('-')) {
        throw 'Use an SSH alias or user@hostname for -Server; shell syntax is not accepted.'
    }
    $options = @('-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3')
    if ($SshConfig) { $options = @('-F', (Resolve-Path -LiteralPath $SshConfig).Path) + $options }
    if ($Port) { $options += @('-p', "$Port") }
    if (-not $IdentityFile) {
        $candidate = Get-BiligoDefaultIdentity
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $IdentityFile = $candidate }
    }
    if ($IdentityFile) {
        $resolved = (Resolve-Path -LiteralPath $IdentityFile).Path
        $options += @('-i', $resolved, '-o', 'IdentitiesOnly=yes')
    }
    return $options
}

function ConvertTo-BiligoShellLiteral {
    param([AllowEmptyString()][string]$Value)
    if ($Value.Contains("`n") -or $Value.Contains("`r") -or $Value.Contains([char]0)) {
        throw 'Remote arguments cannot contain newlines or NUL.'
    }
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Invoke-BiligoSsh {
    param([string[]]$Options, [string]$Server, [string]$Command)
    & ssh @Options $Server $Command
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed (exit $LASTEXITCODE). Check the error above, your SSH key, and sudo -n access." }
}

function Test-BiligoSshLogin {
    param([string[]]$Options, [string]$Server)
    # Capture diagnostics without PowerShell 5.1 turning native stderr into a terminating error.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& ssh @Options -T -o PreferredAuthentications=publickey $Server 'printf BILIGO_SSH_AUTH_OK' 2>&1)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    $diagnostic = ($output | ForEach-Object { $_.ToString() }) -join "`n"
    return [pscustomobject]@{
        Success = ($code -eq 0 -and $diagnostic.Contains('BILIGO_SSH_AUTH_OK'))
        ExitCode = $code
        AuthenticationFailed = ($code -eq 255 -and $diagnostic -match 'Permission denied|Too many authentication failures')
        Diagnostic = $diagnostic
    }
}

function Invoke-BiligoKeygen {
    param([string[]]$Arguments)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = (Get-Command ssh-keygen -CommandType Application -ErrorAction Stop).Source
    # Preserve empty -N / -P values on Windows PowerShell 5.1 as well as PowerShell 7.
    $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-BiligoProcessArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(15000)) { $process.Kill(); throw 'ssh-keygen timed out.' }
        $output = $stdout.GetAwaiter().GetResult()
        $errorText = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "ssh-keygen failed. $errorText" }
        return $output
    } finally { $process.Dispose() }
}

function Get-BiligoBootstrapPublicKey {
    param([string]$IdentityFile)
    $keyFile = if ($IdentityFile) { (Resolve-Path -LiteralPath $IdentityFile).Path } else { Get-BiligoDefaultIdentity }
    if (-not (Test-Path -LiteralPath $keyFile -PathType Leaf)) {
        if (Test-Path -LiteralPath "$keyFile.pub") { throw "Public key $keyFile.pub already exists without its private key; refusing to overwrite it." }
        $null = New-Item -ItemType Directory -Path (Split-Path $keyFile -Parent) -Force
        Write-Host '[SSH] Creating a local Ed25519 key for unattended SSH. Existing keys are never overwritten.'
        $null = Invoke-BiligoKeygen -Arguments @('-q', '-t', 'ed25519', '-N', '', '-C', 'biligo-ssh', '-f', $keyFile)
    }
    if (Test-Path -LiteralPath "$keyFile.pub" -PathType Leaf) {
        $publicKey = [IO.File]::ReadAllText("$keyFile.pub").Trim()
    } else {
        # -P prevents an encrypted private key from hanging in a hidden password prompt.
        $publicKey = (Invoke-BiligoKeygen -Arguments @('-y', '-P', '', '-f', $keyFile)).Trim()
    }
    $parts = $publicKey -split '\s+', 3
    if ($parts.Count -lt 2 -or $parts[0] -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))$' -or
        $parts[1] -notmatch '^[A-Za-z0-9+/]+={0,2}$') { throw 'Invalid SSH public key. Only an OpenSSH .pub key can be installed.' }
    # Drop the comment, including possible non-ASCII characters, for an encoding-independent payload.
    return ($parts[0] + ' ' + $parts[1])
}

function Get-BiligoAuthorizeCommand {
    param([string]$PublicKey)
    $script = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'linux/authorize-ssh-key.sh')).Replace("`r`n", "`n")
    $scriptBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    $keyBase64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($PublicKey))
    # No password or private key enters this command, the process arguments or stdin.
    return "printf %s $scriptBase64 | base64 -d | bash -s -- $keyBase64"
}

function Invoke-BiligoInteractiveKeyInstall {
    param([string[]]$Options, [string]$Server, [string]$Command)
    # OpenSSH uses the existing console to ask the human for the server password.
    # These overrides must precede BatchMode=yes: OpenSSH uses the first supplied value.
    $interactiveOptions = @('-o', 'BatchMode=no', '-o', 'PubkeyAuthentication=no',
        '-o', 'PreferredAuthentications=password,keyboard-interactive', '-o', 'NumberOfPasswordPrompts=3') + $Options
    & ssh @interactiveOptions -T $Server $Command
    if ($LASTEXITCODE -ne 0) { throw 'SSH public-key setup failed. Check the server password, login user and server password-login policy.' }
}

function Initialize-BiligoSshLogin {
    param([string]$Server, [int]$Port, [string]$IdentityFile, [string]$SshConfig, [switch]$NonInteractive)
    $options = @(Get-BiligoSshOptions $Server $Port $IdentityFile $SshConfig)
    $probe = Test-BiligoSshLogin $options $Server
    if ($probe.Success) { Write-Host '[SSH] Key authentication is ready.'; return }
    if (-not $probe.AuthenticationFailed) { throw "SSH connection failed before public-key setup. $($probe.Diagnostic)" }
    if ($NonInteractive) { throw 'SSH key authentication failed. Run deploy-ssh.ps1 without -NonInteractive in a terminal to configure it once.' }
    Write-Host '[SSH] First connection: installing this computer''s public key.'
    Write-Host '[SSH] Enter the SERVER SSH password at the OpenSSH prompt. Typed characters are hidden.'
    Write-Host '[SSH] The script does not read/store the password or upload the private key.'
    $publicKey = Get-BiligoBootstrapPublicKey $IdentityFile
    $command = Get-BiligoAuthorizeCommand $publicKey
    Invoke-BiligoInteractiveKeyInstall $options $Server $command
    # A new default key may have been generated, so rebuild the explicit identity options.
    $options = @(Get-BiligoSshOptions $Server $Port $IdentityFile $SshConfig)
    $verified = Test-BiligoSshLogin $options $Server
    if (-not $verified.Success) {
        throw 'Public key was installed but unattended SSH verification failed. Check AuthorizedKeysFile and permissions; for an encrypted private key, load it into ssh-agent. Deployment has not started.'
    }
    Write-Host '[SSH] Passwordless login verified. Continuing deployment.'
}

function Get-BiligoTarPath {
    # Prefer the Windows Unicode-aware bsdtar over GNU/MSYS tar earlier on PATH.
    if ($env:OS -eq 'Windows_NT' -and $env:SystemRoot) {
        $windowsTar = Join-Path $env:SystemRoot 'System32/tar.exe'
        if (Test-Path -LiteralPath $windowsTar -PathType Leaf) { return $windowsTar }
    }
    return (Get-Command tar -CommandType Application -ErrorAction Stop).Source
}

function New-BiligoArchive {
    param([string]$Project, [string]$Destination)
    # Allow source/resources only. Never traverse local profiles, .git, venv or runtime data.
    $extensions = @('.py', '.html', '.js', '.css', '.png', '.jpg', '.jpeg', '.svg', '.ico')
    $files = @(Get-ChildItem -LiteralPath $Project -File | Where-Object {
        -not $_.Name.StartsWith('.') -and ($extensions -contains $_.Extension.ToLowerInvariant() -or
        $_.Name -in @('requirements.txt', 'start.sh', 'install_linux.sh'))
    })
    foreach ($relative in @('deploy/linux', 'docker/defaults')) {
        $files += @(Get-ChildItem -LiteralPath (Join-Path $Project $relative) -File | Where-Object {
            $_.Extension -in @('.sh', '.py', '.json', '.service')
        })
    }
    $prefix = [IO.Path]::GetFullPath($Project).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $manifest = foreach ($file in $files) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to upload a symbolic link: $($file.FullName)"
        }
        $relative = $file.FullName.Substring($prefix.Length).Replace('\', '/')
        if ($relative -match '[\r\n]' -or $relative.StartsWith('-')) { throw 'Unsafe archive filename.' }
        $relative
    }
    # Some Windows tar builds crash when non-ANSI filenames arrive through argv.
    # Copy the allowlisted upload inputs to a temporary staging directory so tar
    # discovers their Unicode names through the filesystem instead of argv/-T.
    $tarExecutable = Get-BiligoTarPath
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $staging = Join-Path $temporaryRoot ('biligo-upload-stage-' + [guid]::NewGuid().ToString('N'))
    try {
        $null = New-Item -ItemType Directory -Path $staging
        foreach ($relative in $manifest) {
            $target = Join-Path $staging $relative
            $null = New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force
            [IO.File]::Copy((Join-Path $Project $relative), $target)
        }
        & $tarExecutable --format=pax --options=hdrcharset=UTF-8 -czf $Destination -C $staging .
        if ($LASTEXITCODE -ne 0) { throw "Cannot create deployment archive (exit $LASTEXITCODE; tool $tarExecutable)." }
    } finally {
        $resolvedStaging = [IO.Path]::GetFullPath($staging)
        if ($resolvedStaging.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
            (Split-Path $resolvedStaging -Leaf) -match '^biligo-upload-stage-[a-f0-9]{32}$' -and
            (Test-Path -LiteralPath $resolvedStaging)) {
            Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
        }
    }
}

function ConvertTo-BiligoProcessArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW quoting; do not use JSON or a shell for process arguments.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Start-BiligoConnection {
    param([string[]]$Options, [string]$Server, [int]$LocalPort,
        [int]$RemotePort, [switch]$NoBrowser, [switch]$NoFollow, [switch]$ResetPanelPassword)
    $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $LocalPort)
    try { $listener.Start() } catch { throw "Local port $LocalPort is occupied. Choose another -LocalPort." }
    finally { $listener.Stop() }

    $session = 'bash /opt/biligo-ssh/deploy/linux/ssh-session.sh'
    if ($NoFollow) { $session += ' --no-follow' }
    if ($ResetPanelPassword) { $session += ' --reset-panel-password' }
    $remote = 'if test "$(id -u)" = 0; then ' + $session + '; else sudo -n ' + $session + '; fi'
    $arguments = @($Options) + @('-T', '-o', 'ExitOnForwardFailure=yes',
        '-L', "127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort}", $Server, $remote)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = (Get-Command ssh -CommandType Application).Source
    $info.Arguments = (($arguments | ForEach-Object { ConvertTo-BiligoProcessArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.RedirectStandardInput = $true
    $info.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $info.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    $url = "http://127.0.0.1:$LocalPort"
    $ready = $false
    $started = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(75)
    Write-Host "[SSH] $Server -> $url"
    Write-Host '[INFO] Ctrl+C closes this tunnel/log stream; BiliGo keeps running on the server.'
    try {
        [void]$process.Start()
        $started = $true
        $stdout = $process.StandardOutput.ReadLineAsync()
        $stderr = $process.StandardError.ReadLineAsync()
        while ($true) {
            foreach ($stream in @('stdout', 'stderr')) {
                $pending = Get-Variable -Name $stream -ValueOnly
                if ($null -ne $pending -and $pending.IsCompleted) {
                    $line = $pending.GetAwaiter().GetResult()
                    if ($null -ne $line) {
                        Write-Host $line
                        $reader = if ($stream -eq 'stdout') { $process.StandardOutput } else { $process.StandardError }
                        Set-Variable -Name $stream -Value $reader.ReadLineAsync()
                    } else { Set-Variable -Name $stream -Value $null }
                }
            }
            if (-not $ready -and -not $process.HasExited) {
                try {
                    $request = [Net.HttpWebRequest]::Create("$url/health")
                    $request.Proxy = $null
                    $request.Timeout = 500
                    $response = $request.GetResponse()
                    try {
                        $reader = New-Object IO.StreamReader($response.GetResponseStream())
                        $healthy = $reader.ReadToEnd().Trim() -eq 'ok'
                        $reader.Dispose()
                    } finally { $response.Close() }
                    if ($healthy) {
                        $ready = $true
                        Write-Host "[PANEL] $url"
                        if (-not $NoBrowser) {
                            try { Start-Process $url } catch { Write-Warning "Open $url in your browser." }
                        }
                    }
                } catch { }
                if (-not $ready -and [DateTime]::UtcNow -gt $deadline) { throw 'SSH panel health check timed out.' }
            }
            if ($process.HasExited -and $null -eq $stdout -and $null -eq $stderr) { break }
            Start-Sleep -Milliseconds 50
        }
        if ($process.ExitCode -ne 0) { throw "SSH session failed (exit $($process.ExitCode))." }
        if (-not $ready) { throw 'SSH ended before the panel became accessible.' }
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
}
