param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'build-x64')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$exePath = Join-Path $outputPath 'CantoneseImeSettings.exe'
$resourceCompiler = Join-Path (Split-Path -Parent $compilerPath) 'llvm-rc.exe'
$resourcePath = Join-Path $outputPath 'CantoneseImeSettings.res'
Push-Location $PSScriptRoot
try {
    & $resourceCompiler '/fo' $resourcePath '/i' (Join-Path (Split-Path -Parent (Split-Path -Parent $compilerPath)) 'include') 'settings.rc'
    if ($LASTEXITCODE -ne 0) { throw "Settings resource compiler failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-municode','-mwindows','-static','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    (Join-Path $PSScriptRoot 'settings.cpp'), $resourcePath,
    '-o',$exePath,'-luser32','-lgdi32','-lcomctl32','-lshell32','-ladvapi32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Settings compiler failed with exit code $LASTEXITCODE" }
Get-Item -LiteralPath $exePath | Select-Object FullName,Length
