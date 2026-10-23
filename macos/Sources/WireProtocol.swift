// Project-authored implementation of cantonese_ime/native_protocol.py.
// Foundation-only: the same codec is exercised by the macOS command-line tests.
import Foundation

struct WireCandidate: Equatable {
    let text: String
    let reading: String
}

struct WireResponse: Equatable {
    let requestID: UInt32
    let status: UInt32
    let nextOffset: Int?
    let completionTruncated: Bool
    let candidates: [WireCandidate]
}

enum WireError: Error {
    case malformed
    case outOfBounds
    case invalidText
}

enum WireProtocol {
    static let magic: UInt32 = 0x31454D49
    static let learningMagic: UInt32 = 0x314C4D49
    static let maxFrameBytes = 1_048_576
    static let maxInputBytes = 256
    static let maxOffset = 10_000
    static let pageSize = 9

    static func append(_ value: UInt32, to data: inout Data) {
        data.append(contentsOf: (0..<4).map { UInt8(truncatingIfNeeded: value >> ($0 * 8)) })
    }

    static func frame(_ payload: Data) throws -> Data {
        guard (1...maxFrameBytes).contains(payload.count) else { throw WireError.outOfBounds }
        var result = Data()
        append(UInt32(payload.count), to: &result)
        result.append(payload)
        return result
    }

    static func rawBytes(_ raw: String) throws -> Data {
        let bytes = Data(raw.utf8)
        guard bytes.count <= maxInputBytes,
              bytes.allSatisfy({ (65...90).contains($0) || (97...122).contains($0)
                  || (49...54).contains($0) || $0 == 39 || $0 == 32 }) else { throw WireError.invalidText }
        return bytes
    }

    static func lookup(id: UInt32, raw: String, mode: UInt32 = 0, offset: Int = 0) throws -> Data {
        guard mode <= 1, (0...maxOffset).contains(offset) else { throw WireError.outOfBounds }
        let input = try rawBytes(raw)
        var payload = Data()
        for value in [magic, id, mode, UInt32(offset), UInt32(pageSize), UInt32(input.count)] {
            append(value, to: &payload)
        }
        payload.append(input)
        return try frame(payload)
    }

    static func selection(id: UInt32, raw: String, candidate: WireCandidate, mode: UInt32 = 0) throws -> Data {
        let input = try rawBytes(raw)
        let text = Data(candidate.text.utf8)
        let reading = Data(candidate.reading.utf8)
        guard mode <= 1, !raw.trimmingCharacters(in: .whitespaces).isEmpty,
              (1...256).contains(candidate.text.unicodeScalars.count),
              text.count <= 1024, reading.count <= 3583,
              candidate.reading.range(of: "^[a-z]{1,12}[1-6](?: [a-z]{1,12}[1-6]){0,255}$",
                                      options: .regularExpression) != nil else { throw WireError.invalidText }
        var payload = Data()
        for value in [learningMagic, id, mode, UInt32(input.count), UInt32(text.count), UInt32(reading.count)] {
            append(value, to: &payload)
        }
        payload.append(input); payload.append(text); payload.append(reading)
        return try frame(payload)
    }

    static func response(_ payload: Data) throws -> WireResponse {
        guard (28...maxFrameBytes).contains(payload.count) else { throw WireError.malformed }
        var reader = WireReader(payload)
        guard try reader.u32() == magic else { throw WireError.malformed }
        let id = try reader.u32(), status = try reader.u32()
        let next = Int32(bitPattern: try reader.u32())
        let truncated = try reader.u32(), count = try reader.u32(), errorLength = try reader.u32()
        guard status <= 3, truncated <= 1, count <= UInt32(pageSize), errorLength <= 8192,
              next == -1 || (0...maxOffset).contains(Int(next)) else { throw WireError.outOfBounds }
        _ = try reader.text(length: Int(errorLength), allowEmpty: true, maxUTF16: 8192)
        var candidates: [WireCandidate] = []
        for _ in 0..<count {
            let text = try reader.field(allowEmpty: false)
            let reading = try reader.field(allowEmpty: true)
            candidates.append(WireCandidate(text: text, reading: reading))
        }
        guard reader.isAtEnd, (status == 0 || (candidates.isEmpty && next == -1 && truncated == 0)),
              next == -1 || !candidates.isEmpty else { throw WireError.malformed }
        return WireResponse(requestID: id, status: status, nextOffset: next == -1 ? nil : Int(next),
                            completionTruncated: truncated != 0, candidates: candidates)
    }
}

struct WireReader {
    private let bytes: [UInt8]
    private(set) var position = 0
    init(_ data: Data) { bytes = Array(data) }
    var isAtEnd: Bool { position == bytes.count }
    mutating func u32() throws -> UInt32 {
        guard bytes.count - position >= 4 else { throw WireError.malformed }
        var value: UInt32 = 0
        for index in 0..<4 { value |= UInt32(bytes[position + index]) << (index * 8) }
        position += 4
        return value
    }
    mutating func text(length: Int, allowEmpty: Bool, maxUTF16: Int) throws -> String {
        guard length >= 0, length <= bytes.count - position else { throw WireError.malformed }
        let end = position + length
        guard let value = String(bytes: bytes[position..<end], encoding: .utf8),
              (allowEmpty || !value.isEmpty), value.utf16.count <= maxUTF16 else { throw WireError.invalidText }
        position = end
        return value
    }
    mutating func field(allowEmpty: Bool) throws -> String {
        let length = try u32()
        guard length <= UInt32(WireProtocol.maxFrameBytes) else { throw WireError.outOfBounds }
        return try text(length: Int(length), allowEmpty: allowEmpty, maxUTF16: 8192)
    }
}

struct FrameDecoder {
    private var buffer = Data()
    mutating func append(_ bytes: Data) throws -> [Data] {
        buffer.append(bytes)
        var result: [Data] = []
        while buffer.count >= 4 {
            var header = WireReader(Data(buffer.prefix(4)))
            let length = Int(try header.u32())
            guard (1...WireProtocol.maxFrameBytes).contains(length) else { throw WireError.outOfBounds }
            if buffer.count < 4 + length { break }
            result.append(Data(buffer[4..<(4 + length)]))
            buffer = Data(buffer.dropFirst(4 + length))
        }
        guard buffer.count <= WireProtocol.maxFrameBytes + 4 else { throw WireError.outOfBounds }
        return result
    }
}
