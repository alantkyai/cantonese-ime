// Uses the production native client against a broker configured with an
// isolated test learning file. It never activates TSF or injects editor text.
#include "../tsf/ipc.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::string Utf8(const std::wstring& value) {
    const int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
        static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    if (!size) throw std::runtime_error("UTF-16 conversion failed");
    std::string result(size, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
        static_cast<int>(value.size()), result.data(), size, nullptr, nullptr))
        throw std::runtime_error("UTF-16 conversion failed");
    return result;
}
void Require(bool condition, const char* failure) { if (!condition) throw std::runtime_error(failure); }
cime::Page Lookup(cime::Backend& backend, const std::wstring& raw) {
    cime::Page result;
    Require(backend.Lookup(raw, false, 0, result) && !result.candidates.empty(), "Native lookup failed");
    return result;
}
bool Same(const cime::Candidate& a, const cime::Candidate& b) {
    return a.text == b.text && a.reading == b.reading;
}
cime::Candidate NonFirst(const cime::Page& page, bool short_word) {
    for (std::size_t i = 1; i < page.candidates.size(); ++i)
        if (short_word ? page.candidates[i].text.size() == 1 : page.candidates[i].text.size() >= 2)
            return page.candidates[i];
    throw std::runtime_error("Test fixture has no suitable non-first candidate");
}
void Peer(DWORD expected) {
    HANDLE pipe = CreateFileW(cime::Backend::PipeName().c_str(), GENERIC_READ | GENERIC_WRITE,
        0, nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, nullptr);
    Require(pipe != INVALID_HANDLE_VALUE, "Broker pipe unavailable");
    ULONG actual = 0; const BOOL okay = GetNamedPipeServerProcessId(pipe, &actual); CloseHandle(pipe);
    Require(okay && actual == expected, "Unexpected broker peer PID");
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 5) {
        std::cerr << "Usage: LearningSmoke.exe learn|verify OUTPUT_JSON EXPECTED_BROKER_PID TEST_MARKER\n"; return 2;
    }
    try {
        const bool learn = std::wstring(argv[1]) == L"learn";
        Require(learn || std::wstring(argv[1]) == L"verify", "Unknown action");
        Peer(static_cast<DWORD>(std::stoul(argv[3])));
        cime::Backend backend;
        const std::wstring short_raw = L"nei", long_raw = L"neihou";
        auto short_page = Lookup(backend, short_raw), long_page = Lookup(backend, long_raw);
        std::vector<std::string> expected;
        if (learn) {
            const auto short_choice = NonFirst(short_page, true), long_choice = NonFirst(long_page, false);
            Require(short_choice.text != long_choice.text, "Short and long test choices should differ");
            Require(backend.RecordSelection(long_raw, false, long_choice), "Long-phrase learning acknowledgement failed");
            Require(Same(Lookup(backend, short_raw).candidates.front(), short_page.candidates.front()),
                "Learning long input changed the short-input preference");
            Require(backend.RecordSelection(short_raw, false, short_choice), "Short-input learning acknowledgement failed");
            Require(Same(Lookup(backend, long_raw).candidates.front(), long_choice), "Short learning changed long preference");
            Require(Same(Lookup(backend, short_raw).candidates.front(), short_choice), "Short choice was not promoted");
            Require(!backend.RecordSelection(short_raw, false, {L"\u4e0d\u5b58\u5728\u7684\u9078\u64c7", L"nei5"}),
                "Fabricated candidate was accepted");
            expected = {Utf8(short_choice.text), Utf8(short_choice.reading), Utf8(long_choice.text), Utf8(long_choice.reading)};
            std::ofstream marker(std::filesystem::path(argv[4]), std::ios::binary | std::ios::trunc);
            Require(static_cast<bool>(marker), "Cannot create test marker");
            for (const auto& line : expected) marker << line << '\n';
            marker.close(); Require(static_cast<bool>(marker), "Cannot save test marker");
        } else {
            std::ifstream marker(std::filesystem::path(argv[4]), std::ios::binary);
            std::string line; while (std::getline(marker, line)) expected.push_back(line);
            Require(expected.size() == 4, "Test marker is invalid");
            Require(Utf8(short_page.candidates.front().text) == expected[0] && Utf8(short_page.candidates.front().reading) == expected[1],
                "Restart lost short-input preference");
            Require(Utf8(long_page.candidates.front().text) == expected[2] && Utf8(long_page.candidates.front().reading) == expected[3],
                "Restart lost long-phrase preference");
        }
        std::ofstream output(std::filesystem::path(argv[2]), std::ios::binary | std::ios::trunc);
        Require(static_cast<bool>(output), "Cannot create test report");
        output << "{\n\"schema_version\":1,\"kind\":\"production_native_learning_ipc\","
               << "\"action\":\"" << (learn ? "learn" : "verify_after_restart") << "\","
               << "\"client_pid\":" << GetCurrentProcessId() << ",\"client_bits\":" << sizeof(void*) * 8
               << ",\"broker_pid\":" << std::stoul(argv[3]) << ",\"passed\":true,"
               << "\"short_input\":\"nei\",\"long_input\":\"neihou\","
               << "\"isolated_test_learning_store_required\":true,\"tsf_typing_proof\":false\n}\n";
        output.close(); Require(static_cast<bool>(output), "Cannot save test report");
        std::cout << "Native learning IPC " << (learn ? "selection/isolation" : "restart persistence") << " passed.\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
