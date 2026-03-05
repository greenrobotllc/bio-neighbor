//
//  CancerResearchDownloadView.swift
//  BioNeighbor
//
//  Cancer Research data loading interface in Download Data tab
//

import SwiftUI

struct MechanismDataStatus {
    let mechanismId: Int
    let targetsCount: Int
    let ligandsCount: Int
    let assaysCount: Int
    let outcomesCount: Int
    let cancerMappingsCount: Int
    let lastLoaded: String?
}

struct CancerResearchDownloadView: View {
    @State private var mechanisms: [Mechanism] = []
    @State private var dataStatus: [Int: MechanismDataStatus] = [:]
    @State private var isLoading = false
    @State private var loadingMechanismIds: Set<Int> = []
    @State private var errorMessage: String?
    @State private var successMessage: String?
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Cancer Research Data")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    
                    Text("Load targets, ligands, assays, and outcomes for cancer research mechanisms")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .padding()
                
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
                    .padding()
                    .background(Color.green.opacity(0.1))
                    .cornerRadius(8)
                    .padding(.horizontal)
                }
                
                if let error = errorMessage {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text(error)
                            .font(.caption)
                        Spacer()
                        Button("Dismiss") {
                            errorMessage = nil
                        }
                        .buttonStyle(.plain)
                        .font(.caption)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                    .padding(.horizontal)
                }
                
                // Initialize Mechanisms Section
                if mechanisms.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "flask")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        
                        Text("No Mechanisms Found")
                            .font(.headline)
                        
                        Text("Initialize mechanisms to begin loading cancer research data")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                        
                        Button(action: {
                            initializeMechanisms()
                        }) {
                            Label("Initialize Mechanisms", systemImage: "plus.circle.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isLoading)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                } else {
                    // Mechanisms List
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Text("Mechanisms")
                                .font(.headline)
                            
                            Spacer()
                            
                            Button(action: {
                                loadAllData()
                            }) {
                                Label("Load All Data", systemImage: "arrow.down.circle.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(isLoading)
                        }
                        .padding(.horizontal)
                        
                        ForEach(mechanisms) { mechanism in
                            MechanismDataCard(
                                mechanism: mechanism,
                                dataStatus: dataStatus[mechanism.id],
                                isLoading: loadingMechanismIds.contains(mechanism.id),
                                onLoadData: {
                                    loadDataForMechanism(mechanism.id)
                                }
                            )
                            .padding(.horizontal)
                        }
                    }
                }
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
                    errorMessage = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200,
                      let data = data else {
                    errorMessage = "Failed to load mechanisms"
                    return
                }
                
                do {
                    let response = try JSONDecoder().decode(MechanismsResponse.self, from: data)
                    if response.success, let mechanisms = response.mechanisms {
                        self.mechanisms = mechanisms
                        // Load data status for each mechanism
                        for mechanism in mechanisms {
                            loadDataStatus(for: mechanism.id)
                        }
                    }
                } catch {
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private func loadDataStatus(for mechanismId: Int) {
        // Get data counts for mechanism
        guard let targetsUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/targets"),
              let ligandsUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/ligands"),
              let assaysUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/assays"),
              let outcomesUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/drug-outcomes"),
              let cancersUrl = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/cancers") else {
            return
        }
        
        // Load all counts in parallel
        let group = DispatchGroup()
        var targetsCount = 0
        var ligandsCount = 0
        var assaysCount = 0
        var outcomesCount = 0
        var cancersCount = 0
        
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
        
        group.enter()
        URLSession.shared.dataTask(with: cancersUrl) { data, _, _ in
            if let data = data,
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let cancers = json["cancers"] as? [[String: Any]] {
                cancersCount = cancers.count
            }
            group.leave()
        }.resume()
        
        group.notify(queue: .main) {
            dataStatus[mechanismId] = MechanismDataStatus(
                mechanismId: mechanismId,
                targetsCount: targetsCount,
                ligandsCount: ligandsCount,
                assaysCount: assaysCount,
                outcomesCount: outcomesCount,
                cancerMappingsCount: cancersCount,
                lastLoaded: nil
            )
        }
    }
    
    private func initializeMechanisms() {
        isLoading = true
        errorMessage = nil
        successMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/initialize") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    errorMessage = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200,
                      let data = data else {
                    errorMessage = "Failed to initialize mechanisms"
                    return
                }
                
                do {
                    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                    if let success = json?["success"] as? Bool, success {
                        let message = json?["message"] as? String ?? "Mechanisms initialized successfully"
                        successMessage = message
                        
                        // Reload mechanisms and status
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
    
    private func loadDataForMechanism(_ mechanismId: Int) {
        loadingMechanismIds.insert(mechanismId)
        errorMessage = nil
        successMessage = nil

        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/load-data") else {
            errorMessage = "Invalid URL"
            loadingMechanismIds.remove(mechanismId)
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Use force_refresh: true to ensure data is actually loaded
        // This will reload even if data exists, which helps when APIs failed previously
        let body: [String: Any] = ["force_refresh": true]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                loadingMechanismIds.remove(mechanismId)
                
                if let error = error {
                    errorMessage = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200,
                      let data = data else {
                    errorMessage = "Failed to load data"
                    return
                }
                
                do {
                    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                    if let success = json?["success"] as? Bool, success {
                        let targets = json?["targets_loaded"] as? Int ?? 0
                        let ligands = json?["ligands_loaded"] as? Int ?? 0
                        let assays = json?["assays_loaded"] as? Int ?? 0
                        let outcomes = json?["outcomes_loaded"] as? Int ?? 0
                        
                        // Check for warnings/errors in response
                        var messageParts: [String] = []
                        if targets > 0 { messageParts.append("\(targets) targets") }
                        if ligands > 0 { messageParts.append("\(ligands) ligands") }
                        if assays > 0 { messageParts.append("\(assays) assays") }
                        if outcomes > 0 { messageParts.append("\(outcomes) outcomes") }
                        
                        if let warnings = json?["warnings"] as? [String], !warnings.isEmpty {
                            // Show warnings if data loading had issues
                            let warningText = warnings.joined(separator: "; ")
                            if messageParts.isEmpty {
                                errorMessage = "Loading completed but no new data: \(warningText)"
                            } else {
                                successMessage = "Loaded: " + messageParts.joined(separator: ", ")
                                errorMessage = "Warnings: \(warningText)"
                            }
                        } else if messageParts.isEmpty {
                            errorMessage = "No data loaded. Check server logs - ChEMBL/PubChem APIs may be unavailable."
                        } else {
                            successMessage = "Loaded: " + messageParts.joined(separator: ", ")
                        }
                        
                        // Reload data status
                        loadDataStatus(for: mechanismId)
                    } else {
                        errorMessage = json?["error"] as? String ?? "Failed to load data"
                    }
                } catch {
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private func loadAllData() {
        // Load mechanisms sequentially to avoid flooding the server
        let mechanismIds = mechanisms.map { $0.id }
        guard let firstId = mechanismIds.first else { return }

        func loadNext(index: Int) {
            guard index < mechanismIds.count else { return }
            let mechanismId = mechanismIds[index]
            loadingMechanismIds.insert(mechanismId)
            errorMessage = nil

            guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanismId)/load-data") else {
                errorMessage = "Invalid URL"
                loadingMechanismIds.remove(mechanismId)
                loadNext(index: index + 1)
                return
            }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let body: [String: Any] = ["force_refresh": true]
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)

            URLSession.shared.dataTask(with: request) { data, response, error in
                DispatchQueue.main.async {
                    loadingMechanismIds.remove(mechanismId)

                    if let error = error {
                        errorMessage = "Network error: \(error.localizedDescription)"
                    } else if let data = data,
                              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                              let success = json["success"] as? Bool, success {
                        loadDataStatus(for: mechanismId)
                    } else {
                        errorMessage = "Failed to load data for mechanism \(mechanismId)"
                    }

                    // Load next mechanism
                    loadNext(index: index + 1)
                }
            }.resume()
        }

        loadNext(index: 0)
    }
}

struct MechanismDataCard: View {
    let mechanism: Mechanism
    let dataStatus: MechanismDataStatus?
    let isLoading: Bool
    let onLoadData: () -> Void
    
    var hasData: Bool {
        guard let status = dataStatus else { return false }
        return status.targetsCount > 0 || status.ligandsCount > 0 || status.assaysCount > 0 || status.outcomesCount > 0
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(mechanism.name)
                        .font(.headline)
                    
                    if let status = dataStatus {
                        HStack(spacing: 12) {
                            if status.targetsCount > 0 {
                                Label("\(status.targetsCount) targets", systemImage: "target")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            if status.ligandsCount > 0 {
                                Label("\(status.ligandsCount) ligands", systemImage: "molecule")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            if status.assaysCount > 0 {
                                Label("\(status.assaysCount) assays", systemImage: "flask")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            if status.outcomesCount > 0 {
                                Label("\(status.outcomesCount) outcomes", systemImage: "chart.bar")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    } else {
                        Text("No data loaded")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
                
                Spacer()
                
                if isLoading {
                    ProgressView()
                        .scaleEffect(0.8)
                } else {
                    Button(action: onLoadData) {
                        Label(hasData ? "Refresh Data" : "Load Data", systemImage: hasData ? "arrow.clockwise" : "arrow.down.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }
}
