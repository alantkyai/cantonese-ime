[CmdletBinding(SupportsShouldProcess=$true)]
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$RegistrationPlanSha256)
$ErrorActionPreference = 'Stop'
if ([IntPtr]::Size -ne 8) { throw 'Use 64-bit PowerShell.' }
$targetRoot = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'CantoneseIME'
$planPath = Join-Path $targetRoot 'machine-registration.plan'
if ((Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash -ne $RegistrationPlanSha256) {
    throw 'Registration plan differs from the reviewed installation.'
}
$manifest = Get-Content -LiteralPath (Join-Path $targetRoot 'package-manifest.json') -Raw | ConvertFrom-Json
$helperPath = Join-Path $targetRoot 'native/CantoneseMachineRegistration.exe'
$helperRecord = @($manifest.files | Where-Object { $_.path -eq 'native/CantoneseMachineRegistration.exe' })
if ($helperRecord.Count -ne 1 -or (Get-FileHash -LiteralPath $helperPath -Algorithm SHA256).Hash -ne $helperRecord[0].sha256) {
    throw 'Installed registration helper does not match the package manifest.'
}
Write-Output "Machine COM/profile removal target: $targetRoot"
Write-Output 'Disable the user profile, stop its broker and close applications using the IME first. Runtime files will be retained.'
if ($WhatIfPreference) { return }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator approval is required.' }
if (-not $PSCmdlet.ShouldProcess($targetRoot,'Remove only the verified project machine COM and TSF definitions')) { return }
& $helperPath --action remove --manifest $planPath --manifest-sha256 $RegistrationPlanSha256 |
    Tee-Object -FilePath (Join-Path $targetRoot 'machine-remove.jsonl')
if ($LASTEXITCODE -ne 0) { throw 'Registration removal was incomplete; files are retained for inspection.' }
Write-Output 'Machine registration removed. Runtime files are retained so no loaded DLL or unrelated file is deleted.'
