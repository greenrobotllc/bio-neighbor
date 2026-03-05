//
//  MechanismWorkspaceView.swift
//  BioNeighbor
//
//  Main workspace container for mechanism research
//

import SwiftUI

enum WorkspaceSection: String, CaseIterable {
    case overview = "Overview"
    case targets = "Targets"
    case ligands = "Ligands"
    case outcomes = "Drug Outcomes"
    case assays = "Assays"
    case similarity = "Similarity Analysis"
    case crossCancer = "Cross-Cancer Comparison"
    case hypotheses = "Hypothesis Generation"
    
    var icon: String {
        switch self {
        case .overview: return "doc.text"
        case .targets: return "target"
        case .ligands: return "molecule"
        case .outcomes: return "chart.bar"
        case .assays: return "flask"
        case .similarity: return "network"
        case .crossCancer: return "cross.case"
        case .hypotheses: return "lightbulb"
        }
    }
}

struct MechanismWorkspaceView: View {
    let mechanism: Mechanism
    let onBackToSelector: (() -> Void)?
    @State private var selectedSection: WorkspaceSection = .overview
    @StateObject private var workspaceState = WorkspaceStateManager.shared
    @State private var isLoadingData = false
    @State private var dataLoadMessage: String?
    @State private var dataLoadError: String?
    
    init(mechanism: Mechanism, onBackToSelector: (() -> Void)? = nil) {
        self.mechanism = mechanism
        self.onBackToSelector = onBackToSelector
    }
    
    var body: some View {
        NavigationSplitView {
            // Section navigation sidebar
            List(WorkspaceSection.allCases, id: \.self, selection: $selectedSection) { section in
                Label(section.rawValue, systemImage: section.icon)
                    .tag(section)
            }
            .navigationTitle(mechanism.name)
            .frame(minWidth: 200, maxWidth: 250)
        } detail: {
            // Main content area
            VStack(spacing: 0) {
                // Breadcrumb navigation with Load Data button
                VStack(spacing: 0) {
                    HStack {
                        CancerBreadcrumbView(items: breadcrumbItems)
                        
                        Spacer()
                        
                        if isLoadingData {
                            HStack(spacing: 8) {
                                ProgressView()
                                    .scaleEffect(0.7)
                                Text("Loading data...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        } else {
                            Button(action: {
                                loadData()
                            }) {
                                Label("Load Data", systemImage: "arrow.down.circle")
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 4)
                }
                
                // Success/Error Messages
                if let message = dataLoadMessage {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                        Text(message)
                            .font(.caption)
                        Spacer()
                        Button("Dismiss") {
                            dataLoadMessage = nil
                        }
                        .buttonStyle(.plain)
                        .font(.caption)
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 6)
                    .background(Color.green.opacity(0.1))
                }
                
                if let error = dataLoadError {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text(error)
                            .font(.caption)
                        Spacer()
                        Button("Dismiss") {
                            dataLoadError = nil
                        }
                        .buttonStyle(.plain)
                        .font(.caption)
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 6)
                    .background(Color.orange.opacity(0.1))
                }
                
                // Research-only disclaimer banner
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.orange)
                    Text("Research Tool Only - Not for Medical Diagnosis or Treatment")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color.orange.opacity(0.1))
                
                // Section content
                Group {
                    switch selectedSection {
                    case .overview:
                        MechanismOverviewView(mechanism: mechanism)
                    case .targets:
                        TargetsView(mechanism: mechanism)
                    case .ligands:
                        LigandsView(mechanism: mechanism)
                    case .outcomes:
                        DrugOutcomesView(mechanism: mechanism)
                    case .assays:
                        AssaysView(mechanism: mechanism)
                    case .similarity:
                        SimilarityAnalysisView(mechanism: mechanism)
                    case .crossCancer:
                        CrossCancerComparisonView(mechanism: mechanism)
                    case .hypotheses:
                        HypothesisGenerationView(mechanism: mechanism)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipped()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            await workspaceState.loadWorkspace(for: mechanism.id)
        }
        .onChange(of: selectedSection) { _ in
            workspaceState.saveSection(selectedSection.rawValue, for: mechanism.id)
        }
    }
    
    private func loadData() {
        isLoadingData = true
        dataLoadMessage = nil
        dataLoadError = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/load-data") else {
            dataLoadError = "Invalid URL"
            isLoadingData = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Use force_refresh: true to ensure data is actually loaded
        let body: [String: Any] = ["force_refresh": true]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                isLoadingData = false
                
                if let error = error {
                    dataLoadError = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200,
                      let data = data else {
                    dataLoadError = "Failed to load data"
                    return
                }
                
                do {
                    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                    if let success = json?["success"] as? Bool, success {
                        let targets = json?["targets_loaded"] as? Int ?? 0
                        let ligands = json?["ligands_loaded"] as? Int ?? 0
                        let assays = json?["assays_loaded"] as? Int ?? 0
                        let outcomes = json?["outcomes_loaded"] as? Int ?? 0
                        let mappings = json?["cancer_mappings_loaded"] as? Int ?? 0
                        
                        // Check for warnings/errors
                        if let warnings = json?["warnings"] as? [String], !warnings.isEmpty {
                            let warningText = warnings.joined(separator: "; ")
                            var messageParts: [String] = []
                            if targets > 0 { messageParts.append("\(targets) targets") }
                            if ligands > 0 { messageParts.append("\(ligands) ligands") }
                            if assays > 0 { messageParts.append("\(assays) assays") }
                            if outcomes > 0 { messageParts.append("\(outcomes) outcomes") }
                            
                            if messageParts.isEmpty {
                                dataLoadError = "No data loaded. Warnings: \(warningText)"
                            } else {
                                dataLoadMessage = "Loaded: " + messageParts.joined(separator: ", ")
                                dataLoadError = "Warnings: \(warningText)"
                            }
                        } else {
                            var messageParts: [String] = []
                            if targets > 0 { messageParts.append("\(targets) targets") }
                            if ligands > 0 { messageParts.append("\(ligands) ligands") }
                            if assays > 0 { messageParts.append("\(assays) assays") }
                            if outcomes > 0 { messageParts.append("\(outcomes) outcomes") }
                            if mappings > 0 { messageParts.append("\(mappings) cancer mappings") }
                            
                            if messageParts.isEmpty {
                                dataLoadError = "No data loaded. Check server logs - ChEMBL/PubChem APIs may be unavailable."
                            } else {
                                dataLoadMessage = "Loaded: " + messageParts.joined(separator: ", ")
                            }
                        }
                        
                        // Auto-dismiss success message after 5 seconds
                        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                            dataLoadMessage = nil
                        }
                    } else {
                        dataLoadError = json?["error"] as? String ?? "Failed to load data"
                    }
                } catch {
                    dataLoadError = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private var breadcrumbItems: [CancerBreadcrumbItem] {
        [
            CancerBreadcrumbItem("Cancer Research", isClickable: true) {
                // Navigate back to mechanism selector
                onBackToSelector?()
            },
            CancerBreadcrumbItem(mechanism.name, isClickable: true) {
                // Switch to Overview section
                selectedSection = .overview
            },
            CancerBreadcrumbItem(selectedSection.rawValue, isClickable: false)
        ]
    }
}
