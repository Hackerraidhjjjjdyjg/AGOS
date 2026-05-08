// AGOS macOS App — Status Bar View
// Menu bar dropdown with agent status, quick actions, and chat input.

import SwiftUI

struct StatusBarView: View {
    @ObservedObject var state: DaemonState
    @State private var userInput: String = ""
    @State private var isProcessing: Bool = false
    @State private var lastResult: String = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // ─── Header ───────────────────────────────────
            HStack {
                Image(systemName: "brain.head.profile")
                    .font(.title2)
                    .foregroundColor(.accentColor)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text("AGOS")
                        .font(.headline)
                    Text(state.isConnected ? "Connected" : "Disconnected")
                        .font(.caption)
                        .foregroundColor(state.isConnected ? .green : .red)
                }
                
                Spacer()
                
                // Tier badge
                Text(state.tier.uppercased())
                    .font(.caption2)
                    .fontWeight(.bold)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(tierColor)
                    .foregroundColor(.white)
                    .cornerRadius(4)
            }
            .padding()
            
            Divider()
            
            // ─── Agent Stats ──────────────────────────────
            VStack(spacing: 8) {
                HStack {
                    StatCard(icon: "person.3.fill", label: "Active", value: "\(state.activeAgents)", color: .blue)
                    StatCard(icon: "clock.fill", label: "Ready", value: "\(state.readyAgents)", color: .green)
                    StatCard(icon: "chart.bar.fill", label: "Scheduled", value: "\(state.totalScheduled)", color: .orange)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            
            Divider()
            
            // ─── Chat Input ───────────────────────────────
            HStack {
                TextField("Ask AGOS anything...", text: $userInput)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { sendMessage() }
                
                Button(action: sendMessage) {
                    Image(systemName: isProcessing ? "hourglass" : "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundColor(.accentColor)
                }
                .disabled(userInput.isEmpty || isProcessing)
                .buttonStyle(.borderless)
            }
            .padding()
            
            // ─── Result ───────────────────────────────────
            if !lastResult.isEmpty {
                ScrollView {
                    Text(lastResult)
                        .font(.system(.caption, design: .monospaced))
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                }
                .frame(maxHeight: 120)
                .padding(.horizontal)
                .padding(.bottom, 8)
            }
            
            Divider()
            
            // ─── Quick Actions ────────────────────────────
            HStack(spacing: 12) {
                QuickAction(icon: "gearshape", label: "Settings") {
                    NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
                }
                
                QuickAction(icon: "arrow.clockwise", label: "Restart") {
                    DaemonManager.shared.stop()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                        DaemonManager.shared.start()
                    }
                }
                
                QuickAction(icon: "power", label: "Quit") {
                    NSApp.terminate(nil)
                }
            }
            .padding()
        }
        .frame(width: 360)
    }
    
    private var tierColor: Color {
        switch state.tier {
        case "enterprise": return .purple
        case "pro": return .blue
        default: return .gray
        }
    }
    
    private func sendMessage() {
        guard !userInput.isEmpty else { return }
        isProcessing = true
        lastResult = "Processing: \(userInput)..."
        
        // TODO: Send via gRPC to daemon
        let input = userInput
        userInput = ""
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            lastResult = "✅ Sent to orchestrator: \(input)"
            isProcessing = false
        }
    }
}

// ─── Components ───────────────────────────────────────────────

struct StatCard: View {
    let icon: String
    let label: String
    let value: String
    let color: Color
    
    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundColor(color)
            Text(value)
                .font(.system(.title2, design: .rounded))
                .fontWeight(.bold)
            Text(label)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }
}

struct QuickAction: View {
    let icon: String
    let label: String
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Image(systemName: icon)
                    .font(.body)
                Text(label)
                    .font(.caption2)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderless)
    }
}
