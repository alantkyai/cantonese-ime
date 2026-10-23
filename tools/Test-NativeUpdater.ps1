[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$updater = Join-Path $project 'native/Update-NativeIme.ps1'
$zero = '0' * 64
. $updater -PackageRoot $project -ManifestSha256 $zero -InstalledManifestSha256 $zero -RegistrationPlanSha256 $zero
$fixture = Join-Path $project ('.local/native/updater-tests/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$checks = New-Object 'Collections.Generic.List[object]'
function Check([string]$Name, [scriptblock]$Test) {
    try { & $Test } catch { throw "$Name : $($_.Exception.Message)" }
    $checks.Add(@{name=$Name; passed=$true})
}
function Reject([scriptblock]$Test) {
    $rejected = $false
    try { & $Test | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw 'Expected validation to reject this fixture.' }
}
function Equal($Expected, $Actual) {
    if ($Expected -cne $Actual) { throw "Expected '$Expected', received '$Actual'." }
}
function Put([string]$Relative, [string]$Text) {
    $path = Get-UpgradePath $fixture $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, $Text, (New-Object Text.UTF8Encoding($false)))
    return $path
}
function Pe([string]$Relative, [bool]$Dll) {
    $path = Put $Relative ''
    $bytes = New-Object byte[] 512
    $bytes[0]=0x4d; $bytes[1]=0x5a; $bytes[60]=0x80
    $bytes[128]=0x50; $bytes[129]=0x45; $bytes[132]=0x64; $bytes[133]=0x86
    $bytes[148]=0xf0; $bytes[152]=0x0b; $bytes[153]=0x02
    if ($Dll) { $bytes[151]=0x20 }
    [IO.File]::WriteAllBytes($path, $bytes)
    return $path
}
function Manifest($Files) {
    $result = [ordered]@{schema_version=1; kind='Cantonese IME native AMD64 preview runtime package';
        native_dll_sha256=(Get-UpgradeHash (Join-Path $fixture 'native/CantoneseIME.dll'));
        dictionary_sha256=(Get-UpgradeHash (Join-Path $fixture 'data/generated/lexicon.sqlite3'));
        external_python=@{path=$script:python; sha256=(Get-UpgradeHash $script:python); architecture='AMD64'};
        files=@($Files)}
    Write-UpgradeJson (Join-Path $fixture 'package-manifest.json') $result
    return Get-UpgradeHash (Join-Path $fixture 'package-manifest.json')
}
function Refresh-DictionaryFixtureManifest([string]$Root) {
    $manifestPath = Join-Path $Root 'package-manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $manifest.dictionary_sha256 = Get-UpgradeHash (Join-Path $Root 'data/generated/lexicon.sqlite3')
    foreach ($record in $manifest.files) {
        $path = Get-UpgradePath $Root $record.path
        $record.bytes = (Get-Item -LiteralPath $path).Length
        $record.sha256 = Get-UpgradeHash $path
    }
    Write-UpgradeJson $manifestPath $manifest
    return Get-UpgradeHash $manifestPath
}
function Refresh-DictionaryFixtureRuntime([string]$Root) {
    $path = Join-Path $Root 'runtime-config.json'
    $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $config.expected_dictionary_sha256 = Get-UpgradeHash (Join-Path $Root 'data/generated/lexicon.sqlite3')
    foreach ($property in @($config.files_sha256.PSObject.Properties)) {
        $property.Value = Get-UpgradeHash (Get-UpgradePath $Root $property.Name)
    }
    Write-UpgradeJson $path $config
}
Check 'safe paths and Windows aliases' {
    Equal (Join-Path $fixture 'native/with space.txt') (Get-UpgradePath $fixture 'native/with space.txt')
    foreach ($relative in @('../escape','x/../escape','x\escape','/escape','C:/escape',
        'x:stream','x//a','x/./a','x/CON.txt','x/lpt1','x/end.','x/end ','x/a?b')) {
        Reject { Get-UpgradePath $fixture $relative }
    }
}
$script:python = Pe 'python.exe' $false
$null = Pe 'native/CantoneseIME.dll' $true
$null = Pe 'native/CantoneseMachineRegistration.exe' $false
Check 'AMD64 PE bounds and DLL flag' {
    Assert-UpgradeAmd64 $python
    Assert-UpgradeAmd64 (Join-Path $fixture 'native/CantoneseIME.dll') $true
    Reject { Assert-UpgradeAmd64 $python $true }
    $bad = Put 'bad.exe' 'not PE'
    Reject { Assert-UpgradeAmd64 $bad }
    $bad = Pe 'bad.exe' $false
    $bytes = [IO.File]::ReadAllBytes($bad); $bytes[132]=0x4c; $bytes[133]=0x01; [IO.File]::WriteAllBytes($bad,$bytes)
    Reject { Assert-UpgradeAmd64 $bad }
    $bytes[60]=0xff; $bytes[61]=0xff; [IO.File]::WriteAllBytes($bad,$bytes)
    Reject { Assert-UpgradeAmd64 $bad }
}
$roles = @('native/CantoneseIME.dll','native/CantoneseMachineRegistration.exe',
    'native/backend/server.py','native/runtime/control.py','native/runtime/Start-Runtime.ps1',
    'data/generated/lexicon.sqlite3','data/generated/lexicon.manifest.json',
    'data/mappings/syllables.json','data/mappings/spellings.json','data/mappings/build.manifest.json',
    'cantonese_ime/engine.py','runtime-config.json')
foreach ($relative in $roles | Where-Object { $_ -notmatch '\.(dll|exe)$' }) { $null = Put $relative '{}'}
Write-UpgradeJson (Join-Path $fixture 'data/generated/lexicon.manifest.json') @{
    database_sha256=(Get-UpgradeHash (Join-Path $fixture 'data/generated/lexicon.sqlite3'))}
$runtimeHashes = [ordered]@{}
foreach ($relative in $roles | Where-Object { $_ -notin @('runtime-config.json','native/CantoneseMachineRegistration.exe') }) {
    $runtimeHashes[$relative] = Get-UpgradeHash (Join-Path $fixture $relative)
}
Write-UpgradeJson (Join-Path $fixture 'runtime-config.json') @{
    schema_version=1;install_root='.';python_executable=$python;python_bits=64;python_sha256=(Get-UpgradeHash $python);
    learning_enabled=$true; learning_file=$null;
    expected_dictionary_sha256=$runtimeHashes['data/generated/lexicon.sqlite3'];files_sha256=$runtimeHashes}
$records = @($roles | ForEach-Object {
    @{path=$_; bytes=(Get-Item -LiteralPath (Join-Path $fixture $_)).Length;sha256=(Get-UpgradeHash (Join-Path $fixture $_))}
})
$pin = Manifest $records
Check 'complete pinned package and runtime' {
    $package = Read-UpgradePackage $fixture $pin
    Assert-UpgradeRuntime $fixture $package $true
    Reject { Read-UpgradePackage $fixture $zero }
}
Check 'duplicate, reserved and escaping manifest records' {
    foreach ($bad in @(@{path='runtime-config.json';bytes=0;sha256=$zero},
        @{path='machine-registration.plan';bytes=0;sha256=$zero},@{path='../escape';bytes=0;sha256=$zero},
        @{path='NATIVE/CANTONESEIME.DLL';bytes=0;sha256=$zero})) {
        $badPin = Manifest ($records + @($bad))
        Reject { Read-UpgradePackage $fixture $badPin }
    }
    $script:pin = Manifest $records
}
Check 'payload alteration and runtime inventory disagreement' {
    $file = Join-Path $fixture 'native/backend/server.py'
    [IO.File]::AppendAllText($file,'changed')
    Reject { Read-UpgradePackage $fixture $pin }
    [IO.File]::WriteAllText($file,'{}',(New-Object Text.UTF8Encoding($false)))
    $package = Read-UpgradePackage $fixture $pin
    $configPath = Join-Path $fixture 'runtime-config.json'
    $saved = [IO.File]::ReadAllBytes($configPath)
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $config.files_sha256.PSObject.Properties.Remove('cantonese_ime/engine.py')
    Write-UpgradeJson $configPath $config
    Reject { Assert-UpgradeRuntime $fixture $package }
    [IO.File]::WriteAllBytes($configPath,$saved)
}
Check 'production learning policy rejects test overrides and disabling' {
    $package = Read-UpgradePackage $fixture $pin
    $path = Join-Path $fixture 'runtime-config.json'
    $saved = [IO.File]::ReadAllBytes($path)
    foreach ($value in @($false, 'true', 1, $null)) {
        $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        $config.learning_enabled = $value; Write-UpgradeJson $path $config
        Reject { Assert-UpgradeRuntime $fixture $package $true }
        [IO.File]::WriteAllBytes($path,$saved)
    }
    $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $config.learning_file = Join-Path $fixture 'smoke-learning.json'; Write-UpgradeJson $path $config
    Reject { Assert-UpgradeRuntime $fixture $package $true }
    [IO.File]::WriteAllBytes($path,$saved)
    Assert-UpgradeRuntime $fixture $package $true
}
$changedRoot = Join-Path $fixture 'dictionary-upgrade'
foreach ($relative in ($roles + @('package-manifest.json'))) {
    $destination = Get-UpgradePath $changedRoot $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath (Get-UpgradePath $fixture $relative) -Destination $destination
}
[IO.File]::WriteAllText((Join-Path $changedRoot 'data/generated/lexicon.sqlite3'),
    'synthetic changed dictionary bytes', (New-Object Text.UTF8Encoding($false)))
$changedDictionaryPin = Get-UpgradeHash (Join-Path $changedRoot 'data/generated/lexicon.sqlite3')
Write-UpgradeJson (Join-Path $changedRoot 'data/generated/lexicon.manifest.json') @{database_sha256=$changedDictionaryPin}
Refresh-DictionaryFixtureRuntime $changedRoot
$changedPackagePin = Refresh-DictionaryFixtureManifest $changedRoot
Check 'dictionary upgrade requires explicit exact opt-in' {
    $old = Read-UpgradePackage $fixture $pin
    $new = Read-UpgradePackage $changedRoot $changedPackagePin
    Assert-UpgradeRuntime $fixture $old
    Assert-UpgradeRuntime $changedRoot $new $true
    $same = Assert-UpgradeDictionaryPolicy $old $old $null
    Equal $false $same.dictionary_changed
    Equal $null $same.dictionary_sha256_pin
    Reject { Assert-UpgradeDictionaryPolicy $old $new $null }
    Reject { Assert-UpgradeDictionaryPolicy $old $new $zero }
    Reject { Assert-UpgradeDictionaryPolicy $old $new $old.Manifest.dictionary_sha256 }
    Reject { Assert-UpgradeDictionaryPolicy $old $new ('g' * 64) }
    $allowed = Assert-UpgradeDictionaryPolicy $old $new $changedDictionaryPin.ToUpperInvariant()
    Equal $true $allowed.dictionary_changed
    Equal $old.Manifest.dictionary_sha256 $allowed.old_dictionary_sha256
    Equal $changedDictionaryPin $allowed.new_dictionary_sha256
    Equal $changedDictionaryPin $allowed.dictionary_sha256_pin
}
Check 'dictionary opt-in never permits interpreter changes' {
    $old = Read-UpgradePackage $fixture $pin
    $new = Read-UpgradePackage $changedRoot $changedPackagePin
    $new.Manifest.external_python.path += '.other'
    Reject { Assert-UpgradeDictionaryPolicy $old $new $changedDictionaryPin }
    $new = Read-UpgradePackage $changedRoot $changedPackagePin
    $new.Manifest.external_python.sha256 = $zero
    Reject { Assert-UpgradeDictionaryPolicy $old $new $changedDictionaryPin }
}
Check 'changed dictionary bytes must retain the reviewed package hash' {
    $path = Join-Path $changedRoot 'data/generated/lexicon.sqlite3'
    $saved = [IO.File]::ReadAllBytes($path)
    try {
        [IO.File]::AppendAllText($path, 'tampered')
        Reject { Read-UpgradePackage $changedRoot $changedPackagePin }
    } finally { [IO.File]::WriteAllBytes($path, $saved) }
    $new = Read-UpgradePackage $changedRoot $changedPackagePin
    $null = Assert-UpgradeDictionaryPolicy (Read-UpgradePackage $fixture $pin) $new $changedDictionaryPin
}
Check 'dictionary config and source manifest cannot disagree with the pin' {
    $configPath = Join-Path $changedRoot 'runtime-config.json'
    $dictionaryManifestPath = Join-Path $changedRoot 'data/generated/lexicon.manifest.json'
    $packageManifestPath = Join-Path $changedRoot 'package-manifest.json'
    $savedConfig = [IO.File]::ReadAllBytes($configPath)
    $savedDictionaryManifest = [IO.File]::ReadAllBytes($dictionaryManifestPath)
    $savedPackageManifest = [IO.File]::ReadAllBytes($packageManifestPath)
    try {
        $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        $config.expected_dictionary_sha256 = $zero
        Write-UpgradeJson $configPath $config
        $invalidPin = Refresh-DictionaryFixtureManifest $changedRoot
        $invalid = Read-UpgradePackage $changedRoot $invalidPin
        $null = Assert-UpgradeDictionaryPolicy (Read-UpgradePackage $fixture $pin) $invalid $changedDictionaryPin
        Reject { Assert-UpgradeRuntime $changedRoot $invalid $true }

        [IO.File]::WriteAllBytes($configPath, $savedConfig)
        Write-UpgradeJson $dictionaryManifestPath @{database_sha256=$zero}
        Refresh-DictionaryFixtureRuntime $changedRoot
        $invalidPin = Refresh-DictionaryFixtureManifest $changedRoot
        $invalid = Read-UpgradePackage $changedRoot $invalidPin
        $null = Assert-UpgradeDictionaryPolicy (Read-UpgradePackage $fixture $pin) $invalid $changedDictionaryPin
        Reject { Assert-UpgradeRuntime $changedRoot $invalid $true }
    } finally {
        [IO.File]::WriteAllBytes($configPath, $savedConfig)
        [IO.File]::WriteAllBytes($dictionaryManifestPath, $savedDictionaryManifest)
        [IO.File]::WriteAllBytes($packageManifestPath, $savedPackageManifest)
    }
    $new = Read-UpgradePackage $changedRoot $changedPackagePin
    Assert-UpgradeRuntime $changedRoot $new $true
}
$planFile = Join-Path $fixture 'machine-registration.plan'
$dllPath = Join-Path $fixture 'native/CantoneseIME.dll'
$dllHash = Get-UpgradeHash $dllPath
$lines = @('CANTONESE_IME_MACHINE_V1','clsid={67718E6F-49A1-4F54-88D6-30578FC70C5D}',
    'profile={A7136205-2245-45CC-A6AA-702B3F2E8D42}','languages=0409,0c04',
    "dll_source=$dllPath","dll_target=$dllPath","dll_sha256=$dllHash")
$null = Put 'machine-registration.plan' (($lines -join "`n") + "`n")
Check 'registration identity, path and BOM guards' {
    $null = Read-UpgradePlan $planFile (Get-UpgradeHash $planFile) $dllPath $dllHash
    Reject { Read-UpgradePlan $planFile $zero $dllPath $dllHash }
    Reject { Read-UpgradePlan $planFile (Get-UpgradeHash $planFile) ($dllPath+'other') $dllHash }
    [IO.File]::WriteAllText($planFile,($lines -join "`n"),(New-Object Text.UTF8Encoding($true)))
    Reject { Read-UpgradePlan $planFile (Get-UpgradeHash $planFile) $dllPath $dllHash }
}
Check 'plain path containment' {
    Assert-UpgradePlainPath $fixture $dllPath
    Reject { Assert-UpgradePlainPath (Join-Path $fixture 'native') $python }
}
Check 'mapped-image owner permission never covers other inputs' {
    $dllOwners = @(@{pid=101;app='synthetic editor'})
    $otherOwners = @(@{pid=202;app='synthetic broker'})
    Equal $false (Get-UpgradeOwnerPolicy $dllOwners @() $false).ready
    Equal $true (Get-UpgradeOwnerPolicy $dllOwners @() $true).ready
    Equal $false (Get-UpgradeOwnerPolicy $dllOwners $otherOwners $true).ready
    Equal $false (Get-UpgradeOwnerPolicy $dllOwners $dllOwners $true).ready
    Equal $false (Get-UpgradeOwnerPolicy @() $otherOwners $true).ready
    Equal $true (Get-UpgradeOwnerPolicy @() @() $false).ready
    Equal $true (Get-UpgradeOwnerPolicy $dllOwners @() $true).existing_apps_keep_old_image
}
Initialize-UpgradeNative
Check 'changed dictionary transaction restores all old pins on publication error' {
    # Exercise actual held-handle rollback for the three coupled dictionary
    # inputs. These are synthetic bytes inside this test's workspace only.
    $transactionRoot = Join-Path $fixture 'dictionary-transaction'
    $installed = Join-Path $transactionRoot 'installed'
    $staged = Join-Path $transactionRoot 'stage'
    $retired = Join-Path $transactionRoot 'retired'
    $coupled = @('data/generated/lexicon.sqlite3', 'data/generated/lexicon.manifest.json', 'runtime-config.json')
    $oldHashes = @{}; $newHashes = @{}; $oldHeld = @{}; $newHeld = @{}
    $withdrawn = @(); $published = @()
    foreach ($relative in $coupled) {
        foreach ($root in @($installed, $staged, $retired)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent (Get-UpgradePath $root $relative)) -Force | Out-Null
        }
        Copy-Item -LiteralPath (Get-UpgradePath $fixture $relative) -Destination (Get-UpgradePath $installed $relative)
        Copy-Item -LiteralPath (Get-UpgradePath $changedRoot $relative) -Destination (Get-UpgradePath $staged $relative)
        $oldHashes[$relative] = Get-UpgradeHash (Get-UpgradePath $installed $relative)
        $newHashes[$relative] = Get-UpgradeHash (Get-UpgradePath $staged $relative)
    }
    try {
        foreach ($relative in $coupled) {
            $oldHeld[$relative] = [CantoneseUpgrade.Files]::Lock((Get-UpgradePath $installed $relative), $false)
            $newHeld[$relative] = [CantoneseUpgrade.Files]::Lock((Get-UpgradePath $staged $relative), $false)
        }
        try {
            foreach ($relative in $coupled) {
                [CantoneseUpgrade.Files]::Rename($oldHeld[$relative], (Get-UpgradePath $retired $relative))
                $withdrawn += $relative
            }
            foreach ($relative in $coupled[0..1]) {
                [CantoneseUpgrade.Files]::Rename($newHeld[$relative], (Get-UpgradePath $installed $relative))
                $published += $relative
            }
            throw 'Injected publication error before config commit.'
        } catch {
            if ($_.Exception.Message -ne 'Injected publication error before config commit.') { throw }
            for ($index=$published.Count-1; $index -ge 0; $index--) {
                $relative = $published[$index]
                [CantoneseUpgrade.Files]::Rename($newHeld[$relative], (Get-UpgradePath $staged $relative))
            }
            for ($index=$withdrawn.Count-1; $index -ge 0; $index--) {
                $relative = $withdrawn[$index]
                [CantoneseUpgrade.Files]::Rename($oldHeld[$relative], (Get-UpgradePath $installed $relative))
            }
        }
        Equal 2 $published.Count
        foreach ($relative in $coupled) {
            Equal $oldHashes[$relative] ([CantoneseUpgrade.Files]::Hash($oldHeld[$relative]))
            Equal $newHashes[$relative] ([CantoneseUpgrade.Files]::Hash($newHeld[$relative]))
        }
    } finally {
        foreach ($held in $newHeld.Values) { $held.Dispose() }
        foreach ($held in $oldHeld.Values) { $held.Dispose() }
    }
    foreach ($relative in $coupled) {
        Equal $oldHashes[$relative] (Get-UpgradeHash (Get-UpgradePath $installed $relative))
        Equal $newHashes[$relative] (Get-UpgradeHash (Get-UpgradePath $staged $relative))
    }
}
Check 'held file identity, copy, rename and rollback primitives' {
    $original = Put 'locked/original.txt' 'old UTF-8 content'
    $renamed = Get-UpgradePath $fixture 'locked/retired.txt'
    $copy = Get-UpgradePath $fixture 'locked/backup.txt'
    $hash = Get-UpgradeHash $original
    $held = [CantoneseUpgrade.Files]::Lock($original,$false)
    try {
        Equal $hash ([CantoneseUpgrade.Files]::Hash($held))
        Reject { $reader=[IO.File]::OpenRead($original); $reader.Dispose() }
        [CantoneseUpgrade.Files]::Copy($held,$copy)
        Equal $hash (Get-UpgradeHash $copy)
        [CantoneseUpgrade.Files]::Rename($held,$renamed)
        Equal $false (Test-Path -LiteralPath $original)
        Equal $hash ([CantoneseUpgrade.Files]::Hash($held))
        Reject { [CantoneseUpgrade.Files]::Rename($held,$copy) }
        [CantoneseUpgrade.Files]::Rename($held,$original)
        Equal $hash ([CantoneseUpgrade.Files]::Hash($held))
    } finally { $held.Dispose() }
    Equal $hash (Get-UpgradeHash $original)
}
Check 'mapped-image handle uses no write access and pins rename identity' {
    $original = Put 'read-delete/original.txt' 'pinned original'
    $retired = Get-UpgradePath $fixture 'read-delete/retired.txt'
    $hash = Get-UpgradeHash $original
    $held = [CantoneseUpgrade.Files]::LockMappedImage($original)
    try {
        Equal $hash ([CantoneseUpgrade.Files]::Hash($held))
        Reject { $writer=[IO.File]::OpenWrite($original); $writer.Dispose() }
        [CantoneseUpgrade.Files]::Rename($held,$retired)
        Equal $hash ([CantoneseUpgrade.Files]::Hash($held))
        [CantoneseUpgrade.Files]::Rename($held,$original)
    } finally { $held.Dispose() }
    Equal $hash (Get-UpgradeHash $original)
}
Check 'rename length changes remain exact and never overwrite' {
    $directory = Join-Path $fixture 'rename-stress'
    New-Item -ItemType Directory -Path $directory | Out-Null
    for ($iteration=0; $iteration -lt 40; $iteration++) {
        $leaf = 'f' + $iteration + ('x' * ($iteration % 19)) + '.txt'
        $original = Join-Path $directory $leaf
        $destination = Join-Path $directory ('renamed-' + $iteration + '.txt')
        $existing = Join-Path $directory ('exists-' + $iteration + '.txt')
        [IO.File]::WriteAllText($original,'original'); [IO.File]::WriteAllText($existing,'keep')
        $held = [CantoneseUpgrade.Files]::Lock($original,$false)
        try {
            [CantoneseUpgrade.Files]::Rename($held,$destination)
            Equal $true (Test-Path -LiteralPath $destination)
            Reject { [CantoneseUpgrade.Files]::Rename($held,$existing) }
            [CantoneseUpgrade.Files]::Rename($held,$original)
        } finally { $held.Dispose() }
        Equal 'keep' ([IO.File]::ReadAllText($existing))
        Equal 'original' ([IO.File]::ReadAllText($original))
        Equal (2 * ($iteration+1)) @(Get-ChildItem -LiteralPath $directory -File).Count
    }
}
Check 'directory handle prevents directory replacement' {
    $directory = Join-Path $fixture 'locked'
    $held = [CantoneseUpgrade.Files]::Lock($directory,$true)
    try { Reject { [IO.Directory]::Move($directory,($directory+'-moved')) } }
    finally { $held.Dispose() }
}
$report = @{passed=$true;checks=@($checks.ToArray());updater_sha256=(Get-UpgradeHash $updater);
    scope='Isolated workspace fixtures; no installed runtime, registry, controller, apps or Program Files changes.';
    fixture_directory=$fixture;actual_update_exercised=$false}
Write-UpgradeJson (Join-Path $fixture 'report.json') $report
$report | ConvertTo-Json -Depth 5
