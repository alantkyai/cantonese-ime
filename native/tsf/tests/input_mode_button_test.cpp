// Native COM contract checks with real Windows icon resources. No registration,
// global input activation, keyboard injection, broker or private learning store.
#include "../input_mode_button.h"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <shellapi.h>
#include <vector>

namespace {
class Owner final : public cime::ui::InputModeOwner {
public:
    bool EnglishMode() const override { return english; }
    HRESULT ToggleInputMode() override { ++toggles; english = !english; item->ModeChanged(); return S_OK; }
    HRESULT ShowAppearanceMenu(POINT point) override { ++appearance_menus; menu_point = point; return S_OK; }
    bool english = false;
    unsigned toggles = 0;
    unsigned appearance_menus = 0;
    POINT menu_point{};
    cime::ui::InputModeButton* item = nullptr;
};
class Sink final : public ITfLangBarItemSink {
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** value) override {
        if (!value) return E_POINTER;
        *value = nullptr;
        if (iid != IID_IUnknown && iid != IID_ITfLangBarItemSink) return E_NOINTERFACE;
        *value = static_cast<ITfLangBarItemSink*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references; }
    ULONG STDMETHODCALLTYPE Release() override { return --references; }
    HRESULT STDMETHODCALLTYPE OnUpdate(DWORD flags) override {
        events.push_back(flags);
        if (unadvise_on_update) assert(source->UnadviseSink(cookie) == S_OK);
        return S_OK;
    }
    ULONG references = 1;
    std::vector<DWORD> events;
    bool unadvise_on_update = false;
    ITfSource* source = nullptr;
    DWORD cookie = TF_INVALID_COOKIE;
};
void Text(cime::ui::InputModeButton* item, const wchar_t* expected) {
    BSTR value = nullptr;
    assert(item->GetText(&value) == S_OK && std::wstring(value, SysStringLen(value)) == expected);
    SysFreeString(value);
}
void Require(bool condition, const char* message) {
    if (!condition) { std::cerr << message << '\n'; ExitProcess(1); }
}
struct Surface {
    HDC dc = CreateCompatibleDC(nullptr);
    HBITMAP bitmap = nullptr;
    HGDIOBJ previous = nullptr;
    DWORD* pixels = nullptr;
    int width, height;
    Surface(int w, int h, DWORD rgb) : width(w), height(h) {
        BITMAPINFO info{}; info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = w; info.bmiHeader.biHeight = -h;
        info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = BI_RGB;
        bitmap = CreateDIBSection(dc, &info, DIB_RGB_COLORS, reinterpret_cast<void**>(&pixels), nullptr, 0);
        Require(dc && bitmap && pixels, "CreateDIBSection failed");
        previous = SelectObject(dc, bitmap);
        std::fill(pixels, pixels + w * h, rgb);
    }
    ~Surface() { SelectObject(dc, previous); DeleteObject(bitmap); DeleteDC(dc); }
    Surface(const Surface&) = delete;
    void Save(const wchar_t* path) {
        BITMAPFILEHEADER file{}; file.bfType = 0x4d42;
        file.bfOffBits = sizeof(file) + sizeof(BITMAPINFOHEADER);
        file.bfSize = file.bfOffBits + width * height * 4;
        BITMAPINFOHEADER info{}; info.biSize = sizeof(info); info.biWidth = width; info.biHeight = -height;
        info.biPlanes = 1; info.biBitCount = 32; info.biCompression = BI_RGB;
        HANDLE output = CreateFileW(path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        Require(output != INVALID_HANDLE_VALUE, "Cannot write icon preview");
        DWORD written = 0;
        Require(WriteFile(output, &file, sizeof(file), &written, nullptr) && written == sizeof(file), "Cannot write BMP header");
        Require(WriteFile(output, &info, sizeof(info), &written, nullptr) && written == sizeof(info), "Cannot write DIB header");
        const DWORD bytes = width * height * 4;
        Require(WriteFile(output, pixels, bytes, &written, nullptr) && written == bytes, "Cannot write BMP pixels");
        CloseHandle(output);
    }
};
void AlphaIcon(HICON icon, int width, int height) {
    ICONINFO info{};
    Require(icon && GetIconInfo(icon, &info), "GetIconInfo failed");
    Require(info.hbmMask && info.hbmColor, "Icon must contain color/alpha bitmap");
    BITMAP bitmap{};
    Require(GetObjectW(info.hbmColor, sizeof(bitmap), &bitmap), "GetObject icon failed");
    Require(bitmap.bmWidth == width && bitmap.bmHeight == height && bitmap.bmBitsPixel == 32,
        "Icon must have requested dimensions and 32-bit color");
    BITMAPINFO dib{}; dib.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    dib.bmiHeader.biWidth = width; dib.bmiHeader.biHeight = -height;
    dib.bmiHeader.biPlanes = 1; dib.bmiHeader.biBitCount = 32;
    std::vector<DWORD> pixels(width * height);
    HDC dc = GetDC(nullptr);
    Require(GetDIBits(dc, info.hbmColor, 0, height, pixels.data(), &dib, DIB_RGB_COLORS) == height,
        "Cannot read icon alpha pixels");
    ReleaseDC(nullptr, dc);
    unsigned transparent = 0, opaque = 0, antialias = 0;
    for (DWORD pixel : pixels) {
        const unsigned alpha = pixel >> 24;
        transparent += alpha == 0; opaque += alpha == 255; antialias += alpha > 0 && alpha < 255;
        Require((pixel & 255) == ((pixel >> 8) & 255) && (pixel & 255) == ((pixel >> 16) & 255),
            "IME icon must use grayscale only");
    }
    Require(transparent && opaque && antialias, "Icon must have transparency, solid glyph and antialias alpha");
    for (DWORD background : {0x202020u, 0xffffffu}) {
        Surface surface(width, height, background);
        Require(DrawIconEx(surface.dc, 0, 0, icon, width, height, 0, nullptr, DI_NORMAL), "DrawIconEx failed");
        GdiFlush();
        unsigned changed = 0, bright = 0, dark = 0;
        for (int i = 0; i < width * height; ++i) {
            DWORD pixel = surface.pixels[i] & 0xffffff;
            changed += pixel != background;
            bright += (pixel & 255) > 200;
            dark += (pixel & 255) < 190;
        }
        Require(changed >= static_cast<unsigned>(width * height / 20), "Icon covers too few pixels");
        Require(background != 0x202020 || bright >= static_cast<unsigned>(width * height / 50),
            "Dark surface has no visible white glyph/tile");
        Require(background != 0xffffff || dark >= static_cast<unsigned>(width * height / 100),
            "White surface has no visible dark outline/glyph");
    }
    DeleteObject(info.hbmMask);
    DeleteObject(info.hbmColor);
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    assert(argc == 2 || argc == 3);
    HMODULE resource = LoadLibraryExW(argv[1], nullptr, LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE);
    assert(resource);
    Owner owner; volatile LONG live_objects = 0;
    auto* item = new cime::ui::InputModeButton(resource, &owner, &live_objects); owner.item = item;
    assert(live_objects == 1);
    TF_LANGBARITEMINFO info{};
    assert(item->GetInfo(&info) == S_OK && info.clsidService == CLSID_CantoneseIME && info.guidItem == GUID_LBI_INPUTMODE);
    assert(!(info.dwStyle & TF_LBI_STYLE_TEXTCOLORICON));
    assert(info.dwStyle & TF_LBI_STYLE_SHOWNINTRAY);
    assert(info.dwStyle & TF_LBI_STYLE_BTN_BUTTON);
    ITfSource* source = nullptr;
    assert(item->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(&source)) == S_OK);
    IUnknown* unknown = nullptr; IUnknown* unknown_from_source = nullptr;
    assert(item->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(&unknown)) == S_OK);
    assert(source->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(&unknown_from_source)) == S_OK);
    assert(unknown == unknown_from_source); unknown->Release(); unknown_from_source->Release();
    assert(item->QueryInterface(IID_ITfSource, nullptr) == E_POINTER);
    assert(item->GetText(nullptr) == E_POINTER && item->GetIcon(nullptr) == E_POINTER);
    assert(item->GetStatus(nullptr) == E_POINTER && item->GetInfo(nullptr) == E_POINTER);
    Sink sink; sink.source = source;
    assert(source->AdviseSink(IID_IUnknown, &sink, &sink.cookie) == CONNECT_E_CANNOTCONNECT);
    assert(source->AdviseSink(IID_ITfLangBarItemSink, &sink, &sink.cookie) == S_OK && sink.references == 2);
    const DWORD first_cookie = sink.cookie;
    DWORD other_cookie = 0;
    assert(source->AdviseSink(IID_ITfLangBarItemSink, &sink, &other_cookie) == CONNECT_E_ADVISELIMIT);
    assert(source->UnadviseSink(first_cookie + 1) == CONNECT_E_NOCONNECTION);
    Text(item, L"\x7cb5");
    HICON cantonese = nullptr; assert(item->GetIcon(&cantonese) == S_OK); AlphaIcon(cantonese, GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON));
    assert(item->OnClick(TF_LBI_CLK_RIGHT, POINT{123,456}, nullptr) == S_OK && owner.toggles == 0);
    assert(owner.appearance_menus == 1 && owner.menu_point.x == 123 && owner.menu_point.y == 456 && sink.events.empty());
    assert(item->OnClick(TF_LBI_CLK_LEFT, POINT{}, nullptr) == S_OK && owner.toggles == 1);
    Text(item, L"\x82f1");
    assert(sink.events.size() == 1 && sink.events.back() == (TF_LBI_ICON | TF_LBI_TEXT | TF_LBI_TOOLTIP));
    BSTR tooltip = nullptr;
    assert(item->GetTooltipString(&tooltip) == S_OK && std::wcsstr(tooltip, L"English mode") && std::wcsstr(tooltip, L"Ctrl+Space")); SysFreeString(tooltip);
    HICON english = nullptr; assert(item->GetIcon(&english) == S_OK); AlphaIcon(english, GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON));
    assert(english != cantonese); DestroyIcon(cantonese); DestroyIcon(english);
    assert(item->Show(FALSE) == S_OK && sink.events.back() == TF_LBI_STATUS);
    DWORD status = 0; assert(item->GetStatus(&status) == S_OK && (status & TF_LBI_STATUS_HIDDEN));
    assert(item->Show(TRUE) == S_OK);
    assert(source->UnadviseSink(first_cookie) == S_OK && sink.references == 1);
    assert(source->AdviseSink(IID_ITfLangBarItemSink, &sink, &sink.cookie) == S_OK && sink.cookie != first_cookie);
    assert(source->UnadviseSink(first_cookie) == CONNECT_E_NOCONNECTION);
    sink.unadvise_on_update = true;
    owner.english = false; item->ModeChanged(); Text(item, L"\x7cb5");
    assert(sink.references == 1);
    sink.unadvise_on_update = false;
    assert(source->AdviseSink(IID_ITfLangBarItemSink, &sink, &sink.cookie) == S_OK);
    item->Detach(); assert(sink.references == 1);
    assert(item->OnClick(TF_LBI_CLK_LEFT, POINT{}, nullptr) == TF_E_DISCONNECTED && owner.toggles == 1);
    assert(item->OnClick(TF_LBI_CLK_RIGHT, POINT{}, nullptr) == TF_E_DISCONNECTED && owner.appearance_menus == 1);
    assert(item->GetStatus(&status) == S_OK && (status & TF_LBI_STATUS_DISABLED));
    source->Release(); assert(item->Release() == 0 && live_objects == 0);
    // Load all actual DPI resources from this exact DLL and render them using
    // the native Windows alpha path on both taskbar-like and white surfaces.
    // Every row is brand/Cantonese/English, at original size and 4x nearest
    // neighbour magnification. Background rows alternate dark and white.
    Surface preview(1250, 648, 0xffffff);
    int column = 0;
    for (int size : {16, 20, 24, 32, 40, 48, 64, 256}) {
        int asset = 0;
        for (int id : {IDI_CANTONESE_BRAND, IDI_CANTONESE_MODE, IDI_ENGLISH_MODE}) {
            HICON icon = static_cast<HICON>(LoadImageW(resource, MAKEINTRESOURCEW(id), IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
            AlphaIcon(icon, size, size);
            if (size <= 64) {
                const int x = column * 175;
                for (int theme = 0; theme < 2; ++theme) {
                    Surface tile(170, 106, theme ? 0xffffff : 0x202020);
                    DrawIconEx(tile.dc, 5, 20, icon, size, size, 0, nullptr, DI_NORMAL);
                    SetBkMode(tile.dc, TRANSPARENT); SetTextColor(tile.dc, theme ? RGB(0,0,0) : RGB(255,255,255));
                    std::wstring label = std::to_wstring(size) + L" px";
                    TextOutW(tile.dc, 5, 2, label.c_str(), static_cast<int>(label.size()));
                    Surface original(size, size, theme ? 0xffffff : 0x202020);
                    DrawIconEx(original.dc, 0, 0, icon, size, size, 0, nullptr, DI_NORMAL);
                    const int enlarged = std::min(90, size * 4);
                    StretchBlt(tile.dc, 75, 16, enlarged, enlarged, original.dc, 0, 0, size, size, SRCCOPY);
                    BitBlt(preview.dc, x, (asset * 2 + theme) * 108, 170, 106, tile.dc, 0, 0, SRCCOPY);
                }
            }
            DestroyIcon(icon); ++asset;
        }
        ++column;
    }
    if (argc == 3) preview.Save(argv[2]);
    HICON brand = nullptr;
    assert(ExtractIconExW(argv[1], 0, nullptr, &brand, 1) == 1 && brand); DestroyIcon(brand);
    FreeLibrary(resource);
    std::cout << "{\"passed\":true,\"icon_variants\":24,\"contrast_renders\":48,\"scope\":\"x64 native COM button, mode notifications, sink ownership, teardown, 32-bit alpha/grayscale, dark and white DrawIconEx contrast, DPI resources and profile icon extraction; no registration/input activation\"}\n";
    return 0;
}
