import Foundation

// InputMethodKit is Objective-C and may call a controller away from the main
// thread. Swift 5.10+ back-deploys assumeIsolated to the macOS 13 deployment
// target. Every AppKit and client-proxy operation passes this checked boundary.
enum MainThread {
    static func run<T>(_ operation: @MainActor () -> T) -> T {
        // Swift 6 constrains assumeIsolated's direct return to Sendable. IMK's
        // menu callback returns an AppKit object, so the checked actor closure
        // returns Void and assigns its result within this synchronous scope.
        var result: T?
        if Thread.isMainThread {
            MainActor.assumeIsolated { result = operation() }
        } else {
            DispatchQueue.main.sync { MainActor.assumeIsolated { result = operation() } }
        }
        return result!
    }
}
