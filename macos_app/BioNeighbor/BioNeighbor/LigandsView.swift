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
    @State private var filteredLigands: [Ligand] = []
    @State private var searchText: String = ""
    @State private var selectedInteractionType: String? = nil
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var interactionTypes: [String] {
        Array(Set(ligands.compactMap { $0.interactionType })).sorted()
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search and filter bar
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search by name, SMILES, or target", text: $searchText)
                        .textFieldStyle(.plain)
                        .onChange(of: searchText) { _ in
                            filterLigands()
                        }
                    
                    if !searchText.isEmpty {
                        Button(action: {
                            searchText = ""
                            filterLigands()
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                
                if !interactionTypes.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            Button(action: {
                                selectedInteractionType = nil
                                filterLigands()
                            }) {
                                Text("All")
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(selectedInteractionType == nil ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                    .foregroundColor(selectedInteractionType == nil ? .white : .primary)
                                    .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            
                            ForEach(interactionTypes, id: \.self) { type in
                                Button(action: {
                                    selectedInteractionType = type
                                    filterLigands()
                                }) {
                                    Text(type.capitalized)
                                        .font(.caption)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(selectedInteractionType == type ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                        .foregroundColor(selectedInteractionType == type ? .white : .primary)
                                        .cornerRadius(4)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            
            Divider()
            
            // Content
            if isLoading {
                ProgressView("Loading ligands...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading ligands")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        loadLigands()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if filteredLigands.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "molecule")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text(searchText.isEmpty ? "No ligands found" : "No ligands match your search")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    if !searchText.isEmpty {
                        Text("Try a different search term")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                List(filteredLigands) { ligand in
                    NavigationLink(destination: LigandDetailView(ligand: ligand)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)) {
                        LigandRow(ligand: ligand)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .onAppear {
            loadLigands()
        }
    }
    
    private func filterLigands() {
        var filtered = ligands
        
        // Filter by search text
        if !searchText.isEmpty {
            let searchLower = searchText.lowercased()
            filtered = filtered.filter { ligand in
                ligand.name?.lowercased().contains(searchLower) ?? false ||
                ligand.smiles?.lowercased().contains(searchLower) ?? false ||
                ligand.geneSymbol?.lowercased().contains(searchLower) ?? false ||
                ligand.proteinName?.lowercased().contains(searchLower) ?? false
            }
        }
        
        // Filter by interaction type
        if let selectedType = selectedInteractionType {
            filtered = filtered.filter { $0.interactionType == selectedType }
        }
        
        filteredLigands = filtered
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
                    print("❌ Error loading ligands: \(error.localizedDescription)")
                    errorMessage = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    print("❌ Invalid response type")
                    errorMessage = "Invalid response from server"
                    return
                }
                
                guard httpResponse.statusCode == 200 else {
                    print("❌ HTTP error: \(httpResponse.statusCode)")
                    errorMessage = "Server error: HTTP \(httpResponse.statusCode)"
                    return
                }
                
                guard let data = data else {
                    print("❌ No data received")
                    errorMessage = "No data received from server"
                    return
                }
                
                do {
                    let response = try JSONDecoder().decode(LigandsResponse.self, from: data)
                    if response.success {
                        let ligands = response.ligands ?? []
                        let count = response.count ?? ligands.count
                        print("✅ Loaded \(count) ligands for mechanism \(mechanism.id)")
                        
                        if ligands.isEmpty {
                            print("⚠️  Warning: API returned success but no ligands")
                        }
                        
                        self.ligands = ligands
                        self.filteredLigands = ligands
                    } else {
                        let errorMsg = response.error ?? "Unknown error"
                        print("❌ API returned error: \(errorMsg)")
                        errorMessage = errorMsg
                    }
                } catch {
                    print("❌ Failed to decode response: \(error)")
                    // Try to log raw response for debugging
                    if let jsonString = String(data: data, encoding: .utf8) {
                        print("Raw response: \(jsonString.prefix(500))")
                    }
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
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
