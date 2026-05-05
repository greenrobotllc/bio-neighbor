//
//  BioNeighborApp.swift
//  BioNeighbor
//
//  Main app entry point
//

import SwiftUI

extension Notification.Name {
    /// Posted when the user invokes Edit ▸ Find Drug… (⌘F). Cancer Research
    /// views observe this and focus their drug-filter field. Other tabs ignore.
    static let cancerFindDrug = Notification.Name("BioNeighbor.cancerFindDrug")
}

@main
struct BioNeighborApp: App {
    var body: some Scene {
        WindowGroup {
            ContentTabView()
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(replacing: .windowSize) {}
            // Add a Find Drug command alongside Edit ▸ Find so ⌘F focuses the
            // drug filter on the Cancer Research tab. On other tabs the
            // keystroke is a no-op (no observer of `.cancerFindDrug`).
            CommandGroup(after: .textEditing) {
                Button("Find Drug…") {
                    NotificationCenter.default.post(name: .cancerFindDrug, object: nil)
                }
                .keyboardShortcut("f", modifiers: .command)
            }
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
        }
    }
}

