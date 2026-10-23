// Read-only Yale smoke through the production cime::Backend client. No TSF
// activation, keyboard events, registration or selection-learning messages.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "../tsf/ipc.h"
#include <algorithm>
#include <chrono>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace {
static_assert(sizeof(void*) == 8, "The Yale IPC smoke is AMD64 only");
std::string Utf8(const std::wstring& value) {
    if (value.empty()) return {};
    const int count = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
        static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    if (!count) throw std::runtime_error("Invalid UTF-16 test value");
    std::string bytes(count, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
        static_cast<int>(value.size()), bytes.data(), count, nullptr, nullptr))
        throw std::runtime_error("UTF-8 conversion failed");
    return bytes;
}
std::string Json(const std::wstring& value) {
    std::ostringstream out; out << '"';
    for (unsigned char byte : Utf8(value)) {
        if (byte == '"' || byte == '\\') out << '\\' << static_cast<char>(byte);
        else if (byte < 32) out << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << unsigned(byte) << std::dec;
        else out << static_cast<char>(byte);
    }
    out << '"'; return out.str();
}
DWORD ServerPid() {
    const auto pipe_name = cime::Backend::PipeName();
    const auto deadline = GetTickCount64() + 250;
    HANDLE handle = INVALID_HANDLE_VALUE;
    while (GetTickCount64() < deadline) {
        handle = CreateFileW(pipe_name.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
            OPEN_EXISTING, FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, nullptr);
        if (handle != INVALID_HANDLE_VALUE) break;
        if (GetLastError() != ERROR_PIPE_BUSY) throw std::runtime_error("Cannot inspect expected broker endpoint");
        const auto now = GetTickCount64();
        if (now >= deadline) break;
        WaitNamedPipeW(pipe_name.c_str(), static_cast<DWORD>(deadline - now));
    }
    if (handle == INVALID_HANDLE_VALUE) throw std::runtime_error("Broker endpoint remained busy");
    ULONG pid = 0; const BOOL success = GetNamedPipeServerProcessId(handle, &pid); CloseHandle(handle);
    if (!success) throw std::runtime_error("Cannot read broker endpoint PID");
    return pid;
}
struct Case {
    std::wstring id, input, target;
    bool strict = false, expect_present = true, long_case = false, incremental = false;
};
struct PrefixTiming {
    unsigned input_length;
    bool success;
    double elapsed_ms;
    std::size_t candidates;
    std::wstring error;
};
struct Result {
    Case test;
    bool passed = false, lookup_ok = true;
    unsigned pages = 0, candidates = 0, rank = 0;
    double first_page_ms = 0, max_request_ms = 0, total_ms = 0;
    std::wstring outcome, reading, error;
    std::vector<PrefixTiming> prefixes;
};
Result Run(cime::Backend& backend, const Case& test) {
    Result result; result.test = test;
    unsigned offset = 0; std::set<std::wstring> seen;
    const auto began = std::chrono::steady_clock::now();
    bool prefixes_passed = true;
    if (test.incremental) {
        for (std::size_t length = 1; length < test.input.size(); ++length) {
            cime::Page page;
            const auto prefix_began = std::chrono::steady_clock::now();
            const bool success = backend.Lookup(test.input.substr(0, length), test.strict, 0, page);
            const double elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - prefix_began).count();
            result.prefixes.push_back({static_cast<unsigned>(length), success, elapsed, page.candidates.size(), page.error});
            result.max_request_ms = std::max(result.max_request_ms, elapsed);
            if (!success) {
                // Do not enqueue hundreds of more requests behind a timed-out
                // conversion. Still test the final complete word below.
                prefixes_passed = false; result.lookup_ok = false; break;
            }
        }
    }
    for (unsigned index = 0; index < 128; ++index) {
        cime::Page page;
        const auto request_began = std::chrono::steady_clock::now();
        const bool success = backend.Lookup(test.input, test.strict, offset, page);
        const double elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - request_began).count();
        if (index == 0) result.first_page_ms = elapsed;
        result.max_request_ms = std::max(result.max_request_ms, elapsed);
        if (!success) {
            result.lookup_ok = false; result.error = page.error; result.outcome = L"capacity_or_error"; break;
        }
        ++result.pages;
        for (std::size_t slot = 0; slot < page.candidates.size(); ++slot) {
            const auto& candidate = page.candidates[slot];
            if (!seen.insert(candidate.text).second) throw std::runtime_error("Duplicate text across native pages");
            ++result.candidates;
            if (candidate.text == test.target) {
                result.rank = offset + static_cast<unsigned>(slot) + 1;
                result.reading = candidate.reading; result.outcome = L"target_found";
                result.passed = test.expect_present && prefixes_passed; break;
            }
        }
        if (result.rank) break;
        if (page.next_offset < 0) {
            result.outcome = L"exhausted_without_target"; result.passed = !test.expect_present && prefixes_passed; break;
        }
        if (static_cast<unsigned>(page.next_offset) != offset + page.candidates.size() ||
            static_cast<unsigned>(page.next_offset) <= offset)
            throw std::runtime_error("Native page cursor did not progress");
        offset = static_cast<unsigned>(page.next_offset);
        if (index == 127) result.outcome = L"audit_page_budget";
    }
    result.total_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - began).count();
    return result;
}
void Write(std::ostream& out, const Result& value) {
    out << "{\"id\":" << Json(value.test.id) << ",\"input\":" << Json(value.test.input)
        << ",\"expected_text\":" << Json(value.test.target) << ",\"mode\":" << (value.test.strict ? "\"jyutping\"" : "\"forgiving\"")
        << ",\"expect_present\":" << (value.test.expect_present ? "true" : "false")
        << ",\"long_input_case\":" << (value.test.long_case ? "true" : "false")
        << ",\"incremental_prefix_case\":" << (value.test.incremental ? "true" : "false")
        << ",\"input_length\":" << value.test.input.size() << ",\"passed\":" << (value.passed ? "true" : "false")
        << ",\"lookup_calls_succeeded\":" << (value.lookup_ok ? "true" : "false") << ",\"outcome\":" << Json(value.outcome)
        << ",\"rank\":";
    if (value.rank) out << value.rank; else out << "null";
    out << ",\"reading\":" << Json(value.reading) << ",\"pages\":" << value.pages
        << ",\"visible_candidates\":" << value.candidates << ",\"first_page_ms\":" << value.first_page_ms
        << ",\"max_request_ms\":" << value.max_request_ms << ",\"total_ms\":" << value.total_ms
        << ",\"error\":" << Json(value.error) << ",\"prefixes_stopped_early\":"
        << (value.test.incremental && value.prefixes.size() + 1 < value.test.input.size() ? "true" : "false")
        << ",\"prefix_requests\":[";
    for (std::size_t index = 0; index < value.prefixes.size(); ++index) {
        if (index) out << ',';
        const auto& row = value.prefixes[index];
        out << "{\"input_length\":" << row.input_length << ",\"success\":" << (row.success ? "true" : "false")
            << ",\"elapsed_ms\":" << row.elapsed_ms << ",\"candidates\":" << row.candidates << ",\"error\":" << Json(row.error) << '}';
    }
    out << "]}";
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    try {
        if (argc < 3) throw std::runtime_error(
            "Usage: CantoneseImeYaleSmoke.exe OUTPUT_JSON EXPECTED_BROKER_PID [--case ID INPUT TEXT] [--long ID INPUT TEXT] [--incremental-long ID INPUT TEXT]");
        std::size_t consumed = 0;
        const auto parsed_pid = std::stoul(argv[2], &consumed);
        if (!parsed_pid || parsed_pid > 0xffffffffUL || consumed != std::wcslen(argv[2]))
            throw std::runtime_error("Expected broker PID must be an unsigned nonzero DWORD");
        const DWORD expected_pid = static_cast<DWORD>(parsed_pid);
        std::vector<Case> cases = {
            {L"torch", L"fogeui", L"\u706b\u70ac"},
            {L"hong_kong", L"heunggong", L"\u9999\u6e2f"},
            {L"set_out", L"cheutfaat", L"\u51fa\u767c"},
            {L"moon", L"yut", L"\u6708"},
            {L"strict_yale_negative", L"geui", L"\u70ac", true, false},
            {L"strict_jyutping_positive", L"geoi", L"\u70ac", true, true}
        };
        for (int index = 3; index < argc;) {
            const std::wstring flag = argv[index++];
            if ((flag != L"--case" && flag != L"--long" && flag != L"--incremental-long") || index + 2 >= argc)
                throw std::runtime_error("Each --case/--long/--incremental-long requires ID, INPUT and expected TEXT");
            Case added{argv[index], argv[index + 1], argv[index + 2]}; index += 3;
            added.long_case = flag == L"--long" || flag == L"--incremental-long";
            added.incremental = flag == L"--incremental-long";
            if (added.long_case && added.input.size() <= 64)
                throw std::runtime_error("The explicit long test must exceed the old 64-character input cap");
            cases.push_back(std::move(added));
        }
        for (const auto& test : cases) {
            if (test.id.empty() || test.target.empty() || test.input.empty() || test.input.size() > cime::kMaxInputLength)
                throw std::runtime_error("A test is empty or exceeds the production input cap");
            for (wchar_t letter : test.input)
                if (!(letter >= L'a' && letter <= L'z') && letter != L'\'')
                    throw std::runtime_error("Native tests accept lowercase plain letters and optional syllable boundaries only");
        }
        const std::filesystem::path output(argv[1]);
        if (output.extension() != L".json" || std::filesystem::exists(output))
            throw std::runtime_error("Choose a new .json evidence path; existing files are retained");
        const DWORD before_pid = ServerPid();
        if (before_pid != expected_pid) throw std::runtime_error("Broker PID differs from the explicitly expected process");
        cime::Backend backend; std::vector<Result> results; bool passed = true;
        for (const auto& test : cases) { results.push_back(Run(backend, test)); passed &= results.back().passed; }
        const DWORD after_pid = ServerPid();
        if (after_pid != expected_pid) throw std::runtime_error("Broker PID changed during smoke");
        std::ofstream stream(output, std::ios::binary);
        if (!stream) throw std::runtime_error("Cannot create evidence JSON");
        stream << std::fixed << std::setprecision(6)
            << "{\"schema_version\":1,\"kind\":\"production_native_yale_lookup_smoke\",\"client_pid\":" << GetCurrentProcessId()
            << ",\"client_bits\":" << sizeof(void*) * 8 << ",\"expected_broker_pid\":" << expected_pid
            << ",\"observed_broker_pid_before\":" << before_pid << ",\"observed_broker_pid_after\":" << after_pid
            << ",\"native_input_limit\":" << cime::kMaxInputLength << ",\"client_deadline_ms\":250"
            << ",\"error_scope\":\"Client exposes success/error text, not numeric status; capacity errors are not automatically classified as transport failures.\""
            << ",\"learning_write_requests\":0,\"keyboard_or_ui_actions\":0,\"tsf_typing_proof\":false,\"passed\":"
            << (passed ? "true" : "false") << ",\"cases\":[";
        for (std::size_t index = 0; index < results.size(); ++index) { if (index) stream << ','; Write(stream, results[index]); }
        stream << "]}\n"; stream.close();
        if (!stream) throw std::runtime_error("Cannot finish evidence JSON");
        std::cout << "Read-only Yale IPC smoke " << (passed ? "passed" : "failed") << "; cases=" << results.size() << '\n';
        return passed ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 2;
    }
}
