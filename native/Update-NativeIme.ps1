[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ManifestSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$InstalledManifestSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$RegistrationPlanSha256,
    [ValidatePattern('^[a-fA-F0-9]{64}$')][string]$DictionarySha256,
    [switch]$AllowMappedDll
)
$ErrorActionPreference = 'Stop'

function Get-UpgradeHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-UpgradeAmd64([string]$Path, [bool]$Dll = $false) {
    $stream = [IO.File]::OpenRead($Path)
    $reader = New-Object IO.BinaryReader($stream)
    try {
        if ($stream.Length -lt 128 -or $reader.ReadUInt16() -ne 0x5a4d) { throw 'Invalid DOS executable header.' }
        $stream.Position = 60; $offset = $reader.ReadUInt32()
        if ($offset -lt 64 -or $offset -gt 16777216 -or $offset + 26 -gt $stream.Length) { throw 'Invalid PE header bounds.' }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw 'Only an AMD64 executable is accepted.' }
        $stream.Position = $offset + 20; $optionalSize = $reader.ReadUInt16(); $flags = $reader.ReadUInt16()
        if ($optionalSize -lt 2 -or $offset + 24 + $optionalSize -gt $stream.Length -or
            $reader.ReadUInt16() -ne 0x20b -or ($Dll -and -not ($flags -band 0x2000))) { throw 'Expected an AMD64 PE32+ DLL/executable.' }
    } finally { $reader.Dispose(); $stream.Dispose() }
}

function Get-UpgradePath([string]$Root, [string]$Relative) {
    # Reject Windows aliases as well as traversal; manifests use forward slashes.
    if (-not $Relative -or $Relative -match '[\\:<>"|?*\x00-\x1f]' -or
        [IO.Path]::IsPathRooted($Relative)) { throw 'Invalid package path.' }
    foreach ($part in ($Relative -split '/')) {
        if (-not $part -or $part -in @('.', '..') -or $part -match '[. ]$' -or
            $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw 'Invalid Windows package path component.'
        }
    }
    $full = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    if (-not $full.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Package path resolves outside its root.'
    }
    return $full
}

function Assert-UpgradePlainPath([string]$Root, [string]$Path) {
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $current = [IO.Path]::GetFullPath($Path)
    if ($current -ne $rootFull -and -not $current.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Path is outside the selected root.'
    }
    for (;;) {
        $item = Get-Item -LiteralPath $current -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point refused: $current" }
        if ($current -eq $rootFull) { break }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}

function Assert-UpgradeProtected([string]$Path) {
    $allowed = @('S-1-5-18', 'S-1-5-32-544',
        'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    $acl = Get-Acl -LiteralPath $Path
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $allowed) {
        throw "Protected SYSTEM/Administrators/TrustedInstaller owner required: $Path"
    }
    if (-not $acl.AreAccessRulesCanonical) { throw "Noncanonical ACL refused: $Path" }
    $raw = [Security.AccessControl.RawSecurityDescriptor]::new($acl.GetSecurityDescriptorBinaryForm(), 0)
    if ($null -eq $raw.DiscretionaryAcl) { throw "Null DACL refused: $Path" }
    # Generic write/all, data/append/EA/attributes, delete-child, delete, DAC and owner.
    $writeMask = [long]0x500D0156
    foreach ($ace in $raw.DiscretionaryAcl) {
        if (($ace.AceFlags -band [Security.AccessControl.AceFlags]::InheritOnly) -or
            $ace.AceType -eq [Security.AccessControl.AceType]::AccessDenied) { continue }
        if ($ace.AceType -ne [Security.AccessControl.AceType]::AccessAllowed) { throw "Unsupported effective ACL entry: $Path" }
        if (([long]$ace.AccessMask -band $writeMask) -and $ace.SecurityIdentifier.Value -notin $allowed) {
            throw "Unprivileged write permission refused: $Path"
        }
    }
}

function Read-UpgradePackage([string]$Root, [string]$ExpectedHash) {
    $path = Join-Path $Root 'package-manifest.json'
    Assert-UpgradePlainPath $Root $path
    if ((Get-Item -LiteralPath $path).Length -gt 2097152 -or (Get-UpgradeHash $path) -ne $ExpectedHash) {
        throw 'Package manifest does not match its explicit SHA256 pin.'
    }
    $value = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($value.schema_version -ne 1 -or $value.kind -ne 'Cantonese IME native AMD64 preview runtime package' -or
        $value.native_dll_sha256 -cnotmatch '^[0-9a-f]{64}$' -or $value.dictionary_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        @($value.files).Count -lt 1 -or @($value.files).Count -gt 2048) { throw 'Unexpected package manifest.' }
    $records = @{}
    $reserved = @('package-manifest.json', 'machine-registration.plan', 'installation.json', 'last-upgrade.json')
    foreach ($record in $value.files) {
        $file = Get-UpgradePath $Root $record.path
        if ($records.ContainsKey($record.path) -or $record.path -in $reserved -or
            $record.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $record.bytes -isnot [ValueType] -or
            $record.bytes -is [bool] -or [long]$record.bytes -lt 0 -or [long]$record.bytes -ne $record.bytes) {
            throw 'Invalid, reserved or duplicate package record.'
        }
        Assert-UpgradePlainPath $Root $file
        $item = Get-Item -LiteralPath $file -Force
        if ($item.PSIsContainer -or $item.Length -ne [long]$record.bytes -or (Get-UpgradeHash $file) -ne $record.sha256) {
            throw "Package file differs from the reviewed manifest: $($record.path)"
        }
        $records[$record.path] = $record
    }
    foreach ($required in @('native/CantoneseIME.dll', 'native/CantoneseMachineRegistration.exe',
        'native/runtime/control.py', 'native/backend/server.py', 'runtime-config.json', 'data/generated/lexicon.sqlite3')) {
        if (-not $records.ContainsKey($required)) { throw "Package lacks $required" }
    }
    if ($records['native/CantoneseIME.dll'].sha256 -ne $value.native_dll_sha256 -or
        $records['data/generated/lexicon.sqlite3'].sha256 -ne $value.dictionary_sha256) { throw 'Package hash fields disagree.' }
    Assert-UpgradeAmd64 (Join-Path $Root 'native/CantoneseIME.dll') $true
    Assert-UpgradeAmd64 (Join-Path $Root 'native/CantoneseMachineRegistration.exe')
    return @{ Manifest = $value; Records = $records }
}

function Assert-UpgradeRuntime([string]$Root, $Package, [bool]$RequireDefaultLearning = $false) {
    $config = Get-Content -LiteralPath (Join-Path $Root 'runtime-config.json') -Raw | ConvertFrom-Json
    if ($RequireDefaultLearning -and ($config.learning_enabled -isnot [bool] -or $config.learning_enabled -ne $true -or
        $null -ne $config.learning_file)) {
        throw 'Production update requires learning enabled at the default per-user store; explicit test-store overrides are refused.'
    }
    if ($config.schema_version -ne 1 -or $config.install_root -ne '.' -or $config.python_bits -ne 64 -or
        $config.expected_dictionary_sha256 -ne $Package.Manifest.dictionary_sha256 -or
        $config.python_executable -ne $Package.Manifest.external_python.path -or
        $config.python_sha256 -ne $Package.Manifest.external_python.sha256 -or
        -not [IO.Path]::IsPathRooted($config.python_executable) -or
        (Get-UpgradeHash $config.python_executable) -ne $config.python_sha256) { throw 'Runtime configuration pins disagree.' }
    Assert-UpgradeAmd64 $config.python_executable
    $expected = @('native/backend/server.py', 'native/runtime/control.py', 'native/runtime/Start-Runtime.ps1',
        'native/CantoneseIME.dll', 'data/generated/lexicon.sqlite3', 'data/generated/lexicon.manifest.json',
        'data/mappings/syllables.json', 'data/mappings/spellings.json', 'data/mappings/build.manifest.json')
    $expected += @($Package.Records.Keys | Where-Object { $_ -match '^cantonese_ime/[^/]+\.py$' })
    $actual = @($config.files_sha256.PSObject.Properties.Name)
    if (@(Compare-Object ($expected | Sort-Object) ($actual | Sort-Object)).Count) { throw 'Runtime file inventory differs.' }
    foreach ($relative in $expected) {
        if (-not $Package.Records.ContainsKey($relative) -or $config.files_sha256.$relative -ne $Package.Records[$relative].sha256) {
            throw "Runtime file hash differs: $relative"
        }
    }
    $dictionary = Get-Content -LiteralPath (Join-Path $Root 'data/generated/lexicon.manifest.json') -Raw | ConvertFrom-Json
    if ($dictionary.database_sha256 -ne $Package.Manifest.dictionary_sha256) { throw 'Dictionary source manifest differs.' }
}

function Assert-UpgradeDictionaryPolicy($Old, $New, [string]$DictionaryPin) {
    # Both packages have already passed independent explicit-manifest/payload
    # verification. Opting in to a dictionary cannot change the interpreter.
    if ($Old.Manifest.external_python.path -ne $New.Manifest.external_python.path -or
        $Old.Manifest.external_python.sha256 -ne $New.Manifest.external_python.sha256) {
        throw 'This updater preserves the external interpreter; review that change separately.'
    }
    $changed = $Old.Manifest.dictionary_sha256 -ne $New.Manifest.dictionary_sha256
    $pin = $null
    if ($DictionaryPin) {
        if ($DictionaryPin -cnotmatch '^[a-fA-F0-9]{64}$') { throw 'Dictionary SHA256 pin must contain exactly 64 hexadecimal digits.' }
        $pin = $DictionaryPin.ToLowerInvariant()
        if ($pin -ne $New.Manifest.dictionary_sha256) {
            throw 'New dictionary does not match its explicit DictionarySha256 pin.'
        }
    } elseif ($changed) {
        throw 'Dictionary change requires an explicitly reviewed -DictionarySha256 pin for the new dictionary.'
    }
    return @{ old_dictionary_sha256=$Old.Manifest.dictionary_sha256;
        new_dictionary_sha256=$New.Manifest.dictionary_sha256;
        dictionary_changed=$changed; dictionary_sha256_pin=$pin }
}

function Read-UpgradePlan([string]$Path, [string]$ExpectedHash, [string]$Dll, [string]$DllHash) {
    if ((Get-UpgradeHash $Path) -ne $ExpectedHash) { throw 'Installed registration plan differs from its explicit pin.' }
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) {
        throw 'Registration plan must be UTF-8 without BOM.'
    }
    $lines = [IO.File]::ReadAllLines($Path, (New-Object Text.UTF8Encoding($false, $true)))
    $expected = @('CANTONESE_IME_MACHINE_V1',
        'clsid={67718E6F-49A1-4F54-88D6-30578FC70C5D}',
        'profile={A7136205-2245-45CC-A6AA-702B3F2E8D42}', 'languages=0409,0c04',
        "dll_source=$Dll", "dll_target=$Dll", "dll_sha256=$DllHash")
    if (($lines -join "`n") -cne ($expected -join "`n")) { throw 'Installed registration identity/path/hash differs.' }
    return $expected
}

function Assert-UpgradeBinding([string]$Dll) {
    $class = 'Software\Classes\CLSID\{67718E6F-49A1-4F54-88D6-30578FC70C5D}'
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryHive]::CurrentUser)) {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, [Microsoft.Win32.RegistryView]::Registry64)
        try {
            $key = $base.OpenSubKey($class, $false)
            if ($hive -eq [Microsoft.Win32.RegistryHive]::CurrentUser) {
                if ($key) { $key.Dispose(); throw 'Current-token HKCU COM override refused.' }
            } else {
                if (-not $key) { throw 'Installed machine COM identity is absent.' }
                $key.Dispose()
                $key = $base.OpenSubKey($class + '\InprocServer32', $false)
                try {
                    if (-not $key -or $key.GetValue('') -ne $Dll -or $key.GetValue('ThreadingModel') -cne 'Apartment') {
                        throw 'Installed COM path/thread model differs.'
                    }
                } finally { if ($key) { $key.Dispose() } }
                $key = $base.OpenSubKey('Software\Microsoft\CTF\TIP\{67718E6F-49A1-4F54-88D6-30578FC70C5D}\LanguageProfile', $false)
                try {
                    if (-not $key -or @(Compare-Object @('0x00000409', '0x00000c04') @($key.GetSubKeyNames() | Sort-Object)).Count) {
                        throw 'Installed machine profile languages differ.'
                    }
                    foreach ($name in $key.GetSubKeyNames()) {
                        $language = $key.OpenSubKey($name, $false)
                        try {
                            $profiles = @($language.GetSubKeyNames())
                            if ($profiles.Count -ne 1 -or $profiles[0] -ne '{A7136205-2245-45CC-A6AA-702B3F2E8D42}') {
                                throw 'Installed machine profile GUID differs.'
                            }
                        } finally { $language.Dispose() }
                    }
                } finally { if ($key) { $key.Dispose() } }
            }
        } finally { $base.Dispose() }
    }
}

function Get-UpgradeOwnerPolicy([object[]]$DllOwners, [object[]]$OtherOwners, [bool]$AllowMapped) {
    # A process present in both lists still blocks: permission applies to the DLL only.
    $blocked = @($OtherOwners)
    if (-not $AllowMapped) { $blocked += @($DllOwners) }
    return @{ ready=($blocked.Count -eq 0); blocking_owners=$blocked;
        dll_owners=@($DllOwners); other_file_owners=@($OtherOwners);
        existing_apps_keep_old_image=($AllowMapped -and @($DllOwners).Count -gt 0) }
}

function Initialize-UpgradeNative {
    if ('CantoneseUpgrade.Files' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;
namespace CantoneseUpgrade {
  public sealed class Owner { public uint pid; public string app; }
  public static class Files {
    [StructLayout(LayoutKind.Sequential)] struct Unique { public uint pid; public System.Runtime.InteropServices.ComTypes.FILETIME started; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Info {
      public Unique process;
      [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string app;
      [MarshalAs(UnmanagedType.ByValTStr, SizeConst=64)] public string service;
      public int type; public uint status; public uint session;
      [MarshalAs(UnmanagedType.Bool)] public bool restartable;
    }
    [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern uint RmStartSession(out uint session, uint flags, StringBuilder key);
    [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern uint RmRegisterResources(uint session, uint count, string[] files, uint processes, IntPtr apps, uint services, IntPtr names);
    [DllImport("rstrtmgr.dll")] static extern uint RmGetList(uint session, out uint needed, ref uint count, [In, Out] Info[] info, ref uint reboot);
    [DllImport("rstrtmgr.dll")] static extern uint RmEndSession(uint session);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetFileInformationByHandle(SafeFileHandle file, int kind, IntPtr data, uint length);
    static void Check(uint error) { if (error != 0) throw new Win32Exception((int)error); }
    public static Owner[] Owners(string[] paths) {
      uint session; Check(RmStartSession(out session, 0, new StringBuilder(33)));
      try {
        Check(RmRegisterResources(session, (uint)paths.Length, paths, 0, IntPtr.Zero, 0, IntPtr.Zero));
        uint count=0, needed=0, reboot=0;
        uint error=RmGetList(session, out needed, ref count, null, ref reboot);
        for (int attempt=0; error==234 && attempt<4; ++attempt) {
          if (needed>4096) throw new IOException("Too many file owners; refusing update.");
          count=needed; Info[] info=new Info[count];
          error=RmGetList(session, out needed, ref count, info, ref reboot);
          if (error==0) {
            List<Owner> result=new List<Owner>();
            for (int i=0; i<count; ++i) result.Add(new Owner { pid=info[i].process.pid, app=info[i].app });
            return result.ToArray();
          }
        }
        Check(error); return new Owner[0];
      } finally { RmEndSession(session); }
    }
    public static SafeFileHandle Lock(string path, bool directory) {
      SafeFileHandle handle=CreateFileW(path, directory ? 0x80000000U : 0xC0010000U,
          directory ? 3U : 0U, IntPtr.Zero, 3, directory ? 0x02000000U : 0U, IntPtr.Zero);
      if (handle.IsInvalid) { int error=Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error, "Cannot lock "+path); }
      return handle;
    }
    public static SafeFileHandle LockMappedImage(string path) {
      // Never request image write access. Retain READ|DELETE identity while denying
      // subsequent writers/deleters; only this held handle can rename the old image.
      SafeFileHandle handle=CreateFileW(path,0x80010000U,1U,IntPtr.Zero,3,0U,IntPtr.Zero);
      if (handle.IsInvalid) { int error=Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error,"Cannot pin mapped image "+path); }
      return handle;
    }
    public static string Hash(SafeFileHandle handle) {
      using (SafeFileHandle alias=new SafeFileHandle(handle.DangerousGetHandle(), false))
      using (FileStream stream=new FileStream(alias, FileAccess.Read))
      using (SHA256 sha=SHA256.Create()) {
        stream.Position=0;
        return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
      }
    }
    public static void Copy(SafeFileHandle handle, string path) {
      using (SafeFileHandle alias=new SafeFileHandle(handle.DangerousGetHandle(), false))
      using (FileStream stream=new FileStream(alias, FileAccess.Read))
      using (FileStream target=new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
        stream.Position=0; stream.CopyTo(target); target.Flush(true);
      }
    }
    public static void Rename(SafeFileHandle handle, string target) {
      // AMD64 FILE_RENAME_INFO: BOOLEAN at 0, HANDLE at 8, length at 16, name at 20.
      byte[] name=Encoding.Unicode.GetBytes(target);
      IntPtr buffer=Marshal.AllocHGlobal(22+name.Length);
      try {
        for(int i=0; i<22+name.Length; ++i) Marshal.WriteByte(buffer,i,0);
        Marshal.WriteInt32(buffer,16,name.Length); Marshal.Copy(name,0,IntPtr.Add(buffer,20),name.Length);
        if (!SetFileInformationByHandle(handle,3,buffer,(uint)(22+name.Length))) throw new Win32Exception(Marshal.GetLastWin32Error(),"Cannot rename to "+target);
      } finally { Marshal.FreeHGlobal(buffer); }
    }
  }
}
'@
}

function Write-UpgradeJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12) + "`n", (New-Object Text.UTF8Encoding($false)))
}

# Dot-sourcing imports validation functions for isolated fixture tests only.
if ($MyInvocation.InvocationName -eq '.') { return }
if ([IntPtr]::Size -ne 8) { throw 'Use 64-bit PowerShell.' }
$sourceRoot = (Resolve-Path -LiteralPath $PackageRoot).Path.TrimEnd('\')
$programFiles = [Environment]::GetFolderPath('ProgramFiles')
$targetRoot = Join-Path $programFiles 'CantoneseIME'
$updatesRoot = Join-Path $programFiles 'CantoneseIME-Updates'
$dll = Join-Path $targetRoot 'native/CantoneseIME.dll'
if ($sourceRoot -eq $targetRoot -or $sourceRoot.StartsWith($targetRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Replacement package must be outside the live installation.'
}
$new = Read-UpgradePackage $sourceRoot $ManifestSha256.ToLowerInvariant()
$old = Read-UpgradePackage $targetRoot $InstalledManifestSha256.ToLowerInvariant()
$helperHash = '81c5ea2dece353da3d2cd823b6ec027bfeb089dd2fa103c54ffb0409a5bfc987'
if ($old.Records['native/CantoneseMachineRegistration.exe'].sha256 -ne $helperHash -or
    $new.Records['native/CantoneseMachineRegistration.exe'].sha256 -ne $helperHash) { throw 'Registration helper changed; separate review is required.' }
$dictionaryPolicy = Assert-UpgradeDictionaryPolicy $old $new $DictionarySha256
Assert-UpgradeRuntime $sourceRoot $new $true
Assert-UpgradeRuntime $targetRoot $old
$planPath = Join-Path $targetRoot 'machine-registration.plan'
$null = Read-UpgradePlan $planPath $RegistrationPlanSha256.ToLowerInvariant() $dll $old.Manifest.native_dll_sha256
Assert-UpgradeBinding $dll
$inventory = @{}
$directories = @($targetRoot)
$pending = New-Object 'Collections.Generic.Queue[string]'
$pending.Enqueue($targetRoot)
while ($pending.Count) {
    $directory = $pending.Dequeue()
    Assert-UpgradePlainPath $targetRoot $directory
    Assert-UpgradeProtected $directory
    foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
        Assert-UpgradePlainPath $targetRoot $item.FullName
        Assert-UpgradeProtected $item.FullName
        if ($item.PSIsContainer) { $directories += $item.FullName; $pending.Enqueue($item.FullName) }
        else {
            $relative = $item.FullName.Substring($targetRoot.Length + 1).Replace('\', '/')
            $inventory[$relative] = @{ path=$relative; bytes=$item.Length; sha256=(Get-UpgradeHash $item.FullName) }
        }
    }
}
Assert-UpgradeProtected $programFiles
if (Test-Path -LiteralPath $updatesRoot) { Assert-UpgradePlainPath $programFiles $updatesRoot; Assert-UpgradeProtected $updatesRoot }
foreach ($relative in $new.Records.Keys) {
    if ($inventory.ContainsKey($relative) -and -not $old.Records.ContainsKey($relative)) {
        throw "New package would overwrite an unmanaged installed file: $relative"
    }
}
Initialize-UpgradeNative
$dllOwners = @([CantoneseUpgrade.Files]::Owners([string[]]@($dll)))
$otherOwners = @([CantoneseUpgrade.Files]::Owners([string[]]@($inventory.Keys | Where-Object { $_ -ne 'native/CantoneseIME.dll' } | ForEach-Object { Join-Path $targetRoot $_ })))
$policy = Get-UpgradeOwnerPolicy -DllOwners $dllOwners -OtherOwners $otherOwners -AllowMapped $AllowMappedDll.IsPresent
$preflight = [ordered]@{ status='preflight'; target=$targetRoot; old_manifest_sha256=$InstalledManifestSha256.ToLowerInvariant();
    new_manifest_sha256=$ManifestSha256.ToLowerInvariant(); old_dll_sha256=$old.Manifest.native_dll_sha256;
    new_dll_sha256=$new.Manifest.native_dll_sha256; registration_plan_sha256=$RegistrationPlanSha256.ToLowerInvariant();
    old_dictionary_sha256=$dictionaryPolicy.old_dictionary_sha256; new_dictionary_sha256=$dictionaryPolicy.new_dictionary_sha256;
    dictionary_changed=$dictionaryPolicy.dictionary_changed; dictionary_sha256_pin=$dictionaryPolicy.dictionary_sha256_pin;
    file_owners=@((@($dllOwners) + @($otherOwners)) | ForEach-Object { @{pid=$_.pid; app=$_.app} });
    dll_owners=@($dllOwners | ForEach-Object { @{pid=$_.pid; app=$_.app} });
    other_file_owners=@($otherOwners | ForEach-Object { @{pid=$_.pid; app=$_.app} });
    blocking_owners=@($policy.blocking_owners | ForEach-Object { @{pid=$_.pid; app=$_.app} }); ready=$policy.ready;
    allow_mapped_dll=$AllowMappedDll.IsPresent; existing_apps_keep_old_image=$policy.existing_apps_keep_old_image;
    registry_changes=$false; local_learning_changes=$false }
$preflight | ConvertTo-Json -Depth 5 | Write-Output
if (-not $policy.ready) {
    throw 'Installed files are in use; close the listed apps gracefully and stop only the owned broker. No replacement was attempted.'
}
if ($policy.existing_apps_keep_old_image) {
    Write-Output 'Only DLL owners are allowed: their existing old image is retained. Reopen each app naturally when its new frontend/UI is needed.'
}
if ($WhatIfPreference) { return }
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run the reviewed update in administrator PowerShell. This script does not request or automate UAC.'
}
if (-not $PSCmdlet.ShouldProcess($targetRoot, 'Back up and replace the pinned IME package without changing registration or user data')) { return }

$operation = Join-Path $updatesRoot ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N'))
$backup = Join-Path $operation 'backup'
$stage = Join-Path $operation 'stage'
$retired = Join-Path $operation 'retired'
$journalPath = Join-Path $operation 'journal.json'
$oldHandles = @{}; $newHandles = @{}; $directoryHandles = @(); $withdrawn = @(); $published = @()
$journal = [ordered]@{ schema_version=1; status='preparing'; started_at_utc=[DateTime]::UtcNow.ToString('o');
    target=$targetRoot; operation=$operation; backup=$backup; old_manifest_sha256=$InstalledManifestSha256.ToLowerInvariant();
    new_manifest_sha256=$ManifestSha256.ToLowerInvariant(); old_dll_sha256=$old.Manifest.native_dll_sha256;
    new_dll_sha256=$new.Manifest.native_dll_sha256; old_registration_plan_sha256=$RegistrationPlanSha256.ToLowerInvariant();
    old_dictionary_sha256=$dictionaryPolicy.old_dictionary_sha256; new_dictionary_sha256=$dictionaryPolicy.new_dictionary_sha256;
    dictionary_changed=$dictionaryPolicy.dictionary_changed; dictionary_sha256_pin=$dictionaryPolicy.dictionary_sha256_pin;
    registration_helper_sha256=$helperHash; clsid='{67718E6F-49A1-4F54-88D6-30578FC70C5D}';
    profile='{A7136205-2245-45CC-A6AA-702B3F2E8D42}'; languages=@('0409','0c04');
    allow_mapped_dll=$AllowMappedDll.IsPresent; existing_apps_keep_old_image=$policy.existing_apps_keep_old_image;
    dll_owners_at_preflight=@($dllOwners | ForEach-Object { @{pid=$_.pid; app=$_.app} });
    registry_changed=$false; local_learning_touched=$false; backup_files=@($inventory.Values | Sort-Object path) }
try {
    foreach ($directory in @($updatesRoot, $operation, $backup, $stage, $retired)) {
        if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }
        Assert-UpgradePlainPath $programFiles $directory; Assert-UpgradeProtected $directory
    }
    Write-UpgradeJson $journalPath $journal
    foreach ($record in $new.Manifest.files) {
        $destination = Get-UpgradePath $stage $record.path
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceRoot $record.path) -Destination $destination
    }
    Copy-Item -LiteralPath (Join-Path $sourceRoot 'package-manifest.json') -Destination (Join-Path $stage 'package-manifest.json')
    $staged = Read-UpgradePackage $stage $ManifestSha256.ToLowerInvariant()
    Assert-UpgradeRuntime $stage $staged $true
    $null = Assert-UpgradeDictionaryPolicy $old $staged $DictionarySha256
    $plan = @('CANTONESE_IME_MACHINE_V1', 'clsid={67718E6F-49A1-4F54-88D6-30578FC70C5D}',
        'profile={A7136205-2245-45CC-A6AA-702B3F2E8D42}', 'languages=0409,0c04',
        "dll_source=$dll", "dll_target=$dll", ('dll_sha256=' + $new.Manifest.native_dll_sha256))
    [IO.File]::WriteAllText((Join-Path $stage 'machine-registration.plan'), ($plan -join "`n") + "`n", (New-Object Text.UTF8Encoding($false)))
    $journal.new_registration_plan_sha256 = Get-UpgradeHash (Join-Path $stage 'machine-registration.plan')
    $receipt = Get-Content -LiteralPath (Join-Path $targetRoot 'installation.json') -Raw | ConvertFrom-Json
    $installation = [ordered]@{}
    foreach ($property in $receipt.PSObject.Properties) { $installation[$property.Name] = $property.Value }
    $installation.package_manifest_sha256 = $ManifestSha256.ToLowerInvariant()
    $installation.registration_plan_sha256 = $journal.new_registration_plan_sha256
    $installation.previous_package_manifest_sha256 = $InstalledManifestSha256.ToLowerInvariant()
    $installation.previous_dictionary_sha256 = $old.Manifest.dictionary_sha256
    $installation.dictionary_sha256 = $new.Manifest.dictionary_sha256
    $installation.upgraded_at_utc = [DateTime]::UtcNow.ToString('o')
    $installation.upgrade_journal = $journalPath
    Write-UpgradeJson (Join-Path $stage 'installation.json') $installation
    $journal.status = 'staged'; Write-UpgradeJson $journalPath $journal
    Write-UpgradeJson (Join-Path $stage 'last-upgrade.json') ([ordered]@{
        schema_version=1; authoritative_journal=$journalPath; backup=$backup;
        old_manifest_sha256=$InstalledManifestSha256.ToLowerInvariant(); new_manifest_sha256=$ManifestSha256.ToLowerInvariant();
        old_dictionary_sha256=$dictionaryPolicy.old_dictionary_sha256; new_dictionary_sha256=$dictionaryPolicy.new_dictionary_sha256;
        dictionary_changed=$dictionaryPolicy.dictionary_changed; dictionary_sha256_pin=$dictionaryPolicy.dictionary_sha256_pin;
        old_registration_plan_sha256=$RegistrationPlanSha256.ToLowerInvariant();
        new_registration_plan_sha256=$journal.new_registration_plan_sha256 })
    $stageHashes = @{}
    foreach ($relative in @('installation.json','last-upgrade.json')) {
        $stageHashes[$relative] = Get-UpgradeHash (Join-Path $stage $relative)
    }

    # Directory handles prevent the fixed installation from being renamed or redirected.
    foreach ($directory in $directories) { $directoryHandles += [CantoneseUpgrade.Files]::Lock($directory, $true) }
    Assert-UpgradeBinding $dll
    foreach ($relative in ($inventory.Keys | Sort-Object)) {
        $handle = if ($AllowMappedDll -and $relative -eq 'native/CantoneseIME.dll') {
            [CantoneseUpgrade.Files]::LockMappedImage((Join-Path $targetRoot $relative))
        } else { [CantoneseUpgrade.Files]::Lock((Join-Path $targetRoot $relative), $false) }
        $oldHandles[$relative] = $handle
        if ([CantoneseUpgrade.Files]::Hash($handle) -ne $inventory[$relative].sha256) { throw "Installed file changed during preflight: $relative" }
        $destination = Get-UpgradePath $backup $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        [CantoneseUpgrade.Files]::Copy($handle, $destination)
        if ((Get-UpgradeHash $destination) -ne $inventory[$relative].sha256) { throw 'Protected baseline backup verification failed.' }
    }
    $deployment = @($new.Records.Keys) + @('package-manifest.json','machine-registration.plan','installation.json','last-upgrade.json')
    foreach ($relative in $deployment) {
        $file = Get-UpgradePath $stage $relative
        Assert-UpgradePlainPath $stage $file; Assert-UpgradeProtected $file
        $newHandles[$relative] = [CantoneseUpgrade.Files]::Lock($file, $false)
    }
    foreach ($relative in $new.Records.Keys) {
        if ([CantoneseUpgrade.Files]::Hash($newHandles[$relative]) -ne $new.Records[$relative].sha256) { throw 'Staged payload changed.' }
    }
    if ([CantoneseUpgrade.Files]::Hash($newHandles['package-manifest.json']) -ne $ManifestSha256.ToLowerInvariant()) { throw 'Staged manifest changed.' }
    if ([CantoneseUpgrade.Files]::Hash($newHandles['machine-registration.plan']) -ne $journal.new_registration_plan_sha256) { throw 'Staged plan changed.' }
    foreach ($relative in $stageHashes.Keys) {
        if ([CantoneseUpgrade.Files]::Hash($newHandles[$relative]) -ne $stageHashes[$relative]) { throw 'Staged installation receipt changed.' }
    }
    $journal.status = 'replacing'; Write-UpgradeJson $journalPath $journal
    # No truncation or overwrite of an existing image: rename through its held handle.
    $replace = @($old.Records.Keys) + @('package-manifest.json','machine-registration.plan','installation.json')
    if ($oldHandles.ContainsKey('last-upgrade.json')) { $replace += 'last-upgrade.json' }
    $replace = @('runtime-config.json','native/CantoneseIME.dll') + @($replace | Where-Object { $_ -notin @('runtime-config.json','native/CantoneseIME.dll') })
    foreach ($relative in $replace) {
        $destination = Get-UpgradePath $retired $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        [CantoneseUpgrade.Files]::Rename($oldHandles[$relative], $destination)
        $withdrawn += $relative
    }
    $order = @($deployment | Where-Object { $_ -notin @('runtime-config.json','native/CantoneseIME.dll') } | Sort-Object) + @('runtime-config.json','native/CantoneseIME.dll')
    foreach ($relative in $order) {
        $destination = Get-UpgradePath $targetRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Assert-UpgradePlainPath $targetRoot (Split-Path -Parent $destination)
        Assert-UpgradeProtected (Split-Path -Parent $destination)
        [CantoneseUpgrade.Files]::Rename($newHandles[$relative], $destination)
        $published += $relative
    }
    $journal.status = 'committed'; $journal.completed_at_utc = [DateTime]::UtcNow.ToString('o')
    Write-UpgradeJson $journalPath $journal
} catch {
    $failure = $_.Exception.Message
    $rollbackErrors = @()
    for ($index=$published.Count-1; $index -ge 0; $index--) {
        $relative = $published[$index]
        try { [CantoneseUpgrade.Files]::Rename($newHandles[$relative], (Get-UpgradePath $stage $relative)) }
        catch { $rollbackErrors += "Withdraw new $relative : $($_.Exception.Message)" }
    }
    for ($index=$withdrawn.Count-1; $index -ge 0; $index--) {
        $relative = $withdrawn[$index]
        try { [CantoneseUpgrade.Files]::Rename($oldHandles[$relative], (Get-UpgradePath $targetRoot $relative)) }
        catch { $rollbackErrors += "Restore old $relative : $($_.Exception.Message)" }
    }
    $journal.status = if ($rollbackErrors.Count) { 'rollback_incomplete' } else { 'rolled_back' }
    $journal.failure = $failure; $journal.rollback_errors = $rollbackErrors
    if (Test-Path -LiteralPath $operation) {
        try { Write-UpgradeJson $journalPath $journal }
        catch { Write-Warning "Could not persist the final failure journal: $($_.Exception.Message)" }
    }
    throw "Update failed: $failure. Status: $($journal.status). Protected evidence retained at $operation. No processes were terminated."
} finally {
    foreach ($handle in $newHandles.Values) { $handle.Dispose() }
    foreach ($handle in $oldHandles.Values) { $handle.Dispose() }
    foreach ($handle in $directoryHandles) { $handle.Dispose() }
}
$journal | ConvertTo-Json -Depth 5 | Write-Output
Write-Output 'Package updated; registration and local learning were not changed. Start the broker as the normal user and repeat ordinary-app acceptance.'
