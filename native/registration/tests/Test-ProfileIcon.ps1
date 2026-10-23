param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [Parameter(Mandatory=$true)][string]$Helper,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../../../.local/native/switcher-icon-tests')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$helperPath = (Resolve-Path -LiteralPath $Helper).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$exe = Join-Path $outputPath 'ProfileIconTest.exe'
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-municode','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    (Join-Path $PSScriptRoot 'profile_icon_test.cpp'),(Join-Path $PSScriptRoot '../../tsf/tsf_guids.cpp'),
    '-o',$exe,'-lole32','-loleaut32','-luuid','-ladvapi32','-lshell32','-luser32','-lgdi32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Profile icon test build failed with exit code $LASTEXITCODE" }
$fixtureRoot = Join-Path $outputPath 'profile-icon-product'
$fixtureNative = Join-Path $fixtureRoot 'native'
New-Item -ItemType Directory -Path $fixtureNative -Force | Out-Null
$fixtureHelper = Join-Path $fixtureNative 'CantoneseMachineRegistration.exe'
Copy-Item -LiteralPath $helperPath -Destination $fixtureHelper -Force
& $exe $fixtureRoot $fixtureHelper
if ($LASTEXITCODE -ne 0) { throw "Profile icon test failed with exit code $LASTEXITCODE" }
Get-FileHash -LiteralPath $exe,$helperPath,$fixtureHelper -Algorithm SHA256
