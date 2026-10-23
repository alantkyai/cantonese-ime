# Read-only inspection of one process and its matching loaded IME modules.
# Run from x64 PowerShell 5.1+ or PowerShell 7. JSON is written to stdout only.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$TargetProcessId,

    [string]$ModulePattern = '(?i)(typeduck|weasel|moqi)'
)

$ErrorActionPreference = 'Stop'

function Get-PeMachine {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $stream = $null
    $reader = $null
    try {
        if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
            return [pscustomobject]@{ status = 'file_not_found'; machine = $null; architecture = $null; isX64 = $null }
        }
        $stream = [System.IO.File]::Open($LiteralPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
        $reader = New-Object System.IO.BinaryReader($stream)
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D) { throw 'Invalid DOS header.' }
        $stream.Position = 0x3C
        $peOffset = [long]$reader.ReadUInt32()
        if ($peOffset -lt 64 -or $peOffset -gt ($stream.Length - 24)) { throw 'PE header offset is out of bounds.' }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) { throw 'Invalid PE signature.' }
        $machine = $reader.ReadUInt16()
        $sectionCount = $reader.ReadUInt16()
        $stream.Position = $peOffset + 20
        $optionalHeaderSize = $reader.ReadUInt16()
        $null = $reader.ReadUInt16() # Characteristics.
        $optionalHeaderOffset = $peOffset + 24
        $sectionTableEnd = $optionalHeaderOffset + $optionalHeaderSize + ([long]$sectionCount * 40)
        if ($sectionCount -lt 1 -or $optionalHeaderSize -lt 2 -or $sectionTableEnd -gt $stream.Length) { throw 'PE header tables are out of bounds.' }
        $optionalMagic = $reader.ReadUInt16()
        if ($optionalMagic -ne 0x10B -and $optionalMagic -ne 0x20B) { throw 'Invalid optional header magic.' }
        if (($machine -eq 0x8664 -and $optionalMagic -ne 0x20B) -or ($machine -eq 0x014C -and $optionalMagic -ne 0x10B)) { throw 'Machine and optional header disagree.' }
        $architecture = switch ($machine) {
            0x014C { 'I386/x86'; break }
            0x8664 { 'AMD64/x64'; break }
            0xAA64 { 'ARM64'; break }
            0xA641 { 'ARM64EC'; break }
            0xA64E { 'ARM64X'; break }
            0x01C0 { 'ARM'; break }
            0x01C4 { 'ARMNT/Thumb-2'; break }
            0x0200 { 'IA64'; break }
            default { 'unknown' }
        }
        return [pscustomobject]@{
            status = 'parsed'
            machine = ('0x{0:X4}' -f $machine)
            architecture = $architecture
            optionalHeaderMagic = ('0x{0:X3}' -f $optionalMagic)
            isX64 = ($machine -eq 0x8664)
        }
    }
    catch {
        $failureStatus = 'invalid_or_unreadable_pe'
        if ($_.Exception -is [System.UnauthorizedAccessException]) { $failureStatus = 'access_denied' }
        return [pscustomobject]@{ status = $failureStatus; machine = $null; architecture = $null; isX64 = $null }
    }
    finally {
        if ($reader) { $reader.Dispose() }
        elseif ($stream) { $stream.Dispose() }
    }
}

function Get-FileEvidence {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $initialLength = $null
    $initialWriteTime = $null
    try {
        $initialFile = Get-Item -LiteralPath $LiteralPath -ErrorAction Stop
        $initialLength = $initialFile.Length
        $initialWriteTime = $initialFile.LastWriteTimeUtc
    }
    catch { }
    $pe = Get-PeMachine -LiteralPath $LiteralPath
    $sha256 = $null
    $hashStatus = 'not_read'
    try {
        if (Test-Path -LiteralPath $LiteralPath -PathType Leaf) {
            $sha256 = (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256 -ErrorAction Stop).Hash
            $hashStatus = 'read'
        }
        else { $hashStatus = 'file_not_found' }
    }
    catch { $hashStatus = 'read_failed' }
    $signatureStatus = 'not_checked'
    try {
        if (Test-Path -LiteralPath $LiteralPath -PathType Leaf) {
            $signatureStatus = (Get-AuthenticodeSignature -LiteralPath $LiteralPath -ErrorAction Stop).Status.ToString()
        }
        else { $signatureStatus = 'file_not_found' }
    }
    catch { $signatureStatus = 'check_failed' }
    $fileUnchangedDuringInspection = $null
    try {
        $finalFile = Get-Item -LiteralPath $LiteralPath -ErrorAction Stop
        if ($null -ne $initialLength -and $null -ne $initialWriteTime) {
            $fileUnchangedDuringInspection = ($initialLength -eq $finalFile.Length -and $initialWriteTime -eq $finalFile.LastWriteTimeUtc)
        }
    }
    catch { }
    return [pscustomobject]@{
        path = $LiteralPath
        pe = $pe
        sha256 = $sha256
        hashStatus = $hashStatus
        signatureStatus = $signatureStatus
        fileUnchangedDuringInspection = $fileUnchangedDuringInspection
    }
}

$inspectorArchitecture = $env:PROCESSOR_ARCHITECTURE
try { $inspectorArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString() } catch { }
$inspectorIsX64 = [Environment]::Is64BitProcess -and $inspectorArchitecture -match '^(X64|AMD64)$'
$result = [ordered]@{
    schemaVersion = 1
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    powershellVersion = $PSVersionTable.PSVersion.ToString()
    inspectorArchitecture = $inspectorArchitecture
    inspectorIsX64 = $inspectorIsX64
    targetProcessId = $TargetProcessId
    modulePattern = $ModulePattern
    inspectionStatus = 'not_started'
    processName = $null
    processStartTimeUtc = $null
    hostExecutable = $null
    moduleEnumerationStatus = 'not_attempted'
    matchingModuleCount = 0
    matchingModules = @()
    processStillRunningAtEnd = $null
    hostX64 = $false
    moduleX64 = $false
    nativeX64MappingVerified = $false
    verificationStatus = 'not_verified'
    notes = @(
        'Only the requested PID is queried. Modules are observed through Get-Process.Modules; PE headers, hashes and signature statuses are read from their mapped file paths on disk.',
        'A verified x64 mapping establishes that matching native x64 modules were loaded into this x64 host at inspection time. It does not establish that preedit, candidate UI or text commit works.',
        'Signature status is reported independently of architecture. No files, registry values, IME registrations or user windows are modified.'
    )
}

try { $moduleRegex = New-Object System.Text.RegularExpressions.Regex($ModulePattern) }
catch {
    $result.inspectionStatus = 'invalid_module_pattern'
    $result.verificationStatus = 'invalid_module_pattern'
    $result | ConvertTo-Json -Depth 10
    return
}
if (-not $inspectorIsX64) {
    $result.inspectionStatus = 'requires_x64_powershell'
    $result.verificationStatus = 'requires_x64_powershell'
    $result | ConvertTo-Json -Depth 10
    return
}

$targetProcess = $null
try {
    $targetProcess = Get-Process -Id $TargetProcessId -ErrorAction Stop
    $result.processName = $targetProcess.ProcessName
    try { $result.processStartTimeUtc = $targetProcess.StartTime.ToUniversalTime().ToString('o') } catch { }
    $hostPath = $null
    try { $hostPath = $targetProcess.Path } catch { }
    if (-not $hostPath) {
        try { $hostPath = $targetProcess.MainModule.FileName } catch { }
    }
    if ($hostPath) {
        $result.hostExecutable = Get-FileEvidence -LiteralPath $hostPath
        $result.hostX64 = ($result.hostExecutable.pe.status -eq 'parsed' -and $result.hostExecutable.pe.isX64 -eq $true)
    }

    try {
        # Materialize the collection inside this try: an enumeration exception must
        # never be confused with a successful inspection containing no IME modules.
        $loadedModules = @($targetProcess.Modules)
        if ($loadedModules.Count -eq 0) {
            $result.moduleEnumerationStatus = 'empty_collection_unverified'
        }
        else {
            $result.moduleEnumerationStatus = 'succeeded'
            $result.matchingModules = @(
                foreach ($module in $loadedModules) {
                    if ($moduleRegex.IsMatch($module.ModuleName) -or $moduleRegex.IsMatch($module.FileName)) {
                        [pscustomobject]@{
                            moduleName = $module.ModuleName
                            baseAddress = ('0x{0:X}' -f $module.BaseAddress.ToInt64())
                            mappedSizeBytes = $module.ModuleMemorySize
                            file = (Get-FileEvidence -LiteralPath $module.FileName)
                        }
                    }
                }
            )
        }
    }
    catch {
        $result.moduleEnumerationStatus = 'failed'
        $result.matchingModules = @()
    }
    $result.matchingModuleCount = $result.matchingModules.Count
    $invalidModules = @($result.matchingModules | Where-Object { $_.file.pe.status -ne 'parsed' -or $_.file.pe.isX64 -ne $true })
    $result.moduleX64 = ($result.matchingModuleCount -gt 0 -and $invalidModules.Count -eq 0)
    try {
        $targetProcess.Refresh()
        $result.processStillRunningAtEnd = (-not $targetProcess.HasExited)
    }
    catch { $result.processStillRunningAtEnd = $false }

    $result.inspectionStatus = 'complete'
    if (-not $result.hostExecutable -or $result.hostExecutable.pe.status -ne 'parsed' -or $result.moduleEnumerationStatus -ne 'succeeded') {
        $result.inspectionStatus = 'partial'
    }
    $unstableOrUnhashedModules = @($result.matchingModules | Where-Object { $_.file.hashStatus -ne 'read' -or $_.file.fileUnchangedDuringInspection -ne $true })
    $hostFileStable = ($result.hostExecutable -and $result.hostExecutable.hashStatus -eq 'read' -and $result.hostExecutable.fileUnchangedDuringInspection -eq $true)
    $result.nativeX64MappingVerified = ($result.hostX64 -and $result.moduleX64 -and $result.moduleEnumerationStatus -eq 'succeeded' -and $result.processStillRunningAtEnd -eq $true -and $hostFileStable -and $unstableOrUnhashedModules.Count -eq 0)
    if ($result.nativeX64MappingVerified) { $result.verificationStatus = 'native_x64_module_mapping_verified' }
    elseif ($result.moduleEnumerationStatus -ne 'succeeded') { $result.verificationStatus = 'module_enumeration_unverified' }
    elseif ($result.matchingModuleCount -eq 0) { $result.verificationStatus = 'no_matching_modules_loaded' }
    elseif (-not $result.hostX64) { $result.verificationStatus = 'host_x64_unverified' }
    elseif (-not $result.moduleX64) { $result.verificationStatus = 'matching_module_x64_unverified' }
    else { $result.verificationStatus = 'file_or_process_stability_unverified' }
}
catch {
    $result.inspectionStatus = 'process_query_failed'
    $result.verificationStatus = 'process_query_failed'
}
finally {
    if ($targetProcess) { $targetProcess.Dispose() }
}
$result | ConvertTo-Json -Depth 10
