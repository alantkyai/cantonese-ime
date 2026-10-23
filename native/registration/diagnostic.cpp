// Explicit registration-stage diagnostic. Default action is read-only inspect.
// Never activates an IME, sets a default keyboard, or edits another CLSID.
#include <windows.h>
#include <msctf.h>
#include <algorithm>
#include <cwchar>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "../tsf/ime_ids.h"
#include "../tsf/tsf_compat.h"

namespace {
template<class T> struct Com {
    T* value = nullptr;
    ~Com() { if (value) value->Release(); }
};
const GUID* const kCategories[] = {&GUID_TFCAT_TIP_KEYBOARD, &GUID_TFCAT_DISPLAYATTRIBUTEPROVIDER, &GUID_TFCAT_TIPCAP_UIELEMENTENABLED};
const wchar_t* const kCategoryNames[] = {L"keyboard", L"display_attribute", L"ui_element"};

std::string Utf8(const std::wstring& text) {
    const int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    std::string result(size, '\0');
    if (size) WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), size, nullptr, nullptr);
    return result;
}
std::string Json(const std::wstring& text) {
    std::ostringstream out; out << '"';
    for (unsigned char c : Utf8(text)) {
        if (c == '\\' || c == '"') out << '\\' << static_cast<char>(c);
        else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
        else out << static_cast<char>(c);
    }
    out << '"'; return out.str();
}
std::wstring Hex(ULONG value) { std::wostringstream out; out << L"0x" << std::hex << std::setw(8) << std::setfill(L'0') << value; return out.str(); }
std::wstring Guid(REFGUID value) { wchar_t buffer[64]{}; StringFromGUID2(value, buffer, 64); return buffer; }
void Log(const wchar_t* stage, HRESULT result, const std::wstring& detail = L"") {
    std::cout << "{\"stage\":" << Json(stage) << ",\"hresult\":" << Json(Hex(static_cast<ULONG>(result)))
              << ",\"succeeded\":" << (SUCCEEDED(result) ? "true" : "false") << ",\"detail\":" << Json(detail) << "}\n";
    std::cout.flush();
}

HRESULT Exists(HKEY hive, const std::wstring& path, bool& exists) {
    HKEY key = nullptr;
    const LONG status = RegOpenKeyExW(hive, path.c_str(), 0, KEY_READ | KEY_WOW64_64KEY, &key);
    exists = status == ERROR_SUCCESS;
    if (exists) RegCloseKey(key);
    return status == ERROR_FILE_NOT_FOUND ? S_OK : HRESULT_FROM_WIN32(status);
}
void Snapshot(const wchar_t* prefix, HKEY hive, const std::wstring& class_key, const std::wstring& tip_key) {
    for (const auto& pair : std::vector<std::pair<std::wstring,std::wstring>>{{L"COM", class_key}, {L"TIP", tip_key}}) {
        bool exists = false;
        const HRESULT result = Exists(hive, pair.second, exists);
        const std::wstring name = std::wstring(prefix) + L"_" + pair.first;
        Log(name.c_str(), result, exists ? L"present" : L"absent");
    }
}
HRESULT CanonicalFile(const std::wstring& path, std::wstring& canonical) {
    HANDLE file = CreateFileW(path.c_str(), FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    if (file == INVALID_HANDLE_VALUE) return HRESULT_FROM_WIN32(GetLastError());
    std::wstring buffer(32768, L'\0');
    const DWORD size = GetFinalPathNameByHandleW(file, buffer.data(), static_cast<DWORD>(buffer.size()), FILE_NAME_NORMALIZED);
    const DWORD error = GetLastError(); CloseHandle(file);
    if (!size || size >= buffer.size()) return HRESULT_FROM_WIN32(size ? ERROR_INSUFFICIENT_BUFFER : error);
    buffer.resize(size); canonical = std::move(buffer); return S_OK;
}
HRESULT CheckComBinding(const std::wstring& key_path, const std::wstring& expected_dll) {
    HKEY key = nullptr;
    LONG status = RegOpenKeyExW(HKEY_CURRENT_USER, (key_path + L"\\InprocServer32").c_str(), 0, KEY_READ | KEY_WOW64_64KEY, &key);
    if (status != ERROR_SUCCESS) return HRESULT_FROM_WIN32(status);
    DWORD kind = 0, size = 0;
    status = RegQueryValueExW(key, nullptr, nullptr, &kind, nullptr, &size);
    std::vector<wchar_t> value(size / sizeof(wchar_t) + 1, L'\0');
    if (status == ERROR_SUCCESS && kind == REG_SZ) status = RegQueryValueExW(key, nullptr, nullptr, &kind,
        reinterpret_cast<BYTE*>(value.data()), &size);
    else if (status == ERROR_SUCCESS) status = ERROR_INVALID_DATATYPE;
    RegCloseKey(key);
    if (status != ERROR_SUCCESS) return HRESULT_FROM_WIN32(status);
    std::wstring registered, expected;
    HRESULT result = CanonicalFile(value.data(), registered);
    if (SUCCEEDED(result)) result = CanonicalFile(expected_dll, expected);
    if (FAILED(result)) return result;
    Log(L"existing_com_dll", S_OK, registered);
    return CompareStringOrdinal(registered.c_str(), -1, expected.c_str(), -1, TRUE) == CSTR_EQUAL ? S_OK : E_ACCESSDENIED;
}
void LogProfile(ITfInputProcessorProfileMgr* profiles, LANGID language, const wchar_t* stage) {
    TF_INPUTPROCESSORPROFILE profile{};
    const HRESULT result = profiles->GetProfile(TF_PROFILETYPE_INPUTPROCESSOR, language,
        CLSID_CantoneseIME, GUID_CantoneseProfile, nullptr, &profile);
    Log(stage, result, L"language=" + Hex(profile.langid) + L" category=" + Guid(profile.catid) +
        L" flags=" + Hex(profile.dwFlags) + L" caps=" + Hex(profile.dwCaps));
}
void Rollback(ITfInputProcessorProfiles* profiles, ITfCategoryMgr* categories, LANGID language) {
    // Only entered after both hives were proven to have no existing TIP key.
    // Keep the existing COM registration and all user files untouched.
    for (unsigned i = 0; i < 3; ++i) Log((L"rollback_category_" + std::wstring(kCategoryNames[i])).c_str(),
        categories->UnregisterCategory(CLSID_CantoneseIME, *kCategories[i], CLSID_CantoneseIME));
    Log(L"rollback_language_profile", profiles->RemoveLanguageProfile(CLSID_CantoneseIME, language, GUID_CantoneseProfile));
    Log(L"rollback_service", profiles->Unregister(CLSID_CantoneseIME));
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    try {
        std::wstring action = L"inspect", dll;
        LANGID language = kCantoneseLanguage;
        for (int i = 1; i < argc; ++i) {
            if (i + 1 == argc) { Log(L"arguments", E_INVALIDARG, L"Missing value"); return 2; }
            const std::wstring name = argv[i], value = argv[++i];
            if (name == L"--action") action = value;
            else if (name == L"--dll") dll = value;
            else if (name == L"--langid") {
                std::size_t consumed = 0; const unsigned long number = std::stoul(value, &consumed, 0);
                if (consumed != value.size() || number > 0xffff) return 2;
                language = static_cast<LANGID>(number);
            } else return 2;
        }
        if (action != L"inspect" && action != L"register-legacy" && action != L"register-profile") return 2;
        Log(L"action", S_OK, action);
        HANDLE token = nullptr; TOKEN_ELEVATION elevation{}; DWORD length = 0;
        if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) { Log(L"open_token", HRESULT_FROM_WIN32(GetLastError())); return 2; }
        const BOOL token_result = GetTokenInformation(token, TokenElevation, &elevation, sizeof(elevation), &length);
        const DWORD token_error = GetLastError(); CloseHandle(token);
        if (!token_result) { Log(L"query_elevation", HRESULT_FROM_WIN32(token_error)); return 2; }
        Log(L"token", S_OK, elevation.TokenIsElevated ? L"elevated" : L"not_elevated");
        // This diagnostic never requests elevation or performs a machine install.
        if (action != L"inspect" && elevation.TokenIsElevated) { Log(L"account_scope_guard", E_ACCESSDENIED, L"Registration probes require a non-elevated token"); return 2; }
        const std::wstring class_key = L"Software\\Classes\\CLSID\\" + Guid(CLSID_CantoneseIME);
        const std::wstring tip_key = L"Software\\Microsoft\\CTF\\TIP\\" + Guid(CLSID_CantoneseIME);
        Snapshot(L"before_HKCU", HKEY_CURRENT_USER, class_key, tip_key);
        Snapshot(L"before_HKLM", HKEY_LOCAL_MACHINE, class_key, tip_key);
        const HRESULT initialized = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
        Log(L"CoInitializeEx", initialized);
        if (FAILED(initialized) && initialized != RPC_E_CHANGED_MODE) return 2;
        struct Cleanup { bool active; ~Cleanup() { if (active) CoUninitialize(); } } cleanup{SUCCEEDED(initialized)};
        Com<ITfInputProcessorProfiles> legacy;
        Com<ITfInputProcessorProfileMgr> modern;
        Com<ITfCategoryMgr> categories;
        HRESULT result = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
            IID_ITfInputProcessorProfiles, reinterpret_cast<void**>(&legacy.value));
        Log(L"CoCreateInstance_legacy_profiles", result); if (FAILED(result)) return 2;
        result = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
            IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&modern.value));
        Log(L"CoCreateInstance_profile_manager", result); if (FAILED(result)) return 2;
        result = CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
            IID_ITfCategoryMgr, reinterpret_cast<void**>(&categories.value));
        Log(L"CoCreateInstance_category_manager", result); if (FAILED(result)) return 2;
        LogProfile(modern.value, language, L"profile_before");
        if (action == L"inspect") return 0;
        if (dll.empty()) { Log(L"arguments", E_INVALIDARG, L"--dll is required for registration probes"); return 2; }
        result = CheckComBinding(class_key, dll);
        Log(L"existing_com_binding_guard", result); if (FAILED(result)) return 2;
        for (HKEY hive : {HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE}) {
            bool exists = false; result = Exists(hive, tip_key, exists);
            if (FAILED(result) || exists) { Log(L"absent_prior_tip_guard", FAILED(result) ? result : HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)); return 2; }
        }
        if (action == L"register-legacy") {
            result = legacy.value->Register(CLSID_CantoneseIME);
            Log(L"ITfInputProcessorProfiles_Register", result);
            if (SUCCEEDED(result)) {
                result = legacy.value->AddLanguageProfile(CLSID_CantoneseIME, language, GUID_CantoneseProfile,
                    kProductName, static_cast<ULONG>(std::wcslen(kProductName)), nullptr, 0, 0);
                Log(L"ITfInputProcessorProfiles_AddLanguageProfile", result);
            }
        } else {
            result = modern.value->RegisterProfile(CLSID_CantoneseIME, language, GUID_CantoneseProfile,
                kProductName, static_cast<ULONG>(std::wcslen(kProductName)), nullptr, 0, 0, nullptr, 0, FALSE, 0);
            Log(L"ITfInputProcessorProfileMgr_RegisterProfile_persistent", result);
        }
        if (SUCCEEDED(result)) {
            for (unsigned i = 0; i < 3; ++i) {
                result = categories.value->RegisterCategory(CLSID_CantoneseIME, *kCategories[i], CLSID_CantoneseIME);
                Log((L"ITfCategoryMgr_RegisterCategory_" + std::wstring(kCategoryNames[i])).c_str(), result);
                if (FAILED(result)) break;
            }
        }
        if (SUCCEEDED(result)) {
            result = legacy.value->EnableLanguageProfile(CLSID_CantoneseIME, language, GUID_CantoneseProfile, TRUE);
            Log(L"ITfInputProcessorProfiles_EnableLanguageProfile_current_user", result);
        }
        const HRESULT outcome = result;
        LogProfile(modern.value, language, L"profile_after_attempt");
        if (FAILED(outcome)) Rollback(legacy.value, categories.value, language);
        Snapshot(L"after_HKCU", HKEY_CURRENT_USER, class_key, tip_key);
        Snapshot(L"after_HKLM", HKEY_LOCAL_MACHINE, class_key, tip_key);
        Log(L"outcome", outcome, L"No default input method, language pack or user files changed");
        return FAILED(outcome) ? 2 : 0;
    } catch (...) { Log(L"exception", E_FAIL); return 2; }
}
