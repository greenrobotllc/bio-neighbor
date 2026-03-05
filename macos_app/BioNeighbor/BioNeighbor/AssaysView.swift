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
    @State private var filteredAssays: [Assay] = []
    @State private var searchText: String = ""
    @State private var selectedDataSource: String? = nil
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedAssay: Assay?
    
    var dataSources: [String] {
        Array(Set(assays.compactMap { $0.dataSource })).sorted()
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search and filter bar
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search by assay type, readout, or data source", text: $searchText)
                        .textFieldStyle(.plain)
                        .onChange(of: searchText) { _ in
                            filterAssays()
                        }
                    
                    if !searchText.isEmpty {
                        Button(action: {
                            searchText = ""
                            filterAssays()
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                
                if !dataSources.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            Button(action: {
                                selectedDataSource = nil
                                filterAssays()
                            }) {
                                Text("All Sources")
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(selectedDataSource == nil ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                    .foregroundColor(selectedDataSource == nil ? .white : .primary)
                                    .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            
                            ForEach(dataSources, id: \.self) { source in
                                Button(action: {
                                    selectedDataSource = source
                                    filterAssays()
                                }) {
                                    Text(source)
                                        .font(.caption)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(selectedDataSource == source ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                        .foregroundColor(selectedDataSource == source ? .white : .primary)
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
                ProgressView("Loading assays...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading assays")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        loadAssays()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if filteredAssays.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "flask")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text(searchText.isEmpty ? "No assays found" : "No assays match your search")
                        .font(.headline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                List(filteredAssays) { assay in
                    Button(action: {
                        selectedAssay = assay
                    }) {
                        AssayRow(assay: assay)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .sheet(item: $selectedAssay) { assay in
            NavigationStack {
                AssayDetailView(assay: assay)
            }
        }
        .onAppear {
            loadAssays()
        }
    }
    
    private func filterAssays() {
        var filtered = assays
        
        // Filter by search text
        if !searchText.isEmpty {
            let searchLower = searchText.lowercased()
            filtered = filtered.filter { assay in
                assay.assayType?.lowercased().contains(searchLower) ?? false ||
                assay.readout?.lowercased().contains(searchLower) ?? false ||
                assay.dataSource?.lowercased().contains(searchLower) ?? false
            }
        }
        
        // Filter by data source
        if let selectedSource = selectedDataSource {
            filtered = filtered.filter { $0.dataSource == selectedSource }
        }
        
        filteredAssays = filtered
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
                    print("❌ Error loading assays: \(error.localizedDescription)")
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
                    let response = try JSONDecoder().decode(AssaysResponse.self, from: data)
                    if response.success {
                        let assays = response.assays ?? []
                        let count = response.count ?? assays.count
                        print("✅ Loaded \(count) assays for mechanism \(mechanism.id)")
                        
                        if assays.isEmpty {
                            print("⚠️  Warning: API returned success but no assays")
                        }
                        
                        self.assays = assays
                        self.filteredAssays = assays
                    } else {
                        let errorMsg = response.error ?? "Unknown error"
                        print("❌ API returned error: \(errorMsg)")
                        errorMessage = errorMsg
                    }
                } catch {
                    print("❌ Failed to decode response: \(error)")
                    if let jsonString = String(data: data, encoding: .utf8) {
                        print("Raw response: \(jsonString.prefix(500))")
                    }
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
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
