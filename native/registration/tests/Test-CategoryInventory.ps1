param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../../../.local/native/registration-hotfix-tests')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$exe = Join-Path $outputPath 'CategoryInventoryTest.exe'
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    (Join-Path $PSScriptRoot 'category_inventory_test.cpp'),(Join-Path $PSScriptRoot '../../tsf/tsf_guids.cpp'),
    '-o',$exe,'-lole32','-loleaut32','-luuid','-ladvapi32','-lshell32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Category inventory test build failed with exit code $LASTEXITCODE" }
& $exe
if ($LASTEXITCODE -ne 0) { throw "Category inventory test failed with exit code $LASTEXITCODE" }
Get-FileHash -LiteralPath $exe -Algorithm SHA256
