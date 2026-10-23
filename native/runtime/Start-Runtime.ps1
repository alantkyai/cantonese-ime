param([string]$Config = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'runtime-config.json'))
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$pythonPath = [string]$settings.python_executable
if (-not [System.IO.Path]::IsPathRooted($pythonPath)) {
    $pythonPath = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $configPath) $pythonPath))
}
if (-not [System.IO.Path]::IsPathRooted($pythonPath) -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'The runtime config must reference an existing absolute x64 Python executable.'
}
& $pythonPath -I (Join-Path $PSScriptRoot 'control.py') start --config $configPath
if ($LASTEXITCODE -ne 0) { throw "Runtime start failed with exit code $LASTEXITCODE." }
