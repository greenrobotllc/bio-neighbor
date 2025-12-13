//
//  MockBackendService.swift
//  BioNeighborTests
//
//  Mock backend service for testing
//

import Foundation
@testable import BioNeighbor

class MockBackendService: BackendServiceProtocol {
    var isBackendRunning: Bool = true
    var baseURL: String = "http://localhost:5000"
    
    var mockStats: DatabaseStats?
    var mockSearchResults: [SearchResult] = []
    var mockDownloadResponse: DownloadResponse?
    var mockDownloadStatus: DownloadStatusResponse?
    var mockError: Error?
    
    func getDatabaseStats() async throws -> DatabaseStats {
        if let error = mockError {
            throw error
        }
        if let stats = mockStats {
            return stats
        }
        return DatabaseStats(molecules: 1000, drugs: 50, diseases: 20, relationships: 100)
    }
    
    func searchMolecules(query: String, limit: Int) async throws -> [SearchResult] {
        if let error = mockError {
            throw error
        }
        return mockSearchResults.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }
    
    func searchDrugs(query: String, limit: Int) async throws -> [SearchResult] {
        if let error = mockError {
            throw error
        }
        return mockSearchResults.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }
    
    func searchDiseases(query: String, limit: Int) async throws -> [SearchResult] {
        if let error = mockError {
            throw error
        }
        return mockSearchResults.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }
    
    func downloadMolecules(count: Int?, source: String?, names: [String]?) async throws -> DownloadResponse {
        if let error = mockError {
            throw error
        }
        if let response = mockDownloadResponse {
            return response
        }
        return DownloadResponse(success: true, message: "Download started", taskId: "test-task-123", error: nil)
    }
    
    func downloadDrugs(names: [String]?, disease: String?, count: Int?) async throws -> DownloadResponse {
        if let error = mockError {
            throw error
        }
        if let response = mockDownloadResponse {
            return response
        }
        return DownloadResponse(success: true, message: "Download started", taskId: "test-task-123", error: nil)
    }
    
    func downloadDiseases(names: [String]?, count: Int?) async throws -> DownloadResponse {
        if let error = mockError {
            throw error
        }
        if let response = mockDownloadResponse {
            return response
        }
        return DownloadResponse(success: true, message: "Download started", taskId: "test-task-123", error: nil)
    }
    
    func getDownloadStatus(taskId: String) async throws -> DownloadStatusResponse {
        if let error = mockError {
            throw error
        }
        if let status = mockDownloadStatus {
            return status
        }
        return DownloadStatusResponse(success: true, running: false, exitCode: 0, message: "Download completed", error: nil)
    }
}

protocol BackendServiceProtocol {
    var isBackendRunning: Bool { get }
    var baseURL: String { get }
    func getDatabaseStats() async throws -> DatabaseStats
    func searchMolecules(query: String, limit: Int) async throws -> [SearchResult]
    func searchDrugs(query: String, limit: Int) async throws -> [SearchResult]
    func searchDiseases(query: String, limit: Int) async throws -> [SearchResult]
    func downloadMolecules(count: Int?, source: String?, names: [String]?) async throws -> DownloadResponse
    func downloadDrugs(names: [String]?, disease: String?, count: Int?) async throws -> DownloadResponse
    func downloadDiseases(names: [String]?, count: Int?) async throws -> DownloadResponse
    func getDownloadStatus(taskId: String) async throws -> DownloadStatusResponse
}

