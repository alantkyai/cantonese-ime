param([string] $InstallRoot)

# Run only as the ordinary user. No language packages, UI language, default
# input override, system account, or other user's settings are changed here.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:OwnedClass = '{67718E6F-49A1-4F54-88D6-30578FC70C5D}'
$script:OwnedProfile = '{A7136205-2245-45CC-A6AA-702B3F2E8D42}'
$script:LegacyTip = '0409:' + $script:OwnedClass + $script:OwnedProfile
$script:HongKongTip = '0C04:' + $script:OwnedClass + $script:OwnedProfile

function Assert-OrdinaryUserRoot([string] $Root) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Input-source activation must run as the ordinary Windows user.'
    }
    $expected = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'CantoneseIME'
    if ([IO.Path]::GetFullPath($Root) -ine $expected) { throw 'Unexpected product root.' }
    if ((Get-Item -LiteralPath $Root).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'A linked product root is not accepted.'
    }
}

function Get-SourceSnapshot($List, [switch] $RawTags) {
    $result = @()
    foreach ($language in $List) {
        $properties = [ordered]@{}
        foreach ($name in @('Handwriting', 'Spellchecking')) {
            if ($null -ne $language.PSObject.Properties[$name]) { $properties[$name] = $language.$name }
        }
        $tag = if ($RawTags) { $language.LanguageTag } else { $language.LanguageTag.ToLowerInvariant() }
        # Windows constructs zh-HK but can return zh-Hant-HK after applying
        # the list. These identify our same Hong Kong input-language slot.
        if (-not $RawTags -and (Test-HongKongTag $tag)) { $tag = 'zh-hant-hk' }
        $result += [ordered]@{
            language_tag = $tag
            input_method_tips = @($language.InputMethodTips | ForEach-Object { $_.ToUpperInvariant() })
            properties = $properties
        }
    }
    return ,$result
}

function Convert-SourceJson($Value) { return ConvertTo-Json -InputObject $Value -Depth 15 -Compress }

function Set-SourceLanguageList($List) {
    $sourceWarnings = @()
    Set-WinUserLanguageList -LanguageList $List -Force -WarningAction SilentlyContinue -WarningVariable sourceWarnings | Out-Null
    foreach ($warning in $sourceWarnings) { [Console]::Error.WriteLine($warning.ToString()) }
}

function Get-UserEnvironment {
    $default = Get-WinDefaultInputMethodOverride
    $ui = Get-WinUILanguageOverride
    return [ordered]@{
        default_override = if ($null -eq $default) { '' } else { $default.InputMethodTip.ToUpperInvariant() }
        ui_override = if ($null -eq $ui) { '' } else { $ui.Name }
        ui_culture = (Get-UICulture).Name
        culture = (Get-Culture).Name
    }
}

function Assert-EnvironmentPreserved($Before) {
    if ((Convert-SourceJson (Get-UserEnvironment)) -cne (Convert-SourceJson $Before)) {
        throw 'The default input or Windows UI language changed during activation.'
    }
}

function Test-HongKongTag([string] $Tag) { return $Tag -ieq 'zh-HK' -or $Tag -ieq 'zh-Hant-HK' }

function Test-HongKongSource($Snapshot) {
    $entries = @($Snapshot | Where-Object { Test-HongKongTag $_.language_tag })
    return $entries.Count -eq 1 -and $entries[0].input_method_tips -contains $script:HongKongTip
}

function Get-UnownedSnapshot($Snapshot, [bool] $HadHongKong, $PublishedHongKongProperties = $null) {
    $result = @()
    foreach ($entry in $Snapshot) {
        $tips = @($entry.input_method_tips | Where-Object { $_ -ine $script:LegacyTip -and $_ -ine $script:HongKongTip })
        if (-not $HadHongKong -and (Test-HongKongTag $entry.language_tag) -and $tips.Count -eq 0 -and
            $null -ne $PublishedHongKongProperties -and
            (Convert-SourceJson $entry.properties) -ceq (Convert-SourceJson $PublishedHongKongProperties)) { continue }
        $result += [ordered]@{ language_tag=$entry.language_tag; input_method_tips=$tips; properties=$entry.properties }
    }
    return ,$result
}

function Write-SourceReceipt($Receipt) {
    $directory = Join-Path $env:LOCALAPPDATA 'CantoneseIME\Installer'
    [void][IO.Directory]::CreateDirectory($directory)
    $target = Join-Path $directory 'input-source-migration.json'
    $temporary = $target + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temporary, (ConvertTo-Json -InputObject $Receipt -Depth 18), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $target -Force
}

function Invoke-OwnedProfile([string] $Root, [string] $Action, [string] $Language) {
    if ($Action -notin @('enable-user','disable-user','inspect-user') -or $Language -notin @('0409','0c04')) {
        throw 'Unexpected owned-profile action.'
    }
    $helper = Join-Path $Root 'native\CantoneseMachineRegistration.exe'
    $plan = Join-Path $Root 'machine-registration.plan'
    $hash = (Get-FileHash -LiteralPath $plan -Algorithm SHA256).Hash.ToLowerInvariant()
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $helper --action $Action --manifest $plan --manifest-sha256 $hash --language $Language 2>&1 | ForEach-Object { $_.ToString() })
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $oldPreference }
    $directory = Join-Path $env:LOCALAPPDATA 'CantoneseIME\Installer'
    [void][IO.Directory]::CreateDirectory($directory)
    [IO.File]::WriteAllLines((Join-Path $directory ('source-' + $Action + '-' + $Language + '.jsonl')), [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
    if ($code -ne 0) { throw ('Owned profile ' + $Action + ' failed for ' + $Language + ': ' + ($lines -join ' ')) }
    return @($lines | Where-Object { $_.Trim() } | ForEach-Object { ConvertFrom-Json -InputObject $_ })
}

function Read-OwnedEnabled([string] $Root, [string] $Language) {
    foreach ($entry in (Invoke-OwnedProfile $Root 'inspect-user' $Language)) {
        if (($null -ne $entry.PSObject.Properties['stage'] -and $entry.stage -eq 'user_enabled_before') -or
            ($null -ne $entry.PSObject.Properties['step'] -and $entry.step -eq 'user_enabled_before')) {
            if ($entry.detail -notin @('true','false')) { throw 'Invalid enabled state.' }
            return $entry.detail -eq 'true'
        }
    }
    throw 'The owned profile did not report its enabled state.'
}

function Assert-HongKongReady([string] $Root) {
    if (-not (Test-HongKongSource (Get-SourceSnapshot (Get-WinUserLanguageList))) -or
        -not (Read-OwnedEnabled $Root '0c04')) { throw 'The Hong Kong input source is not discoverable and enabled.' }
}

function Invoke-CantoneseSourceMigration([string] $Root) {
    Assert-OrdinaryUserRoot $Root
    $beforeList = Get-WinUserLanguageList
    $working = Get-WinUserLanguageList
    $before = Get-SourceSnapshot $beforeList
    if ((Convert-SourceJson $before) -cne (Convert-SourceJson (Get-SourceSnapshot $working))) {
        throw 'The language list changed before activation.'
    }
    # Keep the original typed objects untouched for an in-process rollback.
    for ($index=0; $index -lt $beforeList.Count; $index++) {
        if ([object]::ReferenceEquals($beforeList[$index], $working[$index])) { throw 'The language snapshots are not independent.' }
    }
    $environment = Get-UserEnvironment
    $oldEnabled = Read-OwnedEnabled $Root '0409'
    $hkEnabled = Read-OwnedEnabled $Root '0c04'
    $hadHongKong = @($before | Where-Object { Test-HongKongTag $_.language_tag }).Count -gt 0
    $unownedBefore = Convert-SourceJson (Get-UnownedSnapshot $before $hadHongKong)
    $publishedHongKongProperties = $null
    $receipt = [ordered]@{ schema_version=1; status='prepared'; before=$before; before_raw=(Get-SourceSnapshot $beforeList -RawTags); environment=$environment;
        enabled_before=[ordered]@{ '0409'=$oldEnabled; '0c04'=$hkEnabled }; legacy_retained_as_default=($environment.default_override -ieq $script:LegacyTip);
        hk_proven_before_legacy_removal=$false; rollback_attempted=$false; rollback_succeeded=$false }
    Write-SourceReceipt $receipt
    try {
        $hk = @($working | Where-Object { Test-HongKongTag $_.LanguageTag })
        if ($hk.Count -gt 1) { throw 'Multiple Hong Kong language entries are ambiguous.' }
        if ($hk.Count -eq 0) {
            $newLanguage = New-WinUserLanguageList -Language 'zh-HK'
            if ($newLanguage.Count -ne 1 -or -not (Test-HongKongTag $newLanguage[0].LanguageTag)) { throw 'Windows did not construct the Hong Kong language.' }
            $newLanguage[0].InputMethodTips.Clear()
            [void]$newLanguage[0].InputMethodTips.Add($script:HongKongTip)
            [void]$working.Add($newLanguage[0])
        } elseif ($hk[0].InputMethodTips -notcontains $script:HongKongTip) {
            [void]$hk[0].InputMethodTips.Add($script:HongKongTip)
        }
        $staged = Get-SourceSnapshot $working
        $receipt.staged_expected = $staged
        $receipt.staged_expected_raw = Get-SourceSnapshot $working -RawTags
        if (-not $hadHongKong) {
            $publishedHongKongProperties = @($staged | Where-Object { Test-HongKongTag $_.language_tag })[0].properties
        }
        if ((Convert-SourceJson $staged) -cne (Convert-SourceJson $before)) {
            Assert-EnvironmentPreserved $environment
            if ((Convert-SourceJson (Get-SourceSnapshot (Get-WinUserLanguageList))) -cne (Convert-SourceJson $before)) {
                throw 'The language list changed before the staged write.'
            }
            Set-SourceLanguageList $working
        }
        if (-not (Read-OwnedEnabled $Root '0c04')) {
            [void](Invoke-OwnedProfile $Root 'enable-user' '0c04')
        }
        Assert-HongKongReady $Root
        Assert-EnvironmentPreserved $environment
        $stagedList = Get-WinUserLanguageList
        $receipt.staged_observed = Get-SourceSnapshot $stagedList
        $receipt.staged_observed_raw = Get-SourceSnapshot $stagedList -RawTags
        Write-SourceReceipt $receipt
        if ((Convert-SourceJson $receipt.staged_observed) -cne (Convert-SourceJson $staged)) {
            throw 'The staged input source changed unrelated language settings.'
        }
        $receipt.hk_proven_before_legacy_removal = $true
        $receipt.status = 'hong_kong_ready'
        Write-SourceReceipt $receipt
        if (-not $receipt.legacy_retained_as_default) {
            $finalList = Get-WinUserLanguageList
            foreach ($language in $finalList) {
                for ($index=$language.InputMethodTips.Count-1; $index -ge 0; $index--) {
                    if ($language.InputMethodTips[$index] -ieq $script:LegacyTip) { $language.InputMethodTips.RemoveAt($index) }
                }
            }
            $expected = Get-SourceSnapshot $finalList
            if ((Convert-SourceJson $expected) -cne (Convert-SourceJson $staged)) {
                Assert-EnvironmentPreserved $environment
                if ((Convert-SourceJson (Get-SourceSnapshot (Get-WinUserLanguageList))) -cne (Convert-SourceJson $staged)) {
                    throw 'The language list changed before legacy removal.'
                }
                Set-SourceLanguageList $finalList
            }
            if (Read-OwnedEnabled $Root '0409') {
                [void](Invoke-OwnedProfile $Root 'disable-user' '0409')
            }
            if (Read-OwnedEnabled $Root '0409') { throw 'The legacy owned profile remains enabled.' }
        } else { $expected = $staged }
        Assert-HongKongReady $Root
        Assert-EnvironmentPreserved $environment
        $afterList = Get-WinUserLanguageList
        $after = Get-SourceSnapshot $afterList
        if ((Convert-SourceJson $after) -cne (Convert-SourceJson $expected) -or
            (Convert-SourceJson (Get-UnownedSnapshot $after $hadHongKong $publishedHongKongProperties)) -cne $unownedBefore) {
            throw 'Unrelated language settings changed during migration.'
        }
        $receipt.status = 'ready'; $receipt.after = $after; $receipt.after_raw = Get-SourceSnapshot $afterList -RawTags; $receipt.language = '0c04'
        Write-SourceReceipt $receipt
        return [ordered]@{ status='ready'; language='0c04'; legacy_retained_as_default=$receipt.legacy_retained_as_default }
    } catch {
        $failure = $_.Exception.Message
        $receipt.status = 'failed'; $receipt.failure = $failure
        try {
            Assert-EnvironmentPreserved $environment
            $current = Get-SourceSnapshot (Get-WinUserLanguageList)
            if ((Convert-SourceJson (Get-UnownedSnapshot $current $hadHongKong $publishedHongKongProperties)) -cne $unownedBefore) {
                throw 'Rollback refused because unrelated language settings changed concurrently.'
            }
            $receipt.rollback_attempted = $true
            # Layout/TIP toggles can reintroduce an empty language container.
            # Restore owned flags first, then publish the original typed list.
            if ((Read-OwnedEnabled $Root '0409') -ne $oldEnabled) {
                [void](Invoke-OwnedProfile $Root $(if ($oldEnabled) {'enable-user'} else {'disable-user'}) '0409')
            }
            if ((Read-OwnedEnabled $Root '0c04') -ne $hkEnabled) {
                [void](Invoke-OwnedProfile $Root $(if ($hkEnabled) {'enable-user'} else {'disable-user'}) '0c04')
            }
            $receipt.rollback_profile_states_restored = $true
            Assert-EnvironmentPreserved $environment
            $current = Get-SourceSnapshot (Get-WinUserLanguageList)
            if ((Convert-SourceJson (Get-UnownedSnapshot $current $hadHongKong $publishedHongKongProperties)) -cne $unownedBefore) {
                throw 'Rollback list write refused because unrelated settings changed during profile restoration.'
            }
            Set-SourceLanguageList $beforeList
            $restored = Get-SourceSnapshot (Get-WinUserLanguageList)
            Assert-EnvironmentPreserved $environment
            if ((Convert-SourceJson $restored) -cne (Convert-SourceJson $before) -or
                (Read-OwnedEnabled $Root '0409') -ne $oldEnabled -or (Read-OwnedEnabled $Root '0c04') -ne $hkEnabled) {
                throw 'Prior source settings could not be fully verified after rollback.'
            }
            $receipt.rollback_succeeded = $true
        } catch { $receipt.rollback_error = $_.Exception.Message }
        $afterList = Get-WinUserLanguageList
        $receipt.after = Get-SourceSnapshot $afterList
        $receipt.after_raw = Get-SourceSnapshot $afterList -RawTags
        Write-SourceReceipt $receipt
        throw ('Hong Kong input-source activation failed: ' + $failure + '. Inspect input-source-migration.json for rollback facts.')
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
    try { Invoke-CantoneseSourceMigration $InstallRoot | ConvertTo-Json -Depth 5 -Compress }
    catch { [Console]::Error.WriteLine($_.Exception.Message); exit 2 }
}
