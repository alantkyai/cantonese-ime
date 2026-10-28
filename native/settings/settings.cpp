// Cantonese IME Settings: edits the per-user custom phrases/spellings
// (custom.txt) and the candidate font/size in appearance.ini. A separate
// process, so no dialog ever opens inside a host application. It only reads
// and writes those two files under %LOCALAPPDATA%\CantoneseIME.
#include <windows.h>
#include <commctrl.h>
#include <algorithm>
#include <set>
#include <string>
#include <vector>
#include "settings_model.h"

namespace {
using namespace cime::settings;

constexpr wchar_t kWindowClass[] = L"CantoneseImeSettingsWindow";
constexpr wchar_t kTitle[] = L"\u7cb5\u8a9e\u8f38\u5165\u6cd5\u8a2d\u5b9a";
constexpr wchar_t kBundledFamily[] = L"LXGW WenKai TC";

enum : int {
    IDC_TABS = 100, IDC_STATUS, IDC_SAVE, IDC_CLOSE,
    IDC_PHRASE_LIST = 200, IDC_PHRASE_KEY_LABEL, IDC_PHRASE_KEY, IDC_PHRASE_TEXT_LABEL, IDC_PHRASE_TEXT,
    IDC_PHRASE_ADD, IDC_PHRASE_UPDATE, IDC_PHRASE_DELETE, IDC_PHRASE_HINT,
    IDC_ALIAS_LIST = 300, IDC_ALIAS_KEY_LABEL, IDC_ALIAS_KEY, IDC_ALIAS_TARGET_LABEL, IDC_ALIAS_TARGET,
    IDC_ALIAS_ADD, IDC_ALIAS_UPDATE, IDC_ALIAS_DELETE, IDC_ALIAS_HINT,
    IDC_FONT_LABEL = 400, IDC_FONT, IDC_SIZE_LABEL, IDC_FONT_SIZE, IDC_PREVIEW_LABEL, IDC_PREVIEW, IDC_FONT_HINT,
};

struct Page {
    int list, key_label, key, value_label, value, add, update, remove, hint;
    LineKind kind;
};
const Page kPages[2] = {
    {IDC_PHRASE_LIST, IDC_PHRASE_KEY_LABEL, IDC_PHRASE_KEY, IDC_PHRASE_TEXT_LABEL, IDC_PHRASE_TEXT,
     IDC_PHRASE_ADD, IDC_PHRASE_UPDATE, IDC_PHRASE_DELETE, IDC_PHRASE_HINT, LineKind::Phrase},
    {IDC_ALIAS_LIST, IDC_ALIAS_KEY_LABEL, IDC_ALIAS_KEY, IDC_ALIAS_TARGET_LABEL, IDC_ALIAS_TARGET,
     IDC_ALIAS_ADD, IDC_ALIAS_UPDATE, IDC_ALIAS_DELETE, IDC_ALIAS_HINT, LineKind::Alias},
};

struct State {
    HWND window = nullptr;
    UINT dpi = 96;
    HFONT ui_font = nullptr, preview_font = nullptr;
    std::wstring custom_path, appearance_path, bundled_font_file;
    std::string custom_loaded;      // Bytes read at load/save, to detect outside edits.
    CustomDocument custom;
    std::wstring font_family;       // Empty: bundled default.
    int font_size = 0;              // 0: default 20.
    bool custom_dirty = false, font_dirty = false, bundled_loaded = false;
    int tab = 0;
} g;

int Scale(int value) { return MulDiv(value, static_cast<int>(g.dpi), 96); }
HWND Item(int id) { return GetDlgItem(g.window, id); }
std::wstring Text(int id) {
    const int length = GetWindowTextLengthW(Item(id));
    std::wstring value(static_cast<std::size_t>(length) + 1, L'\0');
    GetWindowTextW(Item(id), value.data(), length + 1);
    value.resize(static_cast<std::size_t>(length));
    return value;
}
void SetStatus(const std::wstring& text) { SetWindowTextW(Item(IDC_STATUS), text.c_str()); }
void UpdateTitle() {
    std::wstring title = kTitle;
    if (g.custom_dirty || g.font_dirty) title += L" *";
    SetWindowTextW(g.window, title.c_str());
}

HWND Create(const wchar_t* type, const wchar_t* text, DWORD style, int id, DWORD ex_style = 0) {
    HWND control = CreateWindowExW(ex_style, type, text, WS_CHILD | style, 0, 0, 0, 0, g.window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), GetModuleHandleW(nullptr), nullptr);
    if (g.ui_font) SendMessageW(control, WM_SETFONT, reinterpret_cast<WPARAM>(g.ui_font), FALSE);
    return control;
}

void CreateUiFont() {
    if (g.ui_font) DeleteObject(g.ui_font);
    g.ui_font = CreateFontW(-MulDiv(9, static_cast<int>(g.dpi), 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Microsoft JhengHei UI");
    for (HWND child = GetWindow(g.window, GW_CHILD); child; child = GetWindow(child, GW_HWNDNEXT))
        if (GetDlgCtrlID(child) != IDC_PREVIEW) SendMessageW(child, WM_SETFONT, reinterpret_cast<WPARAM>(g.ui_font), TRUE);
}

// ---- Custom phrases and spellings ----
void FillList(const Page& page) {
    HWND list = Item(page.list);
    SendMessageW(list, WM_SETREDRAW, FALSE, 0);
    ListView_DeleteAllItems(list);
    int row = 0;
    for (std::size_t index : Entries(g.custom, page.kind)) {
        const auto& line = g.custom.lines[index];
        LVITEMW item{}; item.mask = LVIF_TEXT | LVIF_PARAM; item.iItem = row;
        item.pszText = const_cast<wchar_t*>(line.key.c_str()); item.lParam = static_cast<LPARAM>(index);
        ListView_InsertItem(list, &item);
        ListView_SetItemText(list, row, 1, const_cast<wchar_t*>(line.value.c_str()));
        ++row;
    }
    SendMessageW(list, WM_SETREDRAW, TRUE, 0);
    InvalidateRect(list, nullptr, TRUE);
}
long SelectedLine(const Page& page) {
    HWND list = Item(page.list);
    const int row = ListView_GetNextItem(list, -1, LVNI_SELECTED);
    if (row < 0) return -1;
    LVITEMW item{}; item.mask = LVIF_PARAM; item.iItem = row;
    return ListView_GetItem(list, &item) ? static_cast<long>(item.lParam) : -1;
}
void SelectLine(const Page& page, std::size_t index) {
    HWND list = Item(page.list);
    for (int row = 0, count = ListView_GetItemCount(list); row < count; ++row) {
        LVITEMW item{}; item.mask = LVIF_PARAM; item.iItem = row;
        if (ListView_GetItem(list, &item) && static_cast<std::size_t>(item.lParam) == index) {
            ListView_SetItemState(list, row, LVIS_SELECTED | LVIS_FOCUSED, LVIS_SELECTED | LVIS_FOCUSED);
            ListView_EnsureVisible(list, row, FALSE);
        }
    }
}
bool ReadEntry(const Page& page, std::wstring& key, std::wstring& value) {
    key = AsciiLower(Trim(Text(page.key)));
    value = Trim(Text(page.value));
    if (page.kind == LineKind::Alias) value = AsciiLower(value);
    if (!ValidKey(key)) { SetStatus(page.kind == LineKind::Phrase
        ? L"\u8f38\u5165\u8981\u4fc2 1 \u81f3 32 \u500b\u82f1\u6587\u5b57\u6bcd\uff0c\u4f8b\u5982 hh\u3002" : L"\u62fc\u6cd5\u8981\u4fc2 1 \u81f3 32 \u500b\u82f1\u6587\u5b57\u6bcd\uff0c\u4f8b\u5982 moon\u3002"); SetFocus(Item(page.key)); return false; }
    if (page.kind == LineKind::Phrase && !ValidPhrase(value)) {
        SetStatus(L"\u6587\u5b57\u5514\u53ef\u4ee5\u7559\u7a7a\uff0c\u6700\u591a 64 \u500b\u5b57\uff0c\u4ea6\u5514\u53ef\u4ee5\u6709\u300c=\u300d\u3002"); SetFocus(Item(page.value)); return false; }
    if (page.kind == LineKind::Alias && !ValidTarget(value)) {
        SetStatus(L"\u53f3\u908a\u8981\u4fc2 1 \u81f3 12 \u500b\u82f1\u6587\u5b57\u6bcd\uff1a\u7cb5\u62fc\uff08\u4f8b\u5982 mun\uff09\u6216\u8005\u5df2\u8b58\u5605\u62fc\u6cd5\uff08\u4f8b\u5982 cheut\uff09\u3002"); SetFocus(Item(page.value)); return false; }
    return true;
}
void MarkCustomChanged(const Page& page, std::size_t select, const wchar_t* message) {
    g.custom_dirty = true; UpdateTitle();
    FillList(page);
    if (select != static_cast<std::size_t>(-1)) SelectLine(page, select);
    SetStatus(message);
}
void AddEntryFromFields(const Page& page) {
    std::wstring key, value;
    if (!ReadEntry(page, key, value)) return;
    if (HasEntry(g.custom, page.kind, key, value)) { SetStatus(L"\u5462\u500b\u7d44\u5408\u5df2\u7d93\u6709\u5497\u3002"); return; }
    CustomDocument next = g.custom;
    const std::size_t at = AddEntry(next, page.kind, key, value);
    if (!WithinCustomLimits(next)) { SetStatus(L"\u81ea\u8a02\u6a94\u5df2\u7d93\u5230\u5497\u5927\u5c0f\u4e0a\u9650\u3002"); return; }
    g.custom = std::move(next);
    SetWindowTextW(Item(page.key), L""); SetWindowTextW(Item(page.value), L"");
    SetFocus(Item(page.key));
    MarkCustomChanged(page, at, L"\u5df2\u52a0\u5165\u3002\u64b3\u300c\u5132\u5b58\u300d\u5148\u6703\u751f\u6548\u3002");
}
void UpdateSelected(const Page& page) {
    const long index = SelectedLine(page);
    if (index < 0) { SetStatus(L"\u8acb\u5148\u55ba\u5217\u8868\u63c0\u4e00\u9805\u3002"); return; }
    std::wstring key, value;
    if (!ReadEntry(page, key, value)) return;
    if (HasEntry(g.custom, page.kind, key, value, static_cast<std::size_t>(index))) { SetStatus(L"\u5462\u500b\u7d44\u5408\u5df2\u7d93\u6709\u5497\u3002"); return; }
    UpdateEntry(g.custom, static_cast<std::size_t>(index), key, value);
    MarkCustomChanged(page, static_cast<std::size_t>(index), L"\u5df2\u66f4\u65b0\u3002\u64b3\u300c\u5132\u5b58\u300d\u5148\u6703\u751f\u6548\u3002");
}
void DeleteSelected(const Page& page) {
    const long index = SelectedLine(page);
    if (index < 0) { SetStatus(L"\u8acb\u5148\u55ba\u5217\u8868\u63c0\u4e00\u9805\u3002"); return; }
    RemoveEntry(g.custom, static_cast<std::size_t>(index));
    SetWindowTextW(Item(page.key), L""); SetWindowTextW(Item(page.value), L"");
    MarkCustomChanged(page, static_cast<std::size_t>(-1), L"\u5df2\u522a\u9664\u3002\u64b3\u300c\u5132\u5b58\u300d\u5148\u6703\u751f\u6548\u3002");
}
void LoadSelectionIntoFields(const Page& page) {
    const long index = SelectedLine(page);
    if (index < 0) return;
    SetWindowTextW(Item(page.key), g.custom.lines[static_cast<std::size_t>(index)].key.c_str());
    SetWindowTextW(Item(page.value), g.custom.lines[static_cast<std::size_t>(index)].value.c_str());
}

// ---- Candidate font ----
int CALLBACK CollectFamily(const LOGFONTW* font, const TEXTMETRICW*, DWORD, LPARAM output) {
    if (font->lfFaceName[0] && font->lfFaceName[0] != L'@')
        reinterpret_cast<std::set<std::wstring>*>(output)->insert(font->lfFaceName);
    return 1;
}
void FillFonts() {
    HWND combo = Item(IDC_FONT);
    SendMessageW(combo, CB_RESETCONTENT, 0, 0);
    SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"\u9810\u8a2d\uff08\u971e\u9da9\u6587\u6977\uff09"));
    std::set<std::wstring> families;
    HDC dc = GetDC(nullptr);
    LOGFONTW query{}; query.lfCharSet = DEFAULT_CHARSET;
    EnumFontFamiliesExW(dc, &query, CollectFamily, reinterpret_cast<LPARAM>(&families), 0);
    ReleaseDC(nullptr, dc);
    // A hand-written name (e.g. localized) may not be how Windows lists it.
    if (!g.font_family.empty()) families.insert(g.font_family);
    for (const auto& family : families) SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(family.c_str()));
    LRESULT selected = 0;
    if (!g.font_family.empty()) {
        const LRESULT found = SendMessageW(combo, CB_FINDSTRINGEXACT, 0, reinterpret_cast<LPARAM>(g.font_family.c_str()));
        if (found != CB_ERR) selected = found;
    }
    SendMessageW(combo, CB_SETCURSEL, static_cast<WPARAM>(selected), 0);

    HWND sizes = Item(IDC_FONT_SIZE);
    SendMessageW(sizes, CB_RESETCONTENT, 0, 0);
    SendMessageW(sizes, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"\u9810\u8a2d\uff0820\uff09"));
    for (int size = 10; size <= 48; ++size) SendMessageW(sizes, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(std::to_wstring(size).c_str()));
    SendMessageW(sizes, CB_SETCURSEL, g.font_size ? static_cast<WPARAM>(g.font_size - 9) : 0, 0);
}
void ReadFontFields() {
    const LRESULT family = SendMessageW(Item(IDC_FONT), CB_GETCURSEL, 0, 0);
    if (family <= 0) g.font_family.clear();
    else {
        const LRESULT length = SendMessageW(Item(IDC_FONT), CB_GETLBTEXTLEN, static_cast<WPARAM>(family), 0);
        std::wstring name(static_cast<std::size_t>(length) + 1, L'\0');
        SendMessageW(Item(IDC_FONT), CB_GETLBTEXT, static_cast<WPARAM>(family), reinterpret_cast<LPARAM>(name.data()));
        name.resize(static_cast<std::size_t>(length));
        g.font_family = name;
    }
    const LRESULT size = SendMessageW(Item(IDC_FONT_SIZE), CB_GETCURSEL, 0, 0);
    g.font_size = size <= 0 ? 0 : static_cast<int>(size) + 9;
}
void UpdatePreview() {
    if (g.preview_font) DeleteObject(g.preview_font);
    const wchar_t* family = g.font_family.empty() ? (g.bundled_loaded ? kBundledFamily : L"Microsoft JhengHei UI") : g.font_family.c_str();
    g.preview_font = CreateFontW(-Scale(g.font_size ? g.font_size : 20), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, family);
    SendMessageW(Item(IDC_PREVIEW), WM_SETFONT, reinterpret_cast<WPARAM>(g.preview_font), TRUE);
}

// ---- Load / save ----
void LoadAll() {
    if (!ReadUserFile(g.custom_path, kMaxCustomBytes, g.custom_loaded)) {
        g.custom_loaded.clear();
        SetStatus(L"\u8b80\u5514\u5230 custom.txt\uff1b\u5132\u5b58\u6703\u5efa\u7acb\u65b0\u6a94\u3002");
    }
    g.custom = ParseCustom(g.custom_loaded);
    std::string appearance;
    ReadUserFile(g.appearance_path, cime::ui::appearance_detail::kMaxSettingsBytes, appearance);
    const auto document = cime::ui::appearance_detail::Parse(appearance);
    g.font_family = document.global.font_family;
    g.font_size = document.global.font_size;
    g.custom_dirty = g.font_dirty = false;
}
bool SaveAll() {
    if (g.custom_dirty) {
        std::string current;
        ReadUserFile(g.custom_path, kMaxCustomBytes, current);
        if (current != g.custom_loaded) {
            const int answer = MessageBoxW(g.window,
                L"custom.txt \u55ba\u5462\u500b\u8996\u7a97\u4ee5\u5916\u6539\u904e\u3002\n\n\u300c\u662f\u300d\uff1a\u7528\u5462\u5ea6\u5605\u5167\u5bb9\u8986\u84cb\n\u300c\u5426\u300d\uff1a\u653e\u68c4\u5462\u5ea6\u5605\u6539\u52d5\uff0c\u91cd\u65b0\u8f09\u5165\u6a94\u6848",
                kTitle, MB_YESNOCANCEL | MB_ICONWARNING);
            if (answer == IDCANCEL) return false;
            if (answer == IDNO) {
                g.custom_loaded = current; g.custom = ParseCustom(current); g.custom_dirty = false;
                FillList(kPages[0]); FillList(kPages[1]); UpdateTitle();
                SetStatus(L"\u5df2\u91cd\u65b0\u8f09\u5165 custom.txt\u3002");
                return false;
            }
        }
        const std::string text = SerializeCustom(g.custom);
        if (!WriteUserFile(g.custom_path, text, kMaxCustomBytes)) {
            MessageBoxW(g.window, L"\u5132\u5b58 custom.txt \u5931\u6557\u3002", kTitle, MB_OK | MB_ICONERROR); return false;
        }
        g.custom_loaded = text; g.custom_dirty = false;
    }
    if (g.font_dirty) {
        if (!SaveGlobalFont(g.appearance_path, g.font_family, g.font_size)) {
            MessageBoxW(g.window, L"\u5132\u5b58 appearance.ini \u5931\u6557\u3002", kTitle, MB_OK | MB_ICONERROR); return false;
        }
        g.font_dirty = false;
    }
    UpdateTitle();
    SetStatus(L"\u5df2\u5132\u5b58\u3002\u81ea\u8a02\u5b57\u5373\u523b\u751f\u6548\uff1b\u5b57\u578b\u4e0b\u6b21\u5f48\u51fa\u5019\u9078\u7a97\u751f\u6548\uff08\u5df2\u958b\u4f4f\u5605 app \u53ef\u80fd\u8981\u91cd\u958b\uff09\u3002");
    return true;
}
bool ConfirmClose() {
    if (!g.custom_dirty && !g.font_dirty) return true;
    const int answer = MessageBoxW(g.window, L"\u6709\u6539\u52d5\u672a\u5132\u5b58\u3002\u8981\u5132\u5b58\u55ce\uff1f", kTitle, MB_YESNOCANCEL | MB_ICONQUESTION);
    if (answer == IDCANCEL) return false;
    return answer == IDNO || SaveAll();
}

// ---- Layout ----
void ShowTab(int tab) {
    g.tab = tab;
    for (int i = 0; i < 2; ++i) {
        const Page& page = kPages[i];
        for (int id : {page.list, page.key_label, page.key, page.value_label, page.value, page.add, page.update, page.remove, page.hint})
            ShowWindow(Item(id), i == tab ? SW_SHOW : SW_HIDE);
    }
    for (int id : {IDC_FONT_LABEL, IDC_FONT, IDC_SIZE_LABEL, IDC_FONT_SIZE, IDC_PREVIEW_LABEL, IDC_PREVIEW, IDC_FONT_HINT})
        ShowWindow(Item(id), tab == 2 ? SW_SHOW : SW_HIDE);
}
void Layout() {
    RECT client{}; GetClientRect(g.window, &client);
    const int margin = Scale(10), row = Scale(24), gap = Scale(6), button = Scale(96);
    const int width = client.right - 2 * margin;
    const int bottom = client.bottom - margin - row;
    MoveWindow(Item(IDC_SAVE), client.right - margin - 2 * button - gap, bottom, button, row, TRUE);
    MoveWindow(Item(IDC_CLOSE), client.right - margin - button, bottom, button, row, TRUE);
    MoveWindow(Item(IDC_STATUS), margin, bottom - row - gap, width, row, TRUE);
    const int tabs_bottom = bottom - row - 2 * gap;
    MoveWindow(Item(IDC_TABS), margin, margin, width, tabs_bottom - margin, TRUE);
    RECT inner{margin, margin, margin + width, tabs_bottom};
    TabCtrl_AdjustRect(Item(IDC_TABS), FALSE, &inner);
    const int x = inner.left + gap, w = inner.right - inner.left - 2 * gap;
    for (const Page& page : kPages) {
        const int fields = inner.bottom - gap - 3 * row - 2 * gap;
        MoveWindow(Item(page.list), x, inner.top + gap, w, fields - inner.top - 2 * gap, TRUE);
        const int label = Scale(64), half = (w - 2 * label - 3 * gap) / 2;
        int y = fields;
        MoveWindow(Item(page.key_label), x, y + Scale(3), label, row, TRUE);
        MoveWindow(Item(page.key), x + label, y, half, row, TRUE);
        MoveWindow(Item(page.value_label), x + label + half + gap, y + Scale(3), label, row, TRUE);
        MoveWindow(Item(page.value), x + 2 * label + half + gap, y, half + 2 * gap, row, TRUE);
        y += row + gap;
        MoveWindow(Item(page.add), x, y, button, row, TRUE);
        MoveWindow(Item(page.update), x + button + gap, y, button + Scale(16), row, TRUE);
        MoveWindow(Item(page.remove), x + 2 * button + 2 * gap + Scale(16), y, button + Scale(16), row, TRUE);
        y += row + gap;
        MoveWindow(Item(page.hint), x, y, w, row, TRUE);
        ListView_SetColumnWidth(Item(page.list), 0, Scale(160));
        ListView_SetColumnWidth(Item(page.list), 1, std::max(Scale(120), w - Scale(160) - GetSystemMetrics(SM_CXVSCROLL) - Scale(4)));
    }
    const int label = Scale(80);
    int y = inner.top + 2 * gap;
    MoveWindow(Item(IDC_FONT_LABEL), x, y + Scale(3), label, row, TRUE);
    MoveWindow(Item(IDC_FONT), x + label, y, std::min(w - label, Scale(320)), Scale(300), TRUE);
    y += row + 2 * gap;
    MoveWindow(Item(IDC_SIZE_LABEL), x, y + Scale(3), label, row, TRUE);
    MoveWindow(Item(IDC_FONT_SIZE), x + label, y, Scale(120), Scale(300), TRUE);
    y += row + 2 * gap;
    MoveWindow(Item(IDC_PREVIEW_LABEL), x, y, label, row, TRUE);
    MoveWindow(Item(IDC_PREVIEW), x + label, y, w - label, Scale(72), TRUE);
    y += Scale(72) + 2 * gap;
    MoveWindow(Item(IDC_FONT_HINT), x, y, w, Scale(48), TRUE);
}

void CreateControls() {
    HWND tabs = Create(WC_TABCONTROLW, L"", WS_VISIBLE | WS_CLIPSIBLINGS | WS_TABSTOP, IDC_TABS);
    const wchar_t* names[] = {L"\u81ea\u8a02\u8a5e\u8a9e", L"\u81ea\u8a02\u62fc\u97f3", L"\u5019\u9078\u5b57\u578b"};
    for (int i = 0; i < 3; ++i) {
        TCITEMW item{}; item.mask = TCIF_TEXT; item.pszText = const_cast<wchar_t*>(names[i]);
        TabCtrl_InsertItem(tabs, i, &item);
    }
    const wchar_t* columns[2][2] = {{L"\u8f38\u5165", L"\u6587\u5b57"}, {L"\u62fc\u6cd5", L"\u7576\u4f5c\uff08\u7cb5\u62fc\u6216\u5df2\u8b58\u62fc\u6cd5\uff09"}};
    const wchar_t* labels[2][2] = {{L"\u8f38\u5165", L"\u6587\u5b57"}, {L"\u62fc\u6cd5", L"\u7576\u4f5c"}};
    const wchar_t* hints[2] = {
        L"\u6253\u5b8c\u6574\u500b\u8f38\u5165\uff08\u4f8b\u5982 hh\uff09\uff0c\u81ea\u8a02\u6587\u5b57\u6703\u6392\u7b2c\u4e00\u3002\u540c\u4e00\u500b\u8f38\u5165\u53ef\u4ee5\u6709\u5e7e\u500b\u6587\u5b57\u3002",
        L"\u4f8b\u5982 moon \u7576 mun\uff08\u51fa\u300c\u9580\u300d\uff09\uff0cchut \u7576 cheut\uff08\u51fa\u300c\u51fa\u300d\uff09\u3002\u62fc\u6cd5\u4ea6\u53ef\u4ee5\u55ba\u8a5e\u5165\u9762\u7528\u3002"};
    for (int i = 0; i < 2; ++i) {
        const Page& page = kPages[i];
        HWND list = Create(WC_LISTVIEWW, L"", WS_BORDER | WS_TABSTOP | LVS_REPORT | LVS_SINGLESEL | LVS_SHOWSELALWAYS, page.list);
        ListView_SetExtendedListViewStyle(list, LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER);
        for (int c = 0; c < 2; ++c) {
            LVCOLUMNW column{}; column.mask = LVCF_TEXT | LVCF_WIDTH; column.cx = Scale(160);
            column.pszText = const_cast<wchar_t*>(columns[i][c]);
            ListView_InsertColumn(list, c, &column);
        }
        Create(L"STATIC", labels[i][0], 0, page.key_label);
        Create(L"EDIT", L"", WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_LOWERCASE, page.key, WS_EX_CLIENTEDGE);
        SendMessageW(Item(page.key), EM_SETLIMITTEXT, 32, 0);
        Create(L"STATIC", labels[i][1], 0, page.value_label);
        Create(L"EDIT", L"", WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | (page.kind == LineKind::Alias ? ES_LOWERCASE : 0), page.value, WS_EX_CLIENTEDGE);
        SendMessageW(Item(page.value), EM_SETLIMITTEXT, page.kind == LineKind::Alias ? 12 : 64, 0);
        Create(L"BUTTON", L"\u65b0\u589e", WS_TABSTOP | BS_PUSHBUTTON, page.add);
        Create(L"BUTTON", L"\u66f4\u65b0\u6240\u9078", WS_TABSTOP | BS_PUSHBUTTON, page.update);
        Create(L"BUTTON", L"\u522a\u9664\u6240\u9078", WS_TABSTOP | BS_PUSHBUTTON, page.remove);
        Create(L"STATIC", hints[i], SS_LEFT, page.hint);
    }
    Create(L"STATIC", L"\u5b57\u578b", 0, IDC_FONT_LABEL);
    Create(WC_COMBOBOXW, L"", WS_TABSTOP | WS_VSCROLL | CBS_DROPDOWNLIST, IDC_FONT);
    Create(L"STATIC", L"\u5927\u5c0f", 0, IDC_SIZE_LABEL);
    Create(WC_COMBOBOXW, L"", WS_TABSTOP | WS_VSCROLL | CBS_DROPDOWNLIST, IDC_FONT_SIZE);
    Create(L"STATIC", L"\u9810\u89bd", 0, IDC_PREVIEW_LABEL);
    Create(L"STATIC", L"1  \u4f60\u597d   2  \u5ee3\u6771\u8a71   3  \u66c8\u66c8", SS_LEFT | SS_CENTERIMAGE, IDC_PREVIEW, WS_EX_CLIENTEDGE);
    Create(L"STATIC", L"\u5957\u7528\u5230\u6240\u6709 app\u3002\u7528\u53f3\u9375\u9078\u55ae\u6539\u904e\u5605\u984f\u8272\u540c\u900f\u660e\u5ea6\u5514\u53d7\u5f71\u97ff\u3002\u5927\u5c0f\u4ee5 100% \u7e2e\u653e\u8a08\uff0c\u6703\u8ddf Windows \u7e2e\u653e\u653e\u5927\u3002", SS_LEFT, IDC_FONT_HINT);
    Create(L"STATIC", L"", WS_VISIBLE | SS_LEFT | SS_ENDELLIPSIS, IDC_STATUS);
    Create(L"BUTTON", L"\u5132\u5b58", WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON, IDC_SAVE);
    Create(L"BUTTON", L"\u95dc\u9589", WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON, IDC_CLOSE);
}

int PageForControl(int id) {
    for (int i = 0; i < 2; ++i) {
        const Page& page = kPages[i];
        if (id == page.add || id == page.update || id == page.remove || id == page.list) return i;
    }
    return -1;
}

LRESULT CALLBACK WindowProcedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    switch (message) {
    case WM_CREATE: {
        g.window = window;
        g.dpi = GetDpiForWindow(window); if (!g.dpi) g.dpi = 96;
        CreateUiFont();
        CreateControls();
        CreateUiFont();
        LoadAll();
        FillList(kPages[0]); FillList(kPages[1]); FillFonts(); UpdatePreview();
        ShowTab(0); Layout(); UpdateTitle();
        return 0;
    }
    case WM_SIZE: Layout(); return 0;
    case WM_GETMINMAXINFO: {
        auto* info = reinterpret_cast<MINMAXINFO*>(lparam);
        info->ptMinTrackSize = {Scale(560), Scale(420)};
        return 0;
    }
    case WM_DPICHANGED: {
        g.dpi = HIWORD(wparam);
        CreateUiFont(); UpdatePreview();
        const RECT* suggested = reinterpret_cast<const RECT*>(lparam);
        SetWindowPos(window, nullptr, suggested->left, suggested->top, suggested->right - suggested->left,
            suggested->bottom - suggested->top, SWP_NOZORDER | SWP_NOACTIVATE);
        return 0;
    }
    case WM_NOTIFY: {
        const auto* header = reinterpret_cast<const NMHDR*>(lparam);
        if (header->idFrom == IDC_TABS && header->code == TCN_SELCHANGE) { ShowTab(TabCtrl_GetCurSel(Item(IDC_TABS))); return 0; }
        const int page = PageForControl(static_cast<int>(header->idFrom));
        if (page >= 0 && header->code == LVN_ITEMCHANGED) {
            const auto* change = reinterpret_cast<const NMLISTVIEW*>(lparam);
            if ((change->uNewState & LVIS_SELECTED) && !(change->uOldState & LVIS_SELECTED)) LoadSelectionIntoFields(kPages[page]);
        }
        return 0;
    }
    case WM_COMMAND: {
        const int id = LOWORD(wparam), code = HIWORD(wparam);
        if (id == IDC_SAVE) { SaveAll(); return 0; }
        if (id == IDC_CLOSE || id == IDCANCEL) { if (ConfirmClose()) DestroyWindow(window); return 0; }
        if (id == IDOK) { if (g.tab < 2) AddEntryFromFields(kPages[g.tab]); return 0; }
        if ((id == IDC_FONT || id == IDC_FONT_SIZE) && code == CBN_SELCHANGE) {
            ReadFontFields(); UpdatePreview(); g.font_dirty = true; UpdateTitle();
            SetStatus(L"\u64b3\u300c\u5132\u5b58\u300d\u5957\u7528\u65b0\u5b57\u578b\u3002"); return 0;
        }
        const int page = PageForControl(id);
        if (page >= 0 && code == BN_CLICKED) {
            if (id == kPages[page].add) AddEntryFromFields(kPages[page]);
            else if (id == kPages[page].update) UpdateSelected(kPages[page]);
            else if (id == kPages[page].remove) DeleteSelected(kPages[page]);
            return 0;
        }
        break;
    }
    case WM_CTLCOLORSTATIC: {
        // Labels inside the tab pane sit on the pane's window colour, not the
        // dialog face behind the status line and buttons.
        if (GetDlgCtrlID(reinterpret_cast<HWND>(lparam)) == IDC_STATUS) break;
        HDC dc = reinterpret_cast<HDC>(wparam);
        SetTextColor(dc, GetSysColor(COLOR_WINDOWTEXT));
        SetBkColor(dc, GetSysColor(COLOR_WINDOW));
        return reinterpret_cast<LRESULT>(GetSysColorBrush(COLOR_WINDOW));
    }
    case WM_CLOSE: if (ConfirmClose()) DestroyWindow(window); return 0;
    case WM_DESTROY:
        if (g.preview_font) DeleteObject(g.preview_font);
        if (g.ui_font) DeleteObject(g.ui_font);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

std::wstring BundledFontFile() {
    // The EXE lives in <root>\native; the bundled font is under <root>\assets.
    std::wstring path(32768, L'\0');
    const DWORD count = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    if (!count || count >= path.size()) return {};
    path.resize(count);
    for (int i = 0; i < 2; ++i) { const auto slash = path.find_last_of(L'\\'); if (slash == std::wstring::npos) return {}; path.resize(slash); }
    return path + L"\\assets\\fonts\\lxgw-wenkai-tc\\LXGWWenKaiTC-Regular.ttf";
}
} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show) {
    // One window per user session: a second launch brings the first forward.
    HANDLE single = CreateMutexW(nullptr, TRUE, L"Local\\CantoneseIME.Settings");
    if (single && GetLastError() == ERROR_ALREADY_EXISTS) {
        if (HWND existing = FindWindowW(kWindowClass, nullptr)) {
            if (IsIconic(existing)) ShowWindow(existing, SW_RESTORE);
            SetForegroundWindow(existing);
        }
        CloseHandle(single);
        return 0;
    }
    INITCOMMONCONTROLSEX controls{sizeof(controls), ICC_TAB_CLASSES | ICC_LISTVIEW_CLASSES | ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&controls);
    g.custom_path = UserDataPath(L"custom.txt");
    g.appearance_path = UserDataPath(L"appearance.ini");
    g.bundled_font_file = BundledFontFile();
    if (!g.bundled_font_file.empty() && GetFileAttributesW(g.bundled_font_file.c_str()) != INVALID_FILE_ATTRIBUTES)
        g.bundled_loaded = AddFontResourceExW(g.bundled_font_file.c_str(), FR_PRIVATE, nullptr) > 0;

    WNDCLASSEXW type{}; type.cbSize = sizeof(type); type.lpfnWndProc = WindowProcedure; type.hInstance = instance;
    type.hCursor = LoadCursorW(nullptr, IDC_ARROW); type.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_BTNFACE + 1);
    type.lpszClassName = kWindowClass;
    type.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1)); type.hIconSm = type.hIcon;
    RegisterClassExW(&type);
    const UINT dpi = GetDpiForSystem();
    HWND window = CreateWindowExW(WS_EX_CONTROLPARENT, kWindowClass, kTitle, WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN,
        CW_USEDEFAULT, CW_USEDEFAULT, MulDiv(640, static_cast<int>(dpi), 96), MulDiv(500, static_cast<int>(dpi), 96),
        nullptr, nullptr, instance, nullptr);
    if (!window) return 1;
    ShowWindow(window, show); UpdateWindow(window);
    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        if (IsDialogMessageW(window, &message)) continue;
        TranslateMessage(&message); DispatchMessageW(&message);
    }
    if (g.bundled_loaded) RemoveFontResourceExW(g.bundled_font_file.c_str(), FR_PRIVATE, nullptr);
    if (single) CloseHandle(single);
    return static_cast<int>(message.wParam);
}
