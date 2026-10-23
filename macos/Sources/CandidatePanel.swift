import AppKit

private final class CandidateWindow: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

private final class CandidateButton: NSButton {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

@MainActor
final class CandidatePanel: NSObject {
    private let window: CandidateWindow
    private let content = NSView()
    private var buttons: [NSButton] = []
    private var choose: ((Int) -> Void)?
    private var outsideMonitor: Any?
    var onOutsideClick: (() -> Void)?

    override init() {
        window = CandidateWindow(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel],
                                 backing: .buffered, defer: false)
        super.init()
        window.level = .popUpMenu
        window.isFloatingPanel = true
        window.hidesOnDeactivate = false
        window.becomesKeyOnlyIfNeeded = true
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient, .ignoresCycle]
        content.wantsLayer = true
        content.layer?.cornerRadius = 7
        content.layer?.borderWidth = 0.5
        window.contentView = content
        content.setAccessibilityRole(.list)
        content.setAccessibilityLabel("Cantonese word choices")
    }

    func show(_ candidates: [WireCandidate], selected: Int, caret: NSRect,
              choose: @escaping (Int) -> Void) {
        guard !candidates.isEmpty else { hide(); return }
        self.choose = choose
        buttons.forEach { $0.removeFromSuperview() }; buttons = []
        let screen = NSScreen.screens.first { $0.frame.intersects(caret) } ?? NSScreen.main
        let visible = screen?.visibleFrame ?? NSRect(x: 0, y: 0, width: 800, height: 600)
        let maxWidth = max(40, min(480, visible.width - 12))
        let font = NSFont.systemFont(ofSize: 18)
        let rowHeight: CGFloat = 31
        var x: CGFloat = 5, y: CGFloat = 4, widest: CGFloat = 0
        var frames: [NSRect] = []
        for (index, candidate) in candidates.enumerated() {
            let title = "\(index + 1) \(candidate.text)"
            let measured = (title as NSString).size(withAttributes: [.font: font]).width
            let width = min(maxWidth - 10, max(32, ceil(measured) + 16))
            if x > 5 && x + width > maxWidth - 5 { widest = max(widest, x); x = 5; y += rowHeight }
            frames.append(NSRect(x: x, y: y, width: width, height: rowHeight - 2))
            x += width + 2
        }
        widest = max(widest, x)
        let size = NSSize(width: min(maxWidth, widest + 3), height: y + rowHeight + 4)
        window.setContentSize(size)
        content.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        content.layer?.borderColor = NSColor.separatorColor.cgColor
        for (index, frame) in frames.enumerated() {
            let button = CandidateButton(frame: NSRect(x: frame.minX, y: size.height - frame.maxY,
                                                        width: frame.width, height: frame.height))
            button.title = "\(index + 1) \(candidates[index].text)"
            button.font = font; button.isBordered = false; button.bezelStyle = .inline
            button.setButtonType(.momentaryChange); button.focusRingType = .none
            button.lineBreakMode = .byTruncatingTail
            button.alignment = .left; button.tag = index
            button.target = self; button.action = #selector(selectCandidate(_:))
            button.wantsLayer = true; button.layer?.cornerRadius = 4
            button.layer?.backgroundColor = (index == selected ? NSColor.selectedContentBackgroundColor : NSColor.clear).cgColor
            button.contentTintColor = index == selected ? .alternateSelectedControlTextColor : .labelColor
            button.setAccessibilityLabel(button.title)
            content.addSubview(button); buttons.append(button)
        }
        let anchor = caret == .zero ? NSRect(origin: NSEvent.mouseLocation, size: .zero) : caret
        var origin = NSPoint(x: anchor.minX, y: anchor.minY - size.height - 3)
        if origin.y < visible.minY { origin.y = anchor.maxY + 3 }
        origin.x = min(max(origin.x, visible.minX), max(visible.minX, visible.maxX - size.width))
        origin.y = min(max(origin.y, visible.minY), max(visible.minY, visible.maxY - size.height))
        window.setFrameOrigin(origin)
        window.orderFrontRegardless()
        if outsideMonitor == nil {
            // Mouse-only observation: no event tap, keyboard monitoring,
            // Accessibility permission request or input capture is installed.
            outsideMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
                MainThread.run { self?.hide(); self?.onOutsideClick?() }
            }
        }
    }

    func hide() {
        window.orderOut(nil); choose = nil
        if let outsideMonitor { NSEvent.removeMonitor(outsideMonitor); self.outsideMonitor = nil }
    }
    @objc private func selectCandidate(_ sender: NSButton) { choose?(sender.tag) }
}
