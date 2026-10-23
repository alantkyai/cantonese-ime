param([switch]$LocalProfile, [switch]$BrokerOnly, [string]$LanguageId = '0x0409')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = (Get-Command python.exe -ErrorAction Stop).Source
$stateDirectory = Join-Path $projectRoot '.local/native'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
$readyPath = Join-Path $stateDirectory 'backend-ready.json'
$serverPath = Join-Path $PSScriptRoot 'backend/server.py'
$brokerId = $null
if (Test-Path -LiteralPath $readyPath) {
    $ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($ready.pid)"
    if ($existing -and $existing.CommandLine -and $existing.CommandLine.Contains($serverPath)) {
        $brokerId = [int]$ready.pid
    } elseif ($existing) {
        throw 'The ready file points at another process. Inspect it before restarting.'
    }
}
if (-not $brokerId) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
    $broker = Start-Process -FilePath $pythonPath -ArgumentList @('-u',('"' + $serverPath + '"')) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $stateDirectory "backend-$stamp.stdout.log") `
        -RedirectStandardError (Join-Path $stateDirectory "backend-$stamp.stderr.log")
    $brokerId = $broker.Id
    $matched = $false
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        if ($broker.HasExited) { throw 'The backend exited before becoming ready; inspect its stderr log.' }
        if (Test-Path -LiteralPath $readyPath) {
            $ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
            if ([int]$ready.pid -eq $brokerId) { $matched = $true; break }
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $matched) { throw "Backend PID $brokerId did not publish readiness within 20 seconds." }
}
Write-Output "Backend PID: $brokerId"
if ($BrokerOnly) { return }
$hostPath = Join-Path $stateDirectory 'build-x64/CantoneseImeNativeTestHost.exe'
if (-not (Test-Path -LiteralPath $hostPath)) { throw 'Build the native host first.' }
$proofPath = Join-Path $stateDirectory ('host-proof-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '.jsonl')
$hostArguments = @('--clsid','{67718E6F-49A1-4F54-88D6-30578FC70C5D}',
    '--profile','{A7136205-2245-45CC-A6AA-702B3F2E8D42}','--langid',$LanguageId,
    '--log',('"' + $proofPath + '"'),'--activate')
if ($LocalProfile) { $hostArguments += '--register-local-profile' }
# The test host is deliberately interactive; background broker windows are hidden.
$testHost = Start-Process -FilePath $hostPath -ArgumentList $hostArguments -WorkingDirectory $projectRoot -PassThru
[ordered]@{broker_pid=$brokerId;host_pid=$testHost.Id;host_log=$proofPath;
    profile_scope=$(if ($LocalProfile) {'process-local'} else {'registered profile'});
    launched_at_utc=[DateTime]::UtcNow.ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDirectory 'last-launch.json') -Encoding UTF8
Write-Output "Host PID: $($testHost.Id)"
Write-Output "Evidence log: $proofPath"
