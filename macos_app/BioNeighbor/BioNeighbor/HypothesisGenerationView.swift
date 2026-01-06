//
//  HypothesisGenerationView.swift
//  BioNeighbor
//
//  Section 8: Hypothesis Generation
//

import SwiftUI

struct HypothesisGenerationView: View {
    let mechanism: Mechanism
    @State private var hypotheses: [Hypothesis] = []
    @State private var isLoading = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Hypothesis Generation")
                .font(.title2)
                .bold()
                .padding()
            
            Text("Research hypotheses based on neighbor analysis")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.horizontal)
            
            // Disclaimer
            HStack {
                Image(systemName: "exclamationmark.triangle")
                Text("These are research hypotheses only - not medical advice or treatment recommendations")
                    .font(.caption)
                    .foregroundColor(.orange)
            }
            .padding()
            .background(Color.orange.opacity(0.1))
            .cornerRadius(8)
            .padding(.horizontal)
            
            if isLoading {
                ProgressView("Generating hypotheses...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if hypotheses.isEmpty {
                Text("No hypotheses generated yet")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(hypotheses) { hypothesis in
                    HypothesisRow(hypothesis: hypothesis)
                }
            }
        }
        .onAppear {
            generateHypotheses()
        }
    }
    
    private func generateHypotheses() {
        // Placeholder - would call API to generate hypotheses
        isLoading = false
        hypotheses = []
    }
}

struct HypothesisRow: View {
    let hypothesis: Hypothesis
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(hypothesis.label)
                .font(.headline)
            
            Text(hypothesis.description)
                .font(.body)
            
            if !hypothesis.supportingNeighbors.isEmpty {
                Text("Supporting neighbors: \(hypothesis.supportingNeighbors.joined(separator: ", "))")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if let confidence = hypothesis.confidence {
                HStack {
                    Text("Confidence:")
                    ProgressView(value: confidence)
                        .frame(width: 100)
                    Text(String(format: "%.0f%%", confidence * 100))
                        .font(.caption)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
