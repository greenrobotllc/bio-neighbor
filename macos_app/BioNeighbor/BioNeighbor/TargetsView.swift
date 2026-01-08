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
    @State private var filteredTargets: [Target] = []
    @State private var searchText: String = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedTarget: Target?
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search by gene symbol, protein name, or UniProt ID", text: $searchText)
                    .textFieldStyle(.plain)
                    .onChange(of: searchText) { _ in
                        filterTargets()
                    }
                
                if !searchText.isEmpty {
                    Button(action: {
                        searchText = ""
                        filterTargets()
                    }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            
            Divider()
            
            // Content
            if isLoading {
                ProgressView("Loading targets...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading targets")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        loadTargets()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if filteredTargets.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "target")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text(searchText.isEmpty ? "No targets found" : "No targets match your search")
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
                List(filteredTargets) { target in
                    NavigationLink(destination: TargetDetailView(targetId: target.id)) {
                        TargetRow(target: target)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .onAppear {
            loadTargets()
        }
    }
    
    private func filterTargets() {
        if searchText.isEmpty {
            filteredTargets = targets
        } else {
            let searchLower = searchText.lowercased()
            filteredTargets = targets.filter { target in
                target.geneSymbol?.lowercased().contains(searchLower) ?? false ||
                target.proteinName?.lowercased().contains(searchLower) ?? false ||
                target.uniprotId?.lowercased().contains(searchLower) ?? false
            }
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
                self.filteredTargets = targets
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
