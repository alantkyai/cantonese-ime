#pragma once
// Per-host candidate panel preferences. Never called from DllMain, never
// changes the host's theme/DPI policy, and never opens the learning store.
#include <windows.h>
#include <shlobj.h>
#include <cstdint>
#include <cwctype>
#include <map>
#include <sstream>
#include <string>
#include <utility>

namespace cime::ui {
enum class CandidateTheme { Dark, Light, System };
struct AppearanceSettings {
    AppearanceSettings() = default;
    AppearanceSettings(CandidateTheme theme_value, int opacity_value, std::wstring family = {}, int size = 0)
        : theme(theme_value), opacity_percent(opacity_value), font_family(std::move(family)), font_size(size) {}
    CandidateTheme theme = CandidateTheme::Dark;
    int opacity_percent = 95;
    std::wstring font_family; // Empty: bundled font, then the built-in fallbacks.
    int font_size = 0;        // Logical pixels before DPI scaling; 0: default.
    bool prediction = false;  // Learned next-word suggestions; off unless chosen.
};
inline bool operator==(const AppearanceSettings& a, const AppearanceSettings& b) {
    return a.theme == b.theme && a.opacity_percent == b.opacity_percent
        && a.font_family == b.font_family && a.font_size == b.font_size && a.prediction == b.prediction;
}
struct AppearancePalette {
    COLORREF background, text, highlight, highlight_text, border;
    BYTE alpha;
    bool high_contrast;
};

inline bool ValidPanelOpacity(int value) { return value == 100 || value == 95 || value == 90 || value == 85; }
inline bool ValidFontSize(int value) { return value == 0 || (value >= 10 && value <= 48); }
// A GDI face name is shorter than LF_FACESIZE and has no control characters.
inline bool ValidFontFamily(const std::wstring& value) {
    if (value.size() >= LF_FACESIZE) return false;
    for (wchar_t c : value) if (c < 32 || c == 127) return false;
    return true;
}
inline BYTE PanelAlpha(int value) {
    return static_cast<BYTE>(((ValidPanelOpacity(value) ? value : 95) * 255 + 50) / 100);
}
inline std::wstring AppearanceHostPath() {
    std::wstring path(32768, L'\0');
    const DWORD count = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    if (!count || count >= path.size()) return {};
    path.resize(count); return path;
}
inline std::string AppearanceHostKey(std::wstring path) {
    if (path.empty()) return {};
    // Hash UTF-16 bytes, not std::hash (whose result can vary by toolchain).
    // Invariant lower casing and separators make case-only spelling stable.
    for (wchar_t& c : path) if (c == L'/') c = L'\\';
    std::wstring lower(path.size(), L'\0');
    if (!LCMapStringEx(LOCALE_NAME_INVARIANT, LCMAP_LOWERCASE, path.data(), static_cast<int>(path.size()),
            lower.data(), static_cast<int>(lower.size()), nullptr, nullptr, 0)) return {};
    std::uint64_t hash = 14695981039346656037ull;
    for (wchar_t c : lower) {
        hash ^= static_cast<unsigned>(c) & 255; hash *= 1099511628211ull;
        hash ^= (static_cast<unsigned>(c) >> 8) & 255; hash *= 1099511628211ull;
    }
    constexpr char digits[] = "0123456789abcdef";
    std::string key(20, '0'); key.replace(0, 4, "app-");
    for (unsigned i = 0; i < 16; ++i) key[4 + i] = digits[(hash >> ((15 - i) * 4)) & 15];
    return key;
}
inline std::wstring AppearanceSettingsPath() {
    wchar_t base[MAX_PATH]{};
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA, nullptr, SHGFP_TYPE_CURRENT, base))) return {};
    return std::wstring(base) + L"\\CantoneseIME\\appearance.ini";
}
inline AppearancePalette ResolveAppearance(const AppearanceSettings& settings, bool high_contrast) {
    if (high_contrast || settings.theme == CandidateTheme::System)
        return {GetSysColor(COLOR_WINDOW), GetSysColor(COLOR_WINDOWTEXT), GetSysColor(COLOR_HIGHLIGHT),
            GetSysColor(COLOR_HIGHLIGHTTEXT), GetSysColor(COLOR_3DSHADOW),
            high_contrast ? static_cast<BYTE>(255) : PanelAlpha(settings.opacity_percent), high_contrast};
    if (settings.theme == CandidateTheme::Light)
        return {RGB(250,250,250), RGB(32,33,36), RGB(218,231,249), RGB(18,45,80), RGB(195,198,204),
            PanelAlpha(settings.opacity_percent), false};
    return {RGB(32,33,36), RGB(244,244,244), RGB(54,83,120), RGB(255,255,255), RGB(80,83,90),
        PanelAlpha(settings.opacity_percent), false};
}

namespace appearance_detail {
constexpr DWORD kMaxSettingsBytes = 65536;
constexpr std::size_t kMaxApplications = 256;
struct Document {
    AppearanceSettings global;
    std::map<std::string, AppearanceSettings> applications;
};
inline std::string Trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    return value.substr(first, value.find_last_not_of(" \t\r\n") - first + 1);
}
inline bool ValidKey(const std::string& value) {
    if (value.size() != 20 || value.compare(0, 4, "app-")) return false;
    for (std::size_t i = 4; i < value.size(); ++i)
        if (!(value[i] >= '0' && value[i] <= '9') && !(value[i] >= 'a' && value[i] <= 'f')) return false;
    return true;
}
inline std::wstring Utf8ToWide(const std::string& value) {
    if (value.empty() || value.size() > 1024) return {};
    const int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0);
    if (count <= 0) return {};
    std::wstring result(count, L'\0');
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), result.data(), count)) return {};
    return result;
}
inline std::string WideToUtf8(const std::wstring& value) {
    if (value.empty()) return {};
    const int count = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    if (count <= 0) return {};
    std::string result(count, '\0');
    if (!WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), result.data(), count, nullptr, nullptr)) return {};
    return result;
}
inline void ApplyField(AppearanceSettings& settings, const std::string& key, const std::string& value) {
    if (key == "font") {
        // An empty value restores the default; an invalid name is ignored.
        const std::wstring family = Utf8ToWide(value);
        if (value.empty() || (!family.empty() && ValidFontFamily(family))) settings.font_family = family;
    } else if (key == "font_size") {
        if (!value.empty() && value.size() <= 2 && value.find_first_not_of("0123456789") == std::string::npos) {
            const int size = std::stoi(value);
            if (ValidFontSize(size)) settings.font_size = size;
        }
    } else if (key == "prediction") {
        if (value == "on") settings.prediction = true;
        else if (value == "off") settings.prediction = false;
    } else if (key == "theme") {
        if (value == "dark") settings.theme = CandidateTheme::Dark;
        else if (value == "light") settings.theme = CandidateTheme::Light;
        else if (value == "system") settings.theme = CandidateTheme::System;
    } else if (key == "opacity") {
        if (value == "100") settings.opacity_percent = 100;
        else if (value == "95") settings.opacity_percent = 95;
        else if (value == "90") settings.opacity_percent = 90;
        else if (value == "85") settings.opacity_percent = 85;
    }
}
inline Document Parse(const std::string& text) {
    Document output;
    if (text.size() > kMaxSettingsBytes || text.find('\0') != std::string::npos) return output;
    std::map<std::string, std::map<std::string, std::string>> sections;
    // Notepad may save a hand-edited file with a UTF-8 byte order mark.
    std::istringstream input(text.compare(0, 3, "\xEF\xBB\xBF") ? text : text.substr(3)); std::string line, section;
    while (std::getline(input, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == ';' || line[0] == '#') continue;
        if (line.front() == '[' && line.back() == ']') {
            section = line.substr(1, line.size() - 2);
            if (section != "global" && !ValidKey(section)) section.clear();
            continue;
        }
        const auto equals = line.find('=');
        if (section.empty() || equals == std::string::npos) continue;
        const std::string key = Trim(line.substr(0, equals));
        if (key != "theme" && key != "opacity" && key != "font" && key != "font_size" && key != "prediction") continue;
        if (sections.size() >= kMaxApplications + 1 && !sections.count(section)) continue;
        sections[section][key] = Trim(line.substr(equals + 1));
    }
    const auto global = sections.find("global");
    if (global != sections.end()) for (const auto& field : global->second) ApplyField(output.global, field.first, field.second);
    for (const auto& entry : sections) if (ValidKey(entry.first) && output.applications.size() < kMaxApplications) {
        AppearanceSettings value = output.global;
        for (const auto& field : entry.second) ApplyField(value, field.first, field.second);
        output.applications.emplace(entry.first, value);
    }
    return output;
}
inline const char* ThemeName(CandidateTheme theme) {
    switch (theme) { case CandidateTheme::Light: return "light"; case CandidateTheme::System: return "system"; default: return "dark"; }
}
inline std::string Serialize(const Document& document) {
    std::ostringstream output;
    output << "; Cantonese IME candidate panel. App identifiers are hashed executable paths.\r\n";
    const auto write = [&output](const std::string& section, const AppearanceSettings& value) {
        output << '[' << section << "]\r\ntheme=" << ThemeName(value.theme) << "\r\nopacity="
            << (ValidPanelOpacity(value.opacity_percent) ? value.opacity_percent : 95) << "\r\n";
        // Keep hand-edited font choices when a menu change rewrites the file.
        if (!value.font_family.empty() && ValidFontFamily(value.font_family))
            output << "font=" << WideToUtf8(value.font_family) << "\r\n";
        if (value.font_size && ValidFontSize(value.font_size)) output << "font_size=" << value.font_size << "\r\n";
        if (value.prediction) output << "prediction=on\r\n";
        output << "\r\n";
    };
    write("global", document.global);
    for (const auto& entry : document.applications) if (ValidKey(entry.first)) write(entry.first, entry.second);
    return output.str();
}
inline bool PlainFile(HANDLE file) {
    BY_HANDLE_FILE_INFORMATION info{};
    return GetFileInformationByHandle(file, &info) && !(info.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY));
}
inline std::string Read(const std::wstring& path) {
    if (path.empty()) return {};
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return {};
    LARGE_INTEGER size{}; std::string result;
    if (PlainFile(file) && GetFileSizeEx(file, &size) && size.QuadPart >= 0 && size.QuadPart <= kMaxSettingsBytes) {
        result.resize(static_cast<std::size_t>(size.QuadPart)); DWORD count = 0;
        if (!ReadFile(file, result.data(), static_cast<DWORD>(result.size()), &count, nullptr) || count != result.size()) result.clear();
    }
    CloseHandle(file); return result;
}
inline bool WriteAtomic(const std::wstring& path, const std::string& text) {
    if (path.empty() || text.size() > kMaxSettingsBytes) return false;
    const auto slash = path.find_last_of(L"\\/");
    if (slash == std::wstring::npos || slash == 0) return false;
    const std::wstring directory = path.substr(0, slash);
    if (!CreateDirectoryW(directory.c_str(), nullptr) && GetLastError() != ERROR_ALREADY_EXISTS) return false;
    const DWORD attributes = GetFileAttributesW(directory.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY) || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return false;
    const DWORD existing = GetFileAttributesW(path.c_str());
    if (existing != INVALID_FILE_ATTRIBUTES && (existing & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))) return false;
    const std::wstring temporary = path + L".tmp-" + std::to_wstring(GetCurrentProcessId()) + L"-" + std::to_wstring(GetTickCount64());
    HANDLE file = CreateFileW(temporary.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
        FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    DWORD count = 0;
    const bool written = PlainFile(file) && WriteFile(file, text.data(), static_cast<DWORD>(text.size()), &count, nullptr)
        && count == text.size() && FlushFileBuffers(file);
    CloseHandle(file);
    const bool replaced = written && MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    if (!replaced) DeleteFileW(temporary.c_str());
    return replaced;
}
} // namespace appearance_detail

class CandidateAppearance {
public:
    CandidateAppearance() : path_(AppearanceSettingsPath()), key_(AppearanceHostKey(AppearanceHostPath())) {}
    CandidateAppearance(std::wstring settings_path, std::wstring host_path)
        : path_(std::move(settings_path)), key_(AppearanceHostKey(std::move(host_path))) {}
    void Load() { if (!loaded_) Reload(); }
    void Reload() {
        const auto document = appearance_detail::Parse(appearance_detail::Read(path_));
        const auto found = document.applications.find(key_);
        current_ = found == document.applications.end() ? document.global : found->second;
        overridden_ = found != document.applications.end(); loaded_ = true;
    }
    AppearanceSettings Current() { Load(); return current_; }
    bool HasAppOverride() { Load(); return overridden_; }
    bool LastSaveSucceeded() const { return saved_; }
    const std::string& HostKey() const { return key_; }
    const std::wstring& SettingsPath() const { return path_; }
    AppearancePalette Effective() {
        Load(); HIGHCONTRASTW contrast{}; contrast.cbSize = sizeof(contrast);
        const bool high = SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof(contrast), &contrast, 0)
            && (contrast.dwFlags & HCF_HIGHCONTRASTON);
        return ResolveAppearance(current_, high);
    }
    bool Apply(HWND window) {
        if (!window || !IsWindow(window)) return false;
        const LONG_PTR style = GetWindowLongPtrW(window, GWL_EXSTYLE);
        if (!(style & WS_EX_LAYERED)) {
            SetLastError(ERROR_SUCCESS);
            if (!SetWindowLongPtrW(window, GWL_EXSTYLE, style | WS_EX_LAYERED) && GetLastError() != ERROR_SUCCESS) return false;
        }
        return SetLayeredWindowAttributes(window, 0, Effective().alpha, LWA_ALPHA) != FALSE;
    }
    bool SetForApp(AppearanceSettings settings) {
        if (!ValidPanelOpacity(settings.opacity_percent) || !ValidFontSize(settings.font_size)
            || !ValidFontFamily(settings.font_family)
            || (settings.theme != CandidateTheme::Dark && settings.theme != CandidateTheme::Light && settings.theme != CandidateTheme::System)) return false;
        Load(); current_ = settings; overridden_ = true;
        saved_ = Persist(false); return saved_;
    }
    bool ResetForApp() {
        saved_ = Persist(true);
        if (saved_) Reload();
        return saved_;
    }
    // A native context menu changes only this host application's panel. Text
    // says panel opacity because LWA_ALPHA affects the glyphs as well as the bg.
    // No SetForegroundWindow or host-window message routing is used.
    bool ShowMenu(HWND owner, POINT point) {
        Reload();
        HMENU menu = CreatePopupMenu(), themes = CreatePopupMenu(), opacity = CreatePopupMenu();
        if (!menu || !themes || !opacity) {
            if (menu) DestroyMenu(menu); if (themes) DestroyMenu(themes); if (opacity) DestroyMenu(opacity); return false;
        }
        AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, L"Candidate appearance for this app");
        AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
        const wchar_t* names[] = {L"Dark", L"Light", L"Windows system colors"};
        for (UINT i = 0; i < 3; ++i) AppendMenuW(themes, MF_STRING | (static_cast<UINT>(current_.theme) == i ? MF_CHECKED : 0), 100 + i, names[i]);
        const int levels[] = {100, 95, 90, 85};
        for (UINT i = 0; i < 4; ++i) {
            const std::wstring label = std::to_wstring(levels[i]) + L"%";
            AppendMenuW(opacity, MF_STRING | (current_.opacity_percent == levels[i] ? MF_CHECKED : 0), 200 + i, label.c_str());
        }
        AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(themes), L"Background");
        AppendMenuW(menu, MF_POPUP, reinterpret_cast<UINT_PTR>(opacity), L"Panel opacity");
        AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
        AppendMenuW(menu, MF_STRING | (overridden_ ? 0 : MF_GRAYED), 300, L"Reset appearance for this app");
        const bool settings = !settings_exe_.empty() && GetFileAttributesW(settings_exe_.c_str()) != INVALID_FILE_ATTRIBUTES;
        if (settings) {
            AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
            AppendMenuW(menu, MF_STRING, 400, L"Custom phrases, spellings and font...");
        }
        if (Effective().high_contrast) AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, L"High contrast: Windows colors, 100% opacity");
        if (!saved_) AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, L"Previous change could not be saved");
        HWND temporary = nullptr;
        if (!owner || !IsWindow(owner)) {
            temporary = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, L"STATIC", L"Cantonese IME appearance",
                WS_POPUP, 0, 0, 0, 0, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
            owner = temporary;
        }
        const UINT command = owner ? TrackPopupMenuEx(menu, TPM_NONOTIFY | TPM_RETURNCMD | TPM_RIGHTBUTTON,
            point.x, point.y, owner, nullptr) : 0;
        DestroyMenu(menu); if (temporary) DestroyWindow(temporary);
        if (command == 300) { ResetForApp(); return true; }
        if (command == 400 && settings) { LaunchSettings(); return true; }
        AppearanceSettings next = current_;
        if (command >= 100 && command < 103) next.theme = static_cast<CandidateTheme>(command - 100);
        else if (command >= 200 && command < 204) next.opacity_percent = levels[command - 200];
        else return false;
        SetForApp(next); return true;
    }
    // The separate settings EXE beside the service DLL. It runs as its own
    // process, so no dialog opens inside the host; a sandboxed host that may
    // not create processes simply gets nothing.
    void SetSettingsExecutable(std::wstring path) { settings_exe_ = std::move(path); }
    bool LaunchSettings() const {
        if (settings_exe_.empty()) return false;
        STARTUPINFOW startup{}; startup.cb = sizeof(startup);
        PROCESS_INFORMATION process{};
        std::wstring command = L"\"" + settings_exe_ + L"\"";
        if (!CreateProcessW(settings_exe_.c_str(), command.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &startup, &process)) return false;
        CloseHandle(process.hThread); CloseHandle(process.hProcess);
        return true;
    }
private:
    bool Persist(bool reset) {
        if (path_.empty() || key_.empty()) return false;
        // Cross-process edits reread inside the lock so one app cannot erase
        // another app's most recent choice. Never wait while typing/gameplay.
        const std::string mutex_key = AppearanceHostKey(path_);
        const std::wstring mutex_name = L"Local\\CantoneseIME.Appearance." + std::wstring(mutex_key.begin(), mutex_key.end());
        HANDLE mutex = CreateMutexW(nullptr, FALSE, mutex_name.c_str());
        if (!mutex) return false;
        const DWORD waited = WaitForSingleObject(mutex, 0);
        if (waited != WAIT_OBJECT_0 && waited != WAIT_ABANDONED) { CloseHandle(mutex); return false; }
        auto document = appearance_detail::Parse(appearance_detail::Read(path_));
        if (reset) document.applications.erase(key_);
        else if (document.applications.count(key_) || document.applications.size() < appearance_detail::kMaxApplications)
            document.applications[key_] = current_;
        else { ReleaseMutex(mutex); CloseHandle(mutex); return false; }
        const bool result = appearance_detail::WriteAtomic(path_, appearance_detail::Serialize(document));
        ReleaseMutex(mutex); CloseHandle(mutex); return result;
    }
    std::wstring path_, settings_exe_;
    std::string key_;
    AppearanceSettings current_;
    bool loaded_ = false, overridden_ = false, saved_ = true;
};
} // namespace cime::ui
