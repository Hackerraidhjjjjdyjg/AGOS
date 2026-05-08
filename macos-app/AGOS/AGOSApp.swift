// AGOS macOS App — Entry Point
// SwiftUI menu bar agent with status bar integration.

import SwiftUI

@main
struct AGOSApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var daemonState = DaemonState()
    
    var body: some Scene {
        // Menu Bar Extra — lives in the macOS status bar
        MenuBarExtra("AGOS", systemImage: daemonState.isConnected ? "brain.head.profile" : "brain.head.profile.fill") {
            StatusBarView(state: daemonState)
        }
        .menuBarExtraStyle(.window)
        
        // Settings window
        Settings {
            SettingsView(state: daemonState)
        }
    }
}

// App Delegate — handles lifecycle events
class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Launch the agosd daemon
        DaemonManager.shared.start()
        NSLog("[AGOS] Application launched")
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        DaemonManager.shared.stop()
        NSLog("[AGOS] Application terminated")
    }
}

// Observable state for the daemon connection
class DaemonState: ObservableObject {
    @Published var isConnected: Bool = false
    @Published var activeAgents: Int = 0
    @Published var readyAgents: Int = 0
    @Published var totalScheduled: Int = 0
    @Published var preemptions: Int = 0
    @Published var currentUser: String = ""
    @Published var tier: String = "free"
}

// Daemon lifecycle manager
class DaemonManager {
    static let shared = DaemonManager()
    private var daemonProcess: Process?
    
    func start() {
        let bundlePath = Bundle.main.bundlePath
        let daemonPath = "\(bundlePath)/Contents/MacOS/agosd"
        
        guard FileManager.default.fileExists(atPath: daemonPath) else {
            NSLog("[AGOS] Daemon not found at: \(daemonPath)")
            return
        }
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: daemonPath)
        process.arguments = ["--dev", "--port", "50051", "--ws-port", "8765"]
        
        do {
            try process.run()
            daemonProcess = process
            NSLog("[AGOS] Daemon started (PID: \(process.processIdentifier))")
        } catch {
            NSLog("[AGOS] Failed to start daemon: \(error)")
        }
    }
    
    func stop() {
        daemonProcess?.terminate()
        NSLog("[AGOS] Daemon stopped")
    }
}
