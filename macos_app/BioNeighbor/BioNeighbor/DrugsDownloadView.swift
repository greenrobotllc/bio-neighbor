//
//  DrugsDownloadView.swift
//  BioNeighbor
//
//  Drugs download section
//

import SwiftUI

struct DrugsDownloadView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var stats: DatabaseStats?
    @State private var searchText = ""
    @State private var searchResults: [SearchResult] = []
    @State private var selectedNames: Set<String> = []
    @State private var batchNames = ""
    @State private var selectedDisease = ""
    @State private var diseaseSearchText = ""
    @State private var diseaseSearchResults: [SearchResult] = []
    @State private var maxDrugsPerDisease = 10
    @State private var isDownloading = false
    @State private var downloadProgress = ""
    @State private var errorMessage: String?
    @State private var currentTaskId: String?
    @State private var statusTimer: Timer?
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                Text("Download Drugs")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                
                // Current count
                if let stats = stats {
                    HStack {
                        Text("Current drugs in database:")
                            .font(.headline)
                        Text("\(stats.drugs)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(.green)
                    }
                    .padding()
                    .background(Color.green.opacity(0.1))
                    .cornerRadius(8)
                }
                
                Divider()
                
                // Download by name
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Name")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    // Search field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Search drugs:")
                            .font(.headline)
                        
                        TextField("Enter drug name...", text: $searchText)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: searchText) { newValue in
                                if newValue.count >= 2 {
                                    performSearch()
                                } else {
                                    searchResults = []
                                }
                            }
                        
                        // Search results
                        if !searchResults.isEmpty {
                            List(searchResults) { result in
                                HStack {
                                    Text(result.name)
                                    Spacer()
                                    if selectedNames.contains(result.name) {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundColor(.green)
                                    }
                                }
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    if selectedNames.contains(result.name) {
                                        selectedNames.remove(result.name)
                                    } else {
                                        selectedNames.insert(result.name)
                                    }
                                }
                            }
                            .frame(height: 200)
                        }
                    }
                    
                    // Batch input
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Or enter names (one per line or comma-separated):")
                            .font(.headline)
                        
                        TextEditor(text: $batchNames)
                            .frame(height: 100)
                            .border(Color.gray.opacity(0.3))
                    }
                    
                    // Selected names
                    if !selectedNames.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Selected (\(selectedNames.count)):")
                                .font(.headline)
                            
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack {
                                    ForEach(Array(selectedNames), id: \.self) { name in
                                        HStack {
                                            Text(name)
                                            Button(action: {
                                                selectedNames.remove(name)
                                            }) {
                                                Image(systemName: "xmark.circle.fill")
                                                    .foregroundColor(.red)
                                            }
                                            .buttonStyle(.plain)
                                        }
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.green.opacity(0.1))
                                        .cornerRadius(8)
                                    }
                                }
                            }
                        }
                    }
                    
                    Button(action: downloadByName) {
                        HStack {
                            if isDownloading {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.down.circle.fill")
                            }
                            Text("Download Selected Drugs")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isDownloading || !backendService.isBackendRunning || (selectedNames.isEmpty && batchNames.isEmpty))
                }
                
                Divider()
                
                // Download by disease
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Disease")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Search disease:")
                            .font(.headline)
                        
                        TextField("Enter disease name...", text: $diseaseSearchText)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: diseaseSearchText) { newValue in
                                if newValue.count >= 2 {
                                    performDiseaseSearch()
                                } else {
                                    diseaseSearchResults = []
                                }
                            }
                        
                        // Disease search results
                        if !diseaseSearchResults.isEmpty {
                            List(diseaseSearchResults) { result in
                                Text(result.name)
                                    .contentShape(Rectangle())
                                    .onTapGesture {
                                        selectedDisease = result.name
                                        diseaseSearchText = result.name
                                        diseaseSearchResults = []
                                    }
                            }
                            .frame(height: 150)
                        }
                    }
                    
                    if !selectedDisease.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Selected disease: \(selectedDisease)")
                                .font(.headline)
                            
                            Text("Max drugs per disease: \(maxDrugsPerDisease)")
                                .font(.subheadline)
                            
                            Slider(value: Binding(
                                get: { Double(maxDrugsPerDisease) },
                                set: { maxDrugsPerDisease = Int($0) }
                            ), in: 5...50, step: 5)
                        }
                        
                        Button(action: downloadByDisease) {
                            HStack {
                                if isDownloading {
                                    ProgressView()
                                        .progressViewStyle(.circular)
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "arrow.down.circle.fill")
                                }
                                Text("Download Drugs for \(selectedDisease)")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isDownloading || !backendService.isBackendRunning)
                    }
                }
                
                // Progress/Error
                if !downloadProgress.isEmpty {
                    Text(downloadProgress)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding()
                        .background(Color.green.opacity(0.1))
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
            }
            .padding()
        }
        .onAppear {
            loadStats()
        }
        .onDisappear {
            statusTimer?.invalidate()
        }
    }
    
    private func loadStats() {
        guard backendService.isBackendRunning else { return }
        
        Task {
            do {
                let loadedStats = try await backendService.getDatabaseStats()
                await MainActor.run {
                    stats = loadedStats
                }
            } catch {
                // Silently fail
            }
        }
    }
    
    private func performSearch() {
        guard backendService.isBackendRunning else { return }
        
        Task {
            do {
                let results = try await backendService.searchDrugs(query: searchText, limit: 20)
                await MainActor.run {
                    searchResults = results
                }
            } catch {
                // Silently fail
            }
        }
    }
    
    private func performDiseaseSearch() {
        guard backendService.isBackendRunning else { return }
        
        Task {
            do {
                let results = try await backendService.searchDiseases(query: diseaseSearchText, limit: 20)
                await MainActor.run {
                    diseaseSearchResults = results
                }
            } catch {
                // Silently fail
            }
        }
    }
    
    private func startStatusPolling(taskId: String) {
        statusTimer?.invalidate()
        
        statusTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] timer in
            guard let self = self, self.isDownloading else {
                timer.invalidate()
                return
            }
            
            Task {
                do {
                    let status = try await self.backendService.getDownloadStatus(taskId: taskId)
                    await MainActor.run {
                        if let running = status.running {
                            if !running {
                                self.isDownloading = false
                                timer.invalidate()
                                if let exitCode = status.exitCode, exitCode == 0 {
                                    self.downloadProgress = status.message ?? "Download completed successfully"
                                    self.loadStats()
                                } else {
                                    self.errorMessage = status.message ?? "Download failed"
                                    self.downloadProgress = ""
                                }
                            } else {
                                self.downloadProgress = status.message ?? "Download in progress..."
                            }
                        }
                    }
                } catch {
                    // Silently fail
                }
            }
        }
    }
    
    private func downloadByName() {
        guard backendService.isBackendRunning else { return }
        
        var names: [String] = []
        names.append(contentsOf: selectedNames)
        
        if !batchNames.isEmpty {
            let batch = batchNames.components(separatedBy: CharacterSet(charactersIn: ",\n"))
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
            names.append(contentsOf: batch)
        }
        
        if names.isEmpty {
            errorMessage = "No names selected"
            return
        }
        
        isDownloading = true
        errorMessage = nil
        downloadProgress = "Starting download..."
        currentTaskId = nil
        
        Task {
            do {
                let response = try await backendService.downloadDrugs(names: names)
                await MainActor.run {
                    if let taskId = response.taskId {
                        currentTaskId = taskId
                        startStatusPolling(taskId: taskId)
                        selectedNames.removeAll()
                        batchNames = ""
                    } else {
                        isDownloading = false
                        downloadProgress = response.message ?? "Download started"
                        selectedNames.removeAll()
                        batchNames = ""
                    }
                }
            } catch {
                await MainActor.run {
                    isDownloading = false
                    errorMessage = error.localizedDescription
                    downloadProgress = ""
                }
            }
        }
    }
    
    private func downloadByDisease() {
        guard backendService.isBackendRunning, !selectedDisease.isEmpty else { return }
        
        isDownloading = true
        errorMessage = nil
        downloadProgress = "Starting download..."
        currentTaskId = nil
        
        Task {
            do {
                let response = try await backendService.downloadDrugs(disease: selectedDisease, count: maxDrugsPerDisease)
                await MainActor.run {
                    if let taskId = response.taskId {
                        currentTaskId = taskId
                        startStatusPolling(taskId: taskId)
                    } else {
                        isDownloading = false
                        downloadProgress = response.message ?? "Download started"
                    }
                }
            } catch {
                await MainActor.run {
                    isDownloading = false
                    errorMessage = error.localizedDescription
                    downloadProgress = ""
                }
            }
        }
    }
}

#Preview {
    DrugsDownloadView()
}

