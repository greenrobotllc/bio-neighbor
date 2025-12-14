//
//  DownloadStatisticsView.swift
//  BioNeighbor
//
//  Statistics display component for download interface
//

import SwiftUI

struct DownloadStatisticsView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var stats: DatabaseStats?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var lastUpdated: Date?
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                HStack {
                    Text("Database Statistics")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    
                    Spacer()
                    
                    Button(action: refreshStats) {
                        HStack {
                            if isLoading {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.clockwise")
                            }
                            Text("Refresh")
                        }
                    }
                    .buttonStyle(.bordered)
                    .disabled(isLoading || !backendService.isBackendRunning)
                }
                
                if !backendService.isBackendRunning {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("⚠️ Backend not running")
                            .font(.headline)
                            .foregroundColor(.orange)
                        
                        Text("The Python backend needs to be started to view statistics.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Button("Start Backend") {
                            do {
                                try backendService.startBackend()
                            } catch {
                                errorMessage = error.localizedDescription
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                } else if isLoading {
                    ProgressView("Loading statistics...")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                } else if let stats = stats {
                    // Statistics cards
                    LazyVGrid(columns: [
                        GridItem(.flexible(), spacing: 16),
                        GridItem(.flexible(), spacing: 16)
                    ], spacing: 16) {
                        StatCard(
                            title: "Molecules",
                            count: stats.molecules,
                            icon: "molecule",
                            color: .blue
                        )
                        
                        StatCard(
                            title: "Drugs",
                            count: stats.drugs,
                            icon: "pills",
                            color: .green
                        )
                        
                        StatCard(
                            title: "Diseases",
                            count: stats.diseases,
                            icon: "cross.case",
                            color: .orange
                        )
                        
                        StatCard(
                            title: "Relationships",
                            count: stats.relationships,
                            icon: "link",
                            color: .purple
                        )
                    }
                    
                    if let lastUpdated = lastUpdated {
                        Text("Last updated: \(lastUpdated, style: .time)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.top, 8)
                    }
                } else if let error = errorMessage {
                    Text("Error: \(error)")
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                } else {
                    Text("No statistics available")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding()
                }
            }
            .padding()
        }
        .onAppear {
            if stats == nil {
                refreshStats()
            }
        }
    }
    
    private func refreshStats() {
        guard backendService.isBackendRunning else { return }
        
        isLoading = true
        errorMessage = nil
        
        Task {
            do {
                let loadedStats = try await backendService.getDatabaseStats()
                await MainActor.run {
                    stats = loadedStats
                    lastUpdated = Date()
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

struct StatCard: View {
    let title: String
    let count: Int
    let icon: String
    let color: Color
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(color)
                
                Spacer()
            }
            
            Text(title)
                .font(.headline)
                .foregroundColor(.secondary)
            
            Text("\(count)")
                .font(.system(size: 36, weight: .bold))
                .foregroundColor(color)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.1), radius: 2, x: 0, y: 1)
    }
}

#Preview {
    DownloadStatisticsView()
}

