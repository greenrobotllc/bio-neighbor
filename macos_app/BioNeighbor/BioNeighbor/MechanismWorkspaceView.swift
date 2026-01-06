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
            .frame(minWidth: 200)
        } detail: {
            // Main content area
            VStack(spacing: 0) {
                // Breadcrumb navigation
                CancerBreadcrumbView(items: breadcrumbItems)
                
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
            }
        }
        .onAppear {
            workspaceState.loadWorkspace(for: mechanism.id)
        }
        .onChange(of: selectedSection) { _ in
            workspaceState.saveSection(selectedSection.rawValue, for: mechanism.id)
        }
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
