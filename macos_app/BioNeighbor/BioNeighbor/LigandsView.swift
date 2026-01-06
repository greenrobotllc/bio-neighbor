//
//  LigandsView.swift
//  BioNeighbor
//
//  Section 3: Ligands & Compounds
//

import SwiftUI

struct LigandsView: View {
    let mechanism: Mechanism
    @State private var ligands: [Ligand] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        VStack {
            if isLoading {
                ProgressView("Loading ligands...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                Text("Error: \(error)")
                    .foregroundColor(.red)
            } else {
                List(ligands) { ligand in
                    LigandRow(ligand: ligand)
                }
            }
        }
        .onAppear {
            loadLigands()
        }
    }
    
    private func loadLigands() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/ligands") else {
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
                      let response = try? JSONDecoder().decode(LigandsResponse.self, from: data),
                      response.success,
                      let ligands = response.ligands else {
                    errorMessage = "Failed to decode response"
                    return
                }
                
                self.ligands = ligands
            }
        }.resume()
    }
}

struct LigandRow: View {
    let ligand: Ligand
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(ligand.name ?? "Unknown")
                    .font(.headline)
                
                if let interactionType = ligand.interactionType {
                    Text(interactionType.capitalized)
                        .font(.caption)
                        .foregroundColor(.blue)
                }
                
                if let target = ligand.geneSymbol {
                    Text("Target: \(target)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            Spacer()
            
            if let similarity = ligand.similarity {
                Text(String(format: "%.2f", similarity))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
