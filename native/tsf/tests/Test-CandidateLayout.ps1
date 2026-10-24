param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$Font = (Join-Path $PSScriptRoot '../../../assets/fonts/lxgw-wenkai-tc/LXGWWenKaiTC-Regular.ttf')
)
$ErrorActionPreference = 'Stop'
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$fontPath = (Resolve-Path -LiteralPath $Font).Path
if ((Get-FileHash -LiteralPath $fontPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne '6662480a3f95b4a90c80b189c679617a48adce3a505118a6af63ce5a482b83fa') {
    throw 'Use the exact bundled font asset.'
}
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Use a fresh candidate layout test output directory.' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
$sourcePaths = @('candidate_layout_test.cpp','candidate_layout_render_test.cpp','../candidate_layout.h','../candidate_appearance.h','../candidate_font.h') | ForEach-Object {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot $_)).Path
}
$sourcePaths += $PSCommandPath
$sourcePaths += $fontPath
$sourcePins = @{}
foreach ($path in $sourcePaths) { $sourcePins[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$geometryExe = Join-Path $outputPath 'CandidateLayoutTest.exe'
& $compilerPath '-std=c++17' '-O2' '-Wall' '-Wextra' '-Werror' '-static' $sourcePaths[0] '-o' $geometryExe
if ($LASTEXITCODE -ne 0) { throw "Layout geometry compilation failed: $LASTEXITCODE" }
$geometryOutput = & $geometryExe
if ($LASTEXITCODE -ne 0) { throw "Layout geometry assertions failed: $LASTEXITCODE" }
$renderExe = Join-Path $outputPath 'CandidateLayoutRenderTest.exe'
$arguments = @('-std=c++17','-O2','-Wall','-Wextra','-Werror','-DUNICODE','-D_UNICODE','-DWIN32_LEAN_AND_MEAN','-DNOMINMAX',
    '-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-static','-municode','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat',
    $sourcePaths[1],'-o',$renderExe,'-luser32','-lgdi32','-lshell32')
& $compilerPath @arguments
if ($LASTEXITCODE -ne 0) { throw "Layout render compilation failed: $LASTEXITCODE" }
$renderOutput = @(& $renderExe $outputPath $fontPath)
if ($LASTEXITCODE -ne 0) { throw "Layout render assertions failed: $LASTEXITCODE" }
$results = @($renderOutput | ForEach-Object { $_ | ConvertFrom-Json })
$summary = $results | Where-Object { $_.passed } | Select-Object -Last 1
if (-not $summary.passed -or $summary.renders -ne 12) { throw 'Incomplete layout render result.' }
foreach ($path in $sourcePaths) {
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourcePins[$path]) { throw "Source changed during layout checks: $path" }
}
$pins = @($sourcePaths + @($geometryExe,$renderExe)) | ForEach-Object {
    $item = Get-Item -LiteralPath $_
    [ordered]@{ path=$item.FullName; bytes=$item.Length; sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
[ordered]@{
    passed=$true; checked_at_utc=[DateTime]::UtcNow.ToString('o'); compiler=$compilerPath;
    scope=$summary.scope; geometry=$geometryOutput; renders=@($results | Where-Object { $_.render });
    source_and_binary_pins=$pins; sources_unchanged=$true;
    registration_changed=$false; global_font_installation_changed=$false;
    real_user_preferences_accessed=$false; learning_data_accessed=$false
} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $outputPath 'validation.json') -Encoding utf8
$geometryOutput
$renderOutput
