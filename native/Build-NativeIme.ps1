param([string]$Compiler)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolchainLock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json
if (-not $Compiler) {
    $Compiler = Join-Path (Join-Path $projectRoot $toolchainLock.local_directory) 'bin/x86_64-w64-mingw32-clang++.exe'
}
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = Join-Path $projectRoot '.local/native/build-x64'
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$version = (& $compilerPath --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Compiler version check failed.' }
& (Join-Path $PSScriptRoot 'tsf/build.ps1') -Compiler $compilerPath -OutputDirectory $outputPath
& (Join-Path $PSScriptRoot 'settings/build.ps1') -Compiler $compilerPath -OutputDirectory $outputPath
$hostPath = Join-Path $outputPath 'CantoneseImeNativeTestHost.exe'
$hostArguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE',
    '-DWIN32_LEAN_AND_MEAN','-DNOMINMAX','-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00',
    '-municode','-mwindows','-static','-Wl,--dynamicbase','-Wl,--nxcompat',
    (Join-Path $PSScriptRoot 'testhost/testhost.cpp'),(Join-Path $PSScriptRoot 'tsf/tsf_guids.cpp'),'-o',$hostPath,
    '-luser32','-lgdi32','-lole32','-loleaut32','-luuid','-lcomctl32','-lshell32')
& $compilerPath @hostArguments
if ($LASTEXITCODE -ne 0) { throw "Native host compiler failed with exit code $LASTEXITCODE" }
function Get-PeMachine([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $reader = New-Object System.IO.BinaryReader($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw 'Missing MZ header.' }
        $stream.Position = 0x3c
        $peOffset = $reader.ReadUInt32()
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x4550) { throw 'Missing PE header.' }
        return $reader.ReadUInt16()
    } finally { $reader.Dispose(); $stream.Dispose() }
}
$artifacts = @('CantoneseIME.dll','CantoneseImeSettings.exe','CantoneseImeNativeTestHost.exe') | ForEach-Object {
    $path = Join-Path $outputPath $_
    $machine = Get-PeMachine $path
    if ($machine -ne 0x8664) { throw "Artifact is not AMD64: $path" }
    [ordered]@{ path=$path; bytes=(Get-Item -LiteralPath $path).Length;
        sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant(); pe_machine='0x8664' }
}
$sourcePaths = @('tsf/tsf.cpp','tsf/ipc.cpp','tsf/ipc.h','tsf/candidate_layout.h','tsf/candidate_font.h','tsf/candidate_appearance.h','tsf/input_mode_button.h','tsf/registration.cpp','tsf/ime_ids.h','tsf/tsf_guids.cpp','tsf/tsf_compat.h',
    'tsf/CantoneseIME.rc','tsf/resource.h','tsf/Build-Icons.ps1','tsf/icons/cantonese.ico','tsf/icons/mode-cantonese.ico','tsf/icons/mode-english.ico',
    'tsf/CantoneseIME.def','testhost/testhost.cpp','tsf/build.ps1','Build-NativeIme.ps1',
    'settings/settings.cpp','settings/settings_model.h','settings/settings.rc','settings/settings.manifest','settings/build.ps1')
$sources = $sourcePaths | ForEach-Object {
    $path = Join-Path $PSScriptRoot $_
    [ordered]@{path=$path;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest = [ordered]@{
    compiled_at_utc=[DateTime]::UtcNow.ToString('o'); compiler=$compilerPath; compiler_version=$version;
    toolchain_release=$toolchainLock.version; toolchain_archive_sha256=$toolchainLock.sha256;
    artifacts=@($artifacts); sources=@($sources); native_typing_verified=$false;
    note='Compilation and PE architecture evidence only. Registration, loading and real typing require separate observation.'
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outputPath 'build-manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 6
