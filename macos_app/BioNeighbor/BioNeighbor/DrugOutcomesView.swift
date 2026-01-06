//
//  DrugOutcomesView.swift
//  BioNeighbor
//
//  Section 4: Drug Outcomes & Context
//

import SwiftUI

struct DrugOutcomesView: View {
    let mechanism: Mechanism
    @State private var outcomes: [DrugOutcome] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        VStack {
            if isLoading {
                ProgressView("Loading drug outcomes...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                Text("Error: \(error)")
                    .foregroundColor(.red)
            } else {
                List(outcomes) { outcome in
                    DrugOutcomeRow(outcome: outcome)
                }
            }
        }
        .onAppear {
            loadOutcomes()
        }
    }
    
    private func loadOutcomes() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/drug-outcomes") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    errorMessage = error.localizedDescription
                    return
                }
                
                guard let data = data,
                      let response = try? JSONDecoder().decode(DrugOutcomesResponse.self, from: data),
                      response.success,
                      let outcomes = response.outcomes else {
                    errorMessage = "Failed to decode response"
                    return
                }
                
                self.outcomes = outcomes
            }
        }.resume()
    }
}

struct DrugOutcomeRow: View {
    let outcome: DrugOutcome
    
    var outcomeColor: Color {
        switch outcome.outcomeType {
        case "partial_success": return .yellow
        case "failure": return .red
        case "mixed": return .orange
        default: return .gray
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(outcomeColor)
                    .frame(width: 12, height: 12)
                Text(outcome.outcomeType.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.headline)
            }
            
            if let context = outcome.context {
                Text(context)
                    .font(.body)
            }
            
            if let evidence = outcome.evidenceLevel {
                Text("Evidence: \(evidence)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if let notes = outcome.notes {
                Text(notes)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
        .padding(.vertical, 4)
    }
}
