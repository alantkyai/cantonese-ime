param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [Parameter(Mandatory=$true)][string]$Dll,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../../../.local/native/release-tests')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$dllPath = (Resolve-Path -LiteralPath $Dll).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$exe = Join-Path $outputPath 'InputModeButtonTest.exe'
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-municode','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    (Join-Path $PSScriptRoot 'input_mode_button_test.cpp'),(Join-Path $PSScriptRoot '../tsf_guids.cpp'),
    '-o',$exe,'-lole32','-loleaut32','-luuid','-luser32','-lgdi32','-lshell32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Input mode test build failed with exit code $LASTEXITCODE" }
& $exe $dllPath (Join-Path $outputPath 'input-mode-contrast.bmp')
if ($LASTEXITCODE -ne 0) { throw "Input mode native test failed with exit code $LASTEXITCODE" }
Get-FileHash -LiteralPath $exe,$dllPath -Algorithm SHA256
