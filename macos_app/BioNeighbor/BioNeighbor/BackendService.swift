//
//  BackendService.swift
//  BioNeighbor
//
//  Service for communicating with Python backend
//

import Foundation
import Combine
import AppKit
import Darwin

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
    private var outputPipe: Pipe?
    private var errorPipe: Pipe?
    private let processQueue = DispatchQueue(label: "com.bioneighbor.backend.process", qos: .userInitiated)
    
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
        
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
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
        // Serialize start/stop operations to prevent races
        try processQueue.sync {
            // Check if backend is already running (check process state and health endpoint)
            if let existingProcess = backendProcess, existingProcess.isRunning {
                // Verify health endpoint is responding
                let semaphore = DispatchSemaphore(value: 0)
                var isHealthy = false
                
                guard let url = URL(string: "\(baseURL)/health") else {
                    throw BackendError.backendNotAvailable
                }
                
                var request = URLRequest(url: url)
                request.timeoutInterval = 1.0
                
                URLSession.shared.dataTask(with: request) { _, response, _ in
                    if let httpResponse = response as? HTTPURLResponse,
                       httpResponse.statusCode == 200 {
                        isHealthy = true
                    }
                    semaphore.signal()
                }.resume()
                
                // Wait up to 1 second for health check
                if semaphore.wait(timeout: .now() + 1.0) == .timedOut {
                    // Health check timed out, assume not running
                } else if isHealthy {
                    // Backend is running and healthy, return early
                    DispatchQueue.main.async {
                        self.isBackendRunning = true
                    }
                    return
                }
            }
            
            // If process exists, clean it up first (terminate if still running)
            if let existingProcess = backendProcess {
                if existingProcess.isRunning {
                    existingProcess.terminate()
                    // Best-effort wait a bit, then force kill if needed
                    let deadline = Date().addingTimeInterval(2.0)
                    while existingProcess.isRunning && Date() < deadline {
                        Thread.sleep(forTimeInterval: 0.05)
                    }
                    if existingProcess.isRunning {
                        let pid = existingProcess.processIdentifier
                        kill(pid, SIGKILL)
                    }
                }
                _stopBackendSync()
            }
            
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
            process.currentDirectoryURL = projectRoot
            
            // Set up environment
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONUNBUFFERED"] = "1"
            process.environment = environment
            
            // Redirect output and drain pipes to prevent deadlock
            let outputPipe = Pipe()
            let errorPipe = Pipe()
            process.standardOutput = outputPipe
            process.standardError = errorPipe
            
            // Retain pipes for the lifetime of the process
            self.outputPipe = outputPipe
            self.errorPipe = errorPipe
            
            // Set termination handler to keep UI state correct
            process.terminationHandler = { [weak self] process in
                self?.processQueue.async {
                    guard let self = self else { return }
                    // Clear process and pipes when it exits
                    if self.backendProcess === process {
                        self._stopBackendSync()
                    }
                }
            }
            
            // Drain stdout to prevent deadlock
            let outputHandle = outputPipe.fileHandleForReading
            outputHandle.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty {
                    handle.readabilityHandler = nil
                    return
                }
                // Optionally log or discard the data
                // For now, we'll just drain it to prevent blocking
                if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                    // Uncomment to log backend output:
                    // print("Backend stdout: \(output)")
                }
            }
            
            // Drain stderr to prevent deadlock
            let errorHandle = errorPipe.fileHandleForReading
            errorHandle.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty {
                    handle.readabilityHandler = nil
                    return
                }
                // Optionally log or discard the data
                // For now, we'll just drain it to prevent blocking
                if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                    // Uncomment to log backend errors:
                    // print("Backend stderr: \(output)")
                }
            }
            
            try process.run()
            backendProcess = process
            
            // Wait for server to start with exponential backoff
            var healthCheckSucceeded = false
            for attempt in 0..<5 {
                let delay = pow(2.0, Double(attempt)) * 0.5  // 0.5s, 1s, 2s, 4s, 8s
                Thread.sleep(forTimeInterval: delay)
                
                let semaphore = DispatchSemaphore(value: 0)
                var isHealthy = false
                
                guard let url = URL(string: "\(baseURL)/health") else {
                    break
                }
                
                var request = URLRequest(url: url)
                request.timeoutInterval = 1.0
                
                URLSession.shared.dataTask(with: request) { _, response, _ in
                    if let httpResponse = response as? HTTPURLResponse,
                       httpResponse.statusCode == 200 {
                        isHealthy = true
                    }
                    semaphore.signal()
                }.resume()
                
                if semaphore.wait(timeout: .now() + 2.0) == .success && isHealthy {
                    healthCheckSucceeded = true
                    break
                }
            }
            
            if !healthCheckSucceeded {
                // Health check failed, terminate and cleanup
                process.terminate()
                _stopBackendSync()
                throw BackendError.backendNotAvailable
            }
            
            // Only set isBackendRunning after health check succeeds
            DispatchQueue.main.async {
                self.isBackendRunning = true
            }
        }
    }
    
    // Internal synchronous stop method (must be called on processQueue)
    private func _stopBackendSync() {
        // Remove readability handlers
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        errorPipe?.fileHandleForReading.readabilityHandler = nil
        
        // Close file handles
        outputPipe?.fileHandleForReading.closeFile()
        errorPipe?.fileHandleForReading.closeFile()
        
        // Clear pipes
        outputPipe = nil
        errorPipe = nil
        
        // Clear process
        backendProcess = nil
        
        // Update UI state
        DispatchQueue.main.async {
            self.isBackendRunning = false
        }
    }
    
    func stopBackend() {
        processQueue.sync {
            guard let process = backendProcess else {
                return
            }
            
            // Remove readability handlers
            outputPipe?.fileHandleForReading.readabilityHandler = nil
            errorPipe?.fileHandleForReading.readabilityHandler = nil
            
            // Terminate the process
            process.terminate()
            
            // Set a timeout: if process doesn't exit within 5 seconds, kill it
            let timeout: TimeInterval = 5.0
            let deadline = Date().addingTimeInterval(timeout)
            
            // Wait for process to exit (with timeout)
            while process.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.1)
            }
            
            // If still running, force kill using SIGKILL
            if process.isRunning {
                // Process doesn't have kill() method, use signal() to send SIGKILL
                let pid = process.processIdentifier
                kill(pid, SIGKILL)
                // Give it a moment to die
                Thread.sleep(forTimeInterval: 0.5)
            }
            
            // Close file handles
            outputPipe?.fileHandleForReading.closeFile()
            errorPipe?.fileHandleForReading.closeFile()
            
            // Clear pipes and process
            outputPipe = nil
            errorPipe = nil
            backendProcess = nil
            
            // Update UI state
            DispatchQueue.main.async {
                self.isBackendRunning = false
            }
        }
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
        
        // Backend returns {success: bool, molecule: {...}}
        struct MoleculeDetailResponse: Codable {
            let success: Bool
            let molecule: MoleculeDetail?
            let error: String?
        }
        
        let responseObj = try JSONDecoder().decode(MoleculeDetailResponse.self, from: data)
        
        guard responseObj.success, let molecule = responseObj.molecule else {
            if let error = responseObj.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return molecule
    }
    
    func listMolecules(page: Int = 1, perPage: Int = 20, search: String? = nil, random: Bool = false, randomCount: Int = 20) async throws -> (molecules: [MoleculeBasic], pagination: Pagination?) {
        var urlComponents = URLComponents(string: "\(baseURL)/molecules")
        var queryItems: [URLQueryItem] = []
        
        if random {
            queryItems.append(URLQueryItem(name: "random", value: "true"))
            queryItems.append(URLQueryItem(name: "random_count", value: "\(randomCount)"))
        } else {
            queryItems.append(URLQueryItem(name: "page", value: "\(page)"))
            queryItems.append(URLQueryItem(name: "per_page", value: "\(perPage)"))
            if let search = search, !search.isEmpty {
                queryItems.append(URLQueryItem(name: "search", value: search))
            }
        }
        
        urlComponents?.queryItems = queryItems
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
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
        
        let listResponse = try JSONDecoder().decode(MoleculeListResponse.self, from: data)
        
        guard listResponse.success, let molecules = listResponse.molecules else {
            if let error = listResponse.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return (molecules, listResponse.pagination)
    }
    
    func getMoleculeWithSimilar(index: Int, topK: Int = 10) async throws -> (molecule: MoleculeBasic, similar: [Molecule]) {
        var urlComponents = URLComponents(string: "\(baseURL)/molecule/\(index)")
        urlComponents?.queryItems = [
            URLQueryItem(name: "include_similar", value: "true"),
            URLQueryItem(name: "top_k", value: "\(topK)")
        ]
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let moleculeResponse = try JSONDecoder().decode(MoleculeWithSimilarResponse.self, from: data)
        
        guard moleculeResponse.success else {
            if let error = moleculeResponse.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        guard let molecule = moleculeResponse.molecule else {
            throw BackendError.invalidResponse
        }
        
        return (molecule, moleculeResponse.similar ?? [])
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
    
    func getMoleculeThumbnail(index: Int, width: Int = 100, height: Int = 100) async throws -> NSImage? {
        guard let url = URL(string: "\(baseURL)/molecule/\(index)/thumbnail?width=\(width)&height=\(height)") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
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
    
    func getMolecule3D(index: Int) async throws -> Molecule3DCoordinates {
        guard let url = URL(string: "\(baseURL)/molecule/\(index)/3d") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(Molecule3DResponse.self, from: data)
        
        guard response.success,
              let atoms = response.atoms,
              let bonds = response.bonds,
              let smiles = response.smiles else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return Molecule3DCoordinates(atoms: atoms, bonds: bonds, smiles: smiles)
    }
    
    func getAllDiseases() async throws -> [Disease] {
        guard let url = URL(string: "\(baseURL)/diseases") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DiseasesResponse.self, from: data)
        
        guard response.success else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return response.diseases ?? []
    }
    
    func getDiseaseMolecules(diseaseName: String, limit: Int? = nil) async throws -> [MoleculeBasic] {
        // Custom character set that excludes "/" to prevent path segment breaks
        var allowedChars = CharacterSet.urlPathAllowed
        allowedChars.remove("/")
        let encodedName = diseaseName.addingPercentEncoding(withAllowedCharacters: allowedChars) ?? diseaseName
        var urlComponents = URLComponents(string: "\(baseURL)/diseases/\(encodedName)/molecules")
        
        if let limit = limit {
            urlComponents?.queryItems = [URLQueryItem(name: "limit", value: "\(limit)")]
        }
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DiseaseMoleculesResponse.self, from: data)
        
        guard response.success, let molecules = response.molecules else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return molecules
    }
    
    func getDiseaseTopMolecules(diseaseName: String, topK: Int = 10) async throws -> [MoleculeBasic] {
        // Custom character set that excludes "/" to prevent path segment breaks
        var allowedChars = CharacterSet.urlPathAllowed
        allowedChars.remove("/")
        let encodedName = diseaseName.addingPercentEncoding(withAllowedCharacters: allowedChars) ?? diseaseName
        var urlComponents = URLComponents(string: "\(baseURL)/diseases/\(encodedName)/top-molecules")
        urlComponents?.queryItems = [URLQueryItem(name: "top_k", value: "\(topK)")]
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DiseaseMoleculesResponse.self, from: data)
        
        guard response.success, let molecules = response.molecules else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return molecules
    }
    
    func searchByDisease(diseaseName: String, topK: Int = 10) async throws -> [Molecule] {
        guard let url = URL(string: "\(baseURL)/search/by-disease") else {
            throw BackendError.backendNotAvailable
        }
        
        let requestBody: [String: Any] = [
            "disease_name": diseaseName,
            "top_k": topK
        ]
        
        let requestData = try JSONSerialization.data(withJSONObject: requestBody)
        
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
        
        let searchResponse = try JSONDecoder().decode(DiseaseSearchResponse.self, from: data)
        
        guard searchResponse.success, let results = searchResponse.results else {
            if let error = searchResponse.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return results
    }
    
    func getAllDrugs() async throws -> [Drug] {
        guard let url = URL(string: "\(baseURL)/drugs") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DrugsResponse.self, from: data)
        
        guard response.success, let drugs = response.drugs else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return drugs
    }
    
    func getDrug(id: Int) async throws -> Drug {
        guard let url = URL(string: "\(baseURL)/drugs/\(id)") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DrugResponse.self, from: data)
        
        guard response.success, let drug = response.drug else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return drug
    }
    
    func getDrugMolecules(drugId: Int) async throws -> (drug: Drug, molecules: [MoleculeBasic]) {
        guard let url = URL(string: "\(baseURL)/drugs/\(drugId)/molecules") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DrugMoleculesResponse.self, from: data)
        
        guard response.success, let drug = response.drug, let molecules = response.molecules else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return (drug, molecules)
    }
    
    func getDiseaseDrugs(diseaseName: String, limit: Int? = nil) async throws -> (drugs: [Drug], molecules: [MoleculeBasic]) {
        // Custom character set that excludes "/" to prevent path segment breaks
        var allowedChars = CharacterSet.urlPathAllowed
        allowedChars.remove("/")
        let encodedName = diseaseName.addingPercentEncoding(withAllowedCharacters: allowedChars) ?? diseaseName
        var urlComponents = URLComponents(string: "\(baseURL)/diseases/\(encodedName)/drugs")
        
        if let limit = limit {
            urlComponents?.queryItems = [URLQueryItem(name: "limit", value: "\(limit)")]
        }
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DiseaseDrugsResponse.self, from: data)
        
        guard response.success else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return (response.drugs ?? [], response.molecules ?? [])
    }
    
    func getDatabaseStats() async throws -> DatabaseStats {
        guard let url = URL(string: "\(baseURL)/stats") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(StatsResponse.self, from: data)
        
        guard response.success, let stats = response.stats else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return stats
    }
    
    func searchMolecules(query: String, limit: Int = 20) async throws -> [SearchResult] {
        var urlComponents = URLComponents(string: "\(baseURL)/search/molecules")
        urlComponents?.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)")
        ]
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(AutocompleteResponse.self, from: data)
        
        guard response.success, let results = response.results else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return results
    }
    
    func searchDrugs(query: String, limit: Int = 20) async throws -> [SearchResult] {
        var urlComponents = URLComponents(string: "\(baseURL)/search/drugs")
        urlComponents?.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)")
        ]
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(AutocompleteResponse.self, from: data)
        
        guard response.success, let results = response.results else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return results
    }
    
    func searchDiseases(query: String, limit: Int = 20) async throws -> [SearchResult] {
        var urlComponents = URLComponents(string: "\(baseURL)/search/diseases")
        urlComponents?.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)")
        ]
        
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 30.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(AutocompleteResponse.self, from: data)
        
        guard response.success, let results = response.results else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return results
    }
    
    func downloadMolecules(count: Int? = nil, source: String? = nil, names: [String]? = nil, fullFile: Bool = false) async throws -> DownloadResponse {
        guard let url = URL(string: "\(baseURL)/download/molecules") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 60.0
        
        let request = DownloadMoleculesRequest(count: count, source: source, names: names, fullFile: fullFile ? true : nil)
        urlRequest.httpBody = try JSONEncoder().encode(request)
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DownloadResponse.self, from: data)
        
        guard response.success else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return response
    }
    
    func downloadDrugs(names: [String]? = nil, disease: String? = nil, count: Int? = nil, bulk: Bool = false) async throws -> DownloadResponse {
        guard let url = URL(string: "\(baseURL)/download/drugs") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 60.0
        
        let request = DownloadDrugsRequest(names: names, disease: disease, count: count, bulk: bulk ? true : nil)
        urlRequest.httpBody = try JSONEncoder().encode(request)
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DownloadResponse.self, from: data)
        
        guard response.success else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return response
    }
    
    func downloadDiseases(names: [String]? = nil, count: Int? = nil) async throws -> DownloadResponse {
        guard let url = URL(string: "\(baseURL)/download/diseases") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 60.0
        
        let request = DownloadDiseasesRequest(names: names, count: count)
        urlRequest.httpBody = try JSONEncoder().encode(request)
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DownloadResponse.self, from: data)
        
        guard response.success else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return response
    }
    
    func getDownloadStatus(taskId: String) async throws -> DownloadStatusResponse {
        guard let url = URL(string: "\(baseURL)/download/status/\(taskId)") else {
            throw BackendError.backendNotAvailable
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.timeoutInterval = 10.0
        
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let response = try JSONDecoder().decode(DownloadStatusResponse.self, from: data)
        
        guard response.success else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return response
    }
    
    private func getProjectRoot() -> URL? {
        // Try to find the project root by looking for backend/api.py
        let fileManager = FileManager.default
        
        // 1. Check user-configurable project root from UserDefaults
        if let userPath = UserDefaults.standard.string(forKey: "BioNeighborProjectRoot"),
           !userPath.isEmpty {
            let url = URL(fileURLWithPath: userPath)
            let backendPath = url.appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: backendPath.path) {
                return url
            }
        }
        
        // 2. Check environment variable
        if let envPath = ProcessInfo.processInfo.environment["BIO_NEIGHBOR_ROOT"],
           !envPath.isEmpty {
            let url = URL(fileURLWithPath: envPath)
            let backendPath = url.appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: backendPath.path) {
                return url
            }
        }
        
        // 3. Check app bundle resources (for bundled backend)
        if let bundleResourcePath = Bundle.main.resourcePath {
            let bundleBackendPath = URL(fileURLWithPath: bundleResourcePath).appendingPathComponent("backend/api.py")
            if fileManager.fileExists(atPath: bundleBackendPath.path) {
                return URL(fileURLWithPath: bundleResourcePath)
            }
        }
        
        // 4. Try going up from bundle path to find project root
        if let bundlePath = Bundle.main.bundlePath as String? {
            var currentPath = URL(fileURLWithPath: bundlePath)
            var candidateRoot: URL?
            
            // Go up from .app bundle to find project root
            // Path structure: .../bio-neighbor/macos_app/BioNeighbor/DerivedData/.../BioNeighbor.app
            // We need to get to: .../bio-neighbor/
            for _ in 0..<10 {
                let backendPath = currentPath.appendingPathComponent("backend/api.py")
                if fileManager.fileExists(atPath: backendPath.path) {
                    // Found backend/api.py - this is definitely the root
                    return currentPath
                }
                
                // Record candidate if we see venv or data markers (but keep looking for backend/api.py)
                let venvPath = currentPath.appendingPathComponent("venv/bin/python")
                let dataPath = currentPath.appendingPathComponent("data/molecules.db")
                if candidateRoot == nil && (fileManager.fileExists(atPath: venvPath.path) || fileManager.fileExists(atPath: dataPath.path)) {
                    candidateRoot = currentPath
                }
                
                currentPath = currentPath.deletingLastPathComponent()
                
                // Stop if we've gone too far up
                if currentPath.path == "/" {
                    break
                }
            }
            
            // If we found a candidate but never found backend/api.py, return the candidate
            if let candidate = candidateRoot {
                return candidate
            }
        }
        
        // 5. Fallback: Try common project locations (relative to home directory)
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let commonPaths = [
            homeDir.appendingPathComponent("Documents/GitHub/bio-neighbor"),
            homeDir.appendingPathComponent("Developer/bio-neighbor")
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

