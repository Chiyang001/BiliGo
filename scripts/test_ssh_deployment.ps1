# Dependency-free checks; compatible with Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
. (Join-Path $project 'deploy/ssh-common.ps1')
function Assert-True($Value, $Message) { if (-not $Value) { throw $Message } }
foreach ($relative in @('deploy-ssh.ps1', 'connect-ssh.ps1', 'deploy/ssh-common.ps1')) {
    $syntaxErrors = $null
    $syntaxTokens = $null
    $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $project $relative), [ref]$syntaxTokens, [ref]$syntaxErrors)
    Assert-True ($syntaxErrors.Count -eq 0) "Parse errors in $relative"
}
$options = @(Get-BiligoSshOptions 'user@test-server' 2222 '')
Assert-True ($options -contains 'BatchMode=yes') 'SSH must never wait for password input.'
Assert-True ($options -contains 'StrictHostKeyChecking=accept-new') 'SSH host keys must be checked.'
foreach ($invalid in @('-oProxyCommand=bad', 'user@host;bad', "server`ncommand")) {
    $rejected = $false
    try { $null = Get-BiligoSshOptions $invalid 0 '' } catch { $rejected = $true }
    Assert-True $rejected 'Unsafe server argument was accepted.'
}
Assert-True ((ConvertTo-BiligoShellLiteral "a'b") -eq "'a'\''b'") 'POSIX quoting failed.'
Assert-True ((ConvertTo-BiligoProcessArgument 'a"b\') -eq '"a\"b\\"') 'Windows process argument quoting failed.'
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('biligo-package-test-' + [guid]::NewGuid().ToString('N'))
try {
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'deploy/linux'), (Join-Path $fixture 'docker/defaults'), (Join-Path $fixture '.ssh'), (Join-Path $fixture 'douyin_browser_profile') -Force
    [IO.File]::WriteAllText((Join-Path $fixture 'app.py'), '# source')
    $unicodeImage = ([string][char]0x89c6) + ([char]0x9891) + '.png'
    [IO.File]::WriteAllText((Join-Path $fixture $unicodeImage), 'test image')
    $longName = ('longname-' * 13) + '.py'
    [IO.File]::WriteAllText((Join-Path $fixture $longName), 'long path content')
    [IO.File]::WriteAllText((Join-Path $fixture 'config.json'), 'secret config')
    [IO.File]::WriteAllText((Join-Path $fixture '.env'), 'secret env')
    [IO.File]::WriteAllText((Join-Path $fixture '.secret.py'), 'secret python config')
    [IO.File]::WriteAllText((Join-Path $fixture '.ssh/id_ed25519'), 'secret key')
    [IO.File]::WriteAllText((Join-Path $fixture 'douyin_browser_profile/cookies'), 'secret cookies')
    [IO.File]::WriteAllText((Join-Path $fixture 'deploy/linux/provision-ssh.sh'), '# source')
    [IO.File]::WriteAllText((Join-Path $fixture 'docker/defaults/config.json'), '{}')
    $archive = Join-Path $fixture 'test.tar.gz'
    New-BiligoArchive $fixture $archive
    # Python's independent standard-library parser verifies the generated POSIX archive.
    $archiveJson = & python -c 'import json,sys,tarfile; print(json.dumps(tarfile.open(sys.argv[1]).getnames(), ensure_ascii=True))' $archive
    $members = ConvertFrom-Json -InputObject $archiveJson
    Assert-True ($LASTEXITCODE -eq 0) 'Cannot inspect archive.'
    Assert-True ($members.Count -eq 5) "Unexpected package members: $members"
    Assert-True ($members -contains 'app.py') 'Missing source.'
    Assert-True ($members -contains 'docker/defaults/config.json') 'Missing safe defaults.'
    Assert-True ($members -contains 'deploy/linux/provision-ssh.sh') 'Missing deployment script.'
    $extracted = Join-Path $fixture 'extracted'
    $null = New-Item -ItemType Directory -Path $extracted
    & python -c 'import sys,tarfile; tarfile.open(sys.argv[1]).extractall(sys.argv[2])' $archive $extracted
    Assert-True ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath (Join-Path $extracted $unicodeImage))) 'Unicode filename changed during packaging.'
    Assert-True ([IO.File]::ReadAllText((Join-Path $extracted $longName)) -eq 'long path content') 'Long PAX filename or contents changed.'
    # Generate a new key only inside the test fixture; never touch the user's real SSH keys.
    function Get-BiligoDefaultIdentity { return (Join-Path $fixture 'test identity') }
    $public = Get-BiligoBootstrapPublicKey
    Assert-True ($public.StartsWith('ssh-ed25519 ')) 'Ed25519 generation failed.'
    $privateKey = Join-Path $fixture 'test identity'
    $originalPrivate = [Convert]::ToBase64String([IO.File]::ReadAllBytes($privateKey))
    $samePublic = Get-BiligoBootstrapPublicKey
    Assert-True ($public -eq $samePublic) 'Existing public key was not reused.'
    Assert-True ($originalPrivate -eq [Convert]::ToBase64String([IO.File]::ReadAllBytes($privateKey))) 'Existing private key was changed.'
    Remove-Item -LiteralPath "$privateKey.pub"
    Assert-True ((Get-BiligoBootstrapPublicKey) -eq $public) 'Missing .pub could not be derived without modifying the private key.'
    $authorize = Get-BiligoAuthorizeCommand $public
    Assert-True ($authorize -match '^printf %s [A-Za-z0-9+/=]+ \| base64 -d \| bash -s -- [A-Za-z0-9+/=]+$') 'Unsafe bootstrap command encoding.'
    $scriptEncoded = ($authorize -split ' ')[2]
    $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($scriptEncoded))
    Assert-True ($decoded.Contains('authorized_keys') -and -not $decoded.Contains("`r")) 'Bootstrap script payload is missing or has CRLF.'
} finally {
    $resolved = [IO.Path]::GetFullPath($fixture)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'biligo-package-test-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

function Test-BiligoBootstrapFlow {
    $state = [pscustomobject]@{ Mode = 'ready'; Probes = 0; Keys = 0; Installs = 0 }
    function Test-BiligoSshLogin {
        param($Options, $Server)
        $state.Probes++
        $ready = $state.Mode -eq 'ready' -or ($state.Mode -eq 'first' -and $state.Probes -eq 2)
        return [pscustomobject]@{
            Success = $ready; ExitCode = $(if ($ready) { 0 } else { 255 })
            AuthenticationFailed = (-not $ready -and $state.Mode -ne 'network')
            Diagnostic = 'synthetic connection failure'
        }
    }
    function Get-BiligoBootstrapPublicKey { $state.Keys++; return 'ssh-ed25519 c3ludGhldGlj' }
    function Invoke-BiligoInteractiveKeyInstall { param($Options, $Server, $Command); $state.Installs++ }
    foreach ($mode in @('ready', 'first', 'network', 'verify-failed', 'noninteractive')) {
        $state.Mode = $mode; $state.Probes = 0; $state.Keys = 0; $state.Installs = 0
        $failed = $false
        try { Initialize-BiligoSshLogin -Server 'unit-test' -NonInteractive:($mode -eq 'noninteractive') }
        catch { $failed = $true }
        if ($mode -in @('ready', 'first')) { Assert-True (-not $failed) "Bootstrap unexpectedly failed: $mode" }
        else { Assert-True $failed "Bootstrap should stop before deployment: $mode" }
        if ($mode -in @('first', 'verify-failed')) {
            Assert-True ($state.Probes -eq 2 -and $state.Keys -eq 1 -and $state.Installs -eq 1) 'Bootstrap must install once and verify with BatchMode.'
        } else {
            Assert-True ($state.Probes -eq 1 -and $state.Keys -eq 0 -and $state.Installs -eq 0) 'Ready/network/noninteractive cases must never modify keys or ask for a password.'
        }
    }
}
function Test-BiligoPasswordPromptOptions {
    $state = [pscustomobject]@{ Arguments = @() }
    function ssh { $state.Arguments = @($args); Set-Variable -Name LASTEXITCODE -Scope 1 -Value 0 }
    Invoke-BiligoInteractiveKeyInstall -Options @('-o', 'BatchMode=yes', '-p', '2222') -Server unit-test -Command 'encoded-public-key-command'
    Assert-True ($state.Arguments[1] -eq 'BatchMode=no') 'First SSH BatchMode must enable console input.'
    Assert-True ($state.Arguments -contains 'PubkeyAuthentication=no') 'Password bootstrap must not retry a locked/rejected private key.'
    Assert-True ($state.Arguments -contains 'PreferredAuthentications=password,keyboard-interactive') 'Console password authentication is missing.'
    Assert-True ($state.Arguments -contains '2222') 'Custom SSH port was lost.'
    Assert-True ($state.Arguments[-1] -eq 'encoded-public-key-command') 'Remote command was changed.'
}
Test-BiligoBootstrapFlow
Test-BiligoPasswordPromptOptions
Write-Output 'PASS: SSH bootstrap flows, native key generation/reuse, public-key encoding, console prompt options, syntax and credential-free packaging.'
