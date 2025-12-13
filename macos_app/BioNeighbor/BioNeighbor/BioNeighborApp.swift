//
//  BioNeighborApp.swift
//  BioNeighbor
//
//  Main app entry point
//

import SwiftUI

@main
struct BioNeighborApp: App {
    var body: some Scene {
        WindowGroup {
            ContentTabView()
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 1200, height: 800)
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
            
            DiseaseBrowseView()
                .tabItem {
                    Label("Diseases", systemImage: "cross.case")
                }
                .tag(1)
            
            DrugsView()
                .tabItem {
                    Label("Drugs", systemImage: "pills")
                }
                .tag(2)
            
            DrugDataDownloadView()
                .tabItem {
                    Label("Download Data", systemImage: "arrow.down.circle")
                }
                .tag(3)
            
            SearchView()
                .tabItem {
                    Label("Advanced Search", systemImage: "magnifyingglass")
                }
                .tag(4)
        }
    }
}

