[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ManifestSha256
)
$ErrorActionPreference = 'Stop'
if ([IntPtr]::Size -ne 8) { throw 'Use 64-bit PowerShell.' }
$sourceRoot = (Resolve-Path -LiteralPath $PackageRoot).Path.TrimEnd('\','/')
$manifestPath = Join-Path $sourceRoot 'package-manifest.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne $ManifestSha256) {
    throw 'Package manifest does not match the explicitly supplied hash.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or $manifest.kind -ne 'Cantonese IME native AMD64 preview runtime package') {
    throw 'Unexpected package manifest.'
}
$seen = @{}
foreach ($item in $manifest.files) {
    if ([IO.Path]::IsPathRooted($item.path) -or $item.path.Contains(':') -or
        ($item.path -split '[\\/]') -contains '..' -or $seen.ContainsKey($item.path)) {
        throw 'Invalid or duplicate package path.'
    }
    $seen[$item.path] = $true
    $inputPath = [IO.Path]::GetFullPath((Join-Path $sourceRoot $item.path))
    if (-not $inputPath.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Package input resolves outside its root.'
    }
    if ((Get-Item -LiteralPath $inputPath).Length -ne [long]$item.bytes -or
        (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash -ne $item.sha256) {
        throw "Package file differs from the reviewed manifest: $($item.path)"
    }
}
foreach ($required in @('native/CantoneseIME.dll','native/CantoneseMachineRegistration.exe','native/runtime/control.py','runtime-config.json')) {
    if (-not $seen.ContainsKey($required)) { throw "Package lacks $required" }
}
$targetRoot = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'CantoneseIME'
if (Test-Path -LiteralPath $targetRoot) { throw "Destination already exists; refusing overwrite: $targetRoot" }
$classPath = 'Registry::HKEY_CURRENT_USER\Software\Classes\CLSID\{67718E6F-49A1-4F54-88D6-30578FC70C5D}'
$hasPreviewOverride = Test-Path -LiteralPath $classPath
Write-Output "Verified runtime package: $sourceRoot"
Write-Output "Protected destination: $targetRoot"
Write-Output "Existing preview HKCU COM override: $hasPreviewOverride"
Write-Output 'Machine COM and TSF definitions will be installed; user enabling, broker start and login startup are separate.'
if ($WhatIfPreference) { return }
if ($hasPreviewOverride) { throw 'Remove only the verified preview HKCU COM override as the original user before machine installation.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator approval is required for machine TSF registration. This script does not request or automate UAC.'
}
if (-not $PSCmdlet.ShouldProcess($targetRoot,'Install the reviewed native IME runtime and machine TSF definitions')) { return }
New-Item -ItemType Directory -Path $targetRoot | Out-Null
foreach ($item in $manifest.files) {
    $targetPath = Join-Path $targetRoot $item.path
    New-Item -ItemType Directory -Path (Split-Path -Parent $targetPath) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourceRoot $item.path) -Destination $targetPath
    if ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash -ne $item.sha256) {
        throw "Installed copy failed verification: $($item.path). Files retained for inspection."
    }
}
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $targetRoot 'package-manifest.json')
$dll = Join-Path $targetRoot 'native/CantoneseIME.dll'
$planPath = Join-Path $targetRoot 'machine-registration.plan'
$plan = @('CANTONESE_IME_MACHINE_V1',
    'clsid={67718E6F-49A1-4F54-88D6-30578FC70C5D}',
    'profile={A7136205-2245-45CC-A6AA-702B3F2E8D42}',
    'languages=0409,0c04',"dll_source=$dll","dll_target=$dll",("dll_sha256=" + $manifest.native_dll_sha256))
[IO.File]::WriteAllText($planPath,($plan -join "`n") + "`n",(New-Object Text.UTF8Encoding($false)))
$planHash = (Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant()
$helper = Join-Path $targetRoot 'native/CantoneseMachineRegistration.exe'
& $helper --action install --manifest $planPath --manifest-sha256 $planHash |
    Tee-Object -FilePath (Join-Path $targetRoot 'machine-install.jsonl')
if ($LASTEXITCODE -ne 0) { throw 'Machine registration failed. Runtime files and diagnostics are retained; inspect rollback before retry/removal.' }
[ordered]@{package_manifest_sha256=$ManifestSha256.ToLowerInvariant();registration_plan_sha256=$planHash;
    installed_at_utc=[DateTime]::UtcNow.ToString('o');user_enabling_complete=$false;startup_installed=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $targetRoot 'installation.json') -Encoding UTF8
Write-Output 'Machine definitions installed. Return to the normal user session to enable the profile and start its broker.'
