//
//  DrugDataDownloadView.swift
//  BioNeighbor
//
//  Interface for downloading drug and disease data
//

import SwiftUI

struct DrugDataDownloadView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var isDownloading = false
    @State private var downloadProgress: String = ""
    @State private var downloadStatus: String = ""
    @State private var errorMessage: String?
    @State private var downloadAlzheimers = true
    @State private var downloadTop100 = false
    @State private var maxDiseases = 100
    @State private var maxDrugsPerDisease = 20
    @State private var downloadHistory: [DownloadResult] = []
    
    struct DownloadResult: Identifiable {
        let id = UUID()
        let timestamp: Date
        let success: Bool
        let message: String
    }
    
    var body: some View {
        NavigationSplitView {
            // Sidebar with download controls
            VStack(alignment: .leading, spacing: 20) {
                Text("Data Download")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 10)
                
                Text("Download drug and disease data from PubChem")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Divider()
                
                // Download options
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download Options")
                        .font(.headline)
                    
                    Toggle("Alzheimer's Disease Drugs", isOn: $downloadAlzheimers)
                    
                    Toggle("Top 100 Diseases", isOn: $downloadTop100)
                    
                    if downloadTop100 {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Max Diseases: \(maxDiseases)")
                                .font(.subheadline)
                            Slider(value: Binding(
                                get: { Double(maxDiseases) },
                                set: { maxDiseases = Int($0) }
                            ), in: 10...100, step: 10)
                        }
                        .padding(.leading, 20)
                        
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Max Drugs per Disease: \(maxDrugsPerDisease)")
                                .font(.subheadline)
                            Slider(value: Binding(
                                get: { Double(maxDrugsPerDisease) },
                                set: { maxDrugsPerDisease = Int($0) }
                            ), in: 5...50, step: 5)
                        }
                        .padding(.leading, 20)
                    }
                }
                
                Divider()
                
                // Download button
                Button(action: startDownload) {
                    HStack {
                        if isDownloading {
                            ProgressView()
                                .progressViewStyle(.circular)
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "arrow.down.circle.fill")
                        }
                        Text(isDownloading ? "Downloading..." : "Start Download")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isDownloading || !backendService.isBackendRunning || (!downloadAlzheimers && !downloadTop100))
                
                if !backendService.isBackendRunning {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("⚠️ Backend not running")
                            .font(.headline)
                            .foregroundColor(.orange)
                        
                        Text("The Python backend needs to be started.")
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
                
                // Status
                if !downloadStatus.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Status")
                            .font(.headline)
                        Text(downloadStatus)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                    .background(Color.blue.opacity(0.1))
                    .cornerRadius(8)
                }
                
                if !downloadProgress.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Progress")
                            .font(.headline)
                        Text(downloadProgress)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .fontDesign(.monospaced)
                    }
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
                
                Spacer()
            }
            .padding()
            .frame(minWidth: 300)
        } detail: {
            // Download history
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download History")
                        .font(.title2)
                        .fontWeight(.bold)
                        .padding(.bottom, 8)
                    
                    if downloadHistory.isEmpty {
                        VStack(spacing: 16) {
                            Image(systemName: "clock")
                                .font(.system(size: 60))
                                .foregroundColor(.secondary)
                            Text("No downloads yet")
                                .font(.headline)
                                .foregroundColor(.secondary)
                            Text("Start a download to see history here")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    } else {
                        ForEach(downloadHistory.reversed()) { result in
                            HStack {
                                Image(systemName: result.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                                    .foregroundColor(result.success ? .green : .red)
                                
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(result.message)
                                        .font(.body)
                                    Text(result.timestamp, style: .time)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                
                                Spacer()
                            }
                            .padding()
                            .background(Color(NSColor.controlBackgroundColor))
                            .cornerRadius(8)
                        }
                    }
                }
                .padding()
            }
        }
        .navigationTitle("Download Data")
    }
    
    private func startDownload() {
        guard backendService.isBackendRunning else {
            errorMessage = "Backend is not running"
            return
        }
        
        isDownloading = true
        errorMessage = nil
        downloadStatus = "Preparing download..."
        downloadProgress = ""
        
        // Run download in background queue
        DispatchQueue.global(qos: .userInitiated).async {
            
            do {
                // Build command arguments
                var args: [String] = []
                if self.downloadAlzheimers {
                    args.append("--alzheimers-only")
                }
                if self.downloadTop100 {
                    args.append("--top-100")
                    args.append("--max-diseases")
                    args.append("\(self.maxDiseases)")
                    args.append("--max-drugs-per-disease")
                    args.append("\(self.maxDrugsPerDisease)")
                }
                
                // Execute download script
                let process = Process()
                
                guard let projectRoot = self.getProjectRoot() else {
                    throw NSError(domain: "BioNeighbor", code: 1, userInfo: [NSLocalizedDescriptionKey: "Could not find project root"])
                }
                
                // Use venv Python if available
                let venvPython = projectRoot.appendingPathComponent("venv/bin/python")
                let pythonPath: URL
                if FileManager.default.fileExists(atPath: venvPython.path) {
                    pythonPath = venvPython
                } else {
                    pythonPath = URL(fileURLWithPath: "/usr/bin/python3")
                }
                
                process.executableURL = pythonPath
                let scriptPath = projectRoot.appendingPathComponent("backend/download_disease_drugs.py")
                process.arguments = [scriptPath.path] + args
                
                // Set up environment
                var environment = ProcessInfo.processInfo.environment
                environment["PYTHONUNBUFFERED"] = "1"
                process.environment = environment
                
                // Capture output
                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = pipe
                
                let fileHandle = pipe.fileHandleForReading
                var output = ""
                
                // Read output asynchronously
                fileHandle.readabilityHandler = { handle in
                    let data = handle.availableData
                    if let string = String(data: data, encoding: .utf8) {
                        output += string
                        DispatchQueue.main.async {
                            // Update progress from output
                            if string.contains("Processing:") {
                                let lines = string.components(separatedBy: "\n")
                                for line in lines {
                                    if line.contains("Processing:") {
                                        self.downloadProgress = line.trimmingCharacters(in: .whitespaces)
                                    }
                                }
                            }
                            self.downloadStatus = "Downloading..."
                        }
                    }
                }
                
                try process.run()
                process.waitUntilExit()
                
                fileHandle.readabilityHandler = nil
                
                DispatchQueue.main.async {
                    self.isDownloading = false
                    
                    if process.terminationStatus == 0 {
                        self.downloadStatus = "Download completed successfully!"
                        self.downloadProgress = ""
                        self.downloadHistory.append(DownloadResult(
                            timestamp: Date(),
                            success: true,
                            message: "Downloaded \(self.downloadAlzheimers ? "Alzheimer's " : "")\(self.downloadTop100 ? "top \(self.maxDiseases) diseases" : "drugs")"
                        ))
                    } else {
                        self.errorMessage = "Download failed with exit code \(process.terminationStatus)"
                        self.downloadHistory.append(DownloadResult(
                            timestamp: Date(),
                            success: false,
                            message: "Download failed"
                        ))
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    self.isDownloading = false
                    self.errorMessage = error.localizedDescription
                    self.downloadHistory.append(DownloadResult(
                        timestamp: Date(),
                        success: false,
                        message: "Error: \(error.localizedDescription)"
                    ))
                }
            }
        }
    }
    
    private func getProjectRoot() -> URL? {
        let fileManager = FileManager.default
        guard let bundlePath = Bundle.main.bundlePath as String? else {
            return nil
        }
        
        var currentPath = URL(fileURLWithPath: bundlePath)
        
        for _ in 0..<10 {
            let backendPath = currentPath.appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: backendPath.path) {
                return currentPath
            }
            
            let venvPath = currentPath.appendingPathComponent("venv/bin/python")
            let dataPath = currentPath.appendingPathComponent("data/molecules.db")
            if fileManager.fileExists(atPath: venvPath.path) || fileManager.fileExists(atPath: dataPath.path) {
                return currentPath
            }
            
            currentPath = currentPath.deletingLastPathComponent()
            if currentPath.path == "/" {
                break
            }
        }
        
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let commonPaths = [
            homeDir.appendingPathComponent("Documents/GitHub/bio-neighbor"),
            homeDir.appendingPathComponent("Developer/bio-neighbor"),
            URL(fileURLWithPath: "/Users/andytriboletti/Documents/GitHub/bio-neighbor")
        ]
        
        for path in commonPaths {
            let backendPath = path.appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: backendPath.path) {
                return path
            }
        }
        
        return nil
    }
}

#Preview {
    DrugDataDownloadView()
}

