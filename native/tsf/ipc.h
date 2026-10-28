#pragma once

#include <windows.h>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace cime {

constexpr std::size_t kMaxInputLength = 256;
constexpr std::size_t kMaxLearningReadingBytes = 14 * kMaxInputLength - 1;

struct Candidate {
    std::wstring text;
    std::wstring reading;
};

struct Page {
    std::vector<Candidate> candidates;
    std::int32_t next_offset = -1;
    bool completion_truncated = false;
    std::wstring error;
};

// Protocol version 1, little-endian DWORD fields. See PROTOCOL.md.
class Backend {
public:
    bool Lookup(const std::wstring& raw, bool strict, std::uint32_t offset, Page& page);
    // Call only after the application has successfully committed a candidate.
    // Saving preference data is best effort and must never undo that commit.
    bool RecordSelection(const std::wstring& raw, bool strict, const Candidate& candidate);
    // Learned next-text suggestions (IMP1). Candidates carry no reading.
    bool Predict(const std::wstring& context, Page& page);
    // One consecutive-commit record (IMS1); best effort, never retried.
    bool RecordSequence(const std::wstring& previous, const std::wstring& following);
    static std::wstring PipeName();

private:
    std::uint32_t sequence_ = 0;
};

}  // namespace cime
