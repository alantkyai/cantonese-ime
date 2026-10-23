param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'build-x64')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$dllPath = Join-Path $outputPath 'CantoneseIME.dll'
$resourceCompiler = Join-Path (Split-Path -Parent $compilerPath) 'llvm-rc.exe'
$resourcePath = Join-Path $outputPath 'CantoneseIME.res'
Push-Location $PSScriptRoot
try {
    & $resourceCompiler '/fo' $resourcePath '/i' (Join-Path (Split-Path -Parent (Split-Path -Parent $compilerPath)) 'include') 'CantoneseIME.rc'
    if ($LASTEXITCODE -ne 0) { throw "Resource compiler failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
$sourcePaths = @('tsf.cpp','ipc.cpp','registration.cpp','tsf_guids.cpp','CantoneseIME.def') | ForEach-Object { Join-Path $PSScriptRoot $_ }
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-shared','-static','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat')
$arguments += $sourcePaths
$arguments += $resourcePath
$arguments += @('-o',$dllPath,'-lole32','-loleaut32','-luuid','-luser32','-lgdi32','-ladvapi32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Native compiler failed with exit code $LASTEXITCODE" }
Get-Item -LiteralPath $dllPath | Select-Object FullName,Length
Get-FileHash -LiteralPath $dllPath -Algorithm SHA256
