import AppKit
import Carbon
import InputMethodKit

@objc(CantoneseInputController)
@MainActor
final class CantoneseInputController: IMKInputController {
    private let sessionID = UUID()
    private var state = CompositionState()
    private var inputClient: (any IMKTextInput)?
    private var english = false
    private let engine = EngineClient.shared
    private lazy var panel: CandidatePanel = {
        let result = CandidatePanel()
        result.onOutsideClick = { [weak self] in
            guard let self else { return }
            // A global mouse observation only dismisses UI. It never writes to
            // a possibly changed text field or commits/learns the user's text.
            self.flushBufferedLiterallyOnNextKey = self.deferredSelection != nil || !self.deferredSeparator.isEmpty || !self.bufferedKeys.isEmpty
            self.state.dismissCandidates()
            self.deferredSelection = nil
        }
        return result
    }()
    private var deferredSelection: Int?
    private var deferredSeparator = ""
    private var bufferedKeys: [BufferedKey] = []
    private var flushBufferedLiterallyOnNextKey = false

    nonisolated override func recognizedEvents(_ sender: Any!) -> Int {
        Int(NSEvent.EventTypeMask.keyDown.rawValue)
    }

    nonisolated override func activateServer(_ sender: Any!) {
        MainThread.run {
            super.activateServer(sender)
            self.state.activate()
            self.inputClient = (sender as? any IMKTextInput) ?? (self.client() as? any IMKTextInput)
            self.english = UserDefaults.standard.bool(forKey: "DirectEnglish")
            self.clearDeferred()
            self.updateIndicator()
        }
    }

    nonisolated override func deactivateServer(_ sender: Any!) {
        MainThread.run {
            self.finishLiteral()
            self.state.deactivate(); self.inputClient = nil
            self.engine.cancelLookups(owner: self.sessionID)
            self.panel.hide(); ModeIndicator.shared.hide(owner: self.sessionID)
            super.deactivateServer(sender)
        }
    }

    nonisolated override func commitComposition(_ sender: Any!) {
        MainThread.run { self.finishLiteral() }
    }

    nonisolated override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
        MainThread.run {
            guard let event, let client = sender as? any IMKTextInput else { return false }
            return self.handleKey(event, client: client)
        }
    }

    nonisolated override func menu() -> NSMenu! {
        MainThread.run { self.makeMenu() }
    }

    private func handleKey(_ event: NSEvent, client: any IMKTextInput) -> Bool {
        guard event.type == .keyDown else { return false }
        guard state.active else { return false }
        inputClient = client
        if IsSecureEventInputEnabled() {
            // Secure fields are left to the system's direct input. Do not ask
            // for their text, launch a lookup, or save a selection.
            state.reset(); clearDeferred(); panel.hide(); engine.cancelLookups(owner: sessionID)
            return false
        }
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if event.keyCode == 49 && flags.contains([.control, .shift]) && !flags.contains(.command) && !flags.contains(.option) {
            toggleMode(nil); return true
        }
        if flags.contains(.command) || flags.contains(.control) || flags.contains(.option) {
            finishLiteral(); return false
        }
        if flushBufferedLiterallyOnNextKey { finishLiteral() }
        guard !english, engine.canAcceptInput else { finishLiteral(); return false }
        if event.keyCode == 53 { // Escape discards this uncommitted composition.
            guard !state.raw.isEmpty else { return false }
            cancel(); return true
        }
        if event.keyCode == 36 || event.keyCode == 76 { // Return commits raw letters, as on Windows.
            guard !state.raw.isEmpty else { return false }
            finishLiteral(); return true
        }
        if event.keyCode == 48 { finishLiteral(); return false } // Tab retains its app meaning.
        if flags.contains(.shift) || flags.contains(.capsLock) {
            finishLiteral(); return false
        }

        if deferredSelection != nil {
            switch event.keyCode {
            case 123, 126: deferredSelection = max(0, (deferredSelection ?? 0) - 1); return true
            case 124, 125: deferredSelection = min(8, (deferredSelection ?? 0) + 1); return true
            case 51, 117:
                if bufferedKeys.isEmpty { deferredSelection = nil; deferredSeparator = "" }
                else { bufferedKeys.append(.backspace) }
            case 49: bufferedKeys.append(.space)
            default:
                guard let characters = event.characters, !characters.isEmpty else { finishLiteral(); return false }
                bufferedKeys.append(BufferedKey.classify(characters))
            }
            // Bound held text while the first engine request initializes. A
            // literal flush preserves every received character without waiting.
            if bufferedPreview().utf8.count > 256 || bufferedKeys.count > 256 { finishLiteral() }
            else { markCurrent() }
            return true
        }

        switch event.keyCode {
        case 51, 117:
            guard !state.raw.isEmpty else { return false }
            state.backspace()
            if state.raw.isEmpty { cancel() } else { markCurrent(); requestCurrent() }
            return true
        case 49:
            guard !state.raw.isEmpty else { return false }
            return selectOrDefer(state.selected, literalKey: " ")
        case 123, 126:
            guard !state.raw.isEmpty else { return false }
            if state.selected == 0, let stamp = state.backwardPage() { request(stamp) }
            else { state.move(-1); showCandidates() }
            return true
        case 124, 125:
            guard !state.raw.isEmpty else { return false }
            if state.selected + 1 >= state.candidates.count, let stamp = state.forwardPage() { request(stamp) }
            else { state.move(1); showCandidates() }
            return true
        case 116:
            guard !state.raw.isEmpty else { return false }
            if let stamp = state.backwardPage() { request(stamp) }; return true
        case 121:
            guard !state.raw.isEmpty else { return false }
            if let stamp = state.forwardPage() { request(stamp) }; return true
        default: break
        }

        guard let characters = event.charactersIgnoringModifiers, !characters.isEmpty else { finishLiteral(); return false }
        if characters.utf8.count == 1, let digit = Int(characters), (1...9).contains(digit), !state.raw.isEmpty {
            return selectOrDefer(digit - 1, literalKey: characters)
        }
        if state.append(characters) { markCurrent(); requestCurrent(); return true }
        finishLiteral(); return false
    }

    private func requestCurrent() { request(state.query()) }
    private func request(_ stamp: QueryStamp) {
        panel.hide()
        engine.lookup(raw: stamp.raw, owner: sessionID, offset: stamp.offset) { [weak self] result in
            MainThread.run {
                guard let self, self.state.accepts(stamp) else { return }
                switch result {
                case .success(let response):
                    guard self.state.receive(response, for: stamp) else {
                        if self.deferredSelection != nil { self.finishLiteral() }
                        else { self.panel.hide() }
                        return
                    }
                    if let index = self.deferredSelection {
                        if self.state.candidates.indices.contains(index) { self.choose(index) }
                        else { self.finishLiteral() }
                    } else { self.showCandidates() }
                case .failure:
                    self.state.fail(stamp); self.finishLiteral(); self.updateIndicator()
                }
            }
        }
    }

    @discardableResult private func selectOrDefer(_ index: Int, literalKey: String) -> Bool {
        switch state.selectionDisposition(index) {
        case .wait: deferredSelection = index; deferredSeparator = literalKey; markCurrent(); return true
        case .choose: choose(index); return true
        case .literal:
            finishLiteral()
            if literalKey == " " { insertLiteral(literalKey); return true }
            return false // Let the original numeric key retain its app meaning.
        }
    }

    private func choose(_ index: Int) {
        guard state.active, !state.waiting, state.candidates.indices.contains(index), let client = inputClient,
              !IsSecureEventInputEnabled() else { return }
        let chosen = state.candidates[index], raw = state.raw
        let replay = bufferedKeys
        state.reset(); clearDeferred(); panel.hide(); engine.cancelLookups(owner: sessionID)
        // insertText replaces the marked text exactly once. Learning is sent
        // only after this client method returns; there is no learning retry.
        client.insertText(chosen.text, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
        engine.recordSelection(raw: raw, candidate: chosen)
        for key in replay { replayKey(key) }
    }

    private func replayKey(_ key: BufferedKey) {
        if deferredSelection != nil { bufferedKeys.append(key); markCurrent(); return }
        switch key {
        case .space:
            if state.raw.isEmpty { insertLiteral(" ") }
            else { selectOrDefer(state.selected, literalKey: " ") }
        case .number(let value):
            if state.raw.isEmpty { insertLiteral(String(value)) }
            else if !selectOrDefer(value - 1, literalKey: String(value)) { insertLiteral(String(value)) }
        case .backspace:
            state.backspace(); markCurrent()
            if !state.raw.isEmpty { requestCurrent() }
        case .text(let text):
            // Events held during startup are replayed as the same text, not as
            // injected system keystrokes. This requires no monitoring permission.
            for character in text {
                let value = String(character)
                if state.append(value) { markCurrent(); requestCurrent() }
                else { finishLiteral(); insertLiteral(value) }
            }
        case .punctuation(let text): finishLiteral(); insertLiteral(text)
        }
    }

    private func bufferedPreview() -> String {
        var result = state.raw + deferredSeparator
        for key in bufferedKeys {
            switch key {
            case .text(let text), .punctuation(let text): result.append(text)
            case .space: result.append(" ")
            case .number(let number): result.append(String(number))
            case .backspace: if !result.isEmpty { result.removeLast() }
            }
        }
        return result
    }
    private func clearDeferred() {
        deferredSelection = nil; deferredSeparator = ""; bufferedKeys = []; flushBufferedLiterallyOnNextKey = false
    }
    private func markCurrent() {
        guard state.active, let client = inputClient else { return }
        let raw = bufferedPreview()
        client.setMarkedText(raw, selectionRange: NSRange(location: raw.utf16.count, length: 0),
                             replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
    }
    private func insertLiteral(_ text: String) {
        guard !text.isEmpty, let client = inputClient, !IsSecureEventInputEnabled() else { return }
        client.insertText(text, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
    }
    private func finishLiteral() {
        let raw = bufferedPreview()
        state.reset(); clearDeferred(); panel.hide(); engine.cancelLookups(owner: sessionID)
        insertLiteral(raw)
    }
    private func cancel() {
        state.reset(); clearDeferred(); panel.hide(); engine.cancelLookups(owner: sessionID)
        inputClient?.setMarkedText("", selectionRange: NSRange(location: 0, length: 0),
                                   replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
    }
    private func showCandidates() {
        guard state.active, !state.waiting, !state.raw.isEmpty, !state.candidates.isEmpty, let client = inputClient else {
            panel.hide(); return
        }
        var caret = NSRect.zero
        _ = client.attributes(forCharacterIndex: 0, lineHeightRectangle: &caret)
        let generation = state.generation
        panel.show(state.candidates, selected: state.selected, caret: caret) { [weak self] index in
            guard let self, self.state.active, self.state.generation == generation else { return }
            self.choose(index)
        }
    }

    private func makeMenu() -> NSMenu {
        let menu = NSMenu(title: "Cantonese IME")
        let cantonese = NSMenuItem(title: "粵 Cantonese", action: #selector(setCantonese(_:)), keyEquivalent: "")
        cantonese.target = self; cantonese.state = english ? .off : .on; menu.addItem(cantonese)
        let direct = NSMenuItem(title: "英 English", action: #selector(setEnglish(_:)), keyEquivalent: "")
        direct.target = self; direct.state = english ? .on : .off; menu.addItem(direct)
        let hint = NSMenuItem(title: "Switch mode: Control + Shift + Space", action: nil, keyEquivalent: "")
        hint.isEnabled = false; menu.addItem(hint); menu.addItem(.separator())
        let status = NSMenuItem(title: engine.statusText, action: nil, keyEquivalent: "")
        status.isEnabled = false; menu.addItem(status)
        let restart = NSMenuItem(title: "Restart typing engine", action: #selector(restartEngine(_:)), keyEquivalent: "")
        restart.target = self; menu.addItem(restart)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Quit Cantonese IME", action: #selector(quit(_:)), keyEquivalent: "")
        quit.target = self; menu.addItem(quit)
        return menu
    }
    private func updateIndicator() {
        if state.active { ModeIndicator.shared.show(owner: sessionID, english: english, menu: makeMenu()) }
    }
    private func setMode(_ value: Bool) {
        finishLiteral(); english = value
        UserDefaults.standard.set(value, forKey: "DirectEnglish"); updateIndicator()
    }
    @objc private func setCantonese(_ sender: NSMenuItem) { setMode(false) }
    @objc private func setEnglish(_ sender: NSMenuItem) { setMode(true) }
    @objc private func toggleMode(_ sender: NSMenuItem?) { setMode(!english) }
    @objc private func restartEngine(_ sender: NSMenuItem) { finishLiteral(); engine.restart(); updateIndicator() }
    @objc private func quit(_ sender: NSMenuItem) {
        finishLiteral(); ModeIndicator.shared.hide(owner: sessionID)
        engine.shutdown { NSApplication.shared.terminate(nil) }
    }
}
