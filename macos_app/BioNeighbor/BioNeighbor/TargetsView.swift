//
//  TargetsView.swift
//  BioNeighbor
//
//  Section 2: Targets Involved
//

import SwiftUI

struct TargetsView: View {
    let mechanism: Mechanism
    @State private var targets: [Target] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        VStack {
            if isLoading {
                ProgressView("Loading targets...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                Text("Error: \(error)")
                    .foregroundColor(.red)
            } else {
                List(targets) { target in
                    TargetRow(target: target)
                }
            }
        }
        .onAppear {
            loadTargets()
        }
    }
    
    private func loadTargets() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/targets") else {
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
                      let response = try? JSONDecoder().decode(TargetsResponse.self, from: data),
                      response.success,
                      let targets = response.targets else {
                    errorMessage = "Failed to decode response"
                    return
                }
                
                self.targets = targets
            }
        }.resume()
    }
}

struct TargetRow: View {
    let target: Target
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(target.geneSymbol ?? target.proteinName ?? "Unknown")
                    .font(.headline)
                Spacer()
                if let uniprotId = target.uniprotId {
                    Text(uniprotId)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            if let proteinName = target.proteinName {
                Text(proteinName)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            
            if let function = target.function {
                Text(function)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(3)
            }
            
            if let role = target.roleInMechanism {
                Text("Role: \(role)")
                    .font(.caption)
                    .foregroundColor(.blue)
            }
        }
        .padding(.vertical, 4)
    }
}
