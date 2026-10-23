// Diagnostic TSF application. It observes real input and never supplies target text.
#include <windows.h>
#include <commctrl.h>
#include <msctf.h>
#include "../tsf/tsf_compat.h"
#include <oleauto.h>
#include <richedit.h>
#include <shellapi.h>
#include <tlhelp32.h>
#include <textstor.h>
#include <algorithm>
#include <cstdio>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#if !defined(_M_X64) && !defined(__x86_64__)
#error This acceptance host is AMD64 only.
#endif
static_assert(sizeof(void*) == 8, "AMD64 pointer width required");

namespace {
constexpr wchar_t kClassName[] = L"CantoneseImeNativeTestHost";
constexpr UINT kAttachContext = WM_APP + 1;
constexpr UINT kActivateTarget = WM_APP + 2;
constexpr UINT kDumpCandidate = WM_APP + 3;
constexpr int kEditorId = 100;
constexpr int kActivateId = 101;
constexpr int kEnglishId = 102;
constexpr int kSnapshotId = 103;
constexpr int kBaselineId = 104;

template<class T> class ComPtr {
 public:
  ComPtr() = default;
  ~ComPtr() { reset(); }
  ComPtr(const ComPtr&) = delete;
  ComPtr& operator=(const ComPtr&) = delete;
  T* get() const { return ptr_; }
  T* operator->() const { return ptr_; }
  explicit operator bool() const { return ptr_ != nullptr; }
  T** put() { reset(); return &ptr_; }
  void reset(T* value = nullptr, bool add_ref = false) {
    if (value && add_ref) value->AddRef();
    if (ptr_) ptr_->Release();
    ptr_ = value;
  }
 private:
  T* ptr_ = nullptr;
};

std::string Utf8(const std::wstring& text) {
  if (text.empty()) return {};
  const int bytes = WideCharToMultiByte(CP_UTF8, 0, text.data(),
      static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
  std::string result(static_cast<size_t>(bytes), '\0');
  WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
      result.data(), bytes, nullptr, nullptr);
  return result;
}

std::string Json(const std::string& text) {
  std::ostringstream out;
  out << '"';
  for (const unsigned char ch : text) {
    switch (ch) {
      case '"': out << "\\\""; break;
      case '\\': out << "\\\\"; break;
      case '\n': out << "\\n"; break;
      case '\r': out << "\\r"; break;
      case '\t': out << "\\t"; break;
      default:
        if (ch < 32) out << "\\u" << std::hex << std::setw(4)
                         << std::setfill('0') << static_cast<int>(ch) << std::dec;
        else out << ch;
    }
  }
  out << '"';
  return out.str();
}
std::string Json(const std::wstring& value) { return Json(Utf8(value)); }
std::string Guid(REFGUID value) {
  wchar_t text[40]{};
  StringFromGUID2(value, text, 40);
  return Json(std::wstring(text));
}
std::string Hex(ULONG_PTR value) {
  std::ostringstream out;
  out << "\"0x" << std::hex << value << '"';
  return out.str();
}
std::wstring WindowText(HWND window) {
  const int length = GetWindowTextLengthW(window);
  const int capacity = std::min(length, 32768) + 1;
  std::vector<wchar_t> buffer(static_cast<size_t>(capacity));
  const int copied = GetWindowTextW(window, buffer.data(), capacity);
  return std::wstring(buffer.data(), static_cast<size_t>(std::max(0, copied)));
}

class Logger {
 public:
  bool Open(const std::filesystem::path& path) {
    // CREATE_NEW preserves earlier evidence rather than silently overwriting it.
    file_ = CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                        CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    return file_ != INVALID_HANDLE_VALUE;
  }
  ~Logger() { if (file_ != INVALID_HANDLE_VALUE) CloseHandle(file_); }
  void Write(const std::string& event, const std::string& fields = {}) {
    SYSTEMTIME now{};
    GetSystemTime(&now);
    char stamp[40]{};
    std::snprintf(stamp, sizeof(stamp), "%04u-%02u-%02uT%02u:%02u:%02u.%03uZ", now.wYear,
        now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond, now.wMilliseconds);
    std::string row = "{\"event\":" + Json(event) + ",\"utc\":" + Json(std::string(stamp))
        + ",\"sequence\":" + std::to_string(++sequence_)
        + ",\"pid\":" + std::to_string(GetCurrentProcessId())
        + ",\"tid\":" + std::to_string(GetCurrentThreadId());
    if (!fields.empty()) row += "," + fields;
    row += "}\n";
    DWORD written = 0;
    if (!WriteFile(file_, row.data(), static_cast<DWORD>(row.size()), &written, nullptr)
        || written != row.size()) failed_ = true;
    FlushFileBuffers(file_);
  }
  bool failed() const { return failed_; }
 private:
  HANDLE file_ = INVALID_HANDLE_VALUE;
  unsigned long long sequence_ = 0;
  bool failed_ = false;
};

struct Options {
  CLSID clsid{};
  GUID profile{};
  LANGID language = 0x0c04;
  bool have_clsid = false, have_profile = false, activate = false, register_local = false, probe_com = false;
  std::filesystem::path log;
};

Options ParseOptions() {
  Options opts;
  int argc = 0;
  LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  if (!argv) throw std::runtime_error("Command line unavailable");
  try {
    for (int i = 1; i < argc; ++i) {
      const std::wstring arg = argv[i];
      if (arg == L"--activate") { opts.activate = true; continue; }
      if (arg == L"--register-local-profile") { opts.register_local = true; continue; }
      if (arg == L"--probe-com") { opts.probe_com = true; continue; }
      if (i + 1 == argc) throw std::runtime_error("Missing option value");
      const std::wstring value = argv[++i];
      if (arg == L"--clsid") {
        if (FAILED(CLSIDFromString(value.c_str(), &opts.clsid))) throw std::runtime_error("Invalid CLSID");
        opts.have_clsid = true;
      } else if (arg == L"--profile") {
        if (FAILED(CLSIDFromString(value.c_str(), &opts.profile))) throw std::runtime_error("Invalid profile GUID");
        opts.have_profile = true;
      } else if (arg == L"--langid") {
        size_t consumed = 0;
        const auto id = std::stoul(value, &consumed, 0);
        if (consumed != value.size() || id > 0xffff) throw std::runtime_error("Invalid LANGID");
        opts.language = static_cast<LANGID>(id);
      } else if (arg == L"--log") opts.log = value;
      else throw std::runtime_error("Unknown option");
    }
  } catch (...) { LocalFree(argv); throw; }
  LocalFree(argv);
  if (opts.have_clsid != opts.have_profile) throw std::runtime_error("Supply both CLSID and profile GUID");
  if (opts.activate && !opts.have_profile) throw std::runtime_error("--activate requires profile arguments");
  if (opts.register_local && !opts.have_profile) throw std::runtime_error("Local registration requires profile arguments");
  if (opts.log.empty()) opts.log = L"native-testhost-" + std::to_wstring(GetCurrentProcessId()) + L".jsonl";
  opts.log = std::filesystem::absolute(opts.log);
  return opts;
}

class Host final : public ITfThreadMgrEventSink, public ITfTextEditSink,
                   public ITfUIElementSink {
 public:
  explicit Host(Options options) : opts_(std::move(options)) {}
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** result) override {
    if (!result) return E_POINTER;
    *result = nullptr;
    if (iid == IID_IUnknown || iid == IID_ITfThreadMgrEventSink)
      *result = static_cast<ITfThreadMgrEventSink*>(this);
    else if (iid == IID_ITfTextEditSink) *result = static_cast<ITfTextEditSink*>(this);
    else if (iid == IID_ITfUIElementSink) *result = static_cast<ITfUIElementSink*>(this);
    if (!*result) return E_NOINTERFACE;
    AddRef();
    return S_OK;
  }
  ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
  ULONG STDMETHODCALLTYPE Release() override {
    const ULONG count = InterlockedDecrement(&refs_);
    if (!count) delete this;
    return count;
  }

  bool Initialize(HINSTANCE instance) {
    if (!log_.Open(opts_.log)) return false;
    wchar_t executable[32768]{};
    GetModuleFileNameW(nullptr, executable, 32768);
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(GetModuleHandleW(nullptr));
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(
        reinterpret_cast<const BYTE*>(dos) + dos->e_lfanew);
    log_.Write("host_start", "\"executable\":" + Json(std::wstring(executable))
        + ",\"pe_machine\":" + Hex(nt->FileHeader.Machine)
        + ",\"pointer_bytes\":8,\"target_clsid\":" + Guid(opts_.clsid)
        + ",\"target_profile\":" + Guid(opts_.profile)
        + ",\"target_langid\":" + Hex(opts_.language)
        + ",\"requested_profile_scope\":" + Json(std::string(opts_.register_local ? "local_process" : "pre_registered_profile"))
        + ",\"log\":" + Json(opts_.log.wstring()));
    if (nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64) return false;
    HRESULT hr = CoCreateInstance(CLSID_TF_ThreadMgr, nullptr, CLSCTX_INPROC_SERVER,
        IID_ITfThreadMgr, reinterpret_cast<void**>(thread_mgr_.put()));
    Result("create_thread_manager", hr);
    if (FAILED(hr)) return false;
    hr = thread_mgr_->Activate(&client_id_);
    Result("activate_thread_manager", hr);
    if (FAILED(hr)) return false;
    activated_ = true;
    original_layout_ = GetKeyboardLayout(0);
    ComPtr<ITfThreadMgrEx> extended;
    const HRESULT extended_hr = thread_mgr_->QueryInterface(IID_ITfThreadMgrEx,
        reinterpret_cast<void**>(extended.put()));
    DWORD active_flags = 0;
    const HRESULT flags_hr = extended ? extended->GetActiveFlags(&active_flags) : extended_hr;
    log_.Write("thread_manager_active_flags", "\"hresult\":" + Hex(static_cast<ULONG>(flags_hr))
        + ",\"flags\":" + Hex(active_flags));
    hr = thread_mgr_->QueryInterface(IID_ITfKeystrokeMgr, reinterpret_cast<void**>(keys_.put()));
    Result("query_keystroke_manager", hr);
    if (FAILED(hr)) return false;
    hr = thread_mgr_->QueryInterface(IID_ITfMessagePump, reinterpret_cast<void**>(pump_.put()));
    Result("query_message_pump", hr);
    if (FAILED(hr)) return false;
    thread_mgr_->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(thread_source_.put()));
    if (thread_source_) Result("advise_thread_sink", thread_source_->AdviseSink(
        IID_ITfThreadMgrEventSink, static_cast<ITfThreadMgrEventSink*>(this), &thread_cookie_));
    hr = thread_mgr_->QueryInterface(IID_ITfUIElementMgr, reinterpret_cast<void**>(ui_mgr_.put()));
    Result("query_ui_element_manager", hr);
    if (ui_mgr_) ui_mgr_->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(ui_source_.put()));
    if (ui_source_) Result("advise_ui_sink", ui_source_->AdviseSink(
        IID_ITfUIElementSink, static_cast<ITfUIElementSink*>(this), &ui_cookie_));
    hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
        IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(profiles_.put()));
    Result("create_profile_manager", hr);
    if (!profiles_ && opts_.have_profile) return false;
    if (profiles_) {
      have_original_profile_ = profiles_->GetActiveProfile(GUID_TFCAT_TIP_KEYBOARD, &original_profile_) == S_OK;
    }
    if (opts_.have_profile) LogRequestedProfile("target_profile_before_local_registration");
    if (opts_.register_local) {
      const std::wstring description = L"Cantonese IME native prototype (process-local test)";
      const std::wstring icon_file(executable);
      hr = profiles_->RegisterProfile(opts_.clsid, opts_.language, opts_.profile,
          description.c_str(), static_cast<ULONG>(description.size()),
          icon_file.c_str(), static_cast<ULONG>(icon_file.size()), 0, nullptr, 0,
          TRUE, TF_RP_LOCALPROCESS);
      log_.Write("register_process_local_profile", "\"hresult\":" + Hex(static_cast<ULONG>(hr))
          + ",\"flags\":" + Hex(TF_RP_LOCALPROCESS)
          + ",\"proof_scope\":\"local_process_only\"");
      if (hr != S_OK) return false;
      registered_local_ = true;
      LogRequestedProfile("target_profile_after_local_registration");
    }
    if (opts_.probe_com && opts_.have_clsid) ProbeCom();
    rich_edit_module_ = LoadLibraryW(L"Msftedit.dll");
    if (!rich_edit_module_) { Result("load_msftedit", HRESULT_FROM_WIN32(GetLastError())); return false; }
    WNDCLASSW wc{};
    wc.hInstance = instance; wc.lpfnWndProc = WindowProc; wc.lpszClassName = kClassName;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW); wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return false;
    window_ = CreateWindowExW(0, kClassName, L"Cantonese IME native AMD64 test host",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 1050, 720,
        nullptr, nullptr, instance, this);
    if (!window_) return false;
    ShowWindow(window_, SW_SHOW); UpdateWindow(window_);
    SetFocus(editor_);
    SetTimer(window_, 1, 250, nullptr);
    LogProfile("initial_profile");
    LogModules();
    if (opts_.activate) PostMessageW(window_, kActivateTarget, 0, 0);
    return true;
  }

  int Run() {
    MSG msg{};
    while (true) {
      BOOL more = FALSE;
      const HRESULT hr = pump_ ? pump_->GetMessageW(&msg, nullptr, 0, 0, &more) : E_NOINTERFACE;
      if (!pump_) more = GetMessageW(&msg, nullptr, 0, 0);
      if ((pump_ && FAILED(hr)) || more == -1) { Result("message_pump_error", hr); return 3; }
      if (!more) break;
      bool eaten = false;
      if (msg.message == WM_KEYDOWN || msg.message == WM_KEYUP) {
        last_key_ = static_cast<UINT>(msg.wParam);
        log_.Write("key_received", "\"message\":" + std::to_string(msg.message)
            + ",\"virtual_key\":" + std::to_string(msg.wParam)
            + ",\"editor_focused\":" + (GetFocus() == editor_ ? "true" : "false"));
        BOOL test_eaten = FALSE, actual_eaten = FALSE;
        HRESULT tested = S_FALSE, processed = S_FALSE;
        if (keys_) {
          if (msg.message == WM_KEYDOWN) {
            tested = keys_->TestKeyDown(msg.wParam, msg.lParam, &test_eaten);
            if (tested == S_OK && test_eaten) processed = keys_->KeyDown(msg.wParam, msg.lParam, &actual_eaten);
          } else {
            tested = keys_->TestKeyUp(msg.wParam, msg.lParam, &test_eaten);
            if (tested == S_OK && test_eaten) processed = keys_->KeyUp(msg.wParam, msg.lParam, &actual_eaten);
          }
        }
        eaten = processed == S_OK && actual_eaten;
        log_.Write("key_message", "\"message\":" + std::to_string(msg.message)
            + ",\"virtual_key\":" + std::to_string(msg.wParam)
            + ",\"lparam\":" + Hex(static_cast<ULONG_PTR>(msg.lParam))
            + ",\"editor_focused\":" + (GetFocus() == editor_ ? "true" : "false")
            + ",\"test_hresult\":" + Hex(static_cast<ULONG>(tested))
            + ",\"key_hresult\":" + Hex(static_cast<ULONG>(processed))
            + ",\"eaten\":" + (eaten ? "true" : "false"));
      }
      if (!eaten) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    }
    return log_.failed() ? 4 : 0;
  }

  void Shutdown() {
    shutting_down_ = true;
    DetachContext();
    if (ui_source_ && ui_cookie_ != TF_INVALID_COOKIE) ui_source_->UnadviseSink(ui_cookie_);
    if (thread_source_ && thread_cookie_ != TF_INVALID_COOKIE) thread_source_->UnadviseSink(thread_cookie_);
    ui_cookie_ = thread_cookie_ = TF_INVALID_COOKIE;
    if (profiles_ && changed_profile_ && have_original_profile_) {
      ChangeLanguage(original_profile_.langid);
      Result("restore_original_profile", profiles_->ActivateProfile(original_profile_.dwProfileType,
          original_profile_.langid, original_profile_.clsid, original_profile_.guidProfile,
          original_profile_.hkl, 0));
    } else if (changed_profile_ && original_layout_) {
      ChangeLanguage(LOWORD(reinterpret_cast<ULONG_PTR>(original_layout_)));
      const HKL previous = ActivateKeyboardLayout(original_layout_, 0);
      log_.Write("restore_original_hkl", "\"previous_hkl\":" + Hex(reinterpret_cast<ULONG_PTR>(previous)));
    }
    if (profiles_ && registered_local_) {
      const HRESULT hr = profiles_->UnregisterProfile(opts_.clsid, opts_.language,
          opts_.profile, TF_URP_LOCALPROCESS);
      log_.Write("unregister_process_local_profile", "\"hresult\":" + Hex(static_cast<ULONG>(hr))
          + ",\"flags\":" + Hex(TF_URP_LOCALPROCESS));
      registered_local_ = false;
    }
    if (thread_mgr_ && activated_) Result("deactivate_thread_manager", thread_mgr_->Deactivate());
    activated_ = false;
    ui_source_.reset(); ui_mgr_.reset(); thread_source_.reset(); keys_.reset(); pump_.reset();
    profiles_.reset(); thread_mgr_.reset();
    if (window_ && IsWindow(window_)) DestroyWindow(window_);
    window_ = editor_ = nullptr;
    if (rich_edit_module_) { FreeLibrary(rich_edit_module_); rich_edit_module_ = nullptr; }
    log_.Write("host_stop", "\"log_write_failed\":" + std::string(log_.failed() ? "true" : "false"));
  }

  HRESULT STDMETHODCALLTYPE OnInitDocumentMgr(ITfDocumentMgr*) override { return S_OK; }
  HRESULT STDMETHODCALLTYPE OnUninitDocumentMgr(ITfDocumentMgr*) override { QueueAttach(); return S_OK; }
  HRESULT STDMETHODCALLTYPE OnSetFocus(ITfDocumentMgr*, ITfDocumentMgr*) override { QueueAttach(); return S_OK; }
  HRESULT STDMETHODCALLTYPE OnPushContext(ITfContext*) override { QueueAttach(); return S_OK; }
  HRESULT STDMETHODCALLTYPE OnPopContext(ITfContext*) override { QueueAttach(); return S_OK; }

  HRESULT STDMETHODCALLTYPE OnEndEdit(ITfContext* context, TfEditCookie cookie, ITfEditRecord*) override {
    ComPtr<ITfContextComposition> composition;
    context->QueryInterface(IID_ITfContextComposition, reinterpret_cast<void**>(composition.put()));
    ComPtr<IEnumITfCompositionView> enumerator;
    HRESULT enumeration = composition ? composition->EnumCompositions(enumerator.put()) : E_NOINTERFACE;
    std::string ranges = "[";
    ULONG count = 0;
    if (enumerator) {
      while (count < 16) {
        ComPtr<ITfCompositionView> view;
        ULONG fetched = 0;
        if (enumerator->Next(1, view.put(), &fetched) != S_OK || fetched != 1) break;
        ComPtr<ITfRange> range;
        const HRESULT range_hr = view->GetRange(range.put());
        wchar_t buffer[4096]{}; ULONG copied = 0;
        HRESULT text_hr = range ? range->GetText(cookie, 0, buffer, 4095, &copied) : range_hr;
        CLSID owner{}; view->GetOwnerClsid(&owner);
        if (count) ranges += ',';
        ranges += "{\"text\":" + Json(std::wstring(buffer, copied)) + ",\"owner_clsid\":" + Guid(owner)
            + ",\"get_text_hresult\":" + Hex(static_cast<ULONG>(text_hr))
            + ",\"text_observation_capped\":" + (copied == 4095 ? "true" : "false") + "}";
        ++count;
      }
    }
    ranges += ']';
    ComPtr<ITfRange> start, end;
    std::wstring document;
    HRESULT text_hr = context->GetStart(cookie, start.put());
    if (SUCCEEDED(text_hr)) text_hr = context->GetEnd(cookie, end.put());
    if (SUCCEEDED(text_hr)) text_hr = start->ShiftEndToRange(cookie, end.get(), TF_ANCHOR_END);
    if (SUCCEEDED(text_hr)) {
      wchar_t text[8192]{}; ULONG copied = 0;
      text_hr = start->GetText(cookie, 0, text, 8191, &copied);
      document.assign(text, copied);
    }
    log_.Write("tsf_end_edit", "\"document_text\":" + Json(document)
        + ",\"document_get_text_hresult\":" + Hex(static_cast<ULONG>(text_hr))
        + ",\"document_observation_capped\":" + (document.size() == 8191 ? "true" : "false")
        + ",\"composition_enum_hresult\":" + Hex(static_cast<ULONG>(enumeration))
        + ",\"composition_count\":" + std::to_string(count) + ",\"compositions\":" + ranges
        + ",\"composition_observation_capped\":" + (count == 16 ? "true" : "false")
        + ",\"last_virtual_key\":" + std::to_string(last_key_));
    if (previous_compositions_ > 0 && count == 0) {
      log_.Write("composition_ended", "\"document_text\":" + Json(document)
          + ",\"last_virtual_key\":" + std::to_string(last_key_)
          + ",\"interpretation\":\"Compare baseline and key events; this event alone does not classify commit versus cancel.\"");
    }
    previous_compositions_ = count;
    return S_OK;
  }

  HRESULT STDMETHODCALLTYPE BeginUIElement(DWORD id, BOOL* show) override {
    if (!show) return E_POINTER;
    *show = TRUE; // Preserve the TIP's real candidate window for visual evidence.
    log_.Write("candidate_ui_begin", "\"id\":" + std::to_string(id) + ",\"show_native_ui\":true");
    if (window_) PostMessageW(window_, kDumpCandidate, id, 0);
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE UpdateUIElement(DWORD id) override { DumpCandidate(id); return S_OK; }
  HRESULT STDMETHODCALLTYPE EndUIElement(DWORD id) override {
    log_.Write("candidate_ui_end", "\"id\":" + std::to_string(id)); return S_OK;
  }

 private:
  ~Host() = default;
  void Result(const std::string& event, HRESULT hr) {
    log_.Write(event, "\"hresult\":" + Hex(static_cast<ULONG>(hr)));
  }
  void QueueAttach() { if (window_ && !shutting_down_) PostMessageW(window_, kAttachContext, 0, 0); }
  void DetachContext() {
    if (context_source_ && context_cookie_ != TF_INVALID_COOKIE) context_source_->UnadviseSink(context_cookie_);
    context_cookie_ = TF_INVALID_COOKIE;
    context_source_.reset(); context_.reset(); previous_compositions_ = 0;
  }
  void AttachContext() {
    if (!thread_mgr_ || shutting_down_) return;
    ComPtr<ITfDocumentMgr> document;
    ComPtr<ITfContext> current;
    if (SUCCEEDED(thread_mgr_->GetFocus(document.put())) && document) document->GetTop(current.put());
    if (current.get() == context_.get()) return;
    DetachContext();
    if (!current) return;
    context_.reset(current.get(), true);
    context_->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(context_source_.put()));
    HRESULT hr = context_source_ ? context_source_->AdviseSink(IID_ITfTextEditSink,
        static_cast<ITfTextEditSink*>(this), &context_cookie_) : E_NOINTERFACE;
    TF_STATUS status{};
    const HRESULT status_hr = context_->GetStatus(&status);
    log_.Write("context_attached", "\"advise_hresult\":" + Hex(static_cast<ULONG>(hr))
        + ",\"status_hresult\":" + Hex(static_cast<ULONG>(status_hr))
        + ",\"static_flags\":" + Hex(status.dwStaticFlags)
        + ",\"dynamic_flags\":" + Hex(status.dwDynamicFlags)
        + ",\"transitory\":" + ((status.dwStaticFlags & TS_SS_TRANSITORY) ? "true" : "false"));
  }
  void DumpCandidate(DWORD id) {
    if (!ui_mgr_) return;
    ComPtr<ITfUIElement> ui;
    HRESULT hr = ui_mgr_->GetUIElement(id, ui.put());
    ComPtr<ITfCandidateListUIElement> list;
    if (ui) hr = ui->QueryInterface(IID_ITfCandidateListUIElement, reinterpret_cast<void**>(list.put()));
    if (!list) { log_.Write("candidate_ui_nonlist", "\"id\":" + std::to_string(id)
        + ",\"hresult\":" + Hex(static_cast<ULONG>(hr))); return; }
    UINT count = 0, selected = 0;
    const HRESULT count_hr = list->GetCount(&count);
    const HRESULT selected_hr = list->GetSelection(&selected);
    std::string strings = "[";
    for (UINT i = 0; i < std::min(count, 90U); ++i) {
      BSTR text = nullptr;
      HRESULT item_hr = list->GetString(i, &text);
      if (i) strings += ',';
      strings += "{\"index\":" + std::to_string(i) + ",\"hresult\":" + Hex(static_cast<ULONG>(item_hr))
          + ",\"text\":" + Json(text ? std::wstring(text, SysStringLen(text)) : std::wstring()) + "}";
      if (text) SysFreeString(text);
    }
    strings += ']';
    log_.Write("candidate_list", "\"id\":" + std::to_string(id)
        + ",\"count\":" + std::to_string(count) + ",\"selection\":" + std::to_string(selected)
        + ",\"count_hresult\":" + Hex(static_cast<ULONG>(count_hr))
        + ",\"selection_hresult\":" + Hex(static_cast<ULONG>(selected_hr))
        + ",\"candidates\":" + strings);
  }
  void ChangeLanguage(LANGID language) {
    ComPtr<ITfInputProcessorProfiles> legacy;
    HRESULT hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
        IID_ITfInputProcessorProfiles, reinterpret_cast<void**>(legacy.put()));
    LANGID before = 0, after = 0;
    if (legacy) legacy->GetCurrentLanguage(&before);
    if (SUCCEEDED(hr)) hr = legacy->ChangeCurrentLanguage(language);
    if (legacy) legacy->GetCurrentLanguage(&after);
    if (hr == S_OK) changed_profile_ = true;
    log_.Write("change_current_thread_language", "\"hresult\":" + Hex(static_cast<ULONG>(hr))
        + ",\"requested_langid\":" + Hex(language) + ",\"before_langid\":" + Hex(before)
        + ",\"after_langid\":" + Hex(after));
  }
  void ActivateTarget() {
    SetFocus(editor_);
    if (!profiles_ || !opts_.have_profile) return;
    ChangeLanguage(opts_.language);
    LogRequestedProfile("target_profile_before_activation");
    // Process-local registration is explicit; never enable/persist a user profile or use FORSESSION.
    const DWORD flags = registered_local_ ? TF_IPPMF_FORPROCESS : 0;
    const HRESULT hr = profiles_->ActivateProfile(TF_PROFILETYPE_INPUTPROCESSOR,
        opts_.language, opts_.clsid, opts_.profile, nullptr, flags);
    if (hr == S_OK) changed_profile_ = true;
    log_.Write("activate_target_profile", "\"hresult\":" + Hex(static_cast<ULONG>(hr))
        + ",\"flags\":" + Hex(flags)
        + ",\"proof_scope\":" + Json(std::string(registered_local_ ? "local_process_only" : "pre_registered_profile")));
    AttachContext(); LogProfile("profile_after_target_activation");
    LogRequestedProfile("target_profile_after_activation");
    Snapshot("after_target_activation"); LogModules();
  }
  void ActivateEnglish() {
    SetFocus(editor_);
    const int count = GetKeyboardLayoutList(0, nullptr);
    std::vector<HKL> layouts(static_cast<size_t>(std::max(0, count)));
    if (count > 0) GetKeyboardLayoutList(count, layouts.data());
    for (HKL layout : layouts) {
      const LANGID language = LOWORD(reinterpret_cast<ULONG_PTR>(layout));
      if (PRIMARYLANGID(language) != LANG_ENGLISH) continue;
      ChangeLanguage(language);
      const HRESULT hr = profiles_ ? profiles_->ActivateProfile(TF_PROFILETYPE_KEYBOARDLAYOUT,
          language, CLSID_NULL, GUID_NULL, layout, 0) : E_NOINTERFACE;
      if (hr == S_OK) changed_profile_ = true;
      Result("activate_existing_english_layout", hr);
      LogProfile("profile_after_english_activation"); return;
    }
    log_.Write("english_layout_unavailable", "\"note\":\"No installed English HKL found; use Windows input selector.\"");
  }
  void LogProfile(const std::string& event) {
    TF_INPUTPROCESSORPROFILE profile{};
    const HRESULT hr = profiles_ ? profiles_->GetActiveProfile(GUID_TFCAT_TIP_KEYBOARD, &profile) : E_NOINTERFACE;
    log_.Write(event, "\"hresult\":" + Hex(static_cast<ULONG>(hr))
        + ",\"requested_category\":" + Guid(GUID_TFCAT_TIP_KEYBOARD)
        + ",\"type\":" + std::to_string(profile.dwProfileType)
        + ",\"langid\":" + Hex(profile.langid) + ",\"clsid\":" + Guid(profile.clsid)
        + ",\"profile\":" + Guid(profile.guidProfile)
        + ",\"category\":" + Guid(profile.catid) + ",\"flags\":" + Hex(profile.dwFlags)
        + ",\"caps\":" + Hex(profile.dwCaps)
        + ",\"hkl\":" + Hex(reinterpret_cast<ULONG_PTR>(GetKeyboardLayout(0))));
  }
  void LogRequestedProfile(const std::string& event) {
    TF_INPUTPROCESSORPROFILE profile{};
    const HRESULT hr = profiles_ ? profiles_->GetProfile(TF_PROFILETYPE_INPUTPROCESSOR,
        opts_.language, opts_.clsid, opts_.profile, nullptr, &profile) : E_NOINTERFACE;
    log_.Write(event, "\"hresult\":" + Hex(static_cast<ULONG>(hr))
        + ",\"requested_langid\":" + Hex(opts_.language)
        + ",\"requested_clsid\":" + Guid(opts_.clsid)
        + ",\"requested_profile\":" + Guid(opts_.profile)
        + ",\"type\":" + std::to_string(profile.dwProfileType)
        + ",\"langid\":" + Hex(profile.langid) + ",\"clsid\":" + Guid(profile.clsid)
        + ",\"profile\":" + Guid(profile.guidProfile) + ",\"category\":" + Guid(profile.catid)
        + ",\"flags\":" + Hex(profile.dwFlags) + ",\"caps\":" + Hex(profile.dwCaps));
    if (hr == S_OK && profile.catid != GUID_NULL) {
      TF_INPUTPROCESSORPROFILE active{};
      const HRESULT active_hr = profiles_->GetActiveProfile(profile.catid, &active);
      log_.Write("active_target_category_profile", "\"reason\":" + Json(event)
          + ",\"hresult\":" + Hex(static_cast<ULONG>(active_hr))
          + ",\"requested_category\":" + Guid(profile.catid)
          + ",\"type\":" + std::to_string(active.dwProfileType)
          + ",\"langid\":" + Hex(active.langid) + ",\"clsid\":" + Guid(active.clsid)
          + ",\"profile\":" + Guid(active.guidProfile)
          + ",\"category\":" + Guid(active.catid) + ",\"flags\":" + Hex(active.dwFlags)
          + ",\"caps\":" + Hex(active.dwCaps));
    }
  }
  void ProbeCom() {
    // Optional load-only diagnostic. Deliberately never calls Activate/ActivateEx.
    ComPtr<ITfTextInputProcessorEx> processor;
    const HRESULT hr = CoCreateInstance(opts_.clsid, nullptr, CLSCTX_INPROC_SERVER,
        IID_ITfTextInputProcessorEx, reinterpret_cast<void**>(processor.put()));
    log_.Write("com_load_probe", "\"hresult\":" + Hex(static_cast<ULONG>(hr))
        + ",\"requested_clsid\":" + Guid(opts_.clsid)
        + ",\"service_activate_called\":false,\"diagnostic_only\":true");
  }
  void Snapshot(const std::string& reason) {
    if (!editor_) return;
    const std::wstring text = WindowText(editor_);
    CHARRANGE selection{};
    SendMessageW(editor_, EM_EXGETSEL, 0, reinterpret_cast<LPARAM>(&selection));
    log_.Write("document_snapshot", "\"reason\":" + Json(reason) + ",\"text\":" + Json(text)
        + ",\"window_text_length\":" + std::to_string(GetWindowTextLengthW(editor_))
        + ",\"snapshot_capped\":" + (text.size() == 32768 ? "true" : "false")
        + ",\"selection_start\":" + std::to_string(selection.cpMin)
        + ",\"selection_end\":" + std::to_string(selection.cpMax));
    if (status_) {
      std::wstring message = L"PID " + std::to_wstring(GetCurrentProcessId())
          + L" | AMD64 | TSF compositions observed: " + std::to_wstring(previous_compositions_)
          + L"\r\nLog: " + opts_.log.wstring() + L"\r\nLast document snapshot: " + text;
      SetWindowTextW(status_, message.c_str());
    }
  }
  void LogModules() {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
    if (snapshot == INVALID_HANDLE_VALUE) { Result("module_snapshot_error", HRESULT_FROM_WIN32(GetLastError())); return; }
    MODULEENTRY32W entry{}; entry.dwSize = sizeof(entry);
    if (Module32FirstW(snapshot, &entry)) do {
      log_.Write("loaded_module", "\"name\":" + Json(std::wstring(entry.szModule))
          + ",\"path\":" + Json(std::wstring(entry.szExePath))
          + ",\"base\":" + Hex(reinterpret_cast<ULONG_PTR>(entry.modBaseAddr))
          + ",\"size\":" + std::to_string(entry.modBaseSize));
    } while (Module32NextW(snapshot, &entry));
    CloseHandle(snapshot);
  }
  bool CreateControls(HWND window, HINSTANCE instance) {
    const HFONT font = static_cast<HFONT>(GetStockObject(DEFAULT_GUI_FONT));
    header_ = CreateWindowW(L"STATIC", L"Native AMD64 TSF acceptance host. Type ASCII keys into the large editor. Candidate windows remain visible.",
        WS_CHILD | WS_VISIBLE, 12, 10, 1000, 32, window, nullptr, instance, nullptr);
    const std::pair<int, const wchar_t*> buttons[] = {{kActivateId,L"Activate target IME"},
        {kEnglishId,L"Switch to English"},{kSnapshotId,L"Snapshot + modules"},{kBaselineId,L"Mark cancel baseline"}};
    int left = 12;
    for (const auto& item : buttons) {
      // A clickable STATIC does not steal focus and terminate the composition being observed.
      HWND button = CreateWindowW(L"STATIC", item.second, WS_CHILD | WS_VISIBLE | WS_BORDER | SS_NOTIFY | SS_CENTER | SS_CENTERIMAGE,
          left, 44, 190, 32, window, reinterpret_cast<HMENU>(static_cast<INT_PTR>(item.first)), instance, nullptr);
      SendMessageW(button, WM_SETFONT, reinterpret_cast<WPARAM>(font), TRUE);
      if (item.first == kActivateId && !opts_.have_profile) EnableWindow(button, FALSE);
      left += 200;
    }
    editor_ = CreateWindowExW(WS_EX_CLIENTEDGE, MSFTEDIT_CLASS, L"",
        WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | ES_MULTILINE | ES_AUTOVSCROLL | ES_WANTRETURN,
        12, 88, 1000, 390, window, reinterpret_cast<HMENU>(kEditorId), instance, nullptr);
    if (!editor_) { Result("create_editor_failed", HRESULT_FROM_WIN32(GetLastError())); return false; }
    SendMessageW(editor_, EM_SETEDITSTYLE, SES_USECTF, SES_USECTF);
    SendMessageW(editor_, EM_SETEVENTMASK, 0, ENM_CHANGE | ENM_SELCHANGE);
    SendMessageW(editor_, EM_EXLIMITTEXT, 0, 32768);
    SendMessageW(editor_, WM_SETFONT, reinterpret_cast<WPARAM>(font), TRUE);
    SetWindowSubclass(editor_, EditorProc, 1, reinterpret_cast<DWORD_PTR>(this));
    status_ = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"Observations are evidence, not an automatic pass.",
        WS_CHILD | WS_VISIBLE | WS_VSCROLL | ES_MULTILINE | ES_READONLY,
        12, 490, 1000, 160, window, nullptr, instance, nullptr);
    SendMessageW(status_, WM_SETFONT, reinterpret_cast<WPARAM>(font), TRUE);
    log_.Write("editor_created", "\"class\":\"RICHEDIT50W\",\"edit_style\":"
        + Hex(static_cast<ULONG_PTR>(SendMessageW(editor_, EM_GETEDITSTYLE, 0, 0)))
        + ",\"ses_usectf\":" + ((SendMessageW(editor_, EM_GETEDITSTYLE, 0, 0) & SES_USECTF) ? "true" : "false"));
    return true;
  }
  static LRESULT CALLBACK EditorProc(HWND window, UINT message, WPARAM wp, LPARAM lp,
                                     UINT_PTR, DWORD_PTR data) {
    auto* self = reinterpret_cast<Host*>(data);
    if (message == WM_PASTE || message == WM_SETTEXT || message == EM_REPLACESEL
        || message == WM_IME_STARTCOMPOSITION || message == WM_IME_ENDCOMPOSITION
        || message == WM_IME_COMPOSITION || message == WM_CHAR) {
      self->log_.Write("editor_message", "\"message\":" + std::to_string(message)
          + ",\"wparam\":" + Hex(wp) + ",\"lparam\":" + Hex(static_cast<ULONG_PTR>(lp))
          + ",\"note\":\"Observed message; not proof of physical versus injected origin.\"");
    }
    return DefSubclassProc(window, message, wp, lp);
  }
  static LRESULT CALLBACK WindowProc(HWND window, UINT message, WPARAM wp, LPARAM lp) {
    auto* self = reinterpret_cast<Host*>(GetWindowLongPtrW(window, GWLP_USERDATA));
    if (message == WM_NCCREATE) {
      self = static_cast<Host*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
      SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
      self->window_ = window;
    }
    if (!self) return DefWindowProcW(window, message, wp, lp);
    switch (message) {
      case WM_CREATE: return self->CreateControls(window, reinterpret_cast<CREATESTRUCTW*>(lp)->hInstance) ? 0 : -1;
      case WM_SIZE: {
        const int width = LOWORD(lp), height = HIWORD(lp);
        if (self->editor_) MoveWindow(self->editor_, 12, 88, std::max(100,width-24), std::max(100,height-280), TRUE);
        if (self->status_) MoveWindow(self->status_, 12, std::max(200,height-180), std::max(100,width-24), 165, TRUE);
        return 0;
      }
      case WM_COMMAND:
        if (LOWORD(wp) == kEditorId && HIWORD(wp) == EN_CHANGE) self->Snapshot("EN_CHANGE");
        else if (LOWORD(wp) == kActivateId) self->ActivateTarget();
        else if (LOWORD(wp) == kEnglishId) self->ActivateEnglish();
        else if (LOWORD(wp) == kSnapshotId) { self->Snapshot("manual_snapshot"); self->LogProfile("manual_profile"); self->LogModules(); SetFocus(self->editor_); }
        else if (LOWORD(wp) == kBaselineId) { self->Snapshot("cancel_baseline"); SetFocus(self->editor_); }
        return 0;
      case WM_TIMER: self->AttachContext(); return 0;
      case kAttachContext: self->AttachContext(); return 0;
      case kActivateTarget: self->ActivateTarget(); return 0;
      case kDumpCandidate: self->DumpCandidate(static_cast<DWORD>(wp)); return 0;
      case WM_INPUTLANGCHANGE: self->LogProfile("input_language_changed"); break;
      case WM_SETFOCUS: if (self->editor_) SetFocus(self->editor_); return 0;
      case WM_CLOSE: self->Snapshot("window_close"); DestroyWindow(window); return 0;
      case WM_DESTROY: KillTimer(window, 1); self->window_ = nullptr; PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(window, message, wp, lp);
  }

  volatile LONG refs_ = 1;
  Options opts_;
  Logger log_;
  HWND window_ = nullptr, editor_ = nullptr, header_ = nullptr, status_ = nullptr;
  HMODULE rich_edit_module_ = nullptr;
  ComPtr<ITfThreadMgr> thread_mgr_;
  ComPtr<ITfKeystrokeMgr> keys_;
  ComPtr<ITfMessagePump> pump_;
  ComPtr<ITfInputProcessorProfileMgr> profiles_;
  ComPtr<ITfSource> thread_source_, ui_source_, context_source_;
  ComPtr<ITfUIElementMgr> ui_mgr_;
  ComPtr<ITfContext> context_;
  DWORD thread_cookie_ = TF_INVALID_COOKIE, ui_cookie_ = TF_INVALID_COOKIE, context_cookie_ = TF_INVALID_COOKIE;
  TfClientId client_id_ = TF_CLIENTID_NULL;
  bool activated_ = false, shutting_down_ = false, changed_profile_ = false, have_original_profile_ = false;
  bool registered_local_ = false;
  TF_INPUTPROCESSORPROFILE original_profile_{};
  HKL original_layout_ = nullptr;
  ULONG previous_compositions_ = 0;
  UINT last_key_ = 0;
};
} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int) {
  SetProcessDPIAware();
  const HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  if (FAILED(com)) { MessageBoxW(nullptr, L"COM STA initialization failed.", L"Native test host", MB_ICONERROR); return 2; }
  int result = 2;
  Host* host = nullptr;
  try {
    host = new Host(ParseOptions());
    if (host->Initialize(instance)) result = host->Run();
    else MessageBoxW(nullptr, L"Host initialization failed. Check the new JSONL log or choose a new --log filename.", L"Native test host", MB_ICONERROR);
  } catch (const std::exception&) {
    MessageBoxW(nullptr, L"Use --clsid {GUID} --profile {GUID} --langid 0x0c04 --log NEWFILE [--activate] [--register-local-profile]. Local registration is process-scoped only.", L"Native test host arguments", MB_ICONERROR);
  }
  if (host) { host->Shutdown(); host->Release(); }
  CoUninitialize();
  return result;
}
