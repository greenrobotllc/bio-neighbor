//
//  SimilarityAnalysisView.swift
//  BioNeighbor
//
//  Section 6: Similarity & Neighbor Analysis
//

import SwiftUI

struct SimilarityAnalysisView: View {
    let mechanism: Mechanism
    let selectedLigandId: Int?
    @State private var availableLigands: [Ligand] = []
    @State private var selectedLigand: Ligand?
    @State private var similarLigands: [Ligand] = []
    @State private var isLoadingLigands = false
    @State private var isLoadingSimilar = false
    @State private var errorMessage: String?
    private let topK: Int = 10
    
    init(mechanism: Mechanism, selectedLigandId: Int? = nil) {
        self.mechanism = mechanism
        self.selectedLigandId = selectedLigandId
    }
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Similarity Analysis")
                        .font(.title2)
                        .bold()
                    
                    Text("Find similar ligands across mechanisms based on structural similarity")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
                
                Divider()
                
                // Ligand Selector
                VStack(alignment: .leading, spacing: 12) {
                    Text("Select a Ligand")
                        .font(.headline)
                    
                    if isLoadingLigands {
                        ProgressView("Loading ligands...")
                            .frame(maxWidth: .infinity)
                    } else if availableLigands.isEmpty {
                        Text("No ligands available for this mechanism")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Picker("Ligand", selection: $selectedLigand) {
                            Text("Select a ligand...")
                                .tag(nil as Ligand?)
                            ForEach(availableLigands) { ligand in
                                Text(ligand.name ?? "Unknown (\(ligand.id))")
                                    .tag(ligand as Ligand?)
                            }
                        }
                        .pickerStyle(.menu)
                        .frame(maxWidth: 400)
                        
                        if let selected = selectedLigand {
                            HStack {
                                Text("Selected: \(selected.name ?? "Unknown")")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                
                                Spacer()
                                
                                Button("Find Similar") {
                                    findSimilarLigands()
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(isLoadingSimilar)
                            }
                            .padding(.top, 8)
                        }
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
                .padding(.horizontal)
                
                // Results
                if isLoadingSimilar {
                    VStack(spacing: 12) {
                        ProgressView("Finding similar ligands...")
                        Text("This may take a few moments")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 200)
                    .padding()
                } else if let error = errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 32))
                            .foregroundColor(.orange)
                        Text("Error")
                            .font(.headline)
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity, minHeight: 200)
                    .padding()
                } else if !similarLigands.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Similar Ligands")
                                .font(.headline)
                            
                            Spacer()
                            
                            Text("\(similarLigands.count) results")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal)
                        
                        ForEach(similarLigands) { ligand in
                            NavigationLink(destination: LigandDetailView(ligand: ligand)) {
                                VStack(alignment: .leading, spacing: 8) {
                                    HStack {
                                        Text(ligand.name ?? "Unknown")
                                            .font(.headline)
                                        
                                        Spacer()
                                        
                                        if let similarity = ligand.similarity ?? ligand.similarityScore {
                                            HStack(spacing: 4) {
                                                ProgressView(value: similarity, total: 1.0)
                                                    .frame(width: 100)
                                                Text(String(format: "%.3f", similarity))
                                                    .font(.caption)
                                                    .fontDesign(.monospaced)
                                                    .foregroundColor(.secondary)
                                                    .frame(width: 50, alignment: .trailing)
                                            }
                                        }
                                    }
                                    
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
                                .padding()
                                .background(Color(NSColor.controlBackgroundColor))
                                .cornerRadius(8)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.horizontal)
                    }
                } else if selectedLigand != nil {
                    VStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 32))
                            .foregroundColor(.secondary)
                        Text("Click 'Find Similar' to search for similar ligands")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 200)
                    .padding()
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "molecule")
                            .font(.system(size: 32))
                            .foregroundColor(.secondary)
                        Text("Select a ligand above to find similar compounds")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 200)
                    .padding()
                }
            }
        }
        .onAppear {
            loadAvailableLigands()
        }
    }
    
    private func loadAvailableLigands() {
        isLoadingLigands = true
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/ligands") else {
            isLoadingLigands = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoadingLigands = false

                if let error = error {
                    errorMessage = "Failed to load ligands: \(error.localizedDescription)"
                    return
                }

                guard let data = data else {
                    errorMessage = "No data received"
                    return
                }

                do {
                    let response = try JSONDecoder().decode(LigandsResponse.self, from: data)
                    if response.success, let ligands = response.ligands {
                        self.availableLigands = ligands

                        // Auto-select if selectedLigandId was provided
                        if let selectedId = selectedLigandId,
                           let ligand = ligands.first(where: { $0.id == selectedId }) {
                            selectedLigand = ligand
                        }
                    } else {
                        errorMessage = response.error ?? "Failed to load ligands"
                    }
                } catch {
                    errorMessage = "Failed to decode ligands: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private func findSimilarLigands() {
        guard let selected = selectedLigand else { return }
        
        isLoadingSimilar = true
        errorMessage = nil
        similarLigands = []
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/similarity/ligands") else {
            errorMessage = "Invalid URL"
            isLoadingSimilar = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "ligand_id": selected.id,
            "top_k": topK
        ]
        
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                isLoadingSimilar = false
                
                if let error = error {
                    errorMessage = error.localizedDescription
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response"
                    return
                }
                
                guard httpResponse.statusCode == 200 else {
                    errorMessage = "Server error: HTTP \(httpResponse.statusCode)"
                    return
                }
                
                guard let data = data else {
                    errorMessage = "No data received"
                    return
                }
                
                do {
                    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                    
                    if let success = json?["success"] as? Bool, success,
                       let similar = json?["similar_ligands"] as? [[String: Any]] {
                        // Parse similar ligands
                        var ligands: [Ligand] = []
                        for item in similar {
                            if let jsonData = try? JSONSerialization.data(withJSONObject: item),
                               let ligand = try? JSONDecoder().decode(Ligand.self, from: jsonData) {
                                ligands.append(ligand)
                            }
                        }
                        self.similarLigands = ligands
                    } else {
                        errorMessage = json?["error"] as? String ?? "Failed to find similar ligands"
                    }
                } catch {
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
}
