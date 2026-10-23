#pragma once
#include <windows.h>
#include <msctf.h>
#include <oleauto.h>
#include <olectl.h>
#include <cwchar>
#include "tsf_compat.h"
#include "ime_ids.h"
#include "resource.h"

namespace cime::ui {
class InputModeOwner {
public:
    virtual bool EnglishMode() const = 0;
    virtual HRESULT ToggleInputMode() = 0;
protected:
    ~InputModeOwner() = default;
};

// A borrowed owner avoids a service -> item -> service reference cycle. TSF
// calls on the service's apartment; Detach precedes RemoveItem/deactivation.
class InputModeButton final : public ITfLangBarItemButton, public ITfSource {
public:
    InputModeButton(HINSTANCE module, InputModeOwner* owner, volatile LONG* live_objects = nullptr)
        : module_(module), owner_(owner), live_objects_(live_objects), english_(owner && owner->EnglishMode()) {
        if (live_objects_) InterlockedIncrement(live_objects_);
    }
    ~InputModeButton() {
        Detach();
        if (live_objects_) InterlockedDecrement(live_objects_);
    }
    void Detach() {
        owner_ = nullptr;
        ITfLangBarItemSink* sink = sink_; sink_ = nullptr;
        if (sink) sink->Release();
    }
    void ModeChanged() {
        if (!owner_) return;
        english_ = owner_->EnglishMode();
        Notify(TF_LBI_ICON | TF_LBI_TEXT | TF_LBI_TOOLTIP);
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** value) override {
        if (!value) return E_POINTER;
        *value = nullptr;
        if (iid == IID_IUnknown || iid == IID_ITfLangBarItem || iid == IID_ITfLangBarItemButton)
            *value = static_cast<ITfLangBarItemButton*>(this);
        else if (iid == IID_ITfSource) *value = static_cast<ITfSource*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return static_cast<ULONG>(InterlockedIncrement(&references_)); }
    ULONG STDMETHODCALLTYPE Release() override {
        const LONG remaining = InterlockedDecrement(&references_);
        if (!remaining) delete this;
        return static_cast<ULONG>(remaining);
    }
    HRESULT STDMETHODCALLTYPE GetInfo(TF_LANGBARITEMINFO* value) override {
        if (!value) return E_POINTER;
        *value = {};
        value->clsidService = CLSID_CantoneseIME;
        value->guidItem = GUID_LBI_INPUTMODE;
        // Supply the documented alpha-blended white glyph/black outline
        // directly. TEXTCOLORICON requests a monochrome icon; these icons
        // already contain the alpha pixels required by the IME guidelines.
        value->dwStyle = TF_LBI_STYLE_BTN_BUTTON | TF_LBI_STYLE_SHOWNINTRAY;
        std::wcsncpy(value->szDescription, L"Cantonese / English", TF_LBI_DESC_MAXLEN - 1);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStatus(DWORD* value) override {
        if (!value) return E_POINTER;
        *value = (!shown_ ? TF_LBI_STATUS_HIDDEN : 0) | (!owner_ ? TF_LBI_STATUS_DISABLED : 0);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Show(BOOL shown) override {
        if (shown_ != (shown != FALSE)) { shown_ = shown != FALSE; Notify(TF_LBI_STATUS); }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetTooltipString(BSTR* value) override {
        return String(english_ ? L"English mode (Ctrl+Space to switch to Cantonese)"
                               : L"Cantonese mode (Ctrl+Space to switch to English)", value);
    }
    HRESULT STDMETHODCALLTYPE OnClick(TfLBIClick click, POINT, const RECT*) override {
        if (click != TF_LBI_CLK_LEFT) return S_OK;
        return owner_ ? owner_->ToggleInputMode() : TF_E_DISCONNECTED;
    }
    HRESULT STDMETHODCALLTYPE InitMenu(ITfMenu*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE OnMenuSelect(UINT) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetIcon(HICON* value) override {
        if (!value) return E_POINTER;
        // LR_SHARED is deliberately absent: TSF owns and destroys this handle.
        *value = static_cast<HICON>(LoadImageW(module_, MAKEINTRESOURCEW(english_ ? IDI_ENGLISH_MODE : IDI_CANTONESE_MODE),
            IMAGE_ICON, GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), LR_DEFAULTCOLOR));
        return *value ? S_OK : HRESULT_FROM_WIN32(GetLastError());
    }
    HRESULT STDMETHODCALLTYPE GetText(BSTR* value) override { return String(english_ ? L"\x82f1" : L"\x7cb5", value); }
    HRESULT STDMETHODCALLTYPE AdviseSink(REFIID iid, IUnknown* unknown, DWORD* cookie) override {
        if (!cookie) return E_POINTER;
        *cookie = TF_INVALID_COOKIE;
        if (iid != IID_ITfLangBarItemSink) return CONNECT_E_CANNOTCONNECT;
        if (!unknown) return E_INVALIDARG;
        if (sink_) return CONNECT_E_ADVISELIMIT;
        const HRESULT result = unknown->QueryInterface(IID_ITfLangBarItemSink, reinterpret_cast<void**>(&sink_));
        if (SUCCEEDED(result)) {
            // Never reuse a cookie, so delayed UnadviseSink cannot remove a new sink.
            if (++next_cookie_ == TF_INVALID_COOKIE) ++next_cookie_;
            cookie_ = next_cookie_; *cookie = cookie_;
        }
        return result;
    }
    HRESULT STDMETHODCALLTYPE UnadviseSink(DWORD cookie) override {
        if (!sink_ || cookie != cookie_) return CONNECT_E_NOCONNECTION;
        ITfLangBarItemSink* sink = sink_; sink_ = nullptr; sink->Release();
        return S_OK;
    }
private:
    static HRESULT String(const wchar_t* text, BSTR* value) {
        if (!value) return E_POINTER;
        *value = SysAllocString(text); return *value ? S_OK : E_OUTOFMEMORY;
    }
    void Notify(DWORD flags) {
        // A sink may synchronously unadvise while receiving a notification.
        ITfLangBarItemSink* sink = sink_;
        if (sink) { sink->AddRef(); sink->OnUpdate(flags); sink->Release(); }
    }
    HINSTANCE module_;
    InputModeOwner* owner_;
    volatile LONG* live_objects_;
    volatile LONG references_ = 1;
    ITfLangBarItemSink* sink_ = nullptr;
    DWORD cookie_ = TF_INVALID_COOKIE;
    DWORD next_cookie_ = 0;
    bool english_ = false;
    bool shown_ = true;
};
} // namespace cime::ui
