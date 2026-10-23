"""Run the real PowerShell migration against mocked cmdlets, never user settings."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"

FIXTURE = r'''
param([string] $Scenario, [string] $Migration)
$ErrorActionPreference='Stop'
. $Migration
function New-FakeLanguage($Tag, $Tips) {
    $tipsList=New-Object 'Collections.Generic.List[string]'
    foreach ($tip in $Tips) { [void]$tipsList.Add($tip) }
    return [pscustomobject]@{LanguageTag=$Tag; InputMethodTips=$tipsList; Handwriting=$false; Spellchecking=$true}
}
function Copy-FakeList($List) {
    $copy=New-Object 'Collections.Generic.List[object]'
    foreach ($entry in $List) {
        $item=New-FakeLanguage $entry.LanguageTag @($entry.InputMethodTips)
        $item.Handwriting=$entry.Handwriting; $item.Spellchecking=$entry.Spellchecking
        [void]$copy.Add($item)
    }
    return ,$copy
}
$script:current=New-Object 'Collections.Generic.List[object]'
[void]$script:current.Add((New-FakeLanguage 'en-US' @($script:LegacyTip,'0409:00000409')))
[void]$script:current.Add((New-FakeLanguage 'fr-FR' @('040C:0000040C')))
$script:current[1].Handwriting=$true
$script:current[1].Spellchecking=$false
$script:before=Get-SourceSnapshot $script:current
$script:flags=@{'0409'=$true; '0c04'=$false}
$script:events=New-Object 'Collections.Generic.List[string]'
$script:setCount=0; $script:receipt=$null; $script:failedOnce=$false
$script:environment=[ordered]@{default_override=''; ui_override='en-US'; ui_culture='en-US'; culture='en-US'}
if ($Scenario -eq 'existing_hk') {
    $hk=New-FakeLanguage 'zh-HK' @('0C04:UNRELATED-TIP')
    $hk.Handwriting=$true
    [void]$script:current.Insert(1,$hk)
}
if ($Scenario -eq 'windows_empty_hk_existing') {
    $hk=New-FakeLanguage 'zh-Hant-HK' @()
    $hk.Handwriting=$true
    [void]$script:current.Add($hk)
}
if ($Scenario -eq 'already_migrated') {
    $script:current[0].InputMethodTips.RemoveAt(0)
    [void]$script:current.Add((New-FakeLanguage 'zh-Hant-HK' @($script:HongKongTip)))
    $script:flags['0409']=$false; $script:flags['0c04']=$true
}
if ($Scenario -eq 'explicit_default') { $script:environment.default_override=$script:LegacyTip }
$script:before=Get-SourceSnapshot $script:current
function Assert-OrdinaryUserRoot($Root) {
    if ($Scenario -eq 'elevated') { throw 'ordinary user required' }
}
function Get-WinUserLanguageList { return ,(Copy-FakeList $script:current) }
function New-WinUserLanguageList($Language) {
    $list=New-Object 'Collections.Generic.List[object]'
    $item=New-FakeLanguage $Language @('0C04:DEFAULT-WINDOWS-TIP')
    if ($Scenario -like 'windows_*') { $item.Handwriting=$true }
    [void]$list.Add($item)
    return ,$list
}
function Get-UserEnvironment {
    return [ordered]@{default_override=$script:environment.default_override;ui_override=$script:environment.ui_override;
        ui_culture=$script:environment.ui_culture;culture=$script:environment.culture}
}
function Write-SourceReceipt($Receipt) {
    if ($Scenario -eq 'receipt_failure') { throw 'fixture receipt failure' }
    if ($Scenario -eq 'before_set_change' -and $Receipt.status -eq 'prepared') {
        [void]$script:current[1].InputMethodTips.Add('040C:UNRELATED-NEW-TIP')
    }
    $script:receipt=ConvertFrom-Json (ConvertTo-Json -InputObject $Receipt -Depth 18)
}
function Set-WinUserLanguageList {
    [CmdletBinding()]
    param($LanguageList, [switch] $Force)
    $script:setCount++
    [void]$script:events.Add('set-list')
    if ($Scenario -eq 'warning_normal') {
        Write-Warning 'fixture migration warning'; Write-Output 'fixture unwanted cmdlet output'
        Write-Progress -Activity 'fixture migration progress' -Status 'test only' -PercentComplete 50
        Write-Progress -Activity 'fixture migration progress' -Completed
    }
    $script:current=Copy-FakeList $LanguageList
    if ($Scenario -like 'windows_*') {
        foreach ($item in $script:current) {
            if ($item.LanguageTag -ieq 'zh-HK') { $item.LanguageTag='zh-Hant-HK' }
        }
    }
    if ($Scenario -eq 'windows_unrelated_tag_change' -and -not $script:failedOnce) {
        $script:failedOnce=$true; $script:current[1].LanguageTag='fr-Latn-FR'
    }
    if ($Scenario -eq 'partial_set_failure' -and -not $script:failedOnce) {
        $script:failedOnce=$true; throw 'fixture partial list write'
    }
}
function Invoke-OwnedProfile($Root, $Action, $Language) {
    [void]$script:events.Add($Action+':'+$Language)
    if ($Action -eq 'inspect-user') {
        return [pscustomobject]@{stage='user_enabled_before';detail=$script:flags[$Language].ToString().ToLowerInvariant()}
    }
    $script:flags[$Language]=$Action -eq 'enable-user'
    if ($Action -eq 'enable-user' -and $Language -eq '0c04' -and
        $Scenario -in @('hk_failure','concurrent_failure','concurrent_hk_property_failure','concurrent_default_failure','rollback_concurrent_after_profiles') -and -not $script:failedOnce) {
        $script:failedOnce=$true
        if ($Scenario -eq 'concurrent_failure') { [void]$script:current[1].InputMethodTips.Add('040C:UNRELATED-NEW-TIP') }
        if ($Scenario -eq 'concurrent_hk_property_failure') { $script:current[$script:current.Count-1].Handwriting=$true }
        if ($Scenario -eq 'concurrent_default_failure') { $script:environment.default_override='0409:00000409' }
        throw 'fixture HK enable failure'
    }
    if ($Action -eq 'disable-user' -and $Language -eq '0409' -and
        $Scenario -in @('legacy_failure','windows_rollback_container') -and -not $script:failedOnce) {
        $script:failedOnce=$true; throw 'fixture legacy disable failure'
    }
    if ($Action -eq 'disable-user' -and $Language -eq '0c04' -and $Scenario -eq 'windows_rollback_container') {
        $hk=@($script:current | Where-Object { Test-HongKongTag $_.LanguageTag })
        if ($hk.Count -eq 0) {
            $empty=New-FakeLanguage 'zh-Hant-HK' @(); $empty.Handwriting=$true
            [void]$script:current.Add($empty)
        } else { $hk[0].InputMethodTips.Clear() }
    }
    if ($Action -eq 'disable-user' -and $Language -eq '0c04' -and $Scenario -eq 'rollback_concurrent_after_profiles') {
        [void]$script:current[1].InputMethodTips.Add('040C:UNRELATED-NEW-TIP')
    }
    return @()
}
$result=$null; $errorText=$null
try { $result=Invoke-CantoneseSourceMigration 'fixture-root' } catch { $errorText=$_.Exception.Message }
if ($Scenario -eq 'repeat_migrated' -and $null -eq $errorText) {
    $script:events.Clear(); $script:setCount=0
    try { $result=Invoke-CantoneseSourceMigration 'fixture-root' } catch { $errorText=$_.Exception.Message }
}
[ordered]@{result=$result;error=$errorText;before=$script:before;after=(Get-SourceSnapshot $script:current);
    flags=$script:flags;events=@($script:events);set_count=$script:setCount;receipt=$script:receipt;
    environment=$script:environment} | ConvertTo-Json -Depth 20 -Compress
'''


@unittest.skipUnless(POWERSHELL.is_file(), "Native Windows PowerShell is required for mocked migration tests.")
class UserInputSourceTests(unittest.TestCase):
    def run_case(self, scenario):
        local = ROOT / ".local/user-input-source-tests"
        local.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local) as directory:
            fixture = Path(directory) / "fixture.ps1"
            fixture.write_text(FIXTURE, encoding="utf-8")
            child = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                    "-File", str(fixture), "-Scenario", scenario,
                                    "-Migration", str(ROOT / "installer/Set-UserInputSource.ps1")],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
            value = json.loads(child.stdout.lstrip("\ufeff"))
            value["_stderr"] = child.stderr
            return value

    def test_english_and_unrelated_languages_survive_owned_tip_migration(self):
        value = self.run_case("normal")
        self.assertIsNone(value["error"])
        self.assertEqual(value["result"]["language"], "0c04")
        self.assertEqual([row["language_tag"] for row in value["after"]], ["en-us", "fr-fr", "zh-hant-hk"])
        self.assertEqual(value["after"][0]["input_method_tips"], ["0409:00000409"])
        self.assertEqual(value["after"][1], value["before"][1])
        self.assertEqual(len(value["after"][2]["input_method_tips"]), 1)
        self.assertTrue(value["flags"]["0c04"])
        self.assertFalse(value["flags"]["0409"])
        events = value["events"]
        self.assertLess(events.index("enable-user:0c04"), events.index("disable-user:0409"))
        self.assertTrue(value["receipt"]["hk_proven_before_legacy_removal"])
        self.assertEqual(value["environment"], {"default_override": "", "ui_override": "en-US", "ui_culture": "en-US", "culture": "en-US"})

    def test_existing_hong_kong_sources_keep_their_order_and_settings(self):
        value = self.run_case("existing_hk")
        self.assertIsNone(value["error"])
        self.assertEqual([row["language_tag"] for row in value["after"]], ["en-us", "zh-hant-hk", "fr-fr"])
        self.assertEqual(value["after"][1]["input_method_tips"][0], "0C04:UNRELATED-TIP")
        self.assertEqual(value["after"][1]["properties"], value["before"][1]["properties"])

    def test_explicit_legacy_default_is_retained(self):
        value = self.run_case("explicit_default")
        self.assertIsNone(value["error"])
        self.assertTrue(value["result"]["legacy_retained_as_default"])
        self.assertTrue(value["flags"]["0409"])
        self.assertEqual(value["after"][0], value["before"][0])
        self.assertNotIn("disable-user:0409", value["events"])

    def test_hk_failure_restores_typed_list_and_prior_profile_flags(self):
        value = self.run_case("hk_failure")
        self.assertIn("HK enable failure", value["error"])
        self.assertEqual(value["after"], value["before"])
        self.assertEqual(value["flags"], {"0409": True, "0c04": False})
        self.assertTrue(value["receipt"]["rollback_succeeded"])
        self.assertNotIn("disable-user:0409", value["events"])

    def test_partial_legacy_failure_rolls_back_both_owned_profiles(self):
        value = self.run_case("legacy_failure")
        self.assertIn("legacy disable failure", value["error"])
        self.assertEqual(value["after"], value["before"])
        self.assertEqual(value["flags"], {"0409": True, "0c04": False})
        self.assertTrue(value["receipt"]["rollback_succeeded"])

    def test_partial_list_write_is_recovered(self):
        value = self.run_case("partial_set_failure")
        self.assertIn("partial list write", value["error"])
        self.assertEqual(value["after"], value["before"])
        self.assertTrue(value["receipt"]["rollback_succeeded"])

    def test_concurrent_unrelated_change_blocks_broad_rollback(self):
        value = self.run_case("concurrent_failure")
        self.assertIn("HK enable failure", value["error"])
        self.assertEqual(value["set_count"], 1)
        self.assertIn("040C:UNRELATED-NEW-TIP", value["after"][1]["input_method_tips"])
        self.assertFalse(value["receipt"]["rollback_attempted"])
        self.assertIn("concurrently", value["receipt"]["rollback_error"])
        self.assertTrue(value["flags"]["0409"])

    def test_receipt_failure_precedes_any_mutation(self):
        value = self.run_case("receipt_failure")
        self.assertIn("receipt failure", value["error"])
        self.assertEqual(value["set_count"], 0)
        self.assertEqual(value["after"], value["before"])
        self.assertFalse(any(event.startswith("enable-user") or event.startswith("disable-user") for event in value["events"]))

    def test_new_hk_property_change_is_not_deleted_by_rollback(self):
        value = self.run_case("concurrent_hk_property_failure")
        self.assertIsNotNone(value["error"])
        self.assertEqual(value["set_count"], 1)
        self.assertTrue(value["after"][-1]["properties"]["Handwriting"])
        self.assertFalse(value["receipt"]["rollback_attempted"])

    def test_concurrent_default_change_blocks_rollback_before_any_source_toggle(self):
        value = self.run_case("concurrent_default_failure")
        self.assertIsNotNone(value["error"])
        self.assertEqual(value["set_count"], 1)
        self.assertFalse(value["receipt"]["rollback_attempted"])
        self.assertNotIn("disable-user:0409", value["events"])
        self.assertNotIn("disable-user:0c04", value["events"])
        self.assertEqual(value["environment"]["default_override"], "0409:00000409")

    def test_stale_list_is_rechecked_immediately_before_first_write(self):
        value = self.run_case("before_set_change")
        self.assertIn("before the staged write", value["error"])
        self.assertEqual(value["set_count"], 0)
        self.assertIn("040C:UNRELATED-NEW-TIP", value["after"][1]["input_method_tips"])

    def test_cmdlet_warnings_and_output_do_not_corrupt_json_protocol(self):
        value = self.run_case("warning_normal")
        self.assertIsNone(value["error"])
        self.assertEqual(value["result"]["status"], "ready")
        self.assertIn("fixture migration warning", value["_stderr"])

    def test_elevation_is_rejected_before_mutation(self):
        value = self.run_case("elevated")
        self.assertIn("ordinary user", value["error"])
        self.assertEqual(value["set_count"], 0)
        self.assertEqual(value["events"], [])

    def test_windows_hong_kong_tag_normalization_is_accepted_and_raw_diagnostics_retained(self):
        value = self.run_case("windows_normalization")
        self.assertIsNone(value["error"])
        receipt = value["receipt"]
        self.assertEqual(receipt["staged_expected_raw"][-1]["language_tag"], "zh-HK")
        self.assertEqual(receipt["staged_observed_raw"][-1]["language_tag"], "zh-Hant-HK")
        self.assertEqual(receipt["staged_expected"], receipt["staged_observed"])
        self.assertTrue(receipt["hk_proven_before_legacy_removal"])

    def test_existing_empty_canonical_hk_container_is_populated_without_duplicates(self):
        value = self.run_case("windows_empty_hk_existing")
        self.assertIsNone(value["error"])
        hk = [row for row in value["after"] if row["language_tag"] == "zh-hant-hk"]
        self.assertEqual(len(hk), 1)
        self.assertEqual(len(hk[0]["input_method_tips"]), 1)
        self.assertEqual(hk[0]["properties"], value["before"][-1]["properties"])

    def test_rollback_restores_profiles_before_final_list_write_to_remove_empty_container(self):
        value = self.run_case("windows_rollback_container")
        self.assertIn("legacy disable failure", value["error"])
        self.assertEqual(value["after"], value["before"])
        self.assertTrue(value["receipt"]["rollback_succeeded"])
        events = value["events"]
        self.assertGreater(max(index for index, event in enumerate(events) if event == "set-list"), events.index("disable-user:0c04"))

    def test_rollback_rechecks_unrelated_changes_after_profile_restoration(self):
        value = self.run_case("rollback_concurrent_after_profiles")
        self.assertIn("HK enable failure", value["error"])
        self.assertEqual(value["set_count"], 1)
        self.assertIn("040C:UNRELATED-NEW-TIP", value["after"][1]["input_method_tips"])
        self.assertIn("during profile restoration", value["receipt"]["rollback_error"])

    def test_unrelated_language_tag_changes_are_not_normalized_away(self):
        value = self.run_case("windows_unrelated_tag_change")
        self.assertIn("staged input source changed", value["error"])
        self.assertFalse(value["receipt"]["rollback_attempted"])
        self.assertEqual(value["receipt"]["staged_expected_raw"][1]["language_tag"], "fr-FR")
        self.assertEqual(value["receipt"]["staged_observed_raw"][1]["language_tag"], "fr-Latn-FR")

    def test_already_migrated_source_uses_no_setting_or_helper_mutation(self):
        value = self.run_case("already_migrated")
        self.assertIsNone(value["error"])
        self.assertEqual(value["set_count"], 0)
        self.assertEqual(value["after"], value["before"])
        self.assertFalse(any(event.startswith("enable-user") or event.startswith("disable-user") for event in value["events"]))

    def test_repeated_migration_is_idempotent_after_first_success(self):
        value = self.run_case("repeat_migrated")
        self.assertIsNone(value["error"])
        self.assertEqual(value["result"]["status"], "ready")
        self.assertEqual(value["set_count"], 0)
        self.assertFalse(any(event.startswith("enable-user") or event.startswith("disable-user") for event in value["events"]))


if __name__ == "__main__":
    unittest.main()
