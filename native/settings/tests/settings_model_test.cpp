// Settings file model fixtures. Uses only a disposable directory passed on
// the command line; never reads or writes the user's own settings.
#include "../settings_model.h"
#include <cassert>
#include <iostream>

namespace {
using namespace cime::settings;
std::string U8(const std::wstring& value) { return WideToUtf8(value); }
} // namespace

int wmain(int argc, wchar_t** argv) {
    assert(argc == 2);
    const std::wstring directory = argv[1];
    assert(CreateDirectoryW(directory.c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS);
    unsigned checks = 0;
    const std::wstring tong = L"\u66c8\u66c8", tong2 = L"\u77b3\u77b3", hello = L"\u4f60\u597d\u55ce";

    // Classification mirrors cantonese_ime/custom.py, including BOM, tabs,
    // case-folding of keys, and invalid lines that are kept verbatim.
    const std::string original = "\xEF\xBB\xBF# my notes\r\nhh " + U8(tong) + "\r\nHH\t" + U8(tong2) + "\r\n\r\nmoon = mun\r\n"
        "h1 bad\r\nchut=CHEUT\r\nzz = way-too-long-target\r\n# end";
    auto document = ParseCustom(original);
    assert(document.lines.size() == 9); ++checks;
    const auto phrases = Entries(document, LineKind::Phrase), aliases = Entries(document, LineKind::Alias);
    assert(phrases.size() == 2 && document.lines[phrases[0]].key == L"hh" && document.lines[phrases[0]].value == tong); ++checks;
    assert(document.lines[phrases[1]].key == L"hh" && document.lines[phrases[1]].value == tong2); ++checks;
    assert(aliases.size() == 2 && document.lines[aliases[0]].value == L"mun" && document.lines[aliases[1]].key == L"chut"
        && document.lines[aliases[1]].value == L"cheut"); ++checks;
    assert(document.lines[5].kind == LineKind::Other && document.lines[5].raw == L"h1 bad"); ++checks;
    assert(document.lines[7].kind == LineKind::Other); ++checks;
    // Untouched documents serialize back to the same lines (BOM dropped, CRLF).
    assert(SerializeCustom(document) == original.substr(3) + "\r\n"); ++checks;

    // Edits touch only their own lines; new entries join their group.
    const std::size_t added = AddEntry(document, LineKind::Phrase, L"neihou", hello);
    assert(added == 3 && document.lines[3].raw == L"neihou " + hello && document.lines[0].raw == L"# my notes"); ++checks;
    UpdateEntry(document, aliases[0] + 1, L"moon", L"mun");
    assert(document.lines[aliases[0] + 1].raw == L"moon = mun"); ++checks;
    RemoveEntry(document, 1);
    const std::string edited = SerializeCustom(document);
    assert(edited.find(U8(tong)) == std::string::npos && edited.find("h1 bad") != std::string::npos
        && edited.find("# end") != std::string::npos && edited.find(U8(tong2)) != std::string::npos); ++checks;
    assert(HasEntry(document, LineKind::Phrase, L"neihou", hello) && !HasEntry(document, LineKind::Alias, L"neihou", hello)); ++checks;

    // An empty or comment-only file gains a header for the first entry of a kind.
    auto fresh = ParseCustom("");
    AddEntry(fresh, LineKind::Alias, L"ko", L"go");
    assert(SerializeCustom(fresh) == "# Spellings: spelling = syllable\r\nko = go\r\n"); ++checks;
    AddEntry(fresh, LineKind::Phrase, L"gg", L"\u54e5\u54e5");
    assert(Entries(fresh, LineKind::Phrase).size() == 1 && fresh.lines[2].raw.empty()); ++checks;

    // Validation matches the engine's limits; '=' would turn a phrase into a spelling.
    assert(ValidKey(L"hh") && !ValidKey(L"h1") && !ValidKey(L"") && !ValidKey(std::wstring(33, L'a'))); ++checks;
    assert(ValidTarget(L"cheut") && !ValidTarget(std::wstring(13, L'a'))); ++checks;
    assert(ValidPhrase(tong) && !ValidPhrase(L"a=b") && !ValidPhrase(L" x") && !ValidPhrase(std::wstring(65, L'x'))
        && !ValidPhrase(L"a\tb")); ++checks;

    // Atomic file round trip and the size limit.
    const std::wstring custom_path = directory + L"\\custom.txt";
    std::string read;
    assert(ReadUserFile(custom_path, kMaxCustomBytes, read) && read.empty()); ++checks; // missing file: empty
    assert(WriteUserFile(custom_path, edited, kMaxCustomBytes)); ++checks;
    assert(ReadUserFile(custom_path, kMaxCustomBytes, read) && read == edited); ++checks;
    assert(!WriteUserFile(custom_path, std::string(kMaxCustomBytes + 1, 'a'), kMaxCustomBytes)); ++checks;

    // Global font: app sections that held the old global value follow it; a
    // deliberately different app font, and app colours, are kept.
    const std::wstring appearance_path = directory + L"\\appearance.ini";
    const std::string game = cime::ui::AppearanceHostKey(L"C:\\Games\\Client.exe");
    const std::string editor = cime::ui::AppearanceHostKey(L"C:\\Tools\\Editor.exe");
    assert(cime::ui::appearance_detail::WriteAtomic(appearance_path, "[global]\r\ntheme=dark\r\nfont=Segoe UI\r\nfont_size=20\r\n"
        "[" + game + "]\r\ntheme=light\r\nopacity=85\r\nfont=Segoe UI\r\nfont_size=20\r\n"
        "[" + editor + "]\r\ntheme=system\r\nfont=Consolas\r\nfont_size=30\r\n")); ++checks;
    assert(SaveGlobalCandidate(appearance_path, L"\u5fae\u8edf\u6b63\u9ed1\u9ad4", 24, true)); ++checks;
    std::string saved;
    assert(ReadUserFile(appearance_path, cime::ui::appearance_detail::kMaxSettingsBytes, saved)); ++checks;
    const auto parsed = cime::ui::appearance_detail::Parse(saved);
    assert(parsed.global.font_family == L"\u5fae\u8edf\u6b63\u9ed1\u9ad4" && parsed.global.font_size == 24
        && parsed.global.theme == cime::ui::CandidateTheme::Dark); ++checks;
    const auto& game_settings = parsed.applications.at(game);
    assert(game_settings.font_family == parsed.global.font_family && game_settings.font_size == 24
        && game_settings.theme == cime::ui::CandidateTheme::Light && game_settings.opacity_percent == 85); ++checks;
    const auto& editor_settings = parsed.applications.at(editor);
    assert(editor_settings.font_family == L"Consolas" && editor_settings.font_size == 30
        && editor_settings.theme == cime::ui::CandidateTheme::System); ++checks;
    // The suggestion switch is inherited the same way and survives a round trip.
    assert(parsed.global.prediction && game_settings.prediction && editor_settings.prediction); ++checks;
    assert(saved.find("prediction=on") != std::string::npos); ++checks;
    assert(SaveGlobalCandidate(appearance_path, L"", 0, false)); ++checks; // back to the bundled default
    ReadUserFile(appearance_path, cime::ui::appearance_detail::kMaxSettingsBytes, saved);
    assert(saved.find("font=") == std::string::npos || saved.find("font=Consolas") != std::string::npos); ++checks;
    assert(saved.find("prediction=on") == std::string::npos); ++checks;
    assert(!SaveGlobalCandidate(appearance_path, L"x", 9, false)); ++checks;

    assert(DeleteFileW(custom_path.c_str()) && DeleteFileW(appearance_path.c_str()) && RemoveDirectoryW(directory.c_str()));
    std::cout << "{\"passed\":true,\"checks\":" << checks
              << ",\"scope\":\"custom.txt classification parity, comment-preserving edits, validation, atomic round trip, global font inheritance in appearance.ini\"}\n";
    return 0;
}
