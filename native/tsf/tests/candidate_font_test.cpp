// Actual x64 Windows GDI font-selection/measurement checks; no IME registration.
#include "../candidate_font.h"
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

#if defined(CIME_FONT_ANCHOR_FIXTURE)
// A loadable inert AMD64 fixture tests GetModuleFileNameW anchoring without
// registering or activating the project IME in any desktop process.
extern "C" BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) { return TRUE; }
#else
namespace {
class Surface {
public:
    HDC dc = nullptr;
    HBITMAP bitmap = nullptr;
    HGDIOBJ previous = nullptr;
    void* pixels = nullptr;
    int width = 0, height = 0;
    Surface(int w, int h) : width(w), height(h) {
        dc = CreateCompatibleDC(nullptr); assert(dc);
        BITMAPINFO info{};
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = width; info.bmiHeader.biHeight = -height;
        info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32; info.bmiHeader.biCompression = BI_RGB;
        bitmap = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &pixels, nullptr, 0); assert(bitmap && pixels);
        previous = SelectObject(dc, bitmap); assert(previous && previous != HGDI_ERROR);
        RECT bounds{0, 0, width, height}; FillRect(dc, &bounds, GetSysColorBrush(COLOR_WINDOW));
    }
    ~Surface() { SelectObject(dc, previous); DeleteObject(bitmap); DeleteDC(dc); }
    void Save(const std::wstring& path, int crop_width, int crop_height) {
        assert(crop_width > 0 && crop_width <= width && crop_height > 0 && crop_height <= height);
        GdiFlush();
        BITMAPFILEHEADER file{};
        file.bfType = 0x4d42; file.bfOffBits = sizeof(file) + sizeof(BITMAPINFOHEADER);
        file.bfSize = file.bfOffBits + static_cast<DWORD>(crop_width * crop_height * 4);
        BITMAPINFOHEADER info{}; info.biSize = sizeof(info); info.biWidth = crop_width; info.biHeight = -crop_height;
        info.biPlanes = 1; info.biBitCount = 32; info.biCompression = BI_RGB;
        HANDLE output = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        assert(output != INVALID_HANDLE_VALUE);
        DWORD written = 0;
        assert(WriteFile(output, &file, sizeof(file), &written, nullptr) && written == sizeof(file));
        assert(WriteFile(output, &info, sizeof(info), &written, nullptr) && written == sizeof(info));
        for (int y = 0; y < crop_height; ++y) {
            const auto* row = static_cast<const unsigned char*>(pixels) + y * width * 4;
            const DWORD bytes = static_cast<DWORD>(crop_width * 4);
            assert(WriteFile(output, row, bytes, &written, nullptr) && written == bytes);
        }
        assert(CloseHandle(output));
    }
};

std::wstring Face(HDC dc) {
    wchar_t family[LF_FACESIZE]{};
    assert(GetTextFaceW(dc, LF_FACESIZE, family) > 0);
    return family;
}

bool Equal(const std::wstring& left, const wchar_t* right) {
    return CompareStringOrdinal(left.c_str(), -1, right, -1, TRUE) == CSTR_EQUAL;
}

const std::vector<std::wstring> labels{
    L"1  \u5514\u597d", L"2  \u5514\u4fc2\u5497", L"3  \u706b\u70ac", L"4  \u4f60\u597d",
    L"5  \u5ee3\u6771\u8a71", L"6  \u55f0\u5572", L"7  \u5605", L"8  \u55ba\u5ea6", L"9  \u7cb5"
};

void Check(const wchar_t* preferred, const wchar_t* expected, unsigned dpi, int logical_height,
           const std::wstring& path, bool save, unsigned& rendered) {
    using namespace cime::ui;
    Surface surface(Scale(480, dpi), Scale(300, dpi));
    const HGDIOBJ original = GetCurrentObject(surface.dc, OBJ_FONT);
    const std::wstring original_face = Face(surface.dc);
    HFONT font = CreateCandidateFont(surface.dc, dpi, preferred, logical_height); assert(font);
    // The helper only borrows the caller's DC; no selected object can escape.
    assert(GetCurrentObject(surface.dc, OBJ_FONT) == original && Face(surface.dc) == original_face);
    LOGFONTW specification{}; assert(GetObjectW(font, sizeof(specification), &specification) == sizeof(specification));
    assert(specification.lfHeight == -Scale(logical_height, dpi));
    assert(specification.lfWeight == FW_NORMAL && specification.lfQuality == CLEARTYPE_QUALITY);
    HGDIOBJ previous = SelectObject(surface.dc, font); assert(previous && previous != HGDI_ERROR);
    const std::wstring actual = Face(surface.dc); assert(Equal(actual, expected));
    TEXTMETRICW metrics{}; assert(GetTextMetricsW(surface.dc, &metrics) && metrics.tmHeight > 0);
    // GetTextFace alone cannot prove the Chinese text is drawn by that family:
    // Segoe UI realizes by name but uses font linking for these glyphs. The two
    // proposed CJK families must supply this representative BMP sample directly.
    const std::wstring sample = L"\u5514\u597d\u4fc2\u5605\u55f0\u5572\u55ba\u7cb5";
    std::vector<WORD> glyphs(sample.size());
    assert(GetGlyphIndicesW(surface.dc, sample.c_str(), static_cast<int>(sample.size()), glyphs.data(),
        GGI_MARK_NONEXISTING_GLYPHS) != GDI_ERROR);
    const bool sample_covered = std::all_of(glyphs.begin(), glyphs.end(), [](WORD glyph) { return glyph != 0xffff; });
    if (!Equal(actual, L"Segoe UI")) assert(sample_covered);
    std::vector<int> widths;
    for (const auto& label : labels) {
        SIZE size{}; assert(GetTextExtentPoint32W(surface.dc, label.c_str(), static_cast<int>(label.size()), &size));
        assert(size.cx > 0 && size.cy > 0); widths.push_back(size.cx);
    }
    const auto layout = MakeLayout(widths, std::max<int>(metrics.tmHeight, Scale(logical_height, dpi)),
        surface.width, surface.height, dpi);
    assert(layout.cells.size() == labels.size());
    SetBkMode(surface.dc, TRANSPARENT);
    for (std::size_t i = 0; i < labels.size(); ++i) {
        const auto& cell = layout.cells[i]; assert(!cell.Empty());
        assert(cell.left >= 0 && cell.top >= 0 && cell.right <= layout.width && cell.bottom <= layout.height);
        assert(cell.bottom - cell.top >= metrics.tmHeight + 2 * Scale(4, dpi));
        assert(cell.right - cell.left >= widths[i] + 2 * layout.text_padding_x);
        assert(HitTest(layout, cell.left + layout.text_padding_x + 1, (cell.top + cell.bottom) / 2) == static_cast<int>(i));
        RECT box{cell.left, cell.top, cell.right, cell.bottom};
        if (i == 0) { FillRect(surface.dc, &box, GetSysColorBrush(COLOR_HIGHLIGHT)); SetTextColor(surface.dc, GetSysColor(COLOR_HIGHLIGHTTEXT)); }
        else SetTextColor(surface.dc, GetSysColor(COLOR_WINDOWTEXT));
        box.left += layout.text_padding_x; box.right -= layout.text_padding_x;
        assert(DrawTextW(surface.dc, labels[i].c_str(), static_cast<int>(labels[i].size()), &box,
            DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS | DT_NOPREFIX) > 0);
    }
    // A phrase wider than the allowed popup still clips to one bounded cell.
    const std::wstring phrase(300, L'\u7cb5'); SIZE phrase_size{};
    assert(GetTextExtentPoint32W(surface.dc, phrase.c_str(), static_cast<int>(phrase.size()), &phrase_size));
    const auto bounded = MakeLayout({phrase_size.cx}, metrics.tmHeight, surface.width, surface.height, dpi);
    assert(bounded.width == surface.width && bounded.cells.size() == 1 && !bounded.cells[0].Empty());
    RECT border{0, 0, layout.width, layout.height}; FrameRect(surface.dc, &border, GetSysColorBrush(COLOR_3DSHADOW));
    GdiFlush();
    SelectObject(surface.dc, previous); assert(DeleteObject(font));
    if (save) { surface.Save(path, layout.width, layout.height); ++rendered; }
    std::wcout << L"{\"dpi\":" << dpi << L",\"preferred\":\"" << (preferred ? preferred : L"(none)") << L"\",\"realized\":\"" << actual
        << L"\",\"logical_height\":" << logical_height << L",\"line_height\":" << metrics.tmHeight
        << L",\"sample_glyphs_in_primary_face\":" << (sample_covered ? L"true" : L"false")
        << L",\"popup_width\":" << layout.width << L",\"popup_height\":" << layout.height << L"}\n";
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    using namespace cime::ui;
    if (argc == 2 && std::wstring(argv[1]) == L"--expect-private-font-absent") {
        Surface surface(32, 32);
        HFONT unexpected = TryCandidateFont(surface.dc, 96, kBundledCandidateFontFamily, 20);
        if (unexpected) { DeleteObject(unexpected); return 2; }
        std::cout << "{\"other_process_has_private_font\":false}\n";
        return 0;
    }
    if (argc == 3 && std::wstring(argv[1]) == L"--expect-path-refused") {
        PrivateCandidateFont font;
        assert(!font.EnsureForModulePath(argv[2]) && !font.Loaded());
        std::cout << "{\"unsafe_path_refused\":true}\n";
        return 0;
    }
    assert(argc == 4);
    unsigned checks = 0, rendered = 0;
    const std::wstring directory = argv[1];
    const std::wstring fixture = directory + L"\\fixture";
    const std::wstring module_path = fixture + L"\\native\\CantoneseIME.dll";
    const std::wstring font_path = fixture + L"\\assets\\fonts\\lxgw-wenkai-tc\\LXGWWenKaiTC-Regular.ttf";
    for (const auto& path : {fixture, fixture + L"\\native", fixture + L"\\assets", fixture + L"\\assets\\fonts", fixture + L"\\assets\\fonts\\lxgw-wenkai-tc"})
        assert(CreateDirectoryW(path.c_str(), nullptr));
    wchar_t executable[32768]{};
    assert(GetModuleFileNameW(nullptr, executable, 32768) > 0);
    assert(CopyFileW(argv[3], module_path.c_str(), TRUE));
    HMODULE anchor = LoadLibraryExW(module_path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    assert(anchor);
    Surface before(32, 32);
    assert(!TryCandidateFont(before.dc, 96, kBundledCandidateFontFamily, 20));
    {
        PrivateCandidateFont absent;
        assert(!absent.EnsureForModulePath(module_path) && !absent.Loaded());
        Check(nullptr, L"Microsoft JhengHei UI", 96, 20, L"", false, rendered); ++checks;
    }
    assert(CopyFileW(argv[2], font_path.c_str(), TRUE));
    PrivateCandidateFont first, second;
    assert(first.EnsureForModule(anchor) && first.Loaded() && first.FontCount() > 0);
    const DWORD loaded_font_faces = first.FontCount();
    assert(first.EnsureForModule(anchor)); // One owner loads only once.
    assert(second.EnsureForModulePath(module_path) && second.Loaded() && second.FontCount() > 0);
    // Private memory fonts must not appear in another process or install fonts
    // globally. No shell, desktop interaction or font-change broadcast is used.
    std::wstring command = L"\"" + std::wstring(executable) + L"\" --expect-private-font-absent";
    std::vector<wchar_t> child_command(command.begin(), command.end()); child_command.push_back(0);
    STARTUPINFOW start{}; start.cb = sizeof(start); PROCESS_INFORMATION child{};
    assert(CreateProcessW(executable, child_command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &start, &child));
    assert(WaitForSingleObject(child.hProcess, 30000) == WAIT_OBJECT_0);
    DWORD child_exit = 1; assert(GetExitCodeProcess(child.hProcess, &child_exit) && child_exit == 0);
    assert(CloseHandle(child.hThread) && CloseHandle(child.hProcess));
    // GDI owns a copied image: an installer can retire and replace the source
    // file while both owners' font resources remain live.
    assert(MoveFileExW(font_path.c_str(), (font_path + L".retired").c_str(), 0));
    assert(CopyFileW(argv[2], font_path.c_str(), TRUE));
    for (unsigned dpi : {96u, 120u, 144u, 192u}) {
        Check(kBundledCandidateFontFamily, kBundledCandidateFontFamily, dpi, kCandidateFontLogicalHeight,
            directory + L"\\wenkai-tc-" + std::to_wstring(dpi) + L".bmp", true, rendered); ++checks;
        Check(L"Microsoft JhengHei UI", L"Microsoft JhengHei UI", dpi, 20, directory + L"\\jhenghei-ui-" + std::to_wstring(dpi) + L".bmp", true, rendered); ++checks;
        Check(L"CantoneseMissingCandidateFont123", L"Microsoft JhengHei UI", dpi, 20, L"", false, rendered); ++checks;
    }
    Check(L"Segoe UI", L"Segoe UI", 96, 17, std::wstring(argv[1]) + L"\\current-segoe-96.bmp", true, rendered); ++checks;
    assert(first.Reset() && !first.Loaded());
    Check(kBundledCandidateFontFamily, kBundledCandidateFontFamily, 96, 20, L"", false, rendered); ++checks;
    assert(second.Reset() && !second.Loaded());
    assert(!TryCandidateFont(before.dc, 96, kBundledCandidateFontFamily, 20));
    { PrivateCandidateFont scoped; assert(scoped.EnsureForModulePath(module_path)); }
    assert(!TryCandidateFont(before.dc, 96, kBundledCandidateFontFamily, 20));
    // The released owner can be re-used after deactivation/reactivation.
    assert(first.EnsureForModule(anchor) && first.Reset());
    assert(!TryCandidateFont(before.dc, 96, kBundledCandidateFontFamily, 20));
    std::wstring unused_root, unused_font;
    assert(!CandidateFontPaths(L"native\\CantoneseIME.dll", unused_root, unused_font));
    assert(!CandidateFontPaths(fixture + L"\\other\\CantoneseIME.dll", unused_root, unused_font));
    assert(!CandidateFontPaths(fixture + L"\\native\\other.dll", unused_root, unused_font));
    assert(!CandidateFontPaths(fixture + L"\\..\\native\\CantoneseIME.dll", unused_root, unused_font));
    assert(!CandidateFontPaths(L"\\\\server\\share\\native\\CantoneseIME.dll", unused_root, unused_font));
    Surface surface(32, 32);
    const HGDIOBJ original = GetCurrentObject(surface.dc, OBJ_FONT);
    assert(!cime::ui::TryCandidateFont(surface.dc, 96, L"CantoneseMissingCandidateFont123", 20));
    assert(GetCurrentObject(surface.dc, OBJ_FONT) == original);
    assert(!cime::ui::CreateCandidateFont(nullptr, 96, kBundledCandidateFontFamily, 20));
    assert(!cime::ui::CreateCandidateFont(surface.dc, 96, kBundledCandidateFontFamily, 0));
    assert(FreeLibrary(anchor));
    std::wcout << L"{\"passed\":true,\"font_cases\":" << checks << L",\"popup_renders\":" << rendered
        << L",\"private_font_faces\":" << loaded_font_faces
        << L",\"separate_process_private_font_absent\":true,\"asset_retire_replace_while_active\":true,\"multiple_owners_and_cleanup\":true"
        << L",\"scope\":\"Actual Windows GDI private copied-memory font loading, regular resolved family, absent-font fallback, direct CJK sample glyph indices, DC ownership, numbered-label metrics/wrapping/hit testing at four DPIs; offscreen popup renders, no live IME activation, global install or complete glyph-coverage claim\"}\n";
    return 0;
}
#endif
