// Native x64 offscreen popup checks with the actual privately loaded font.
// Creates only disposable fixture files and memory DCs; no IME registration,
// visible windows, user preferences, learning data or system font install.
#include "../candidate_font.h"
#include "../candidate_appearance.h"
#include <cassert>
#include <iostream>

namespace {
class Surface {
public:
    HDC dc = nullptr;
    HBITMAP bitmap = nullptr;
    HGDIOBJ previous = nullptr;
    void* pixels = nullptr;
    int width, height;
    Surface(int w, int h) : width(w), height(h) {
        dc = CreateCompatibleDC(nullptr); assert(dc);
        BITMAPINFO info{};
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = width; info.bmiHeader.biHeight = -height;
        info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32; info.bmiHeader.biCompression = BI_RGB;
        bitmap = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &pixels, nullptr, 0); assert(bitmap && pixels);
        previous = SelectObject(dc, bitmap); assert(previous && previous != HGDI_ERROR);
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
        DWORD count = 0;
        assert(WriteFile(output, &file, sizeof(file), &count, nullptr) && count == sizeof(file));
        assert(WriteFile(output, &info, sizeof(info), &count, nullptr) && count == sizeof(info));
        for (int y = 0; y < crop_height; ++y) {
            const auto* row = static_cast<const unsigned char*>(pixels) + y * width * 4;
            const DWORD bytes = static_cast<DWORD>(crop_width * 4);
            assert(WriteFile(output, row, bytes, &count, nullptr) && count == bytes);
        }
        assert(CloseHandle(output));
    }
};

void Fill(HDC dc, const RECT& bounds, COLORREF color) {
    HBRUSH brush = CreateSolidBrush(color); assert(brush);
    assert(FillRect(dc, &bounds, brush)); assert(DeleteObject(brush));
}

const std::vector<std::wstring> labels{
    L"1  \u5514\u597d", L"2  \u5514\u4fc2\u5497", L"3  \u706b\u70ac", L"4  \u63db\u5497\u5572\u5b57\u578b",
    L"5  \u5ee3\u6771\u8a71", L"6  \u55f0\u5572", L"7  \u9ede\u89e3\u4f60\u4eca\u65e5\u5481\u9072\u5148\u5230",
    L"8  \u55ba\u5ea6", L"9  \u518d\u50be\u5566"
};

void Render(const std::wstring& directory, const wchar_t* name, unsigned dpi,
            cime::ui::CandidateOrientation orientation, bool high_contrast, bool small_viewport) {
    using namespace cime::ui;
    const int maximum_width = Scale(small_viewport ? 180 : 480, dpi);
    const int maximum_height = Scale(small_viewport ? 90 : 500, dpi);
    Surface surface(maximum_width, maximum_height);
    HFONT font = CreateCandidateFont(surface.dc, dpi, kBundledCandidateFontFamily, kCandidateFontLogicalHeight); assert(font);
    HGDIOBJ old = SelectObject(surface.dc, font); assert(old && old != HGDI_ERROR);
    wchar_t family[LF_FACESIZE]{};
    assert(GetTextFaceW(surface.dc, LF_FACESIZE, family) > 0);
    assert(CompareStringOrdinal(family, -1, kBundledCandidateFontFamily, -1, TRUE) == CSTR_EQUAL);
    TEXTMETRICW metrics{}; assert(GetTextMetricsW(surface.dc, &metrics));
    auto choices = labels;
    if (small_viewport) choices[0] = L"1  " + std::wstring(80, L'\u7cb5');
    std::vector<int> widths;
    for (const auto& label : choices) {
        std::vector<WORD> glyphs(label.size());
        assert(GetGlyphIndicesW(surface.dc, label.c_str(), static_cast<int>(label.size()), glyphs.data(), GGI_MARK_NONEXISTING_GLYPHS) != GDI_ERROR);
        assert(std::all_of(glyphs.begin(), glyphs.end(), [](WORD glyph) { return glyph != 0xffff; }));
        SIZE extent{}; assert(GetTextExtentPoint32W(surface.dc, label.c_str(), static_cast<int>(label.size()), &extent));
        widths.push_back(extent.cx);
    }
    const std::size_t selected = small_viewport ? 8 : 3;
    const auto layout = MakeLayout(widths, std::max<int>(metrics.tmHeight, Scale(kCandidateFontLogicalHeight, dpi)),
        maximum_width, maximum_height, dpi, selected, orientation);
    assert(layout.width > 0 && layout.width <= maximum_width && layout.height > 0 && layout.height <= maximum_height);
    assert(layout.cells.size() == choices.size() && !layout.cells[selected].Empty());
    const auto colors = ResolveAppearance({CandidateTheme::Dark,95,orientation}, high_contrast);
    assert(colors.alpha == (high_contrast ? 255 : 242));
    const RECT bounds{0,0,layout.width,layout.height}; Fill(surface.dc, bounds, colors.background);
    SetBkMode(surface.dc, TRANSPARENT);
    std::size_t visible = 0;
    for (std::size_t i = 0; i < choices.size(); ++i) {
        const auto& cell = layout.cells[i];
        if (cell.Empty()) continue;
        ++visible;
        assert(cell.left >= 0 && cell.top >= 0 && cell.right <= layout.width && cell.bottom <= layout.height);
        if (orientation == CandidateOrientation::Vertical) {
            assert(cell.left == layout.cells[selected].left && cell.right == layout.cells[selected].right);
        }
        if (!small_viewport) {
            assert(cell.bottom - cell.top >= metrics.tmHeight + 2 * Scale(4,dpi));
            assert(cell.right - cell.left >= widths[i] + 2 * layout.text_padding_x);
        }
        assert(HitTest(layout, cell.left + layout.text_padding_x + 1, (cell.top+cell.bottom)/2) == static_cast<int>(i));
        RECT box{cell.left,cell.top,cell.right,cell.bottom};
        Fill(surface.dc, box, i == selected ? colors.highlight : colors.background);
        SetTextColor(surface.dc, i == selected ? colors.highlight_text : colors.text);
        box.left += layout.text_padding_x; box.right -= layout.text_padding_x;
        assert(DrawTextW(surface.dc, choices[i].c_str(), static_cast<int>(choices[i].size()), &box,
            DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS | DT_NOPREFIX) > 0);
    }
    assert(visible > 0 && (small_viewport || visible == choices.size()));
    const Rect work{-1920,-100,0,980};
    const auto placed = PlacePopup(layout, {-5,970,-1,980}, work, Scale(3,dpi));
    assert(placed.left >= work.left && placed.top >= work.top && placed.right <= work.right && placed.bottom <= work.bottom);
    HBRUSH border = CreateSolidBrush(colors.border); assert(border && FrameRect(surface.dc,&bounds,border)); assert(DeleteObject(border));
    GdiFlush();
    std::size_t ink = 0;
    const auto& selected_cell = layout.cells[selected];
    for (int y = selected_cell.top + 1; y < selected_cell.bottom - 1; ++y) {
        for (int x = selected_cell.left + layout.text_padding_x; x < selected_cell.right - layout.text_padding_x; ++x) {
            const auto* pixel = static_cast<const unsigned char*>(surface.pixels) + (y * surface.width + x) * 4;
            if (RGB(pixel[2],pixel[1],pixel[0]) != colors.highlight) ++ink;
        }
    }
    assert(ink > 0); // The real selected number/word painted visible GDI pixels.
    SelectObject(surface.dc, old); assert(DeleteObject(font));
    surface.Save(directory + L"\\" + name + L".bmp", layout.width, layout.height);
    std::wcout << L"{\"render\":\"" << name << L"\",\"dpi\":" << dpi
        << L",\"orientation\":\"" << (orientation == CandidateOrientation::Vertical ? L"vertical" : L"horizontal")
        << L"\",\"font\":\"" << family << L"\",\"width\":" << layout.width << L",\"height\":" << layout.height
        << L",\"visible_cells\":" << visible << L",\"selected_index\":" << selected
        << L",\"selected_glyph_pixels\":" << ink << L",\"high_contrast\":" << (high_contrast ? L"true" : L"false")
        << L",\"small_viewport\":" << (small_viewport ? L"true" : L"false") << L"}\n";
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    using namespace cime::ui;
    assert(argc == 3);
    const std::wstring directory = argv[1], fixture = directory + L"\\fixture";
    for (const auto& path : {fixture,fixture+L"\\native",fixture+L"\\assets",fixture+L"\\assets\\fonts",fixture+L"\\assets\\fonts\\lxgw-wenkai-tc"})
        assert(CreateDirectoryW(path.c_str(),nullptr));
    wchar_t self[32768]{}; assert(GetModuleFileNameW(nullptr,self,32768) > 0);
    const std::wstring module = fixture + L"\\native\\CantoneseIME.dll";
    // An inert regular-file module anchor tests the same guarded private font
    // path without loading or registering a production TSF DLL.
    assert(CopyFileW(self,module.c_str(),TRUE));
    assert(CopyFileW(argv[2],(fixture+L"\\assets\\fonts\\lxgw-wenkai-tc\\LXGWWenKaiTC-Regular.ttf").c_str(),TRUE));
    PrivateCandidateFont font; assert(font.EnsureForModulePath(module) && font.Loaded());
    for (unsigned dpi : {96u,120u,144u,192u}) {
        for (const auto orientation : {CandidateOrientation::Horizontal,CandidateOrientation::Vertical}) {
            const std::wstring name = std::wstring(orientation == CandidateOrientation::Vertical ? L"vertical-" : L"horizontal-") + std::to_wstring(dpi);
            Render(directory,name.c_str(),dpi,orientation,false,false);
        }
    }
    for (const auto orientation : {CandidateOrientation::Horizontal,CandidateOrientation::Vertical}) {
        const std::wstring prefix = orientation == CandidateOrientation::Vertical ? L"vertical" : L"horizontal";
        Render(directory,(prefix+L"-high-contrast-96").c_str(),96,orientation,true,false);
        Render(directory,(prefix+L"-viewport-long-96").c_str(),96,orientation,false,true);
    }
    assert(font.Reset());
    std::cout << "{\"passed\":true,\"renders\":12,\"scope\":\"real bundled private-memory font, horizontal and vertical numbered choices, four DPIs, High Contrast source colors, selected viewport/long words, hit indices and monitor bounds; offscreen GDI source pixels, not live opacity or installed IME acceptance\"}\n";
}
