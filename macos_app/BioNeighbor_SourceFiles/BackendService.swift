//
//  BackendService.swift
//  BioNeighbor
//
//  Service for communicating with Python backend
//

import Foundation
import Combine

enum BackendError: LocalizedError {
    case invalidSMILES
    case backendNotAvailable
    case networkError(String)
    case invalidResponse
    case unknownError(String)
    
    var errorDescription: String? {
        switch self {
        case .invalidSMILES:
            return "Invalid SMILES string"
        case .backendNotAvailable:
            return "Backend service is not available. Please ensure the Python backend is running."
        case .networkError(let message):
            return "Network error: \(message)"
        case .invalidResponse:
            return "Invalid response from backend"
        case .unknownError(let message):
            return "Error: \(message)"
        }
    }
}

class BackendService: ObservableObject {
    static let shared = BackendService()
    
    private let baseURL = "http://127.0.0.1:5000"
    private var backendProcess: Process?
    
    @Published var isBackendRunning = false
    
    private init() {
        checkBackendHealth()
    }
    
    func checkBackendHealth() {
        guard let url = URL(string: "\(baseURL)/health") else {
            isBackendRunning = false
            return
        }
        
        var request = URLRequest(url: url)
        request.timeoutInterval = 2.0
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let httpResponse = response as? HTTPURLResponse,
                   httpResponse.statusCode == 200 {
                    self?.isBackendRunning = true
                } else {
                    self?.isBackendRunning = false
                }
            }
        }.resume()
    }
    
    func startBackend() throws {
        // Get the path to the Python backend
        guard let projectRoot = getProjectRoot() else {
            throw BackendError.backendNotAvailable
        }
        
        let venvPython = projectRoot.appendingPathComponent("venv/bin/python")
        let apiScript = projectRoot.appendingPathComponent("backend/api.py")
        
        // Check if files exist
        guard FileManager.default.fileExists(atPath: venvPython.path) else {
            throw BackendError.backendNotAvailable
        }
        
        guard FileManager.default.fileExists(atPath: apiScript.path) else {
            throw BackendError.backendNotAvailable
        }
        
        // Start backend process
        let process = Process()
        process.executableURL = URL(fileURLWithPath: venvPython.path)
        process.arguments = [apiScript.path, "--mode", "http", "--host", "127.0.0.1", "--port", "5000"]
        
        // Set up environment
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        process.environment = environment
        
        // Redirect output (optional, for debugging)
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        
        try process.run()
        backendProcess = process
        
        // Wait a bit for server to start
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.checkBackendHealth()
        }
    }
    
    func stopBackend() {
        backendProcess?.terminate()
        backendProcess = nil
        isBackendRunning = false
    }
    
    func searchSimilar(querySmiles: String, topK: Int = 10) async throws -> [Molecule] {
        guard let url = URL(string: "\(baseURL)/search") else {
            throw BackendError.backendNotAvailable
        }
        
        let request = SearchRequest(querySmiles: querySmiles, topK: topK)
        let requestData = try JSONEncoder().encode(request)
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = requestData
        urlRequest.timeoutInterval = 30.0
        
        let (data, response) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let searchResponse = try JSONDecoder().decode(SearchResponse.self, from: data)
        
        guard searchResponse.success, let results = searchResponse.results else {
            if let error = searchResponse.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return results
    }
    
    func getMoleculeByIndex(_ index: Int) async throws -> MoleculeDetail {
        guard let url = URL(string: "\(baseURL)/molecule/\(index)") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 10.0
        
        let (data, response) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw BackendError.invalidResponse
        }
        
        let responseDict = try JSONDecoder().decode([String: MoleculeDetail].self, from: data)
        
        guard let molecule = responseDict["molecule"] else {
            throw BackendError.invalidResponse
        }
        
        return molecule
    }
    
    func renderMolecule(smiles: String, width: Int = 400, height: Int = 400) async throws -> NSImage? {
        guard let url = URL(string: "\(baseURL)/render") else {
            throw BackendError.backendNotAvailable
        }
        
        let requestBody: [String: Any] = [
            "smiles": smiles,
            "width": width,
            "height": height
        ]
        
        let requestData = try JSONSerialization.data(withJSONObject: requestBody)
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = requestData
        urlRequest.timeoutInterval = 30.0
        
        let (data, response) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw BackendError.invalidResponse
        }
        
        let responseDict = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        
        guard let success = responseDict?["success"] as? Bool,
              success,
              let imageBase64 = responseDict?["image"] as? String else {
            throw BackendError.invalidResponse
        }
        
        // Extract base64 data (remove data:image/png;base64, prefix if present)
        let base64String = imageBase64.components(separatedBy: ",").last ?? imageBase64
        
        guard let imageData = Data(base64Encoded: base64String),
              let image = NSImage(data: imageData) else {
            throw BackendError.invalidResponse
        }
        
        return image
    }
    
    private func getProjectRoot() -> URL? {
        // Try to find the project root by looking for backend/api.py
        let fileManager = FileManager.default
        var currentPath = URL(fileURLWithPath: fileManager.currentDirectoryPath)
        
        // Try going up from current directory
        for _ in 0..<5 {
            let backendPath = currentPath.appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: backendPath.path) {
                return currentPath
            }
            currentPath = currentPath.deletingLastPathComponent()
        }
        
        // Try using the bundle's resource path (for packaged app)
        if let resourcePath = Bundle.main.resourcePath {
            let resourceURL = URL(fileURLWithPath: resourcePath)
            let backendPath = resourceURL.deletingLastPathComponent().appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: backendPath.path) {
                return resourceURL.deletingLastPathComponent()
            }
        }
        
        return nil
    }
}

