import AppKit
import InputMethodKit

@MainActor
final class ApplicationDelegate: NSObject, NSApplicationDelegate {
    private var server: IMKServer?
    func applicationDidFinishLaunching(_ notification: Notification) {
        let bundle = Bundle.main
        let expected = "org.cantoneseime.inputmethod.CantoneseIME"
        guard bundle.bundleIdentifier == expected,
              let connection = bundle.object(forInfoDictionaryKey: "InputMethodConnectionName") as? String,
              connection == expected + "_Connection",
              NSClassFromString("CantoneseInputController") != nil,
              let server = IMKServer(name: connection, bundleIdentifier: expected) else {
            NSLog("Cantonese IME could not initialize its input server.")
            NSApplication.shared.terminate(nil)
            return
        }
        self.server = server
    }
    func applicationWillTerminate(_ notification: Notification) { EngineClient.shared.shutdown() }
}

MainActor.assumeIsolated {
    let application = NSApplication.shared
    let applicationDelegate = ApplicationDelegate()
    application.delegate = applicationDelegate
    application.setActivationPolicy(.accessory)
    withExtendedLifetime(applicationDelegate) { application.run() }
}
