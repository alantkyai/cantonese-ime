# Read-only development preflight for a native Windows TSF IME.
# PowerShell 5.1+; writes JSON to stdout and makes no machine configuration changes.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$notes = New-Object 'System.Collections.Generic.List[string]'

function Get-ExecutableOnPath {
    param([string]$Name)
    $command = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return $command.Source
    }
    return $null
}

function Invoke-NativeProbe {
    param([string]$Executable, [string[]]$Arguments)
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return [pscustomobject]@{ Executed = $false; ExitCode = $null; Text = ''; Status = 'not_found' }
    }
    # Store execution aliases can open the Microsoft Store instead of running a tool.
    if ($Executable -match '\\Microsoft\\WindowsApps\\') {
        return [pscustomobject]@{ Executed = $false; ExitCode = $null; Text = ''; Status = 'app_execution_alias_not_invoked' }
    }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $probeLines = @(& $Executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $probeExitCode = $LASTEXITCODE
        return [pscustomobject]@{ Executed = $true; ExitCode = $probeExitCode; Text = ($probeLines -join "`n"); Status = 'executed' }
    }
    catch {
        return [pscustomobject]@{ Executed = $false; ExitCode = $null; Text = ''; Status = 'execution_failed' }
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Get-ToolVersion {
    param([string]$Name, [string[]]$Arguments, [string]$Pattern)
    $executable = Get-ExecutableOnPath -Name $Name
    $probe = Invoke-NativeProbe -Executable $executable -Arguments $Arguments
    $versionMatch = [regex]::Match($probe.Text, $Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    return [pscustomobject]@{
        foundOnPath = [bool]$executable
        status = $probe.Status
        exitCode = $probe.ExitCode
        version = $(if ($versionMatch.Success) { $versionMatch.Groups[1].Value } else { $null })
    }
}

# Only selected OS fields are returned; no host name, user name, serials or IDs.
$os = [ordered]@{ caption = $null; captionSource = $null; registryProductName = $null; edition = $null; displayVersion = $null; version = $null; build = $null; updateBuildRevision = $null; architecture = $null }
$osRegistryPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
if (Test-Path -LiteralPath $osRegistryPath) {
    try {
        $osRegistry = Get-ItemProperty -LiteralPath $osRegistryPath
        $os.registryProductName = $osRegistry.ProductName
        $os.edition = $osRegistry.EditionID
        $os.displayVersion = $osRegistry.DisplayVersion
        $os.build = $osRegistry.CurrentBuildNumber
        $os.updateBuildRevision = $osRegistry.UBR
        if ($null -ne $osRegistry.CurrentMajorVersionNumber -and $null -ne $osRegistry.CurrentMinorVersionNumber) {
            $os.version = '{0}.{1}.{2}' -f $osRegistry.CurrentMajorVersionNumber, $osRegistry.CurrentMinorVersionNumber, $osRegistry.CurrentBuildNumber
        }
        # Windows 11 may retain "Windows 10" in ProductName. Leave that caption
        # unverified rather than returning a misleading label if CIM is unavailable.
        if (-not ($osRegistry.InstallationType -eq 'Client' -and [int]$osRegistry.CurrentBuildNumber -ge 22000 -and $osRegistry.ProductName -match 'Windows 10')) {
            $os.caption = $osRegistry.ProductName
            $os.captionSource = 'registry'
        }
    }
    catch { $notes.Add('Windows version registry values could not be read.') }
}
try {
    $osCim = Get-CimInstance -ClassName Win32_OperatingSystem -Property Caption, Version, BuildNumber, OSArchitecture -ErrorAction Stop
    $os.caption = $osCim.Caption
    $os.captionSource = 'CIM'
    $os.version = $osCim.Version
    $os.build = $osCim.BuildNumber
    $os.architecture = $osCim.OSArchitecture
}
catch {
    $notes.Add('CIM OS lookup was unavailable; OS version uses registry values and architecture uses process environment plus .NET bitness checks.')
    $os.architecture = $(if ([Environment]::Is64BitOperatingSystem) { '64-bit' } else { '32-bit' })
}
$processArchitecture = $env:PROCESSOR_ARCHITECTURE
$osCpuArchitecture = $(if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE })

$pathTools = [ordered]@{
    python = Get-ToolVersion -Name 'python.exe' -Arguments @('--version') -Pattern 'Python\s+([\d.]+)'
    pythonLauncher = Get-ToolVersion -Name 'py.exe' -Arguments @('--version') -Pattern 'Python\s+([\d.]+)'
    node = Get-ToolVersion -Name 'node.exe' -Arguments @('--version') -Pattern '\bv([\d.]+)'
    git = Get-ToolVersion -Name 'git.exe' -Arguments @('--version') -Pattern 'git version\s+(\S+)'
    cmake = Get-ToolVersion -Name 'cmake.exe' -Arguments @('--version') -Pattern 'cmake version\s+(\S+)'
    ninja = Get-ToolVersion -Name 'ninja.exe' -Arguments @('--version') -Pattern '^\s*([\d.]+)'
    cl = Get-ToolVersion -Name 'cl.exe' -Arguments @('/?') -Pattern 'Compiler Version\s+(\S+)'
}

# Check dotnet on PATH and in standard install roots. A runtime does not imply an SDK.
$dotnetExecutables = New-Object 'System.Collections.Generic.List[string]'
$dotnetPathExecutable = Get-ExecutableOnPath -Name 'dotnet.exe'
if ($dotnetPathExecutable) { $dotnetExecutables.Add($dotnetPathExecutable) }
$dotnetRoots = @()
if ($env:ProgramFiles) { $dotnetRoots += (Join-Path $env:ProgramFiles 'dotnet') }
if (${env:ProgramFiles(x86)}) { $dotnetRoots += (Join-Path ${env:ProgramFiles(x86)} 'dotnet') }
if ($env:DOTNET_ROOT) { $dotnetRoots += $env:DOTNET_ROOT }
if (${env:DOTNET_ROOT(x86)}) { $dotnetRoots += ${env:DOTNET_ROOT(x86)} }
foreach ($dotnetRoot in ($dotnetRoots | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $dotnetRoot -PathType Container)) { continue }
    $candidate = Join-Path $dotnetRoot 'dotnet.exe'
    if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and -not $dotnetExecutables.Contains($candidate)) { $dotnetExecutables.Add($candidate) }
}
$dotnetInstalls = @(
    foreach ($dotnetExecutable in $dotnetExecutables) {
        $sdkProbe = Invoke-NativeProbe -Executable $dotnetExecutable -Arguments @('--list-sdks')
        $runtimeProbe = Invoke-NativeProbe -Executable $dotnetExecutable -Arguments @('--list-runtimes')
        $infoProbe = Invoke-NativeProbe -Executable $dotnetExecutable -Arguments @('--info')
        $sdkVersions = @([regex]::Matches($sdkProbe.Text, '(?m)^([0-9]+\.[0-9]+\.[^\s]+)\s+\[') | ForEach-Object { $_.Groups[1].Value })
        $runtimeVersions = @([regex]::Matches($runtimeProbe.Text, '(?m)^(Microsoft\.[^\s]+)\s+([^\s]+)\s+\[') | ForEach-Object { $_.Groups[1].Value + ' ' + $_.Groups[2].Value })
        $hostVersionMatch = [regex]::Match($infoProbe.Text, '(?ms)^Host:\s*\r?\n\s*Version:\s*(\S+)')
        $hostArchitectureMatch = [regex]::Match($infoProbe.Text, '(?m)^\s*Architecture:\s*(\S+)')
        [pscustomobject]@{
            origin = $(if ($dotnetExecutable -eq $dotnetPathExecutable) { 'PATH' } else { 'standard_or_configured_root' })
            hostVersion = $(if ($hostVersionMatch.Success) { $hostVersionMatch.Groups[1].Value } else { $null })
            hostArchitecture = $(if ($hostArchitectureMatch.Success) { $hostArchitectureMatch.Groups[1].Value } else { $null })
            sdkQueryStatus = $sdkProbe.Status
            sdkQueryExitCode = $sdkProbe.ExitCode
            sdkAvailable = $(if ($sdkProbe.Executed -and $sdkProbe.ExitCode -eq 0) { $sdkVersions.Count -gt 0 } else { $null })
            sdkVersions = $sdkVersions
            runtimeQueryExitCode = $runtimeProbe.ExitCode
            runtimeVersions = $runtimeVersions
        }
    }
)

# vswhere is used only from Microsoft's standard Visual Studio Installer location.
$vswherePath = $null
if (${env:ProgramFiles(x86)}) { $vswherePath = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe' }
$vswherePresent = [bool]($vswherePath -and (Test-Path -LiteralPath $vswherePath -PathType Leaf))
$visualStudioInstalls = @()
$vsQueryStatus = 'not_found'
if ($vswherePresent) {
    $vsProbe = Invoke-NativeProbe -Executable $vswherePath -Arguments @('-all', '-prerelease', '-products', '*', '-format', 'json', '-utf8')
    $vsQueryStatus = $vsProbe.Status
    if ($vsProbe.Executed -and $vsProbe.ExitCode -eq 0) {
        try {
            $vsInstances = @($vsProbe.Text | ConvertFrom-Json)
            $visualStudioInstalls = @(
                foreach ($instance in $vsInstances) {
                    if (-not $instance.installationPath -or -not (Test-Path -LiteralPath $instance.installationPath -PathType Container)) { continue }
                    $msvcRoot = Join-Path $instance.installationPath 'VC\Tools\MSVC'
                    $toolsets = @()
                    if (Test-Path -LiteralPath $msvcRoot -PathType Container) {
                        $toolsets = @(
                            foreach ($toolset in (Get-ChildItem -LiteralPath $msvcRoot -Directory -ErrorAction SilentlyContinue)) {
                                $compilers = @(
                                    foreach ($hostArch in @('Hostx64', 'Hostx86', 'Hostarm64')) {
                                        foreach ($targetArch in @('x64', 'x86', 'arm64', 'arm', 'arm64ec')) {
                                            $compilerPath = Join-Path $toolset.FullName ('bin\' + $hostArch + '\' + $targetArch + '\cl.exe')
                                            if (Test-Path -LiteralPath $compilerPath -PathType Leaf) {
                                                [pscustomobject]@{ host = $hostArch; target = $targetArch }
                                            }
                                        }
                                    }
                                )
                                [pscustomobject]@{ version = $toolset.Name; compilers = $compilers }
                            }
                        )
                    }
                    $bundledCmake = Join-Path $instance.installationPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
                    $bundledNinja = Join-Path $instance.installationPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe'
                    [pscustomobject]@{
                        displayName = $instance.displayName
                        installationVersion = $instance.installationVersion
                        isComplete = $instance.isComplete
                        msvcToolsets = $toolsets
                        bundledCmakePresent = (Test-Path -LiteralPath $bundledCmake -PathType Leaf)
                        bundledNinjaPresent = (Test-Path -LiteralPath $bundledNinja -PathType Leaf)
                    }
                }
            )
        }
        catch { $vsQueryStatus = 'query_or_parse_failed' }
    }
    elseif ($vsProbe.ExitCode -ne 0) { $vsQueryStatus = 'query_failed' }
}

$sdkRoots = @()
$sdkRegistryPaths = @('HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows Kits\Installed Roots')
foreach ($sdkRegistryPath in $sdkRegistryPaths) {
    if (-not (Test-Path -LiteralPath $sdkRegistryPath)) { continue }
    try {
        $sdkRegistry = Get-ItemProperty -LiteralPath $sdkRegistryPath
        foreach ($property in @('KitsRoot10', 'KitsRoot81')) {
            if ($sdkRegistry.$property) { $sdkRoots += [string]$sdkRegistry.$property }
        }
    }
    catch { $notes.Add('A Windows SDK registry root could not be read.') }
}
if (${env:ProgramFiles(x86)}) {
    $sdkRoots += (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10')
    $sdkRoots += (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\8.1')
}
# Trim only directory separators so registry and conventional root duplicates coalesce.
$sdkRoots = @($sdkRoots | ForEach-Object { $_.TrimEnd('\', '/') } | Select-Object -Unique)
$windowsSdkHeaders = @(
    foreach ($sdkRoot in $sdkRoots) {
        if (-not (Test-Path -LiteralPath $sdkRoot -PathType Container)) { continue }
        $includeRoot = Join-Path $sdkRoot 'Include'
        if (-not (Test-Path -LiteralPath $includeRoot -PathType Container)) { continue }
        $versionDirectories = @(Get-ChildItem -LiteralPath $includeRoot -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d+\.\d+\.' })
        $includeSets = @($versionDirectories | ForEach-Object { [pscustomobject]@{ version = $_.Name; directory = $_.FullName } })
        if (Test-Path -LiteralPath (Join-Path $includeRoot 'um\Windows.h') -PathType Leaf) {
            $includeSets += [pscustomobject]@{ version = '8.1/non-versioned'; directory = $includeRoot }
        }
        foreach ($includeSet in $includeSets) {
            [pscustomobject]@{
                version = $includeSet.version
                windowsHeaderPresent = (Test-Path -LiteralPath (Join-Path $includeSet.directory 'um\Windows.h') -PathType Leaf)
                tsfHeaderPresent = (Test-Path -LiteralPath (Join-Path $includeSet.directory 'um\msctf.h') -PathType Leaf)
                tsfFunctionsHeaderPresent = (Test-Path -LiteralPath (Join-Path $includeSet.directory 'um\ctffunc.h') -PathType Leaf)
            }
        }
    }
)

$notes.Add('PATH results do not establish that a tool is absent from the machine. Visual Studio and Windows SDK discovery are reported separately; custom tool installations outside checked roots are not exhaustively searched.')
$notes.Add('Compiler files and SDK headers were checked for presence. No compilation, linking, SDK library validation, installation or IME registration was performed.')
$notes.Add('Executable locations and raw error output are intentionally omitted to avoid exposing user-profile paths.')
[ordered]@{
    schemaVersion = 1
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    powershellVersion = $PSVersionTable.PSVersion.ToString()
    os = $os
    cpuArchitecture = $osCpuArchitecture
    processArchitecture = $processArchitecture
    pathTools = $pathTools
    dotnet = [ordered]@{ foundOnPath = [bool]$dotnetPathExecutable; discoveredInstalls = $dotnetInstalls }
    visualStudio = [ordered]@{ vswhereInStandardLocation = $vswherePresent; queryStatus = $vsQueryStatus; installations = $visualStudioInstalls }
    windowsSdkHeaders = $windowsSdkHeaders
    notes = @($notes)
} | ConvertTo-Json -Depth 10
