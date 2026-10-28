#pragma once
// File model for the settings window: custom.txt phrases/spellings and the
// candidate font in appearance.ini. No UI here so the rules are testable.
// custom.txt parsing mirrors cantonese_ime/custom.py; edits rewrite only the
// lines they touch, so comments and unrecognized lines survive.
#include <windows.h>
#include <shlobj.h>
#include <string>
#include <vector>
#include "../tsf/candidate_appearance.h"

namespace cime::settings {
constexpr std::size_t kMaxCustomBytes = 256 * 1024;
constexpr std::size_t kMaxCustomLines = 5000;
constexpr std::size_t kMaxPhraseLength = 64;

enum class LineKind { Other, Phrase, Alias };
struct CustomLine {
    LineKind kind = LineKind::Other;
    std::wstring key, value; // Phrase: key -> text. Alias: spelling -> target.
    std::wstring raw;        // Exact text written back for this line.
};
struct CustomDocument { std::vector<CustomLine> lines; };

inline bool IsAsciiLower(wchar_t c) { return c >= L'a' && c <= L'z'; }
inline std::wstring AsciiLower(std::wstring value) {
    for (wchar_t& c : value) if (c >= L'A' && c <= L'Z') c = static_cast<wchar_t>(c - L'A' + L'a');
    return value;
}
inline std::wstring Trim(const std::wstring& value) {
    const auto first = value.find_first_not_of(L" \t\r\n");
    if (first == std::wstring::npos) return {};
    return value.substr(first, value.find_last_not_of(L" \t\r\n") - first + 1);
}
inline bool ValidLetters(const std::wstring& value, std::size_t maximum) {
    if (value.empty() || value.size() > maximum) return false;
    for (wchar_t c : value) if (!IsAsciiLower(c)) return false;
    return true;
}
// Input keys and spellings: 1-32 letters. Alias targets: 1-12 letters, either
// a Jyutping syllable or a spelling the IME already accepts.
inline bool ValidKey(const std::wstring& value) { return ValidLetters(value, 32); }
inline bool ValidTarget(const std::wstring& value) { return ValidLetters(value, 12); }
// A phrase containing '=' would be read back as a (likely invalid) spelling.
inline bool ValidPhrase(const std::wstring& value) {
    if (value.empty() || value.size() > kMaxPhraseLength || Trim(value) != value || value.find(L'=') != std::wstring::npos) return false;
    for (wchar_t c : value) if (c < 32 || c == 127) return false;
    return true;
}
inline std::wstring FormatPhrase(const std::wstring& key, const std::wstring& text) { return key + L" " + text; }
inline std::wstring FormatAlias(const std::wstring& spelling, const std::wstring& target) { return spelling + L" = " + target; }

inline CustomLine ClassifyLine(const std::wstring& raw) {
    CustomLine line; line.raw = raw;
    const std::wstring text = Trim(raw);
    if (text.empty() || text[0] == L'#') return line;
    const auto equals = text.find(L'=');
    if (equals != std::wstring::npos) {
        const std::wstring spelling = AsciiLower(Trim(text.substr(0, equals)));
        const std::wstring target = AsciiLower(Trim(text.substr(equals + 1)));
        if (ValidKey(spelling) && ValidTarget(target)) { line.kind = LineKind::Alias; line.key = spelling; line.value = target; }
        return line;
    }
    const auto split = text.find_first_of(L" \t");
    if (split == std::wstring::npos) return line;
    const std::wstring key = AsciiLower(text.substr(0, split));
    const std::wstring phrase = Trim(text.substr(split + 1));
    if (ValidKey(key) && ValidPhrase(phrase)) { line.kind = LineKind::Phrase; line.key = key; line.value = phrase; }
    return line;
}

inline std::wstring Utf8ToWide(const std::string& value) {
    if (value.empty()) return {};
    const int count = MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0);
    if (count <= 0) return {};
    std::wstring result(count, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), result.data(), count);
    return result;
}
inline std::string WideToUtf8(const std::wstring& value) { return cime::ui::appearance_detail::WideToUtf8(value); }

inline CustomDocument ParseCustom(std::string text) {
    CustomDocument document;
    if (text.compare(0, 3, "\xEF\xBB\xBF") == 0) text.erase(0, 3);
    const std::wstring wide = Utf8ToWide(text);
    std::size_t start = 0;
    while (start < wide.size()) {
        auto end = wide.find(L'\n', start);
        if (end == std::wstring::npos) end = wide.size();
        std::wstring raw = wide.substr(start, end - start);
        if (!raw.empty() && raw.back() == L'\r') raw.pop_back();
        document.lines.push_back(ClassifyLine(raw));
        start = end + 1;
    }
    return document;
}
inline std::string SerializeCustom(const CustomDocument& document) {
    std::wstring text;
    for (const auto& line : document.lines) { text += line.raw; text += L"\r\n"; }
    return WideToUtf8(text);
}
inline std::vector<std::size_t> Entries(const CustomDocument& document, LineKind kind) {
    std::vector<std::size_t> result;
    for (std::size_t i = 0; i < document.lines.size(); ++i) if (document.lines[i].kind == kind) result.push_back(i);
    return result;
}
inline bool HasEntry(const CustomDocument& document, LineKind kind, const std::wstring& key, const std::wstring& value,
                     std::size_t ignore = static_cast<std::size_t>(-1)) {
    for (std::size_t i = 0; i < document.lines.size(); ++i)
        if (i != ignore && document.lines[i].kind == kind && document.lines[i].key == key && document.lines[i].value == value) return true;
    return false;
}
inline CustomLine MakeEntry(LineKind kind, const std::wstring& key, const std::wstring& value) {
    CustomLine line; line.kind = kind; line.key = key; line.value = value;
    line.raw = kind == LineKind::Phrase ? FormatPhrase(key, value) : FormatAlias(key, value);
    return line;
}
// A new entry follows the last entry of its kind, keeping phrases and
// spellings grouped. With none yet, it goes at the end under a short header.
inline std::size_t AddEntry(CustomDocument& document, LineKind kind, const std::wstring& key, const std::wstring& value) {
    const auto existing = Entries(document, kind);
    if (!existing.empty()) {
        const std::size_t at = existing.back() + 1;
        document.lines.insert(document.lines.begin() + static_cast<std::ptrdiff_t>(at), MakeEntry(kind, key, value));
        return at;
    }
    while (!document.lines.empty() && Trim(document.lines.back().raw).empty()) document.lines.pop_back();
    if (!document.lines.empty()) document.lines.push_back(CustomLine{});
    CustomLine header;
    header.raw = kind == LineKind::Phrase ? L"# Phrases: input text" : L"# Spellings: spelling = syllable";
    document.lines.push_back(header);
    document.lines.push_back(MakeEntry(kind, key, value));
    return document.lines.size() - 1;
}
inline void UpdateEntry(CustomDocument& document, std::size_t index, const std::wstring& key, const std::wstring& value) {
    document.lines[index] = MakeEntry(document.lines[index].kind, key, value);
}
inline void RemoveEntry(CustomDocument& document, std::size_t index) {
    document.lines.erase(document.lines.begin() + static_cast<std::ptrdiff_t>(index));
}
inline bool WithinCustomLimits(const CustomDocument& document) {
    return document.lines.size() <= kMaxCustomLines && SerializeCustom(document).size() <= kMaxCustomBytes;
}

// Global font change applied to a freshly read appearance document. App
// sections store full copies, so a section still holding the old global font
// was inheriting it and follows; a deliberately different font is kept.
inline void ApplyGlobalFont(cime::ui::appearance_detail::Document& document, const std::wstring& family, int size) {
    const auto old_family = document.global.font_family;
    const int old_size = document.global.font_size;
    document.global.font_family = family; document.global.font_size = size;
    for (auto& entry : document.applications) {
        if (entry.second.font_family == old_family) entry.second.font_family = family;
        if (entry.second.font_size == old_size) entry.second.font_size = size;
    }
}

inline std::wstring UserDataPath(const wchar_t* name) {
    wchar_t base[MAX_PATH]{};
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA, nullptr, SHGFP_TYPE_CURRENT, base))) return {};
    return std::wstring(base) + L"\\CantoneseIME\\" + name;
}
// Plain-file read/atomic write with the same reparse-point and size refusals
// as the appearance store, but sized for custom.txt.
inline bool ReadUserFile(const std::wstring& path, std::size_t maximum, std::string& output) {
    output.clear();
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (file == INVALID_HANDLE_VALUE) return GetLastError() == ERROR_FILE_NOT_FOUND || GetLastError() == ERROR_PATH_NOT_FOUND;
    LARGE_INTEGER size{}; bool ok = false;
    if (cime::ui::appearance_detail::PlainFile(file) && GetFileSizeEx(file, &size) && size.QuadPart >= 0
            && static_cast<unsigned long long>(size.QuadPart) <= maximum) {
        output.resize(static_cast<std::size_t>(size.QuadPart)); DWORD count = 0;
        ok = output.empty() || (ReadFile(file, output.data(), static_cast<DWORD>(output.size()), &count, nullptr) && count == output.size());
    }
    CloseHandle(file);
    if (!ok) output.clear();
    return ok;
}
inline bool WriteUserFile(const std::wstring& path, const std::string& text, std::size_t maximum) {
    if (path.empty() || text.size() > maximum) return false;
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
    const bool written = (text.empty() || WriteFile(file, text.data(), static_cast<DWORD>(text.size()), &count, nullptr))
        && count == text.size() && FlushFileBuffers(file);
    CloseHandle(file);
    const bool replaced = written && MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    if (!replaced) DeleteFileW(temporary.c_str());
    return replaced;
}

// Same cross-process lock the candidate panel's menu uses for appearance.ini.
class AppearanceLock {
public:
    explicit AppearanceLock(const std::wstring& path, DWORD wait_ms = 2000) {
        const std::string key = cime::ui::AppearanceHostKey(path);
        if (key.empty()) return;
        mutex_ = CreateMutexW(nullptr, FALSE, (L"Local\\CantoneseIME.Appearance." + std::wstring(key.begin(), key.end())).c_str());
        if (!mutex_) return;
        const DWORD waited = WaitForSingleObject(mutex_, wait_ms);
        held_ = waited == WAIT_OBJECT_0 || waited == WAIT_ABANDONED;
    }
    ~AppearanceLock() { if (held_) ReleaseMutex(mutex_); if (mutex_) CloseHandle(mutex_); }
    AppearanceLock(const AppearanceLock&) = delete;
    AppearanceLock& operator=(const AppearanceLock&) = delete;
    bool Held() const { return held_; }
private:
    HANDLE mutex_ = nullptr;
    bool held_ = false;
};

inline bool SaveGlobalFont(const std::wstring& path, const std::wstring& family, int size) {
    if (!cime::ui::ValidFontFamily(family) || !cime::ui::ValidFontSize(size)) return false;
    AppearanceLock lock(path);
    if (!lock.Held()) return false;
    std::string text;
    if (!ReadUserFile(path, cime::ui::appearance_detail::kMaxSettingsBytes, text)) return false;
    auto document = cime::ui::appearance_detail::Parse(text);
    ApplyGlobalFont(document, family, size);
    return cime::ui::appearance_detail::WriteAtomic(path, cime::ui::appearance_detail::Serialize(document));
}
} // namespace cime::settings
