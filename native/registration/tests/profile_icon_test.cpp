// Exercise the exact production RegisterProfile argument wrapper with a tiny
// capture target. This never creates COM objects or calls registration APIs.
#define wmain CimeMachineRegistrationProgram
#include "../machine.cpp"
#undef wmain
#include <cassert>

namespace {
struct CapturedProfile {
    CLSID clsid{}; LANGID language = 0; GUID profile{};
    std::wstring description, icon_file;
    ULONG icon_location = 0; HKL substitute = nullptr;
    DWORD preferred = 0; BOOL enabled = TRUE; DWORD flags = 0;
};
struct CaptureManager {
    std::vector<CapturedProfile> calls;
    HRESULT result = S_OK;
    HRESULT RegisterProfile(REFCLSID clsid, LANGID language, REFGUID profile,
        const WCHAR* description, ULONG description_count, const WCHAR* icon_file,
        ULONG icon_file_count, ULONG icon_location, HKL substitute,
        DWORD preferred, BOOL enabled, DWORD flags) {
        calls.push_back({clsid, language, profile, std::wstring(description, description_count),
            std::wstring(icon_file, icon_file_count), icon_location, substitute, preferred, enabled, flags});
        return result;
    }
};
std::vector<DWORD> Pixels(HICON icon, int size) {
    ICONINFO info{}; assert(icon && GetIconInfo(icon, &info) && info.hbmColor);
    BITMAP bitmap{}; assert(GetObjectW(info.hbmColor, sizeof(bitmap), &bitmap));
    assert(bitmap.bmWidth == size && bitmap.bmHeight == size && bitmap.bmBitsPixel == 32);
    BITMAPINFO dib{}; dib.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    dib.bmiHeader.biWidth = size; dib.bmiHeader.biHeight = -size;
    dib.bmiHeader.biPlanes = 1; dib.bmiHeader.biBitCount = 32;
    std::vector<DWORD> pixels(size * size); HDC dc = GetDC(nullptr);
    assert(GetDIBits(dc, info.hbmColor, 0, size, pixels.data(), &dib, DIB_RGB_COLORS) == size);
    ReleaseDC(nullptr, dc); DeleteObject(info.hbmColor); DeleteObject(info.hbmMask);
    assert(std::any_of(pixels.begin(), pixels.end(), [](DWORD pixel) { return (pixel >> 24) == 255; }));
    assert(std::any_of(pixels.begin(), pixels.end(), [](DWORD pixel) { return (pixel >> 24) == 0; }));
    return pixels;
}
}

int wmain(int argc, wchar_t** argv) {
    assert(argc == 3);
    Plan plan; plan.product_root = argv[1];
    // An independent target proves this wrapper derives the fixed helper EXE
    // rather than accidentally continuing to use the code DLL as IconFile.
    plan.target = plan.product_root + L"\\native\\CantoneseIME.dll";
    const std::wstring path = argv[2];
    assert(BrandingPath(plan) == path && path != plan.target);
    CheckBrandingSelfPath(plan, path);
    unsigned rejections = 0;
    auto reject = [&](const auto& body) { bool failed = false; try { body(); } catch (const Failure&) { failed = true; }
        assert(failed); ++rejections; };
    reject([&] { CheckBrandingSelfPath(plan, plan.target); });
    reject([&] { CheckBrandingSelfPath(plan, plan.product_root + L"\\CantoneseMachineRegistration.exe"); });
    reject([&] { CheckBrandingSelfPath(plan, plan.product_root + L"\\native\\..\\native\\CantoneseMachineRegistration.exe"); });
    CaptureManager manager;
    for (LANGID language : kLanguages) assert(RegisterReleaseProfile(&manager, language, plan) == S_OK);
    assert(manager.calls.size() == 2);
    HMODULE resource = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE);
    assert(resource);
    BrandingResources(resource);
    reject([&] { BrandingResources(GetModuleHandleW(nullptr)); }); // This test EXE has no branding resources.
    Handle file; OpenRead(path, file); CheckPe(file.value, false);
    reject([&] { CheckPe(file.value); }); // The resource container is an EXE, not the COM DLL.
    unsigned extractions = 0;
    for (unsigned i = 0; i < manager.calls.size(); ++i) {
        const auto& call = manager.calls[i];
        assert(IsEqualCLSID(call.clsid, CLSID_CantoneseIME) && call.language == kLanguages[i]);
        assert(IsEqualGUID(call.profile, GUID_CantoneseProfile) && call.description == kProductName);
        assert(call.icon_file == path && !call.substitute && !call.preferred && !call.enabled && !call.flags);
        assert(call.icon_location == static_cast<ULONG>(-IDI_CANTONESE_BRAND));
        const int signed_location = static_cast<int>(call.icon_location);
        assert(signed_location == -101);
        for (int size : {16, 20, 24, 32, 40, 48}) {
            HICON extracted = nullptr;
            // Use the value actually captured from the production wrapper,
            // rather than a separately hardcoded extractor input.
            assert(SHDefExtractIconW(call.icon_file.c_str(), signed_location, 0, &extracted, nullptr,
                MAKELONG(size, size)) == S_OK && extracted);
            HICON direct = static_cast<HICON>(LoadImageW(resource, MAKEINTRESOURCEW(-signed_location),
                IMAGE_ICON, size, size, LR_DEFAULTCOLOR));
            assert(direct && Pixels(extracted, size) == Pixels(direct, size));
            DestroyIcon(extracted); DestroyIcon(direct); ++extractions;
        }
    }
    SetLastError(0);
    HICON missing = static_cast<HICON>(LoadImageW(resource, MAKEINTRESOURCEW(0), IMAGE_ICON, 16, 16, LR_DEFAULTCOLOR));
    assert(!missing);
    FreeLibrary(resource);
    manager.result = E_FAIL;
    assert(RegisterReleaseProfile(&manager, kLanguages[0], plan) == E_FAIL && manager.calls.size() == 3);
    std::cout << "{\"passed\":true,\"profiles\":2,\"captured_location\":-101,\"matching_resource_extractions\":" << extractions
              << ",\"guard_rejections\":" << rejections
              << ",\"scope\":\"production fixed helper EXE profile argument capture, exact self-path and resource/PE guards, HRESULT propagation, actual captured icon resource lookup and absent resource0 control; no registration or input changes\"}\n";
    return 0;
}
