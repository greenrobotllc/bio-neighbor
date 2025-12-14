//
//  TestHelpers.swift
//  BioNeighborTests
//
//  Test helper utilities
//

import Foundation
@testable import BioNeighbor

struct TestDataFactory {
    static func createDatabaseStats(
        molecules: Int = 1000,
        drugs: Int = 50,
        diseases: Int = 20,
        relationships: Int = 100
    ) -> DatabaseStats {
        return DatabaseStats(
            molecules: molecules,
            drugs: drugs,
            diseases: diseases,
            relationships: relationships
        )
    }
    
    static func createSearchResult(
        id: Int = 1,
        name: String = "Test Molecule",
        chemblId: String? = "CHEMBL123",
        smiles: String? = "CCO"
    ) -> SearchResult {
        return SearchResult(
            id: id,
            name: name,
            chemblId: chemblId,
            smiles: smiles,
            genericName: nil,
            brandNames: nil,
            meshId: nil
        )
    }
    
    static func createDownloadResponse(
        success: Bool = true,
        message: String = "Download started",
        taskId: String = "test-task-123"
    ) -> DownloadResponse {
        return DownloadResponse(
            success: success,
            message: message,
            taskId: taskId,
            error: nil
        )
    }
    
    static func createDownloadStatusResponse(
        running: Bool = false,
        exitCode: Int? = 0,
        message: String = "Download completed"
    ) -> DownloadStatusResponse {
        return DownloadStatusResponse(
            success: true,
            running: running,
            exitCode: exitCode,
            message: message,
            error: nil
        )
    }
}

extension DownloadState: Equatable {
    public static func == (lhs: DownloadState, rhs: DownloadState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle):
            return true
        case (.starting, .starting):
            return true
        case (.inProgress(let lhsMsg), .inProgress(let rhsMsg)):
            return lhsMsg == rhsMsg
        case (.completed(let lhsMsg), .completed(let rhsMsg)):
            return lhsMsg == rhsMsg
        case (.failed(let lhsErr), .failed(let rhsErr)):
            return lhsErr == rhsErr
        default:
            return false
        }
    }
}

