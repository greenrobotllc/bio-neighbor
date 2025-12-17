//
//  SearchView.swift
//  BioNeighbor
//
//  Main search interface
//

import SwiftUI

struct SearchView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var querySmiles = ""
    @State private var topK = 10
    @State private var isSearching = false
    @State private var searchResults: [Molecule] = []
    @State private var errorMessage: String?
    
    var body: some View {
        NavigationStack {
            NavigationSplitView {
            // Sidebar with search form
            VStack(alignment: .leading, spacing: 20) {
                Text("BioNeighbor")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 10)
                
                Text("Find similar molecules using molecular similarity search")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Divider()
                
                VStack(alignment: .leading, spacing: 12) {
                    Text("SMILES String")
                        .font(.headline)
                    
                    TextField("e.g., CC(=O)Oc1ccccc1C(=O)O", text: $querySmiles)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.body, design: .monospaced))
                    
                    Text("Enter a SMILES string to search for similar molecules")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                VStack(alignment: .leading, spacing: 12) {
                    Text("Number of Results")
                        .font(.headline)
                    
                    Stepper(value: $topK, in: 1...50) {
                        Text("\(topK) results")
                    }
                }
                
                Button(action: performSearch) {
                    HStack {
                        if isSearching {
                            ProgressView()
                                .progressViewStyle(.circular)
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "magnifyingglass")
                        }
                        Text(isSearching ? "Searching..." : "Search")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSearching || querySmiles.isEmpty || !backendService.isBackendRunning)
                
                if !backendService.isBackendRunning {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("⚠️ Backend not running")
                            .font(.headline)
                            .foregroundColor(.orange)
                        
                        Text("The Python backend needs to be started. Click the button below to start it.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Button("Start Backend") {
                            do {
                                try backendService.startBackend()
                            } catch {
                                errorMessage = error.localizedDescription
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                }
                
                if let error = errorMessage {
                    Text("Error: \(error)")
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
                
                Spacer()
            }
            .padding()
            .frame(minWidth: 300)
        } detail: {
            // Results view
            if isSearching {
                ProgressView("Searching...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if searchResults.isEmpty {
                VStack(spacing: 20) {
                    Image(systemName: "molecule")
                        .font(.system(size: 60))
                        .foregroundColor(.secondary)
                    Text("Enter a SMILES string and click Search to find similar molecules")
                        .font(.headline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ResultsView(results: searchResults)
            }
            }
            .navigationDestination(for: Molecule.self) { molecule in
                MoleculeDetailView(molecule: molecule)
            }
        }
        .onAppear {
            backendService.checkBackendHealth()
        }
    }
    
    private func performSearch() {
        guard !querySmiles.isEmpty else { return }
        
        isSearching = true
        errorMessage = nil
        searchResults = []
        
        Task {
            do {
                let results = try await backendService.searchSimilar(querySmiles: querySmiles, topK: topK)
                await MainActor.run {
                    searchResults = results
                    isSearching = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isSearching = false
                }
            }
        }
    }
}

#Preview {
    SearchView()
}

