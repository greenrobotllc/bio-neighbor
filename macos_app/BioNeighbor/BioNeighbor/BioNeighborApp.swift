//
//  BioNeighborApp.swift
//  BioNeighbor
//
//  Main app entry point
//

import SwiftUI

extension Notification.Name {
    /// Posted when the user invokes Edit ▸ Find… (⌘F). Any view with a
    /// page-level search field listens and focuses it; views without one
    /// ignore the notification (no-op).
    static let cancerFindDrug = Notification.Name("BioNeighbor.cancerFindDrug")
}

/// App-wide text size scale. Persisted via @AppStorage and applied at the
/// WindowGroup root via `.dynamicTypeSize`, so it cascades to every view.
enum AppTextSize: Int, CaseIterable, Identifiable {
    case small = 0
    case medium = 1
    case `default` = 2
    case large = 3
    case extraLarge = 4
    case huge = 5

    var id: Int { rawValue }

    var displayName: String {
        switch self {
        case .small: return "Small"
        case .medium: return "Medium"
        case .default: return "Default"
        case .large: return "Large"
        case .extraLarge: return "Extra Large"
        case .huge: return "Huge"
        }
    }

    var dynamicType: DynamicTypeSize {
        switch self {
        case .small: return .small
        case .medium: return .medium
        case .default: return .large           // SwiftUI's "default"
        case .large: return .xLarge
        case .extraLarge: return .xxLarge
        case .huge: return .xxxLarge
        }
    }

    /// Multiplier applied to the named-text-style base point sizes. macOS
    /// SwiftUI does NOT honor app-level dynamicTypeSize for `.font(.body)`
    /// etc., so we drive scaling explicitly via the `.appFont(...)` modifier
    /// below.
    var scale: CGFloat {
        switch self {
        case .small: return 0.85
        case .medium: return 0.92
        case .default: return 1.0
        case .large: return 1.20
        case .extraLarge: return 1.45
        case .huge: return 1.75
        }
    }
}

// MARK: - .appFont(.body) — explicit, app-storage-driven font scaling
//
// macOS SwiftUI ignores `.dynamicTypeSize` for named text styles, so we
// emit `.font(.system(size: base * scale, weight:, design:))` ourselves.
// Use `.appFont(.body)` instead of `.font(.body)` anywhere we want the user's
// Settings text-size choice to take effect.

private extension Font.TextStyle {
    /// Apple's macOS body sizes per text style. Used as the base before
    /// applying our scale.
    var basePointSize: CGFloat {
        switch self {
        case .largeTitle: return 26
        case .title: return 22
        case .title2: return 17
        case .title3: return 15
        case .headline: return 13
        case .subheadline: return 11
        case .body: return 13
        case .callout: return 12
        case .footnote: return 10
        case .caption: return 10
        case .caption2: return 10
        @unknown default: return 13
        }
    }
}

struct AppFontModifier: ViewModifier {
    @AppStorage("appTextSize") private var sizeRaw: Int = AppTextSize.default.rawValue
    let style: Font.TextStyle
    let weight: Font.Weight?
    let monospaced: Bool

    private var pointSize: CGFloat {
        let scale = (AppTextSize(rawValue: sizeRaw) ?? .default).scale
        return style.basePointSize * scale
    }

    /// SwiftUI's named text styles imply a default weight (.headline is
    /// semibold, others are regular). Match that so callers don't need to
    /// pass `weight: .semibold` everywhere.
    private var resolvedWeight: Font.Weight {
        if let weight = weight { return weight }
        switch style {
        case .headline: return .semibold
        default: return .regular
        }
    }

    func body(content: Content) -> some View {
        content.font(
            .system(
                size: pointSize,
                weight: resolvedWeight,
                design: monospaced ? .monospaced : .default
            )
        )
    }
}

extension View {
    /// Replacement for `.font(.body)` that respects the app's Settings text size.
    func appFont(
        _ style: Font.TextStyle,
        weight: Font.Weight? = nil,
        monospaced: Bool = false
    ) -> some View {
        modifier(AppFontModifier(style: style, weight: weight, monospaced: monospaced))
    }
}

@main
struct BioNeighborApp: App {
    var body: some Scene {
        WindowGroup {
            // Wrap the tab view so @AppStorage("appTextSize") is read inside a
            // View — SwiftUI on macOS doesn't reliably propagate dynamicTypeSize
            // when @AppStorage is read at the App level.
            AppShell()
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(replacing: .windowSize) {}
            // ⌘F — focuses whatever page-level search field is visible on the
            // current tab. Drugs tab focuses its drug search; Cancer Research
            // tabs (subtype list, drugs list, drug detail) focus their
            // respective filters. Tabs without a search field ignore it.
            CommandGroup(after: .textEditing) {
                Button("Find on Page…") {
                    NotificationCenter.default.post(name: .cancerFindDrug, object: nil)
                }
                .keyboardShortcut("f", modifiers: .command)
            }
        }

        // Standard macOS Settings window — accessed via ⌘, or App Menu ▸ Settings.
        Settings {
            SettingsView()
        }
    }
}

/// Wraps ContentTabView so the dynamic-type read happens inside a View
/// (where @AppStorage triggers SwiftUI re-render) rather than at the App
/// level (where it doesn't always propagate on macOS).
struct AppShell: View {
    @AppStorage("appTextSize") private var textSizeRaw: Int = AppTextSize.default.rawValue

    private var textSize: AppTextSize {
        AppTextSize(rawValue: textSizeRaw) ?? .default
    }

    var body: some View {
        ContentTabView()
            // Apply via both the typed modifier and the explicit environment
            // value as belt-and-suspenders — SwiftUI on macOS has been
            // inconsistent about which path actually re-applies on change.
            .dynamicTypeSize(textSize.dynamicType)
            .environment(\.dynamicTypeSize, textSize.dynamicType)
            .textSelection(.enabled)
    }
}

/// Minimal settings window. Currently houses just the text size picker; new
/// app-level preferences land here as the app grows.
struct SettingsView: View {
    @AppStorage("appTextSize") private var textSizeRaw: Int = AppTextSize.default.rawValue

    @AppStorage("ollamaEnabled") private var ollamaEnabled: Bool = false
    @AppStorage("ollamaEndpoint") private var ollamaEndpoint: String = OllamaService.defaultEndpoint
    @AppStorage("ollamaModel") private var ollamaModel: String = OllamaService.defaultModel

    @State private var ollamaTestState: OllamaTestState = .idle
    private enum OllamaTestState: Equatable {
        case idle
        case testing
        case ok(Int)
        case failed(String)
    }

    var body: some View {
        Form {
            Section("Appearance") {
                Picker("Text size", selection: $textSizeRaw) {
                    ForEach(AppTextSize.allCases) { size in
                        Text(size.displayName).tag(size.rawValue)
                    }
                }
                .pickerStyle(.menu)
                Text("Affects all text in the app. Changes take effect immediately.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Section("AI Assistant (Ollama)") {
                Toggle("Enable on-device AI summaries", isOn: $ollamaEnabled)
                TextField("Endpoint", text: $ollamaEndpoint, prompt: Text(OllamaService.defaultEndpoint))
                    .textFieldStyle(.roundedBorder)
                TextField("Model", text: $ollamaModel, prompt: Text(OllamaService.defaultModel))
                    .textFieldStyle(.roundedBorder)
                HStack {
                    Button("Test connection") {
                        Task { await runOllamaTest() }
                    }
                    .disabled(ollamaTestState == .testing)
                    switch ollamaTestState {
                    case .idle:
                        EmptyView()
                    case .testing:
                        ProgressView().controlSize(.small)
                    case .ok(let count):
                        Label("OK — \(count) model\(count == 1 ? "" : "s") available", systemImage: "checkmark.circle.fill")
                            .foregroundColor(.green)
                            .font(.caption)
                    case .failed(let msg):
                        Label(msg, systemImage: "xmark.circle.fill")
                            .foregroundColor(.red)
                            .font(.caption)
                            .lineLimit(2)
                    }
                }
                Text("Requires Ollama 0.20+ (ollama.com) running locally. Pull a model first: `ollama pull gemma4:26b` (≈18 GB) or `ollama pull gemma4` (≈9.6 GB E4B for lower-RAM machines).")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(20)
        .frame(width: 480)
    }

    @MainActor
    private func runOllamaTest() async {
        ollamaTestState = .testing
        do {
            let models = try await OllamaService.shared.listModels()
            ollamaTestState = .ok(models.count)
        } catch {
            ollamaTestState = .failed(error.localizedDescription)
        }
    }
}

struct ContentTabView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            BrowseView()
                .tabItem {
                    Label("Molecules", systemImage: "square.grid.2x2")
                }
                .tag(0)
                .accessibilityIdentifier("moleculesTab")
            
            DiseaseBrowseView()
                .tabItem {
                    Label("Diseases", systemImage: "cross.case")
                }
                .tag(1)
                .accessibilityIdentifier("diseasesTab")
            
            DrugsView()
                .tabItem {
                    Label("Drugs", systemImage: "pills")
                }
                .tag(2)
                .accessibilityIdentifier("drugsTab")
            
            DrugDataDownloadView()
                .tabItem {
                    Label("Download Data", systemImage: "arrow.down.circle")
                }
                .tag(3)
                .accessibilityIdentifier("downloadDataTab")
            
            SearchView()
                .tabItem {
                    Label("Advanced Search", systemImage: "magnifyingglass")
                }
                .tag(4)
                .accessibilityIdentifier("advancedSearchTab")
            
            CancerResearchView()
                .tabItem {
                    Label("Cancer Research", systemImage: "flask")
                }
                .tag(5)
                .accessibilityIdentifier("cancerResearchTab")

            TreatmentAuditorView()
                .tabItem {
                    Label("Treatment Auditor", systemImage: "checklist")
                }
                .tag(6)
                .accessibilityIdentifier("treatmentAuditorTab")
        }
    }
}

