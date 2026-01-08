//
//  CancerResearchView.swift
//  BioNeighbor
//
//  Main Cancer Research tab view
//

import SwiftUI

struct CancerResearchView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var mechanisms: [Mechanism] = []
    @State private var selectedMechanism: Mechanism?
    @State private var isLoading = false
    @State private var isInitializing = false
    @State private var errorMessage: String?
    @State private var successMessage: String?
    @State private var mechanismDataCounts: [Int: MechanismDataCounts] = [:]
    
    var body: some View {
        NavigationSplitView {
            // Sidebar: Mechanism selector
            if isLoading {
                ProgressView("Loading mechanisms...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .navigationTitle("Cancer Research")
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading mechanisms")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                    Button("Retry") {
                        loadMechanisms()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
                .navigationTitle("Cancer Research")
            } else if mechanisms.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "flask")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("No mechanisms found")
                        .font(.headline)
                    Text("Initialize mechanisms to begin loading cancer research data")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                    
                    Button(action: {
                        initializeMechanisms()
                    }) {
                        Label("Initialize Mechanisms", systemImage: "plus.circle.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(isInitializing)
                    
                    if isInitializing {
                        ProgressView("Initializing mechanisms and loading data...")
                            .padding(.top, 8)
                    }
                    
                    Button("Refresh") {
                        loadMechanisms()
                    }
                    .buttonStyle(.bordered)
                    .padding(.top, 8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
                .navigationTitle("Cancer Research")
            } else {
                VStack(spacing: 0) {
                    List {
                        ForEach(mechanisms, id: \.id) { mechanism in
                            Button(action: {
                                selectedMechanism = mechanism
                            }) {
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(mechanism.name)
                                            .foregroundColor(selectedMechanism?.id == mechanism.id ? .white : .primary)
                                        Spacer()
                                    }
                                    
                                    if let counts = mechanismDataCounts[mechanism.id] {
                                        HStack(spacing: 8) {
                                            if counts.targets > 0 {
                                                Label("\(counts.targets)", systemImage: "target")
                                                    .font(.caption2)
                                                    .foregroundColor(selectedMechanism?.id == mechanism.id ? .white.opacity(0.8) : .secondary)
                                            }
                                            if counts.ligands > 0 {
                                                Label("\(counts.ligands)", systemImage: "molecule")
                                                    .font(.caption2)
                                                    .foregroundColor(selectedMechanism?.id == mechanism.id ? .white.opacity(0.8) : .secondary)
                                            }
                                            if counts.assays > 0 {
                                                Label("\(counts.assays)", systemImage: "flask")
                                                    .font(.caption2)
                                                    .foregroundColor(selectedMechanism?.id == mechanism.id ? .white.opacity(0.8) : .secondary)
                                            }
                                            if counts.outcomes > 0 {
                                                Label("\(counts.outcomes)", systemImage: "chart.bar")
                                                    .font(.caption2)
                                                    .foregroundColor(selectedMechanism?.id == mechanism.id ? .white.opacity(0.8) : .secondary)
                                            }
                                            
                                            if counts.targets == 0 && counts.ligands == 0 && counts.assays == 0 && counts.outcomes == 0 {
                                                Text("No data")
                                                    .font(.caption2)
                                                    .foregroundColor(selectedMechanism?.id == mechanism.id ? .white.opacity(0.8) : .orange)
                                            }
                                        }
                                    } else {
                                        Text("Loading status...")
                                            .font(.caption2)
                                            .foregroundColor(selectedMechanism?.id == mechanism.id ? .white.opacity(0.8) : .secondary)
                                    }
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .background(selectedMechanism?.id == mechanism.id ? Color.accentColor : Color.clear)
                                .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .listStyle(.sidebar)
                    .onAppear {
                        // Load data counts for all mechanisms
                        for mechanism in mechanisms {
                            loadDataCounts(for: mechanism.id)
                        }
                    }
                    
                    Divider()
                    
                    // Success/Error Messages
                    if let success = successMessage {
                        HStack {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                            Text(success)
                                .font(.caption)
                            Spacer()
                            Button("Dismiss") {
                                successMessage = nil
                            }
                            .buttonStyle(.plain)
                            .font(.caption)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.green.opacity(0.1))
                        .cornerRadius(4)
                    }
                    
                    VStack(spacing: 8) {
                        HStack {
                            Button(action: {
                                initializeMechanisms()
                            }) {
                                Label("Initialize Mechanisms", systemImage: "plus.circle.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.regular)
                            .disabled(isInitializing)
                            
                            if isInitializing {
                                ProgressView()
                                    .scaleEffect(0.8)
                                    .padding(.leading, 8)
                            }
                            
                            Spacer()
                            
                            Button(action: {
                                loadMechanisms()
                            }) {
                                Label("Refresh", systemImage: "arrow.clockwise")
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                        
                        HStack {
                            Text("\(mechanisms.count) mechanism\(mechanisms.count == 1 ? "" : "s")")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Spacer()
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 8)
                }
                .navigationTitle("Cancer Research")
                .frame(minWidth: 200)
            }
        } detail: {
            // Main workspace
            if let mechanism = selectedMechanism {
                MechanismWorkspaceView(mechanism: mechanism, onBackToSelector: {
                    selectedMechanism = nil
                })
            } else {
                VStack {
                    Image(systemName: "flask")
                        .font(.system(size: 64))
                        .foregroundColor(.secondary)
                    Text("Select a mechanism to begin")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    if !mechanisms.isEmpty {
                        Text("Click on a mechanism in the sidebar to explore it")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                    }
                    Text("Research Tool Only - Not for Medical Diagnosis or Treatment")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            loadMechanisms()
        }
    }
    
    private func loadMechanisms() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    errorMessage = "Network error: \(error.localizedDescription)\n\nMake sure the backend server is running."
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response from server"
                    return
                }
                
                guard httpResponse.statusCode == 200 else {
                    errorMessage = "Server error: HTTP \(httpResponse.statusCode)"
                    return
                }
                
                guard let data = data else {
                    errorMessage = "No data received from server"
                    return
                }
                
                do {
                    let response = try JSONDecoder().decode(MechanismsResponse.self, from: data)
                    
                    if !response.success {
                        errorMessage = response.error ?? "Failed to load mechanisms"
                        return
                    }
                    
                    guard let mechanisms = response.mechanisms else {
                        errorMessage = "No mechanisms in response"
                        return
                    }
                    
                    self.mechanisms = mechanisms
                    print("📊 Loaded \(mechanisms.count) mechanisms: \(mechanisms.map { $0.name }.joined(separator: ", "))")
                    
                    // Load data counts for all mechanisms
                    for mechanism in mechanisms {
                        loadDataCounts(for: mechanism.id)
                    }
                    
                    // Auto-select first mechanism if none selected
                    if selectedMechanism == nil && !mechanisms.isEmpty {
                        selectedMechanism = mechanisms[0]
                        print("✅ Auto-selected mechanism: \(mechanisms[0].name)")
                    }
                } catch {
                    // Try to decode error message
                    if let errorDict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let errorMsg = errorDict["error"] as? String {
                        errorMessage = errorMsg
                    } else {
                        errorMessage = "Failed to decode response: \(error.localizedDescription)"
                    }
                }
            }
        }.resume()
    }
    
    private func initializeMechanisms() {
        isInitializing = true
        errorMessage = nil
        successMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/initialize") else {
            errorMessage = "Invalid URL"
            isInitializing = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                isInitializing = false
                
                if let error = error {
                    errorMessage = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response from server"
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
                    if let success = json?["success"] as? Bool, success {
                        let message = json?["message"] as? String ?? "Mechanisms initialized successfully"
                        
                        // Extract data counts from response
                        if let dataLoaded = json?["data_loaded"] as? [String: [String: Any]] {
                            var countsMessage = "Initialized mechanisms. "
                            var countsParts: [String] = []
                            
                            for (key, data) in dataLoaded {
                                if let targets = data["targets_loaded"] as? Int, targets > 0 {
                                    countsParts.append("\(targets) targets")
                                }
                                if let ligands = data["ligands_loaded"] as? Int, ligands > 0 {
                                    countsParts.append("\(ligands) ligands")
                                }
                                if let assays = data["assays_loaded"] as? Int, assays > 0 {
                                    countsParts.append("\(assays) assays")
                                }
                                if let outcomes = data["outcomes_loaded"] as? Int, outcomes > 0 {
                                    countsParts.append("\(outcomes) outcomes")
                                }
                            }
                            
                            if !countsParts.isEmpty {
                                countsMessage += "Loaded: " + countsParts.joined(separator: ", ")
                            }
                            
                            successMessage = countsMessage
                            
                            // Auto-dismiss after 8 seconds
                            DispatchQueue.main.asyncAfter(deadline: .now() + 8) {
                                successMessage = nil
                            }
                        } else {
                            successMessage = message
                            DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                                successMessage = nil
                            }
                        }
                        
                        // Reload mechanisms after initialization
                        print("✅ Mechanisms initialized, reloading...")
                        loadMechanisms()
                    } else {
                        errorMessage = json?["error"] as? String ?? "Failed to initialize mechanisms"
                    }
                } catch {
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private func loadDataCounts(for mechanismId: Int) {
        // Load data counts for a mechanism
        let group = DispatchGroup()
        var targetsCount = 0
        var ligandsCount = 0
        var assaysCount = 0
        var outcomesCount = 0
        
        guard let targetsUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/targets"),
              let ligandsUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/ligands"),
              let assaysUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/assays"),
              let outcomesUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/drug-outcomes") else {
            return
        }
        
        group.enter()
        URLSession.shared.dataTask(with: targetsUrl) { data, _, _ in
            if let data = data,
               let response = try? JSONDecoder().decode(TargetsResponse.self, from: data),
               let targets = response.targets {
                targetsCount = targets.count
            }
            group.leave()
        }.resume()
        
        group.enter()
        URLSession.shared.dataTask(with: ligandsUrl) { data, _, _ in
            if let data = data,
               let response = try? JSONDecoder().decode(LigandsResponse.self, from: data),
               let ligands = response.ligands {
                ligandsCount = ligands.count
            }
            group.leave()
        }.resume()
        
        group.enter()
        URLSession.shared.dataTask(with: assaysUrl) { data, _, _ in
            if let data = data,
               let response = try? JSONDecoder().decode(AssaysResponse.self, from: data),
               let assays = response.assays {
                assaysCount = assays.count
            }
            group.leave()
        }.resume()
        
        group.enter()
        URLSession.shared.dataTask(with: outcomesUrl) { data, _, _ in
            if let data = data,
               let response = try? JSONDecoder().decode(DrugOutcomesResponse.self, from: data),
               let outcomes = response.outcomes {
                outcomesCount = outcomes.count
            }
            group.leave()
        }.resume()
        
        group.notify(queue: .main) {
            mechanismDataCounts[mechanismId] = MechanismDataCounts(
                targets: targetsCount,
                ligands: ligandsCount,
                assays: assaysCount,
                outcomes: outcomesCount
            )
        }
    }
}

struct MechanismDataCounts {
    let targets: Int
    let ligands: Int
    let assays: Int
    let outcomes: Int
}
