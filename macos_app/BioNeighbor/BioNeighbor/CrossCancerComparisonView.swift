//
//  CrossCancerComparisonView.swift
//  BioNeighbor
//
//  Section 7: Cross-Cancer Comparison
//

import SwiftUI

struct CrossCancerComparisonView: View {
    let mechanism: Mechanism
    @State private var cancerMappings: [CancerMechanismMapping] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Cross-Cancer Comparison")
                .font(.title2)
                .bold()
                .padding()
            
            Text("Cancer types with activity for this mechanism")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.horizontal)
            
            if isLoading {
                ProgressView("Loading cancer mappings...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                Text("Error: \(error)")
                    .foregroundColor(.red)
            } else {
                List(cancerMappings) { mapping in
                    CancerMappingRow(mapping: mapping)
                }
            }
        }
        .onAppear {
            loadCancerMappings()
        }
    }
    
    private func loadCancerMappings() {
        isLoading = true
        errorMessage = nil
        
        // Get all cancers and filter for this mechanism
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/cancers") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                // For now, show placeholder - full implementation would query mechanism-specific mappings
                isLoading = false
            }
        }.resume()
    }
}

struct CancerMappingRow: View {
    let mapping: CancerMechanismMapping
    
    var activityColor: Color {
        switch mapping.activityLevel {
        case "High": return .red
        case "Moderate": return .orange
        case "Low": return .yellow
        default: return .gray
        }
    }
    
    var body: some View {
        HStack {
            Text(mapping.cancerType)
                .font(.headline)
            Spacer()
            if let level = mapping.activityLevel {
                HStack {
                    Circle()
                        .fill(activityColor)
                        .frame(width: 12, height: 12)
                    Text(level)
                        .font(.caption)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
