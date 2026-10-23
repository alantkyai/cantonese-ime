import AppKit

@MainActor
final class ModeIndicator {
    static let shared = ModeIndicator()
    private var item: NSStatusItem?
    private var owner: UUID?
    func show(owner: UUID, english: Bool, menu: NSMenu) {
        self.owner = owner
        if item == nil { item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength) }
        item?.button?.title = english ? "英" : "粵"
        item?.button?.toolTip = english ? "Cantonese IME — English mode" : "Cantonese IME — Cantonese mode"
        item?.button?.setAccessibilityLabel(item?.button?.toolTip)
        item?.menu = menu
    }
    func hide(owner: UUID) {
        guard self.owner == owner else { return }
        if let item { NSStatusBar.system.removeStatusItem(item) }
        item = nil; self.owner = nil
    }
}
