//
//  DrugOutcomeDetailView.swift
//  BioNeighbor
//
//  Detailed view for a drug outcome
//

import SwiftUI

struct DrugOutcomeDetailView: View {
    let outcome: DrugOutcome
    @Environment(\.dismiss) private var dismiss
    
    var outcomeColor: Color {
        switch outcome.outcomeType {
        case "success": return .green
        case "partial_success": return .yellow
        case "failure": return .red
        case "mixed": return .orange
        default: return .gray
        }
    }
    
    var outcomeLabel: String {
        outcome.outcomeType.replacingOccurrences(of: "_", with: " ").capitalized
    }
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        HStack(spacing: 12) {
                            Circle()
                                .fill(outcomeColor)
                                .frame(width: 16, height: 16)
                            Text(outcomeLabel)
                                .font(.largeTitle)
                                .fontWeight(.bold)
                        }
                        
                        Spacer()
                        
                        Button("Done") {
                            dismiss()
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding()
                
                Divider()
                
                // Context
                if let context = outcome.context {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Context")
                            .font(.headline)
                        Text(context)
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                }
                
                // Evidence Level
                if let evidenceLevel = outcome.evidenceLevel {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Evidence Level")
                            .font(.headline)
                        Text(evidenceLevel)
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))
                    .cornerRadius(8)
                    .padding(.horizontal)
                }
                
                // Notes
                if let notes = outcome.notes {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Notes")
                            .font(.headline)
                        Text(notes)
                            .font(.body)
                            .foregroundColor(.secondary)
                            .italic()
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
        .navigationTitle("Drug Outcome Details")
        .frame(minWidth: 600, minHeight: 500)
    }
}
