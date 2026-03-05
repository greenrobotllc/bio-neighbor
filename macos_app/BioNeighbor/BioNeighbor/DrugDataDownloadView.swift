//
//  DrugDataDownloadView.swift
//  BioNeighbor
//
//  Enhanced data download interface with sidebar navigation
//

import SwiftUI

enum DownloadSection: String, CaseIterable {
    case overview = "Overview"
    case molecules = "Molecules"
    case drugs = "Drugs"
    case diseases = "Diseases"
    case cancerResearch = "Cancer Research"
    case history = "History"
    
    var icon: String {
        switch self {
        case .overview: return "chart.bar"
        case .molecules: return "molecule"
        case .drugs: return "pills"
        case .diseases: return "cross.case"
        case .cancerResearch: return "flask"
        case .history: return "clock"
        }
    }
}

struct EnhancedDownloadResult: Identifiable {
    let id = UUID()
    let timestamp: Date
    let type: String  // "molecules", "drugs", "diseases"
    let success: Bool
    let message: String
    let quantity: Int?
    let source: String?
    let details: String?
}

struct DrugDataDownloadView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var selectedSection: DownloadSection = .overview
    @State private var downloadHistory: [EnhancedDownloadResult] = []
    
    var body: some View {
        NavigationSplitView {
            // Sidebar
            List(DownloadSection.allCases, id: \.self, selection: $selectedSection) { section in
                Label(section.rawValue, systemImage: section.icon)
                    .tag(section)
                    .accessibilityIdentifier("downloadSection_\(section.rawValue)")
            }
            .navigationTitle("Download Data")
            .frame(minWidth: 200)
            .accessibilityIdentifier("downloadDataSidebar")
        } detail: {
            // Main content
            Group {
                switch selectedSection {
                case .overview:
                    DownloadStatisticsView()
                case .molecules:
                    MoleculesDownloadViewRx()
                case .drugs:
                    DrugsDownloadViewRx()
                case .diseases:
                    DiseasesDownloadViewRx()
                case .cancerResearch:
                    CancerResearchDownloadView()
                case .history:
                    DownloadHistoryView(history: $downloadHistory)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .onAppear {
            loadHistory()
        }
    }
    
    private func loadHistory() {
        // Load history from UserDefaults or file
        // For now, initialize empty
    }
}

struct DownloadHistoryView: View {
    @Binding var history: [EnhancedDownloadResult]
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Download History")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 8)
                
                if history.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "clock")
                            .font(.system(size: 60))
                            .foregroundColor(.secondary)
                        Text("No downloads yet")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        Text("Start a download to see history here")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                } else {
                    ForEach(history.reversed()) { result in
                        DownloadHistoryCard(result: result)
                    }
                }
            }
            .padding()
        }
    }
}

struct DownloadHistoryCard: View {
    let result: EnhancedDownloadResult
    @State private var isExpanded = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: result.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundColor(result.success ? .green : .red)
                
                VStack(alignment: .leading, spacing: 4) {
                    Text(result.message)
                        .font(.headline)
                    
                    HStack {
                        Label(result.type.capitalized, systemImage: typeIcon(result.type))
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        if let quantity = result.quantity {
                            Text("• \(quantity) items")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        if let source = result.source {
                            Text("• \(source)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    Text(result.timestamp, style: .time)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                if result.details != nil {
                    Button(action: {
                        isExpanded.toggle()
                    }) {
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            
            if isExpanded, let details = result.details {
                Text(details)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))
                    .cornerRadius(8)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.1), radius: 2, x: 0, y: 1)
    }
    
    private func typeIcon(_ type: String) -> String {
        switch type {
        case "molecules": return "molecule"
        case "drugs": return "pills"
        case "diseases": return "cross.case"
        default: return "doc"
        }
    }
}

#Preview {
    DrugDataDownloadView()
}
