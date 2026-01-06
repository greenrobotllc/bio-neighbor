//
//  MechanismOverviewView.swift
//  BioNeighbor
//
//  Section 1: Mechanism Overview
//

import SwiftUI

struct MechanismOverviewView: View {
    let mechanism: Mechanism
    @State private var isLoading = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Mechanism name and description
                VStack(alignment: .leading, spacing: 12) {
                    Text(mechanism.name)
                        .font(.largeTitle)
                        .bold()
                    
                    if let description = mechanism.description {
                        Text(description)
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                }
                .padding()
                
                Divider()
                
                // Biological summary
                if let summary = mechanism.biologicalSummary {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Biological Summary")
                            .font(.headline)
                        Text(summary)
                            .font(.body)
                    }
                    .padding()
                }
                
                // Tumor microenvironment role
                if let role = mechanism.tumorMicroenvironmentRole {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Role in Tumor Microenvironment")
                            .font(.headline)
                        Text(role)
                            .font(.body)
                    }
                    .padding()
                }
                
                // Immune effects
                if let effects = mechanism.immuneEffects {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Immune Effects")
                            .font(.headline)
                        Text(effects)
                            .font(.body)
                    }
                    .padding()
                }
                
                // Data sources
                if let sources = mechanism.dataSources, !sources.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Data Sources")
                            .font(.headline)
                        ForEach(sources, id: \.self) { source in
                            Text("• \(source)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding()
                }
                
                // Disclaimer
                HStack {
                    Image(systemName: "info.circle")
                    Text("This information is for research purposes only and does not constitute medical advice.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color.blue.opacity(0.1))
                .cornerRadius(8)
                .padding()
            }
        }
    }
}
