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
            SearchView()
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 1000, height: 700)
    }
}

