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
    @State private var filteredMappings: [CancerMechanismMapping] = []
    @State private var searchText: String = ""
    @State private var selectedActivityLevel: String? = nil
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var activityLevels: [String] {
        Array(Set(cancerMappings.compactMap { $0.activityLevel })).sorted { level1, level2 in
            let order = ["High": 1, "Moderate": 2, "Low": 3]
            return (order[level1] ?? 99) < (order[level2] ?? 99)
        }
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(alignment: .leading, spacing: 8) {
                Text("Cross-Cancer Comparison")
                    .font(.title2)
                    .bold()
                
                Text("Cancer types with activity for this mechanism")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding()
            
            Divider()
            
            // Search and filter bar
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search by cancer type", text: $searchText)
                        .textFieldStyle(.plain)
                        .onChange(of: searchText) { _ in
                            filterMappings()
                        }
                    
                    if !searchText.isEmpty {
                        Button(action: {
                            searchText = ""
                            filterMappings()
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                
                if !activityLevels.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            Button(action: {
                                selectedActivityLevel = nil
                                filterMappings()
                            }) {
                                Text("All Levels")
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(selectedActivityLevel == nil ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                    .foregroundColor(selectedActivityLevel == nil ? .white : .primary)
                                    .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            
                            ForEach(activityLevels, id: \.self) { level in
                                Button(action: {
                                    selectedActivityLevel = level
                                    filterMappings()
                                }) {
                                    Text(level)
                                        .font(.caption)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(selectedActivityLevel == level ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                        .foregroundColor(selectedActivityLevel == level ? .white : .primary)
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
                ProgressView("Loading cancer mappings...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading cancer mappings")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        loadCancerMappings()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if filteredMappings.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "cross.case")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text(searchText.isEmpty ? "No cancer mappings found" : "No mappings match your search")
                        .font(.headline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                List(filteredMappings) { mapping in
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
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/cancers") else {
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
                       let cancers = json?["cancers"] as? [[String: Any]] {
                        var mappings: [CancerMechanismMapping] = []
                        for item in cancers {
                            if let jsonData = try? JSONSerialization.data(withJSONObject: item),
                               let mapping = try? JSONDecoder().decode(CancerMechanismMapping.self, from: jsonData) {
                                mappings.append(mapping)
                            }
                        }
                        self.cancerMappings = mappings
                        self.filteredMappings = mappings
                    } else {
                        errorMessage = json?["error"] as? String ?? "Failed to load cancer mappings"
                    }
                } catch {
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private func filterMappings() {
        var filtered = cancerMappings
        
        // Filter by search text
        if !searchText.isEmpty {
            let searchLower = searchText.lowercased()
            filtered = filtered.filter { mapping in
                mapping.cancerType.lowercased().contains(searchLower) ||
                mapping.evidenceSource?.lowercased().contains(searchLower) ?? false
            }
        }
        
        // Filter by activity level
        if let selectedLevel = selectedActivityLevel {
            filtered = filtered.filter { $0.activityLevel == selectedLevel }
        }
        
        filteredMappings = filtered
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
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(mapping.cancerType)
                    .font(.headline)
                Spacer()
                if let level = mapping.activityLevel {
                    HStack(spacing: 6) {
                        Circle()
                            .fill(activityColor)
                            .frame(width: 12, height: 12)
                        Text(level)
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(activityColor.opacity(0.2))
                    .cornerRadius(4)
                }
            }
            
            if let evidence = mapping.evidenceSource {
                Text(evidence)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 8)
    }
}
