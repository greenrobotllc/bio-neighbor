//
//  AssaysView.swift
//  BioNeighbor
//
//  Section 5: Assays & Evidence
//

import SwiftUI

struct AssaysView: View {
    let mechanism: Mechanism
    @State private var assays: [Assay] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        VStack {
            if isLoading {
                ProgressView("Loading assays...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                Text("Error: \(error)")
                    .foregroundColor(.red)
            } else {
                List(assays) { assay in
                    AssayRow(assay: assay)
                }
            }
        }
        .onAppear {
            loadAssays()
        }
    }
    
    private func loadAssays() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/assays") else {
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
                      let response = try? JSONDecoder().decode(AssaysResponse.self, from: data),
                      response.success,
                      let assays = response.assays else {
                    errorMessage = "Failed to decode response"
                    return
                }
                
                self.assays = assays
            }
        }.resume()
    }
}

struct AssayRow: View {
    let assay: Assay
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(assay.assayType ?? "Unknown Assay")
                    .font(.headline)
                Spacer()
                if let source = assay.dataSource {
                    Text(source)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            if let readout = assay.readout {
                Text("Readout: \(readout)")
                    .font(.body)
            }
            
            if let limitations = assay.limitations {
                Text("Limitations: \(limitations)")
                    .font(.caption)
                    .foregroundColor(.orange)
            }
        }
        .padding(.vertical, 4)
    }
}
