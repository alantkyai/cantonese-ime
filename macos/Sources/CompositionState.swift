// Foundation-only per-client state. A response can update only its original
// active session, raw spelling, generation and page request.
import Foundation

enum BufferedKey: Equatable {
    case text(String)
    case backspace
    case space
    case number(Int)
    case punctuation(String)

    static func classify(_ characters: String) -> BufferedKey {
        if characters.utf8.count == 1, let digit = Int(characters), (1...9).contains(digit) { return .number(digit) }
        if !characters.isEmpty && characters.utf8.allSatisfy({ (97...122).contains($0) || $0 == 39 }) { return .text(characters) }
        return .punctuation(characters)
    }
}

enum SelectionDisposition: Equatable { case wait, choose, literal }

struct QueryStamp: Equatable {
    let generation: UInt64
    let raw: String
    let offset: Int
    let previousOffsets: [Int]
}

struct CompositionState {
    private(set) var generation: UInt64 = 0
    private(set) var active = false
    private(set) var raw = ""
    private(set) var candidates: [WireCandidate] = []
    private(set) var selected = 0
    private(set) var offset = 0
    private(set) var nextOffset: Int?
    private(set) var previousOffsets: [Int] = []
    private(set) var waiting = false
    private(set) var completionTruncated = false

    mutating func activate() { reset(); active = true }
    mutating func deactivate() { reset(); active = false }
    mutating func reset() {
        generation &+= 1; raw = ""; candidates = []; selected = 0; offset = 0
        nextOffset = nil; previousOffsets = []; waiting = false; completionTruncated = false
    }
    @discardableResult mutating func append(_ text: String) -> Bool {
        guard active, !text.isEmpty, text.utf8.allSatisfy({ (97...122).contains($0) || $0 == 39 }),
              raw.utf8.count + text.utf8.count <= WireProtocol.maxInputBytes else { return false }
        raw.append(text); invalidatePage(); return true
    }
    mutating func backspace() {
        if !raw.isEmpty { raw.removeLast(); invalidatePage() }
    }
    private mutating func invalidatePage() {
        generation &+= 1; candidates = []; selected = 0; offset = 0; nextOffset = nil
        previousOffsets = []; waiting = false; completionTruncated = false
    }
    mutating func query(offset requested: Int = 0, previousOffsets proposed: [Int]? = nil) -> QueryStamp {
        generation &+= 1; waiting = true
        return QueryStamp(generation: generation, raw: raw, offset: requested, previousOffsets: proposed ?? previousOffsets)
    }
    func accepts(_ stamp: QueryStamp) -> Bool {
        active && generation == stamp.generation && raw == stamp.raw
    }
    @discardableResult mutating func receive(_ response: WireResponse, for stamp: QueryStamp) -> Bool {
        guard accepts(stamp) else { return false }
        waiting = false
        guard response.status == 0,
              Set(response.candidates.map(\.text)).count == response.candidates.count,
              response.nextOffset == nil || response.nextOffset == stamp.offset + response.candidates.count else { return false }
        candidates = response.candidates; selected = 0; offset = stamp.offset
        nextOffset = response.nextOffset; completionTruncated = response.completionTruncated
        previousOffsets = stamp.previousOffsets
        return true
    }
    mutating func fail(_ stamp: QueryStamp) {
        // A failed page request does not replace its previously visible page.
        // Input edits already cleared that page before issuing a fresh query.
        if accepts(stamp) { waiting = false }
    }
    mutating func dismissCandidates() {
        generation &+= 1; waiting = false; candidates = []; nextOffset = nil
    }
    mutating func highlight(_ index: Int) {
        if candidates.indices.contains(index) { selected = index }
    }
    func selectionDisposition(_ index: Int) -> SelectionDisposition {
        if waiting { return .wait }
        return candidates.indices.contains(index) ? .choose : .literal
    }
    mutating func move(_ delta: Int) { highlight(selected + delta) }
    mutating func forwardPage() -> QueryStamp? {
        guard !waiting, let next = nextOffset else { return nil }
        return query(offset: next, previousOffsets: previousOffsets + [offset])
    }
    mutating func backwardPage() -> QueryStamp? {
        guard !waiting, let previous = previousOffsets.last else { return nil }
        return query(offset: previous, previousOffsets: Array(previousOffsets.dropLast()))
    }
}
