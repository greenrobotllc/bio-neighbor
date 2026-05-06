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
        }
        .padding(20)
        .frame(width: 420)
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
        }
    }
}

