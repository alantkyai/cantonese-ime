// Uses only an explicit disposable fixture directory and hidden native windows.
// Does not read the user's appearance settings, learning data, or input state.
#include "../candidate_appearance.h"
#include "../candidate_font.h"
#include <cassert>
#include <iostream>

namespace {
std::wstring Join(const std::wstring& parent, const wchar_t* child) { return parent + L"\\" + child; }
void Fixture(const std::wstring& path, const std::string& text) { assert(cime::ui::appearance_detail::WriteAtomic(path, text)); }
void ReadAlpha(HWND window, BYTE expected) {
    BYTE alpha = 0; DWORD flags = 0; COLORREF key = 0;
    assert(GetLayeredWindowAttributes(window, &key, &alpha, &flags));
    assert(alpha == expected && flags == LWA_ALPHA);
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    using namespace cime::ui;
    assert(argc == 2);
    const std::wstring directory = argv[1];
    assert(CreateDirectoryW(directory.c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS);
    const std::wstring path = Join(directory, L"appearance.ini");
    assert(GetFileAttributesW(path.c_str()) == INVALID_FILE_ATTRIBUTES); // fresh fixture only
    const std::wstring game = L"C:\\Games\\Client.exe", editor = L"C:\\Tools\\Editor.exe";
    const std::string game_key = AppearanceHostKey(game), editor_key = AppearanceHostKey(editor);
    assert(game_key == AppearanceHostKey(L"c:/games/CLIENT.EXE"));
    assert(game_key != editor_key && game_key.size() == 20 && AppearanceHostKey(L"").empty());
    assert(!AppearanceHostPath().empty());
    CandidateAppearance app(path, game);
    assert((app.Current() == AppearanceSettings{CandidateTheme::Dark, 95}) && !app.HasAppOverride());
    assert(GetFileAttributesW(path.c_str()) == INVALID_FILE_ATTRIBUTES); // load does not create settings
    assert(!app.SetForApp({CandidateTheme::Dark, 0}));
    assert(!app.SetForApp({static_cast<CandidateTheme>(77), 95}));
    assert(GetFileAttributesW(path.c_str()) == INVALID_FILE_ATTRIBUTES);

    Fixture(path, "[global]\ntheme=light\nopacity=90\n[" + game_key + "]\ntheme=system\nopacity=85\n");
    app.Reload(); assert((app.Current() == AppearanceSettings{CandidateTheme::System,85}) && app.HasAppOverride());
    CandidateAppearance other(path, editor);
    assert((other.Current() == AppearanceSettings{CandidateTheme::Light,90}) && !other.HasAppOverride());
    assert(app.SetForApp({CandidateTheme::Dark,95}));
    assert(other.SetForApp({CandidateTheme::Light,100}));
    app.Reload(); assert((app.Current() == AppearanceSettings{CandidateTheme::Dark,95}));
    assert(app.ResetForApp() && !app.HasAppOverride());
    assert((app.Current() == AppearanceSettings{CandidateTheme::Light,90}));
    other.Reload(); assert((other.Current() == AppearanceSettings{CandidateTheme::Light,100}));
    assert(appearance_detail::Read(path).find(game_key) == std::string::npos);
    assert(appearance_detail::Read(path).find("C:\\Games") == std::string::npos);

    Fixture(path, "[global]\ntheme=evil\nopacity=-1\n[" + game_key + "]\nopacity=101\ntheme=unrecognised\n[app-../bad]\ntheme=light\n");
    app.Reload(); assert((app.Current() == AppearanceSettings{CandidateTheme::Dark,95}));
    const auto malformed = appearance_detail::Parse("[global]\ntheme=system\nopacity=0\n[" + game_key + "]\nopacity=85\n");
    assert(malformed.global.theme == CandidateTheme::System && malformed.global.opacity_percent == 95);
    assert(malformed.applications.at(game_key).opacity_percent == 85);
    assert(appearance_detail::Parse(std::string(65537, 'a')).applications.empty());
    assert(appearance_detail::Parse(std::string("[global]\ntheme=light\0", 22)).global.theme == CandidateTheme::Dark);
    assert(appearance_detail::Parse("[app-000000000000000G]\ntheme=light\n").applications.empty());
    // Hand-edited font choices: UTF-8 names, size bounds, app inheritance, BOM.
    const std::string jhenghei_utf8 = "\xE5\xBE\xAE\xE8\xBB\x9F\xE6\xAD\xA3\xE9\xBB\x91\xE9\xAB\x94";
    const std::wstring jhenghei_local = L"微軟正黑體";
    const auto fonts = appearance_detail::Parse("\xEF\xBB\xBF[global]\nfont= Segoe UI \nfont_size=24\n[" + game_key
        + "]\nfont=" + jhenghei_utf8 + "\nfont_size=99\n[" + editor_key + "]\nfont=" + std::string(40, 'x') + "\nfont_size=9\n");
    assert(fonts.global.font_family == L"Segoe UI" && fonts.global.font_size == 24);
    assert(fonts.applications.at(game_key).font_family == jhenghei_local && fonts.applications.at(game_key).font_size == 24);
    assert(fonts.applications.at(editor_key).font_family == L"Segoe UI" && fonts.applications.at(editor_key).font_size == 24);
    assert(appearance_detail::Parse("[global]\nfont=Segoe UI\nfont=\n").global.font_family.empty());
    assert(appearance_detail::Parse("[global]\nfont_size=-5\nfont_size=4x\n").global.font_size == 0);
    assert(appearance_detail::Parse("[global]\nfont=bad\xff\n").global.font_family.empty());
    // Learned suggestions are off unless explicitly on; unknown values are ignored.
    assert(!appearance_detail::Parse("[global]\ntheme=dark\n").global.prediction);
    assert(appearance_detail::Parse("[global]\nprediction=on\n").global.prediction);
    assert(!appearance_detail::Parse("[global]\nprediction=on\nprediction=maybe\nprediction=off\n").global.prediction);
    assert(appearance_detail::Serialize(appearance_detail::Parse("[global]\nprediction=on\n")).find("prediction=on") != std::string::npos);
    // A menu change rewrites the file and must keep the hand-edited font lines.
    Fixture(path, "[global]\ntheme=dark\nfont=" + jhenghei_utf8 + "\nfont_size=28\n");
    app.Reload();
    AppearanceSettings themed = app.Current(); themed.theme = CandidateTheme::Light;
    assert(app.SetForApp(themed));
    app.Reload();
    assert(app.Current().font_family == jhenghei_local && app.Current().font_size == 28 && app.Current().theme == CandidateTheme::Light);
    other.Reload(); assert(other.Current().font_family == jhenghei_local && other.Current().theme == CandidateTheme::Dark);
    assert(appearance_detail::Read(path).find("font=" + jhenghei_utf8) != std::string::npos);
    themed.font_size = 9; assert(!app.SetForApp(themed));
    assert(app.ResetForApp());
    // User font resolution: an installed face (English or localized name) wins;
    // an absent face falls back to the existing order instead of substitution.
    {
        HDC dc = CreateCompatibleDC(nullptr); assert(dc);
        const auto face = [dc](HFONT font) {
            HGDIOBJ previous = SelectObject(dc, font); wchar_t name[LF_FACESIZE]{};
            GetTextFaceW(dc, LF_FACESIZE, name); SelectObject(dc, previous); return std::wstring(name);
        };
        HFONT segoe = CreateCandidateFont(dc, 96, nullptr, 24, L"Segoe UI"); assert(segoe);
        LOGFONTW specification{}; assert(GetObjectW(segoe, sizeof(specification), &specification));
        assert(specification.lfHeight == -24 && face(segoe) == L"Segoe UI"); DeleteObject(segoe);
        assert(!TryUserCandidateFont(dc, 96, L"CantoneseMissingCandidateFont123", 20));
        assert(!TryUserCandidateFont(dc, 96, std::wstring(LF_FACESIZE, L'x').c_str(), 20));
        assert(!TryUserCandidateFont(dc, 96, L"Segoe UI", 0));
        HFONT fallback = CreateCandidateFont(dc, 96, nullptr, 20, L"CantoneseMissingCandidateFont123"); assert(fallback);
        assert(face(fallback) != L"CantoneseMissingCandidateFont123"); DeleteObject(fallback);
        if (HFONT english = TryUserCandidateFont(dc, 96, L"Microsoft JhengHei", 20)) {
            DeleteObject(english);
            HFONT localized = TryUserCandidateFont(dc, 96, jhenghei_local.c_str(), 20); assert(localized); DeleteObject(localized);
        }
        DeleteDC(dc);
    }

    assert(PanelAlpha(100) == 255 && PanelAlpha(95) == 242 && PanelAlpha(90) == 230 && PanelAlpha(85) == 217);
    assert(PanelAlpha(5) == 242);
    const auto dark = ResolveAppearance({CandidateTheme::Dark,85}, false);
    assert(dark.background == RGB(32,33,36) && dark.text == RGB(244,244,244) && dark.alpha == 217 && !dark.high_contrast);
    const auto light = ResolveAppearance({CandidateTheme::Light,95}, false);
    assert(light.background == RGB(250,250,250) && light.alpha == 242);
    const auto high = ResolveAppearance({CandidateTheme::Dark,85}, true);
    assert(high.background == GetSysColor(COLOR_WINDOW) && high.text == GetSysColor(COLOR_WINDOWTEXT));
    assert(high.highlight == GetSysColor(COLOR_HIGHLIGHT) && high.highlight_text == GetSysColor(COLOR_HIGHLIGHTTEXT));
    assert(high.high_contrast && high.alpha == 255);
    const auto system = ResolveAppearance({CandidateTheme::System,90}, false);
    assert(system.background == GetSysColor(COLOR_WINDOW) && system.alpha == 230 && !system.high_contrast);

    // The native API must preserve a nonactivating popup and accept every
    // opacity preset. The window is never shown and foreground is unchanged.
    HWND foreground = GetForegroundWindow();
    HWND window = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
        L"STATIC", L"Cantonese IME appearance test", WS_POPUP, 0, 0, 20, 20,
        nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    assert(window && !IsWindowVisible(window));
    for (int level : {100,95,90,85}) {
        assert(app.SetForApp({CandidateTheme::Dark,level}));
        assert(app.Apply(window));
        ReadAlpha(window, app.Effective().alpha);
        const LONG_PTR style = GetWindowLongPtrW(window, GWL_EXSTYLE);
        assert((style & WS_EX_NOACTIVATE) && (style & WS_EX_TOOLWINDOW) && (style & WS_EX_TOPMOST) && (style & WS_EX_LAYERED));
        assert(!IsWindowVisible(window) && GetForegroundWindow() == foreground);
    }
    assert(!app.Apply(nullptr));
    DestroyWindow(window);
    assert(GetForegroundWindow() == foreground);

    // A non-file target must never be treated as a settings file.
    const std::wstring blocked = Join(directory, L"blocked.ini");
    assert(CreateDirectoryW(blocked.c_str(), nullptr));
    CandidateAppearance cannot_write(blocked, game);
    assert(!cannot_write.SetForApp({CandidateTheme::Light,90}));
    assert(!cannot_write.LastSaveSucceeded());
    assert(appearance_detail::Read(blocked).empty());
    assert(RemoveDirectoryW(blocked.c_str()));
    assert(DeleteFileW(path.c_str()));
    assert(RemoveDirectoryW(directory.c_str()));
    std::cout << "{\"passed\":true,\"scope\":\"isolated app preferences, validation/defaults, atomic persistence/reset, Windows high contrast, native hidden layered window, no foreground activation\"}\n";
    return 0;
}
