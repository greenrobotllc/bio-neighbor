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
                    Label("Browse", systemImage: "square.grid.2x2")
                }
                .tag(0)
            
            SearchView()
                .tabItem {
                    Label("Advanced Search", systemImage: "magnifyingglass")
                }
                .tag(1)
        }
    }
}

