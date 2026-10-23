// Project-authored read-only broker smoke test. This does not activate TSF or
// generate keystrokes: every conversion uses the production native IPC client.
#include "../tsf/ipc.h"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {
std::string Utf8(const std::wstring& value) {
    if (value.empty()) return {};
    const int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS,
        value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    if (!size) throw std::runtime_error("Invalid UTF-16 text in IPC result.");
    std::string result(size, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
        static_cast<int>(value.size()), result.data(), size, nullptr, nullptr))
        throw std::runtime_error("Could not encode IPC result.");
    return result;
}

std::string Json(const std::wstring& value) {
    std::ostringstream out;
    out << '"';
    for (unsigned char byte : Utf8(value)) {
        if (byte == '"' || byte == '\\') out << '\\' << static_cast<char>(byte);
        else if (byte < 32) out << "\\u00" << std::hex << std::setw(2)
                                << std::setfill('0') << static_cast<unsigned>(byte) << std::dec;
        else out << static_cast<char>(byte);
    }
    out << '"';
    return out.str();
}

std::string UtcNow() {
    SYSTEMTIME time{};
    GetSystemTime(&time);
    std::ostringstream out;
    out << std::setfill('0') << std::setw(4) << time.wYear << '-'
        << std::setw(2) << time.wMonth << '-' << std::setw(2) << time.wDay << 'T'
        << std::setw(2) << time.wHour << ':' << std::setw(2) << time.wMinute << ':'
        << std::setw(2) << time.wSecond << '.' << std::setw(3) << time.wMilliseconds << 'Z';
    return out.str();
}

DWORD ProbeServerPid() {
    const auto name = cime::Backend::PipeName();
    HANDLE pipe = CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0,
        nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT |
        SECURITY_IDENTIFICATION, nullptr);
    if (pipe == INVALID_HANDLE_VALUE) throw std::runtime_error("Could not inspect broker endpoint.");
    ULONG pid = 0;
    const BOOL success = GetNamedPipeServerProcessId(pipe, &pid);
    CloseHandle(pipe);
    if (!success) throw std::runtime_error("Could not read broker peer PID.");
    return pid;
}

struct Result {
    std::wstring input;
    unsigned offset;
    bool success;
    double elapsed_ms;
    cime::Page page;
};

Result Lookup(cime::Backend& backend, const std::wstring& input, unsigned offset) {
    Result result{input, offset, false, 0, {}};
    const auto started = std::chrono::steady_clock::now();
    result.success = backend.Lookup(input, false, offset, result.page);
    result.elapsed_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - started).count();
    return result;
}

bool Contains(const Result& result, const std::wstring& text) {
    for (const auto& candidate : result.page.candidates)
        if (candidate.text == text) return true;
    return false;
}

void WriteResult(std::ostream& out, const Result& result) {
    out << "{\"input\":" << Json(result.input)
        << ",\"mode\":\"forgiving\",\"offset\":" << result.offset
        << ",\"success\":" << (result.success ? "true" : "false")
        << ",\"elapsed_ms\":" << std::fixed << std::setprecision(6) << result.elapsed_ms
        << ",\"next_offset\":";
    if (result.page.next_offset < 0) out << "null";
    else out << result.page.next_offset;
    out << ",\"completion_truncated\":" << (result.page.completion_truncated ? "true" : "false")
        << ",\"error\":" << Json(result.page.error) << ",\"candidates\":[";
    for (std::size_t index = 0; index < result.page.candidates.size(); ++index) {
        if (index) out << ',';
        const auto& candidate = result.page.candidates[index];
        out << "{\"rank\":" << result.offset + index + 1
            << ",\"text\":" << Json(candidate.text)
            << ",\"reading\":" << Json(candidate.reading) << '}';
    }
    out << "]}";
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 3) {
        std::cerr << "Usage: CantoneseImeIpcSmoke.exe OUTPUT_JSON EXPECTED_BROKER_PID\n";
        return 2;
    }
    try {
        const DWORD expected_pid = static_cast<DWORD>(std::stoul(argv[2]));
        const DWORD actual_pid = ProbeServerPid();
        if (!expected_pid || actual_pid != expected_pid)
            throw std::runtime_error("Broker peer PID does not match the expected running broker.");
        cime::Backend backend;
        std::vector<Result> results;
        results.push_back(Lookup(backend, L"bohim", 0));
        results.push_back(Lookup(backend, L"neihou", 0));
        std::string termination = "page_limit";
        unsigned offset = 0;
        unsigned successful_lei_pages = 0;
        for (unsigned page = 0; page < 128; ++page) {
            results.push_back(Lookup(backend, L"lei", offset));
            const auto& result = results.back();
            if (!result.success) { termination = "reported_error"; break; }
            ++successful_lei_pages;
            if (result.page.next_offset < 0) { termination = "end_of_results"; break; }
            if (static_cast<unsigned>(result.page.next_offset) <= offset)
                throw std::runtime_error("Non-progressing native candidate page.");
            offset = static_cast<unsigned>(result.page.next_offset);
        }
        const bool basic_success = results[0].success && results[1].success;
        const bool expected_basic_targets = Contains(results[0], L"\u4fdd\u96aa") &&
                                            Contains(results[1], L"\u4f60\u597d");
        // The existing client exposes only success/error text, not wire status.
        // Recognize this exact engine error only after an advertised limited tail;
        // a generic unavailable/timeout error is a failed smoke, not exhaustion.
        const bool reported_capacity = termination == "reported_error" && successful_lei_pages > 0 &&
            results[results.size() - 2].page.completion_truncated &&
            results.back().page.error == L"Candidate search exceeds the bounded pool; refine the input to continue.";
        if (reported_capacity) termination = "reported_capacity_limit";
        const bool paging_tail_handled = termination == "end_of_results" || reported_capacity;
        const bool basic_smoke_pass = basic_success && expected_basic_targets && successful_lei_pages >= 2;
        const bool smoke_pass = basic_smoke_pass && paging_tail_handled;
        std::ofstream out(std::filesystem::path(argv[1]), std::ios::binary | std::ios::trunc);
        if (!out) throw std::runtime_error("Could not create output JSON.");
        out << "{\n\"report_schema_version\":1,\"kind\":\"native_client_broker_ipc_smoke\","
            << "\"captured_at_utc\":\"" << UtcNow() << "\",\"client_pid\":" << GetCurrentProcessId()
            << ",\"client_pointer_bits\":" << sizeof(void*) * 8
            << ",\"expected_broker_pid\":" << expected_pid << ",\"observed_broker_pid\":" << actual_pid
            << ",\"client_deadline_ms\":250,\"learning_write_requests\":0,\"tsf_typing_proof\":false,"
            << "\"basic_lookup_success\":" << (basic_success ? "true" : "false")
            << ",\"expected_basic_targets_observed\":" << (expected_basic_targets ? "true" : "false")
            << ",\"successful_lei_pages\":" << successful_lei_pages
            << ",\"lei_page_limit\":128,\"lei_termination\":\"" << termination
            << "\",\"basic_ipc_and_paging_pass\":" << (basic_smoke_pass ? "true" : "false")
            << ",\"paging_tail_handled\":" << (paging_tail_handled ? "true" : "false")
            << ",\"ipc_smoke_pass\":" << (smoke_pass ? "true" : "false")
            << ",\"limits\":[\"Native client returns a success flag and error text, not the numeric wire status.\","
            << "\"IPC lookup success is not native TSF composition, keyboard input, or UI validation.\"],\n\"requests\":[\n";
        for (std::size_t index = 0; index < results.size(); ++index) {
            if (index) out << ",\n";
            WriteResult(out, results[index]);
        }
        out << "\n]}\n";
        out.close();
        if (!out) throw std::runtime_error("Could not finish output JSON.");
        std::cout << "IPC JSON saved; successful lei pages=" << successful_lei_pages
                  << "; termination=" << termination << "; smoke=" << (smoke_pass ? "pass" : "fail") << '\n';
        return smoke_pass ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
