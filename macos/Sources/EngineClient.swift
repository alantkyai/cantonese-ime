import Foundation

enum EngineFailure: Error {
    case unavailable
    case busy
    case protocolFailure
    case timeout
}

// One engine process per input-method app, shared by the independent IMK
// sessions. All pipe work, startup and deadlines occur off the UI thread.
final class EngineClient {
    static let shared = EngineClient()
    typealias Completion = (Result<WireResponse, EngineFailure>) -> Void
    private struct Request {
        let id: UInt32
        let owner: UUID?
        let learning: Bool
        let payload: Data
        let completion: Completion
    }
    private let queue = DispatchQueue(label: "org.cantoneseime.engine", qos: .userInitiated)
    private let statusLock = NSLock()
    private var status = "Starting typing engine"
    private var acceptingInput = true
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var errors: FileHandle?
    private var pending: [Request] = []
    private var current: Request?
    private var decoder = FrameDecoder()
    private var deadline: DispatchSourceTimer?
    private var nextID: UInt32 = 0
    private var receivedFirstResponse = false

    var statusText: String {
        statusLock.lock(); defer { statusLock.unlock() }; return status
    }
    var canAcceptInput: Bool {
        statusLock.lock(); defer { statusLock.unlock() }; return acceptingInput
    }
    private func setStatus(_ text: String, accepting: Bool) {
        statusLock.lock(); status = text; acceptingInput = accepting; statusLock.unlock()
    }
    private func deliver(_ completion: @escaping Completion, _ result: Result<WireResponse, EngineFailure>) {
        DispatchQueue.main.async { completion(result) }
    }
    private func identifier() -> UInt32 {
        nextID &+= 1
        if nextID == 0 { nextID = 1 }
        return nextID
    }

    func lookup(raw: String, owner: UUID, offset: Int, completion: @escaping Completion) {
        queue.async {
            guard self.canAcceptInput else { self.deliver(completion, .failure(.unavailable)); return }
            // Only the newest queued query for this controller is useful. An
            // in-flight query is consumed normally, then ignored by its stamp.
            self.pending.removeAll { $0.owner == owner && !$0.learning }
            guard self.pending.count < 64 else { self.deliver(completion, .failure(.busy)); return }
            let id = self.identifier()
            do {
                self.pending.append(Request(id: id, owner: owner, learning: false,
                    payload: try WireProtocol.lookup(id: id, raw: raw, offset: offset), completion: completion))
                self.pump()
            } catch { self.deliver(completion, .failure(.protocolFailure)) }
        }
    }

    func recordSelection(raw: String, candidate: WireCandidate) {
        queue.async {
            guard self.canAcceptInput, self.pending.filter({ $0.learning }).count < 32 else { return }
            let id = self.identifier()
            guard let payload = try? WireProtocol.selection(id: id, raw: raw, candidate: candidate) else { return }
            // Fire once, after the client's insertText returns. No retry of a
            // timed-out acknowledgement: the selection may already be saved.
            self.pending.append(Request(id: id, owner: nil, learning: true, payload: payload, completion: { _ in }))
            self.pump()
        }
    }

    func cancelLookups(owner: UUID) {
        queue.async { self.pending.removeAll { $0.owner == owner && !$0.learning } }
    }

    func restart() {
        queue.async {
            self.stop(.unavailable)
            self.setStatus("Starting typing engine", accepting: true)
            // No startup I/O on the UI thread; the next query starts the child.
        }
    }

    func shutdown(completion: (() -> Void)? = nil) {
        queue.async {
            self.stop(.unavailable)
            if let completion { DispatchQueue.main.async(execute: completion) }
        }
    }

    private func start() throws {
        guard let resources = Bundle.main.resourceURL else { throw EngineFailure.unavailable }
        let python = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/CantoneseIMEEngine")
        let engine = resources.appendingPathComponent("engine")
        let bridge = engine.appendingPathComponent("stdio_bridge.py")
        let database = engine.appendingPathComponent("data/generated/lexicon.sqlite3")
        guard FileManager.default.isExecutableFile(atPath: python.path),
              FileManager.default.fileExists(atPath: bridge.path),
              FileManager.default.fileExists(atPath: database.path),
              let dictionaryHash = Bundle.main.object(forInfoDictionaryKey: "CantoneseIMEDictionarySHA256") as? String,
              dictionaryHash.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else { throw EngineFailure.unavailable }
        let child = Process()
        child.executableURL = python
        child.arguments = ["-I", "-B", bridge.path, "--dictionary", database.path,
                           "--expected-dictionary-sha256", dictionaryHash]
        // No inherited Python modules, user site packages or shell expansion.
        child.environment = ["PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "LC_CTYPE": "UTF-8"]
        child.currentDirectoryURL = engine
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        child.standardInput = stdin; child.standardOutput = stdout; child.standardError = stderr
        process = child; input = stdin.fileHandleForWriting; output = stdout.fileHandleForReading; errors = stderr.fileHandleForReading
        decoder = FrameDecoder(); receivedFirstResponse = false
        stdout.fileHandleForReading.readabilityHandler = { [weak self, weak child] handle in
            let bytes = (try? handle.read(upToCount: 65_536)) ?? Data()
            self?.queue.async { [weak self, weak child] in
                guard let self, let child, self.process === child else { return }
                if bytes.isEmpty { self.stop(.unavailable) } else { self.consume(bytes) }
            }
        }
        // Drain operational diagnostics to prevent a full stderr pipe. Typed
        // text, candidate lists and private learning records are never logged.
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let bytes = (try? handle.read(upToCount: 65_536)) ?? Data()
            if bytes.isEmpty { handle.readabilityHandler = nil }
        }
        child.terminationHandler = { [weak self] child in
            self?.queue.async { [weak self] in
                guard let self, self.process === child else { return }
                self.stop(.unavailable)
            }
        }
        do { try child.run() } catch { stop(.unavailable); throw EngineFailure.unavailable }
    }

    private func pump() {
        guard current == nil, !pending.isEmpty else { return }
        if process == nil {
            do { try start() } catch { stop(.unavailable); return }
        }
        let request = pending.removeFirst(); current = request
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + (receivedFirstResponse ? 2 : 30))
        timer.setEventHandler { [weak self] in self?.stop(.timeout) }
        deadline = timer; timer.resume()
        do { try input?.write(contentsOf: request.payload) } catch { stop(.unavailable) }
    }

    private func consume(_ data: Data) {
        do {
            for payload in try decoder.append(data) {
                let response = try WireProtocol.response(payload)
                guard let request = current, response.requestID == request.id else { throw WireError.malformed }
                deadline?.cancel(); deadline = nil; current = nil; receivedFirstResponse = true
                setStatus("Typing engine ready", accepting: true)
                deliver(request.completion, .success(response))
            }
            pump()
        } catch { stop(.protocolFailure) }
    }

    private func stop(_ reason: EngineFailure) {
        deadline?.cancel(); deadline = nil
        let requests = (current.map { [$0] } ?? []) + pending
        current = nil; pending = []; decoder = FrameDecoder(); receivedFirstResponse = false
        output?.readabilityHandler = nil; errors?.readabilityHandler = nil
        try? input?.close(); try? output?.close(); try? errors?.close()
        input = nil; output = nil; errors = nil
        let child = process; process = nil
        child?.terminationHandler = nil
        if child?.isRunning == true { child?.terminate() }
        setStatus("Typing engine unavailable — Restart from this menu", accepting: false)
        for request in requests { deliver(request.completion, .failure(reason)) }
    }
}
