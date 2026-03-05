//
//  DrugOutcomesView.swift
//  BioNeighbor
//
//  Section 4: Drug Outcomes & Context
//

import SwiftUI

struct DrugOutcomesView: View {
    let mechanism: Mechanism
    @State private var outcomes: [DrugOutcome] = []
    @State private var filteredOutcomes: [DrugOutcome] = []
    @State private var searchText: String = ""
    @State private var selectedOutcomeType: String? = nil
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedOutcome: DrugOutcome?
    
    var outcomeTypes: [String] {
        Array(Set(outcomes.map { $0.outcomeType })).sorted()
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search and filter bar
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search by context or notes", text: $searchText)
                        .textFieldStyle(.plain)
                        .onChange(of: searchText) { _ in
                            filterOutcomes()
                        }
                    
                    if !searchText.isEmpty {
                        Button(action: {
                            searchText = ""
                            filterOutcomes()
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                
                if !outcomeTypes.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            Button(action: {
                                selectedOutcomeType = nil
                                filterOutcomes()
                            }) {
                                Text("All")
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(selectedOutcomeType == nil ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                    .foregroundColor(selectedOutcomeType == nil ? .white : .primary)
                                    .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                            
                            ForEach(outcomeTypes, id: \.self) { type in
                                Button(action: {
                                    selectedOutcomeType = type
                                    filterOutcomes()
                                }) {
                                    Text(type.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .font(.caption)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(selectedOutcomeType == type ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                                        .foregroundColor(selectedOutcomeType == type ? .white : .primary)
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
                ProgressView("Loading drug outcomes...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading outcomes")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        loadOutcomes()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if filteredOutcomes.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "chart.bar")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text(searchText.isEmpty ? "No outcomes found" : "No outcomes match your search")
                        .font(.headline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                List(filteredOutcomes) { outcome in
                    Button(action: {
                        selectedOutcome = outcome
                    }) {
                        DrugOutcomeRow(outcome: outcome)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .sheet(item: $selectedOutcome) { outcome in
            NavigationStack {
                DrugOutcomeDetailView(outcome: outcome)
            }
        }
        .onAppear {
            loadOutcomes()
        }
    }
    
    private func filterOutcomes() {
        var filtered = outcomes
        
        // Filter by search text
        if !searchText.isEmpty {
            let searchLower = searchText.lowercased()
            filtered = filtered.filter { outcome in
                outcome.context?.lowercased().contains(searchLower) ?? false ||
                outcome.notes?.lowercased().contains(searchLower) ?? false
            }
        }
        
        // Filter by outcome type
        if let selectedType = selectedOutcomeType {
            filtered = filtered.filter { $0.outcomeType == selectedType }
        }
        
        filteredOutcomes = filtered
    }
    
    private func loadOutcomes() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)/drug-outcomes") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    print("❌ Error loading outcomes: \(error.localizedDescription)")
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
                    let response = try JSONDecoder().decode(DrugOutcomesResponse.self, from: data)
                    if response.success {
                        let outcomes = response.outcomes ?? []
                        let count = response.count ?? outcomes.count
                        print("✅ Loaded \(count) outcomes for mechanism \(mechanism.id)")
                        
                        if outcomes.isEmpty {
                            print("⚠️  Warning: API returned success but no outcomes")
                        }
                        
                        self.outcomes = outcomes
                        self.filteredOutcomes = outcomes
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

struct DrugOutcomeRow: View {
    let outcome: DrugOutcome
    
    var outcomeColor: Color {
        switch outcome.outcomeType {
        case "success": return .green
        case "partial_success": return .yellow
        case "failure": return .red
        case "mixed": return .orange
        default: return .gray
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(outcomeColor)
                    .frame(width: 12, height: 12)
                Text(outcome.outcomeType.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.headline)
            }
            
            if let context = outcome.context {
                Text(context)
                    .font(.body)
            }
            
            if let evidence = outcome.evidenceLevel {
                Text("Evidence: \(evidence)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if let notes = outcome.notes {
                Text(notes)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
        .padding(.vertical, 4)
    }
}
