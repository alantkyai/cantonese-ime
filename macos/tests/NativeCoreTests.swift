// Host-native Foundation tests. No IMK server, registration, global input
// activation, GUI automation, keyboard injection or personal learning access.
import Foundation

@main
struct NativeCoreTests {
    static var checks = 0
    static func expect(_ condition: @autoclosure () throws -> Bool, _ label: String) rethrows {
        let passed = try condition()
        precondition(passed, label)
        checks += 1
    }
    static func rejects(_ label: String, _ body: () throws -> Void) {
        do { try body(); preconditionFailure("Accepted invalid input: " + label) }
        catch { checks += 1 }
    }
    static func hex(_ string: String) -> Data {
        let characters = Array(string)
        return Data(stride(from: 0, to: characters.count, by: 2).map {
            UInt8(String(characters[$0...($0 + 1)]), radix: 16)!
        })
    }
    static func page(_ id: UInt32 = 1, next: Int? = nil, text: String = "火炬", status: UInt32 = 0) -> WireResponse {
        WireResponse(requestID: id, status: status, nextOffset: next, completionTruncated: false,
                     candidates: status == 0 ? [WireCandidate(text: text, reading: "fo2 keoi5")] : [])
    }

    static func main() throws {
        // These independent golden vectors were emitted by the project's Python
        // native_protocol encode_request/encode_learning_request/encode_response.
        let lookup = hex("1e000000494d45312a00000000000000000000000900000006000000666f67657569")
        let learn = hex("20000000494d4c312b000000000000000200000003000000030000006e67e594946e6734")
        let response = hex("33000000494d45312a00000000000000ffffffff00000000010000000000000006000000e781abe782ac09000000666f32206b656f6935")
        try expect(WireProtocol.lookup(id: 42, raw: "fogeui") == lookup, "Python lookup wire compatibility")
        try expect(WireProtocol.selection(id: 43, raw: "ng", candidate: WireCandidate(text: "唔", reading: "ng4")) == learn,
                   "Python learning wire compatibility")
        var decoder = FrameDecoder()
        var fragments: [Data] = []
        for byte in response { fragments += try decoder.append(Data([byte])) }
        expect(fragments.count == 1, "Fragmented frame count")
        let decoded = try WireProtocol.response(fragments[0])
        expect(decoded.requestID == 42 && decoded.status == 0, "Response identity/status")
        expect(decoded.candidates == [WireCandidate(text: "火炬", reading: "fo2 keoi5")], "UTF8 candidates")
        var combined = FrameDecoder()
        try expect(combined.append(response + response).count == 2, "Multiple frames in one read")
        rejects("zero frame") { var decoder = FrameDecoder(); _ = try decoder.append(Data([0, 0, 0, 0])) }
        rejects("oversized frame") { var decoder = FrameDecoder(); _ = try decoder.append(Data([1, 0, 16, 0])) }
        rejects("nonASCII request") { _ = try WireProtocol.lookup(id: 1, raw: "粵") }
        rejects("oversized input") { _ = try WireProtocol.lookup(id: 1, raw: String(repeating: "a", count: 257)) }
        rejects("invalid mode") { _ = try WireProtocol.lookup(id: 1, raw: "ng", mode: 2) }
        rejects("negative offset") { _ = try WireProtocol.lookup(id: 1, raw: "ng", offset: -1) }
        rejects("bad learning reading") {
            _ = try WireProtocol.selection(id: 1, raw: "ng", candidate: WireCandidate(text: "唔", reading: "ng"))
        }
        rejects("empty learning input") {
            _ = try WireProtocol.selection(id: 1, raw: "", candidate: WireCandidate(text: "唔", reading: "ng4"))
        }
        rejects("trailing response bytes") { _ = try WireProtocol.response(fragments[0] + Data([0])) }
        rejects("bad UTF8 candidate") {
            var bad = fragments[0]; bad[32] = 0xff; _ = try WireProtocol.response(bad)
        }
        rejects("invalid next cursor") {
            var bad = fragments[0]
            bad.replaceSubrange(12..<16, with: [0xfe, 0xff, 0xff, 0xff])
            _ = try WireProtocol.response(bad)
        }

        var state = CompositionState()
        state.activate(); expect(state.append("ng"), "Append input")
        let old = state.query()
        expect(state.append("ho"), "Append while query pending")
        expect(!state.receive(page(), for: old), "Old spelling response is stale")
        let first = state.query()
        expect(state.receive(page(next: 1, text: "唔好"), for: first), "Current response accepted")
        expect(state.raw == "ngho" && state.candidates[0].text == "唔好", "Current raw/page")
        let next = state.forwardPage()!
        expect(state.previousOffsets.isEmpty && state.offset == 0, "Forward history is tentative")
        state.fail(next)
        expect(state.previousOffsets.isEmpty && state.offset == 0, "Failed forward preserves history")
        let second = state.forwardPage()!
        expect(!state.receive(page(next: 1), for: second), "Regressing cursor rejected")
        expect(state.previousOffsets.isEmpty && state.offset == 0, "Bad cursor preserves history")
        let third = state.forwardPage()!
        expect(state.receive(page(next: 2, text: "另一詞"), for: third), "Second page accepted")
        expect(state.previousOffsets == [0] && state.offset == 1, "Successful forward publishes history")
        let backward = state.backwardPage()!
        expect(state.previousOffsets == [0] && state.offset == 1, "Back history remains tentative")
        expect(!state.receive(page(status: 2), for: backward), "Capacity failure rejected")
        expect(state.previousOffsets == [0] && state.offset == 1, "Failed backward preserves history")
        let finalBack = state.backwardPage()!
        expect(state.receive(page(next: 1), for: finalBack), "Successful backward")
        expect(state.previousOffsets.isEmpty && state.offset == 0, "Successful backward publishes history")
        let dismissed = state.query()
        state.dismissCandidates()
        expect(!state.receive(page(), for: dismissed) && state.raw == "ngho", "Outside dismissal rejects old UI response")
        let deactivated = state.query()
        state.deactivate()
        expect(!state.receive(page(), for: deactivated) && state.raw.isEmpty, "Inactive session rejects response")
        state.activate(); _ = state.append("ng")
        let duplicateStamp = state.query()
        let duplicate = WireResponse(requestID: 1, status: 0, nextOffset: nil, completionTruncated: false,
            candidates: [WireCandidate(text: "唔", reading: "ng4"), WireCandidate(text: "唔", reading: "m4")])
        expect(!state.receive(duplicate, for: duplicateStamp), "Duplicate candidate texts rejected")
        expect(state.selectionDisposition(0) == .literal, "Unknown input needs literal fallback")
        let pending = state.query()
        expect(state.selectionDisposition(1) == .wait, "Selection waits for original pending generation")
        _ = state.receive(page(), for: pending)
        expect(state.selectionDisposition(0) == .choose && state.selectionDisposition(8) == .literal,
               "Valid choice selected; invalid number retains literal meaning")
        expect(BufferedKey.classify("2") == .number(2), "Buffered number retains candidate-selection meaning")
        expect(BufferedKey.classify("hou") == .text("hou"), "Buffered ASCII composition")
        expect(BufferedKey.classify(".") == .punctuation("."), "Buffered punctuation")
        expect(BufferedKey.classify("0") == .punctuation("0"), "Zero is not candidate selection")
        MainThread.run { expect(Thread.isMainThread, "Main-thread isolation boundary") }
        let report: [String: Any] = ["passed": true, "checks": checks,
            "scope": "Host-native Foundation wire/state tests; not IMK activation or native typing proof"]
        let json = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        FileHandle.standardOutput.write(json + Data([10]))
    }
}
