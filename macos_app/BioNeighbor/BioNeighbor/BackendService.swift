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
    /// NCI PDQ summary not mapped for this cancer type. Carries the cancer
    /// type's display name so callers can show a precise "skipped" message.
    case pdqUnavailable(cancerType: String)

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
        case .pdqUnavailable(let cancerType):
            return "No NCI PDQ summary mapped for \(cancerType)."
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

    /// Throws a descriptive `BackendError` for any non-200 response, parsing
    /// the backend's `{"error": "..."}` body when present so failures surface
    /// the actual reason instead of a hard-coded "Failed to fetch X" string.
    /// No-op on success.
    private func ensureOK(_ response: URLResponse, data: Data, fallback: String) throws {
        guard let http = response as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        guard http.statusCode == 200 else {
            if let body = try? JSONDecoder().decode([String: String].self, from: data),
               let message = body["error"] {
                throw BackendError.networkError(message)
            }
            throw BackendError.networkError("\(fallback) (HTTP \(http.statusCode))")
        }
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
        
        do {
            let listResponse = try JSONDecoder().decode(MoleculeListResponse.self, from: data)
            
            guard listResponse.isSuccess, let molecules = listResponse.molecules else {
                if let error = listResponse.error {
                    throw BackendError.unknownError(error)
                }
                throw BackendError.invalidResponse
            }
            
            return (molecules, listResponse.pagination)
        } catch {
            throw error
        }
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
        
        do {
            let moleculeResponse = try JSONDecoder().decode(MoleculeWithSimilarResponse.self, from: data)
            
            guard moleculeResponse.isSuccess else {
                if let error = moleculeResponse.error {
                    throw BackendError.unknownError(error)
                }
                throw BackendError.invalidResponse
            }
            
            guard let molecule = moleculeResponse.molecule else {
                throw BackendError.invalidResponse
            }
            
            return (molecule, moleculeResponse.similar ?? [])
        } catch {
            throw error
        }
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
        
        print("🟡 getAllDrugs: Requesting \(url)")
        let (data, urlResponse) = try await URLSession.shared.data(for: urlRequest)
        
        guard let httpResponse = urlResponse as? HTTPURLResponse else {
            print("🔴 getAllDrugs: Invalid response type")
            throw BackendError.invalidResponse
        }
        
        print("🟡 getAllDrugs: HTTP status \(httpResponse.statusCode)")
        
        guard httpResponse.statusCode == 200 else {
            let errorString = String(data: data, encoding: .utf8) ?? "Unknown error"
            print("🔴 getAllDrugs: HTTP \(httpResponse.statusCode), response: \(errorString)")
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }
        
        let dataString = String(data: data, encoding: .utf8) ?? "Unable to decode"
        print("🟡 getAllDrugs: Response data (first 500 chars): \(String(dataString.prefix(500)))")
        
        do {
            let response = try JSONDecoder().decode(DrugsResponse.self, from: data)
            print("🟡 getAllDrugs: Decoded response - success: \(response.isSuccess), drugs count: \(response.drugs?.count ?? 0)")
            
            guard response.isSuccess, let drugs = response.drugs else {
                let errorMsg = response.error ?? "Unknown error"
                print("🔴 getAllDrugs: Response indicates failure - \(errorMsg)")
                throw BackendError.unknownError(errorMsg)
            }
            
            print("🟡 getAllDrugs: Successfully returning \(drugs.count) drugs")
            return drugs
        } catch let decodingError as DecodingError {
            print("🔴 getAllDrugs: Decoding error - \(decodingError)")
            print("🔴 getAllDrugs: Raw data: \(dataString)")
            throw BackendError.invalidResponse
        } catch {
            print("🔴 getAllDrugs: Unexpected error - \(error)")
            throw error
        }
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
    
    /// Live drug search with ChEMBL write-through cache. Returns merged
    /// local + ChEMBL hits with a `source` flag per row. Use this in any UI
    /// that wants the freshest data (vs. searchDrugs which is autocomplete-shaped).
    func searchDrugsLive(query: String, limit: Int = 20, includeChembl: Bool = true) async throws -> (results: [DrugSearchResult], chemblUsed: Bool) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return ([], false) }

        var urlComponents = URLComponents(string: "\(baseURL)/search/drugs")
        urlComponents?.queryItems = [
            URLQueryItem(name: "q", value: trimmed),
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "include_chembl", value: includeChembl ? "1" : "0"),
        ]
        guard let url = urlComponents?.url else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        // ChEMBL fallback adds up to ~5s; keep timeout generous.
        request.timeoutInterval = 15.0

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            // Surface backend-supplied error messages instead of swallowing
            // them — matches the pattern used by `searchDrugs` etc.
            if let errorData = try? JSONDecoder().decode([String: String].self, from: data),
               let errorMessage = errorData["error"] {
                throw BackendError.networkError(errorMessage)
            }
            throw BackendError.networkError("HTTP \(httpResponse.statusCode)")
        }

        let envelope = try JSONDecoder().decode(DrugSearchEnvelope.self, from: data)
        guard envelope.success else {
            throw BackendError.unknownError(envelope.error ?? "Drug search failed")
        }
        return (envelope.results ?? [], envelope.chemblUsed ?? false)
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
    
    func getMoleculeBonds(index: Int) async throws -> MoleculeBondData {
        guard let url = URL(string: "\(baseURL)/molecule/\(index)/bonds") else {
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
        
        let response = try JSONDecoder().decode(MoleculeBondDataResponse.self, from: data)
        
        guard response.success,
              let atoms = response.atoms,
              let bonds = response.bonds,
              let smiles = response.smiles else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return MoleculeBondData(atoms: atoms, bonds: bonds, smiles: smiles)
    }
    
    func getFunctionalGroups(index: Int) async throws -> [FunctionalGroup] {
        guard let url = URL(string: "\(baseURL)/molecule/\(index)/functional-groups") else {
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
        
        let response = try JSONDecoder().decode(FunctionalGroupsResponse.self, from: data)
        
        guard response.success, let functionalGroups = response.functionalGroups else {
            if let error = response.error {
                throw BackendError.unknownError(error)
            }
            throw BackendError.invalidResponse
        }
        
        return functionalGroups
    }
    
    func compareMolecules(smiles1: String? = nil, smiles2: String? = nil, index1: Int? = nil, index2: Int? = nil) async throws -> MoleculeComparisonResponse {
        guard let url = URL(string: "\(baseURL)/molecules/compare") else {
            throw BackendError.backendNotAvailable
        }
        
        let request = CompareMoleculesRequest(smiles1: smiles1, smiles2: smiles2, index1: index1, index2: index2)
        let requestData = try JSONEncoder().encode(request)
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = requestData
        urlRequest.timeoutInterval = 60.0
        
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
        
        let response = try JSONDecoder().decode(MoleculeComparisonResponse.self, from: data)
        
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
    
    // MARK: - Cancer Research API Methods
    
    func fetchMechanisms() async throws -> [Mechanism] {
        guard let url = URL(string: "\(baseURL)/cancer-research/mechanisms") else {
            throw BackendError.backendNotAvailable
        }
        
        let (data, response) = try await URLSession.shared.data(from: url)
        
        try ensureOK(response, data: data, fallback: "Failed to fetch mechanisms")
        
        let mechanismsResponse = try JSONDecoder().decode(MechanismsResponse.self, from: data)
        guard mechanismsResponse.success, let mechanisms = mechanismsResponse.mechanisms else {
            throw BackendError.unknownError(mechanismsResponse.error ?? "Failed to fetch mechanisms")
        }

        return mechanisms
    }

    func fetchMechanism(id: Int) async throws -> Mechanism {
        guard let url = URL(string: "\(baseURL)/cancer-research/mechanisms/\(id)") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch mechanism")

        let mechanismResponse = try JSONDecoder().decode(MechanismResponse.self, from: data)
        guard mechanismResponse.success, let mechanism = mechanismResponse.mechanism else {
            throw BackendError.unknownError(mechanismResponse.error ?? "Failed to fetch mechanism")
        }

        return mechanism
    }

    func fetchTargets(for mechanismId: Int) async throws -> [Target] {
        guard let url = URL(string: "\(baseURL)/cancer-research/mechanisms/\(mechanismId)/targets") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch targets")

        let targetsResponse = try JSONDecoder().decode(TargetsResponse.self, from: data)
        guard targetsResponse.success, let targets = targetsResponse.targets else {
            throw BackendError.unknownError(targetsResponse.error ?? "Failed to fetch targets")
        }

        return targets
    }

    func fetchLigands(for mechanismId: Int) async throws -> [Ligand] {
        guard let url = URL(string: "\(baseURL)/cancer-research/mechanisms/\(mechanismId)/ligands") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch ligands")

        let ligandsResponse = try JSONDecoder().decode(LigandsResponse.self, from: data)
        guard ligandsResponse.success, let ligands = ligandsResponse.ligands else {
            throw BackendError.unknownError(ligandsResponse.error ?? "Failed to fetch ligands")
        }

        return ligands
    }

    func fetchDrugOutcomes(for mechanismId: Int) async throws -> [DrugOutcome] {
        guard let url = URL(string: "\(baseURL)/cancer-research/mechanisms/\(mechanismId)/drug-outcomes") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch drug outcomes")

        let outcomesResponse = try JSONDecoder().decode(DrugOutcomesResponse.self, from: data)
        guard outcomesResponse.success, let outcomes = outcomesResponse.outcomes else {
            throw BackendError.unknownError(outcomesResponse.error ?? "Failed to fetch drug outcomes")
        }

        return outcomes
    }

    func fetchAssays(for mechanismId: Int) async throws -> [Assay] {
        guard let url = URL(string: "\(baseURL)/cancer-research/mechanisms/\(mechanismId)/assays") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch assays")

        let assaysResponse = try JSONDecoder().decode(AssaysResponse.self, from: data)
        guard assaysResponse.success, let assays = assaysResponse.assays else {
            throw BackendError.unknownError(assaysResponse.error ?? "Failed to fetch assays")
        }

        return assays
    }
    
    func fetchCancers() async throws -> [String] {
        guard let url = URL(string: "\(baseURL)/cancer-research/cancers") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch cancers")

        let cancersResponse = try JSONDecoder().decode(CancersResponse.self, from: data)
        guard cancersResponse.success, let cancers = cancersResponse.cancers else {
            throw BackendError.unknownError(cancersResponse.error ?? "Failed to fetch cancers")
        }

        return cancers
    }
    
    func listWorkspaces() async throws -> [Workspace] {
        guard let url = URL(string: "\(baseURL)/cancer-research/workspaces") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to list workspaces")

        let workspacesResponse = try JSONDecoder().decode(WorkspacesResponse.self, from: data)
        guard workspacesResponse.success else {
            throw BackendError.unknownError(workspacesResponse.error ?? "Failed to list workspaces")
        }

        return workspacesResponse.workspaces ?? []
    }

    func createWorkspace(mechanismId: Int, filters: [String: Any] = [:], selections: [String: Any] = [:], notes: String = "") async throws -> Int {
        guard let url = URL(string: "\(baseURL)/cancer-research/workspaces") else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "mechanism_id": mechanismId,
            "filters": filters,
            "selections": selections,
            "notes": notes
        ]

        let bodyData: Data
        do {
            bodyData = try JSONSerialization.data(withJSONObject: body)
        } catch {
            throw BackendError.unknownError("Failed to encode workspace data")
        }
        request.httpBody = bodyData

        let (data, response) = try await URLSession.shared.data(for: request)

        try ensureOK(response, data: data, fallback: "Failed to create workspace")

        let workspaceResponse = try JSONDecoder().decode(WorkspaceCreateResponse.self, from: data)
        guard workspaceResponse.success, let workspaceId = workspaceResponse.workspaceId else {
            throw BackendError.unknownError(workspaceResponse.error ?? "Failed to create workspace")
        }

        return workspaceId
    }
    
    func updateWorkspace(id: Int, filters: [String: Any]? = nil, selections: [String: Any]? = nil, notes: String? = nil) async throws {
        guard let url = URL(string: "\(baseURL)/cancer-research/workspaces/\(id)") else {
            throw BackendError.backendNotAvailable
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        var body: [String: Any] = [:]
        if let filters = filters { body["filters"] = filters }
        if let selections = selections { body["selections"] = selections }
        if let notes = notes { body["notes"] = notes }

        let bodyData: Data
        do {
            bodyData = try JSONSerialization.data(withJSONObject: body)
        } catch {
            throw BackendError.unknownError("Failed to encode workspace update data")
        }
        request.httpBody = bodyData
        
        let (data, response) = try await URLSession.shared.data(for: request)

        try ensureOK(response, data: data, fallback: "Failed to update workspace")
    }

    // MARK: - Cancer Research v2 (disease-first browse)

    func fetchCancerTypes() async throws -> [CancerType] {
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/cancer-types") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch cancer types")

        let decoded = try JSONDecoder().decode(CancerTypesResponse.self, from: data)
        guard decoded.success, let types = decoded.cancerTypes else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch cancer types")
        }
        return types
    }

    func fetchSubtypes(forCancerTypeId typeId: Int) async throws -> [CancerSubtype] {
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/cancer-types/\(typeId)/subtypes") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch subtypes")

        let decoded = try JSONDecoder().decode(SubtypesResponse.self, from: data)
        guard decoded.success, let subtypes = decoded.subtypes else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch subtypes")
        }
        return subtypes
    }

    func fetchSubtypeDetail(id subtypeId: Int) async throws -> CancerSubtype {
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/subtypes/\(subtypeId)") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        try ensureOK(response, data: data, fallback: "Failed to fetch subtype")

        let decoded = try JSONDecoder().decode(SubtypeDetailResponse.self, from: data)
        guard decoded.success, let subtype = decoded.subtype else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch subtype")
        }
        return subtype
    }

    func fetchSubtypeTopDrugs(subtypeId: Int, limit: Int = 25, refresh: Bool = false) async throws -> [SubtypeTopDrug] {
        var components = URLComponents(string: "\(baseURL)/cancer-research/v2/subtypes/\(subtypeId)/top-drugs")
        components?.queryItems = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "refresh", value: refresh ? "1" : "0"),
        ]
        guard let url = components?.url else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        // ChEMBL pulls can take 30+ seconds when refresh=true.
        request.timeoutInterval = refresh ? 120.0 : 60.0

        let (data, response) = try await URLSession.shared.data(for: request)

        try ensureOK(response, data: data, fallback: "Failed to fetch top drugs")

        let decoded = try JSONDecoder().decode(SubtypeTopDrugsResponse.self, from: data)
        guard decoded.success, let drugs = decoded.drugs else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch top drugs")
        }
        return drugs
    }

    func fetchClinicalTrials(chemblId: String, limit: Int = 15) async throws -> [ClinicalTrial] {
        var components = URLComponents(string: "\(baseURL)/cancer-research/v2/drugs/\(chemblId)/trials")
        components?.queryItems = [URLQueryItem(name: "limit", value: "\(limit)")]
        guard let url = components?.url else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        // Each trial fetch hits ClinicalTrials.gov; up to 30 in parallel takes ~10-30s.
        request.timeoutInterval = 90.0

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to fetch clinical trials")

        let decoded = try JSONDecoder().decode(ClinicalTrialsResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch clinical trials")
        }
        return decoded.trials ?? []
    }

    /// Fetch the NCI PDQ treatment-summary sections for a subtype. Throws
    /// `BackendError.pdqUnavailable(cancerType:)` when the parent cancer type
    /// isn't in pdq_fetcher's slug map (hematologic / rare cancers) so the
    /// auditor can render a "skipped" step instead of a generic error.
    func fetchPDQSummary(
        subtypeId: Int,
        stage: String?,
        stageDetail: String?
    ) async throws -> PDQSummary {
        var components = URLComponents(string: "\(baseURL)/cancer-research/v2/subtypes/\(subtypeId)/treatment-summary")
        var query: [URLQueryItem] = []
        if let stage, !stage.isEmpty {
            query.append(URLQueryItem(name: "stage", value: stage))
        }
        if let stageDetail, !stageDetail.isEmpty {
            query.append(URLQueryItem(name: "stage_detail", value: stageDetail))
        }
        components?.queryItems = query.isEmpty ? nil : query
        guard let url = components?.url else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        // PDQ fetch hits cancer.gov once on cold cache, then cached for the
        // server lifetime; 20s covers the worst case.
        request.timeoutInterval = 20.0

        let (data, response) = try await URLSession.shared.data(for: request)
        // Decode first — a 404 with reason="pdq_unavailable" carries useful
        // payload that we want to surface as a typed error.
        let decoded = try JSONDecoder().decode(PDQSummaryResponse.self, from: data)
        if decoded.success,
           let slug = decoded.slug,
           let sourceURL = decoded.sourceURL,
           let sections = decoded.sections {
            return PDQSummary(
                slug: slug,
                sourceURL: sourceURL,
                stage: decoded.stage,
                stageDetail: decoded.stageDetail,
                sections: sections
            )
        }
        if decoded.reason == "pdq_unavailable" {
            throw BackendError.pdqUnavailable(cancerType: decoded.cancerType ?? "this cancer type")
        }
        // Fall through to generic HTTP/error handling.
        try ensureOK(response, data: data, fallback: "Failed to fetch PDQ summary")
        throw BackendError.unknownError(decoded.error ?? "Failed to fetch PDQ summary")
    }

    /// Fetch CT.gov trials matching a subtype's condition + a modality
    /// (radiation / surgery / chemotherapy / targeted). Returns `[]` on
    /// no-results or when CT.gov fails — a single failed modality should not
    /// block the rest of the audit.
    func fetchModalityTrials(
        subtypeId: Int,
        modality: String,
        limit: Int = 8
    ) async throws -> [ClinicalTrial] {
        var components = URLComponents(string: "\(baseURL)/cancer-research/v2/subtypes/\(subtypeId)/modality-trials")
        components?.queryItems = [
            URLQueryItem(name: "modality", value: modality),
            URLQueryItem(name: "limit", value: "\(limit)"),
        ]
        guard let url = components?.url else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 30.0

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to fetch modality trials")

        let decoded = try JSONDecoder().decode(ModalityTrialsResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch modality trials")
        }
        return decoded.trials ?? []
    }

    /// Outcome of `fetchAdverseEventPanel` — top FAERS reactions per drug
    /// plus the symptom→reaction match list (issue #46).
    struct FAERSPanelOutcome {
        let perDrug: [FAERSDrugPanel]
        let symptomMatches: [FAERSSymptomMatch]
    }

    /// Fetch top OpenFDA FAERS reactions for each prescribed drug and
    /// match user-reported symptoms against those reactions (issue #46).
    /// Cached server-side for 7 days. Best-effort — the audit continues
    /// when this throws.
    func fetchAdverseEventPanel(
        drugs: [(name: String, chemblId: String?)],
        symptoms: [String]
    ) async throws -> FAERSPanelOutcome {
        guard !drugs.isEmpty else {
            return FAERSPanelOutcome(perDrug: [], symptomMatches: [])
        }
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/treatment-auditor/adverse-events") else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Cold cache: 2 OpenFDA calls per drug × N drugs. Budget for ~5
        // drugs worst-case.
        request.timeoutInterval = 60.0
        let body = FAERSRequest(
            drugs: drugs.map { FAERSRequestDrug(name: $0.name, chemblId: $0.chemblId) },
            symptoms: symptoms
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to fetch adverse events")

        let decoded = try JSONDecoder().decode(FAERSResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Adverse-event lookup failed")
        }
        return FAERSPanelOutcome(
            perDrug: decoded.perDrug ?? [],
            symptomMatches: decoded.symptomMatches ?? []
        )
    }

    /// Outcome of `fetchTargetOverlap` — bundles the per-drug target list
    /// with the pairwise overlaps so the UI can render both
    /// (deterministic facts) without a second round-trip.
    struct TargetOverlapOutcome {
        let targetsByDrug: [DrugTargetsByDrug]
        let unmatched: [String]
        let overlaps: [DrugTargetOverlap]
    }

    /// Fetch mechanism-of-action target overlap among the supplied drugs
    /// (issue #53). Backed by ChEMBL `mechanism` + `target` resources,
    /// cached server-side. Cold cache for ~5 drugs takes 5-15s; warm
    /// cache is near-instant.
    func fetchTargetOverlap(_ drugs: [(name: String, chemblId: String?)]) async throws -> TargetOverlapOutcome {
        guard !drugs.isEmpty else {
            return TargetOverlapOutcome(targetsByDrug: [], unmatched: [], overlaps: [])
        }
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/treatment-auditor/target-overlap") else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Cold-cache cost dominated by ChEMBL — budget generously.
        request.timeoutInterval = 60.0
        let body = TargetOverlapRequest(
            drugs: drugs.map { TargetOverlapRequestEntry(name: $0.name, chemblId: $0.chemblId) }
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to fetch target overlap")

        let decoded = try JSONDecoder().decode(TargetOverlapResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Target overlap lookup failed")
        }
        return TargetOverlapOutcome(
            targetsByDrug: decoded.targetsByDrug ?? [],
            unmatched: decoded.unmatched ?? [],
            overlaps: decoded.overlaps ?? []
        )
    }

    /// Outcome of `fetchDrugInteractions`. The `drugbankLoaded` flag is
    /// the load-bearing one — when false, the UI must render a "DrugBank
    /// XML not loaded" hint rather than "no interactions found", because
    /// the absence of data is meaningfully different from an empty result.
    struct DrugInteractionsOutcome {
        let drugbankLoaded: Bool
        let matched: [DrugInteractionMatch]
        let unmatched: [String]
        let interactions: [DrugInteraction]
    }

    /// Fetch pairwise DrugBank drug-drug interactions among the supplied
    /// drugs (issue #47). Best-effort: the Treatment Auditor falls back
    /// to "no interactions surfaced" when this throws.
    func fetchDrugInteractions(_ drugs: [(name: String, chemblId: String?, drugbankId: String?)]) async throws -> DrugInteractionsOutcome {
        guard !drugs.isEmpty else {
            return DrugInteractionsOutcome(drugbankLoaded: false, matched: [], unmatched: [], interactions: [])
        }
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/treatment-auditor/drug-interactions") else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Pure local SQL — fast unless the parser is mid-bulk-load. 15s
        // is plenty.
        request.timeoutInterval = 15.0
        let body = DrugInteractionsRequest(
            drugs: drugs.map {
                DrugInteractionsRequestEntry(name: $0.name, chemblId: $0.chemblId, drugbankId: $0.drugbankId)
            }
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to fetch drug interactions")

        let decoded = try JSONDecoder().decode(DrugInteractionsResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Drug interaction lookup failed")
        }
        return DrugInteractionsOutcome(
            drugbankLoaded: decoded.drugbankLoaded ?? false,
            matched: decoded.matched ?? [],
            unmatched: decoded.unmatched ?? [],
            interactions: decoded.interactions ?? []
        )
    }

    /// Normalize a batch of drug names via RxNorm (issue #55). The
    /// Treatment Auditor uses the returned `groupKey` to dedupe
    /// brand-vs-generic entries before fanning out per-drug fetches.
    /// Best-effort: a backend failure should not block the audit, so
    /// callers typically fall back to "treat each input as its own group"
    /// when this throws.
    func normalizeDrugs(_ drugs: [(name: String, chemblId: String?)]) async throws -> [DrugNormalization] {
        guard !drugs.isEmpty else { return [] }
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/treatment-auditor/normalize-drugs") else {
            throw BackendError.backendNotAvailable
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Live RxNorm calls take ~200-500ms each on cache miss; budget
        // generously for first-run audits where every drug is uncached.
        request.timeoutInterval = 30.0
        let body = DrugNormalizationRequest(
            drugs: drugs.map { DrugNormalizationRequestEntry(name: $0.name, chemblId: $0.chemblId) }
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to normalize drug names")

        let decoded = try JSONDecoder().decode(DrugNormalizationResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Drug normalization failed")
        }
        return decoded.normalizations ?? []
    }

    func fetchChEMBLDrugDetail(chemblId: String) async throws -> ChEMBLDrugDetail {
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/drugs/\(chemblId)/detail") else {
            throw BackendError.backendNotAvailable
        }
        var request = URLRequest(url: url)
        // ChEMBL detail involves up to 4 round-trips (molecule + parent + 2 indication pulls).
        request.timeoutInterval = 60.0

        let (data, response) = try await URLSession.shared.data(for: request)
        try ensureOK(response, data: data, fallback: "Failed to fetch ChEMBL drug detail")

        let decoded = try JSONDecoder().decode(ChEMBLDrugDetailResponse.self, from: data)
        guard decoded.success, let detail = decoded.detail else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch ChEMBL drug detail")
        }
        return detail
    }

    func fetchSimilarDrugs(chemblId: String, topK: Int = 20) async throws -> (drugs: [SimilarDrugHit], notInLocalIndex: Bool, fetchedFromChEMBL: Bool) {
        var components = URLComponents(string: "\(baseURL)/cancer-research/v2/drugs/\(chemblId)/similar")
        components?.queryItems = [URLQueryItem(name: "top_k", value: "\(topK)")]
        guard let url = components?.url else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        try ensureOK(response, data: data, fallback: "Failed to fetch similar drugs")

        let decoded = try JSONDecoder().decode(SimilarDrugsResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch similar drugs")
        }
        return (
            decoded.similar ?? [],
            decoded.notInLocalIndex ?? false,
            decoded.fetchedFromChEMBL ?? false
        )
    }

    func searchDrugsInCancerType(typeId: Int, query: String, limitPerSubtype: Int = 5) async throws -> DrugSearchResponse {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        // Mirror searchDrugsLive's empty-query guard so we don't dispatch a
        // backend search for a blank string and accidentally repopulate stale
        // results.
        guard !trimmed.isEmpty else {
            return DrugSearchResponse(
                success: true,
                query: "",
                cancerTypeId: typeId,
                subtypeMatches: [],
                uncachedSubtypeCount: 0,
                note: nil,
                disclaimer: nil,
                error: nil
            )
        }
        var components = URLComponents(string: "\(baseURL)/cancer-research/v2/cancer-types/\(typeId)/drug-search")
        components?.queryItems = [
            URLQueryItem(name: "q", value: trimmed),
            URLQueryItem(name: "limit", value: "\(limitPerSubtype)"),
        ]
        guard let url = components?.url else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        try ensureOK(response, data: data, fallback: "Drug search failed")

        let decoded = try JSONDecoder().decode(DrugSearchResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Drug search failed")
        }
        return decoded
    }

    func fetchSubtypeMechanisms(subtypeId: Int) async throws -> [SubtypeMechanism] {
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/subtypes/\(subtypeId)/mechanisms") else {
            throw BackendError.backendNotAvailable
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        try ensureOK(response, data: data, fallback: "Failed to fetch subtype mechanisms")

        let decoded = try JSONDecoder().decode(SubtypeMechanismsResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Failed to fetch subtype mechanisms")
        }
        return decoded.mechanisms ?? []
    }

    @discardableResult
    func refreshSubtypeDrugs(subtypeId: Int) async throws -> SubtypeRefreshResponse {
        guard let url = URL(string: "\(baseURL)/cancer-research/v2/subtypes/\(subtypeId)/refresh-drugs") else {
            throw BackendError.backendNotAvailable
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 180.0  // ChEMBL refresh can be slow

        let (data, response) = try await URLSession.shared.data(for: request)

        try ensureOK(response, data: data, fallback: "Failed to refresh drugs")

        let decoded = try JSONDecoder().decode(SubtypeRefreshResponse.self, from: data)
        guard decoded.success else {
            throw BackendError.unknownError(decoded.error ?? "Refresh failed")
        }
        return decoded
    }
}

