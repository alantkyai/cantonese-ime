param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Use a fresh appearance test output directory.' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
$sourcePath = Join-Path $PSScriptRoot 'candidate_appearance_test.cpp'
$headerPath = Join-Path $PSScriptRoot '../candidate_appearance.h'
$layoutPath = Join-Path $PSScriptRoot '../candidate_layout.h'
$exe = Join-Path $outputPath 'CandidateAppearanceTest.exe'
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-Werror','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-municode','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    $sourcePath,'-o',$exe,'-luser32','-lshell32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Appearance test build failed with exit code $LASTEXITCODE" }
$output = & $exe (Join-Path $outputPath 'fixture')
if ($LASTEXITCODE -ne 0) { throw "Appearance native test failed with exit code $LASTEXITCODE" }
$result = $output | ConvertFrom-Json
if (-not $result.passed) { throw 'Appearance fixture did not report success.' }
$pins = @($sourcePath,$headerPath,$layoutPath,$PSCommandPath,$exe) | ForEach-Object {
    $item = Get-Item -LiteralPath $_
    [ordered]@{ path=$item.FullName; bytes=$item.Length; sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
[ordered]@{
    passed=$true; checked_at_utc=[DateTime]::UtcNow.ToString('o');
    compiler=$compilerPath; scope=$result.scope; sources_and_binary=$pins;
    registration_changed=$false; host_foreground_changed=$false;
    real_user_preferences_accessed=$false; learning_data_accessed=$false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'validation.json') -Encoding utf8
$output
