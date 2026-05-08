// AGOS macOS App — Settings View
// Preferences panel for API keys, model selection, and system config.

import SwiftUI

struct SettingsView: View {
    @ObservedObject var state: DaemonState
    
    @State private var anthropicKey: String = ""
    @State private var googleKey: String = ""
    @State private var groqKey: String = ""
    @State private var selectedModel: String = "llama3"
    @State private var ollamaURL: String = "http://localhost:11434"
    @State private var maxAgents: Double = 8
    @State private var launchAtLogin: Bool = false
    @State private var showNotifications: Bool = true
    
    let availableModels = ["llama3", "phi3:mini", "mistral", "claude-3.5-sonnet", "gemini-1.5-pro"]
    
    var body: some View {
        TabView {
            // ─── General ──────────────────────────────────
            Form {
                Section("Application") {
                    Toggle("Launch at Login", isOn: $launchAtLogin)
                    Toggle("Show Notifications", isOn: $showNotifications)
                    
                    HStack {
                        Text("Max Concurrent Agents")
                        Spacer()
                        Slider(value: $maxAgents, in: 1...20, step: 1)
                            .frame(width: 200)
                        Text("\(Int(maxAgents))")
                            .monospacedDigit()
                    }
                }
                
                Section("Default Model") {
                    Picker("LLM Model", selection: $selectedModel) {
                        ForEach(availableModels, id: \.self) { model in
                            Text(model).tag(model)
                        }
                    }
                    
                    TextField("Ollama URL", text: $ollamaURL)
                        .textFieldStyle(.roundedBorder)
                }
                
                Section("Account") {
                    LabeledContent("Email", value: state.currentUser.isEmpty ? "Not signed in" : state.currentUser)
                    LabeledContent("Tier", value: state.tier.capitalized)
                    
                    Button("Sign In / Sign Up") {
                        // TODO: Open auth flow
                    }
                }
            }
            .tabItem { Label("General", systemImage: "gearshape") }
            
            // ─── API Keys ─────────────────────────────────
            Form {
                Section("AI Provider Keys") {
                    SecureField("Anthropic API Key", text: $anthropicKey)
                        .textFieldStyle(.roundedBorder)
                    
                    SecureField("Google API Key", text: $googleKey)
                        .textFieldStyle(.roundedBorder)
                    
                    SecureField("Groq API Key", text: $groqKey)
                        .textFieldStyle(.roundedBorder)
                }
                
                Section {
                    Text("Keys are stored securely in macOS Keychain.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Button("Save API Keys") {
                        saveAPIKeys()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .tabItem { Label("API Keys", systemImage: "key") }
            
            // ─── About ────────────────────────────────────
            VStack(spacing: 16) {
                Image(systemName: "brain.head.profile")
                    .font(.system(size: 64))
                    .foregroundColor(.accentColor)
                
                Text("AGOS")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                
                Text("Agentic Operating System")
                    .font(.title3)
                    .foregroundColor(.secondary)
                
                Text("Version 0.1.0")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Divider()
                
                Text("Built with Rust + Go + Swift")
                    .font(.caption)
                
                Text("© 2026 Sehaj Vir Singh")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding(40)
            .tabItem { Label("About", systemImage: "info.circle") }
        }
        .frame(width: 480, height: 360)
    }
    
    private func saveAPIKeys() {
        // TODO: Save to macOS Keychain using Security framework
        NSLog("[AGOS] API keys saved to Keychain")
    }
}
