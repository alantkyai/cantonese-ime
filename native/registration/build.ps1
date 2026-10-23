param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'build-x64')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$exePath = Join-Path $outputPath 'CantoneseMachineRegistration.exe'
$resourceCompiler = Join-Path (Split-Path -Parent $compilerPath) 'llvm-rc.exe'
$resourcePath = Join-Path $outputPath 'CantoneseMachineRegistration.res'
Push-Location $PSScriptRoot
try {
    & $resourceCompiler '/fo' $resourcePath 'branding.rc'
    if ($LASTEXITCODE -ne 0) { throw "Branding resource compiler failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-municode','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    (Join-Path $PSScriptRoot 'machine.cpp'), (Join-Path $PSScriptRoot '../tsf/tsf_guids.cpp'), $resourcePath,
    '-o',$exePath,'-lole32','-loleaut32','-luuid','-ladvapi32','-lshell32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Native compiler failed with exit code $LASTEXITCODE" }
Get-Item -LiteralPath $exePath | Select-Object FullName,Length
Get-FileHash -LiteralPath $exePath -Algorithm SHA256
