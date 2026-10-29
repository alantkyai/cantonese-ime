param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Use a fresh settings test output directory.' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
$exe = Join-Path $outputPath 'SettingsModelTest.exe'
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-Werror','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-municode','-Wl,--no-undefined',
    (Join-Path $PSScriptRoot 'settings_model_test.cpp'),'-o',$exe,'-luser32','-lshell32','-lgdi32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Settings model test build failed with exit code $LASTEXITCODE" }
$output = & $exe (Join-Path $outputPath 'fixture')
if ($LASTEXITCODE -ne 0) { throw "Settings model test failed with exit code $LASTEXITCODE" }
if (-not ($output | ConvertFrom-Json).passed) { throw 'Settings model test did not report success.' }
$output
