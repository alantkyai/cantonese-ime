// Uses only an explicit disposable fixture directory and hidden native windows.
// Does not read the user's appearance settings, learning data, or input state.
#include "../candidate_appearance.h"
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
    assert(!app.SetForApp({CandidateTheme::Dark, 95, static_cast<CandidateOrientation>(77)}));
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

    // Native menu construction/commands use only this disposable INI. Building
    // the menu never shows it, takes focus, or reads real user preferences.
    HWND menu_foreground = GetForegroundWindow();
    assert(app.ApplyMenuCommand(401));
    assert(app.Current().orientation == CandidateOrientation::Vertical);
    CandidateAppearance reopened(path, game);
    assert((reopened.Current() == AppearanceSettings{CandidateTheme::Light,90,CandidateOrientation::Vertical}));
    assert(appearance_detail::Read(path).find("layout=vertical") != std::string::npos);
    other.Reload(); assert(other.Current().orientation == CandidateOrientation::Horizontal);
    HMENU menu = reopened.BuildMenu(); assert(menu);
    HMENU layouts = GetSubMenu(menu, 4); assert(layouts && GetMenuItemCount(layouts) == 2);
    wchar_t label[64]{};
    assert(GetMenuStringW(menu, 4, label, 64, MF_BYPOSITION) > 0 && std::wstring(label) == L"Layout");
    assert(GetMenuStringW(layouts, 400, label, 64, MF_BYCOMMAND) > 0 && std::wstring(label) == L"Horizontal");
    assert(GetMenuStringW(layouts, 401, label, 64, MF_BYCOMMAND) > 0 && std::wstring(label) == L"Vertical");
    assert(!(GetMenuState(layouts, 400, MF_BYCOMMAND) & MF_CHECKED));
    assert(GetMenuState(layouts, 401, MF_BYCOMMAND) & MF_CHECKED);
    assert(DestroyMenu(menu) && GetForegroundWindow() == menu_foreground);
    assert(app.ApplyMenuCommand(100) && app.ApplyMenuCommand(202));
    assert((app.Current() == AppearanceSettings{CandidateTheme::Dark,90,CandidateOrientation::Vertical}));
    assert(!app.ApplyMenuCommand(0) && !app.ApplyMenuCommand(402));
    assert(app.ApplyMenuCommand(400));
    assert(app.Current().orientation == CandidateOrientation::Horizontal);
    assert(app.ApplyMenuCommand(300) && !app.HasAppOverride());
    assert((app.Current() == AppearanceSettings{CandidateTheme::Light,90}));

    const auto inheritance = appearance_detail::Parse("[global]\nlayout=vertical\n[" + game_key + "]\ntheme=light\n");
    assert(inheritance.global.orientation == CandidateOrientation::Vertical);
    assert(inheritance.applications.at(game_key).orientation == CandidateOrientation::Vertical);
    const auto roundtrip = appearance_detail::Parse(appearance_detail::Serialize(inheritance));
    assert(roundtrip.global == inheritance.global && roundtrip.applications.at(game_key) == inheritance.applications.at(game_key));
    assert(appearance_detail::Parse("[global]\nlayout=invalid\n").global.orientation == CandidateOrientation::Horizontal);

    Fixture(path, "[global]\ntheme=evil\nopacity=-1\n[" + game_key + "]\nopacity=101\ntheme=unrecognised\n[app-../bad]\ntheme=light\n");
    app.Reload(); assert((app.Current() == AppearanceSettings{CandidateTheme::Dark,95}));
    const auto malformed = appearance_detail::Parse("[global]\ntheme=system\nopacity=0\n[" + game_key + "]\nopacity=85\n");
    assert(malformed.global.theme == CandidateTheme::System && malformed.global.opacity_percent == 95);
    assert(malformed.applications.at(game_key).opacity_percent == 85);
    assert(appearance_detail::Parse(std::string(65537, 'a')).applications.empty());
    assert(appearance_detail::Parse(std::string("[global]\ntheme=light\0", 22)).global.theme == CandidateTheme::Dark);
    assert(appearance_detail::Parse("[app-000000000000000G]\ntheme=light\n").applications.empty());
    assert(PanelAlpha(100) == 255 && PanelAlpha(95) == 242 && PanelAlpha(90) == 230 && PanelAlpha(85) == 217);
    assert(PanelAlpha(5) == 242);
    const auto dark = ResolveAppearance({CandidateTheme::Dark,85}, false);
    assert(dark.background == RGB(32,33,36) && dark.text == RGB(244,244,244) && dark.alpha == 217 && !dark.high_contrast);
    const auto light = ResolveAppearance({CandidateTheme::Light,95}, false);
    assert(light.background == RGB(250,250,250) && light.alpha == 242);
    const auto high = ResolveAppearance({CandidateTheme::Dark,85,CandidateOrientation::Vertical}, true);
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
    std::cout << "{\"passed\":true,\"scope\":\"isolated app preferences, horizontal/vertical menu commands and persistence/inheritance/reset, validation/defaults, Windows high contrast, hidden layered window, no foreground activation\"}\n";
    return 0;
}
