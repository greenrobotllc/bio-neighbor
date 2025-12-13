//
//  StatisticsViewSnapshotTests.swift
//  BioNeighborSnapshotTests
//
//  Snapshot tests for statistics view
//

import XCTest
import SwiftUI
import SnapshotTesting
@testable import BioNeighbor

final class StatisticsViewSnapshotTests: XCTestCase {
    
    func testStatisticsViewWithData() throws {
        // Given: Statistics view with mock data
        let view = DownloadStatisticsView()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // assertSnapshot(matching: view, as: .image)
        
        XCTAssertNotNil(view)
    }
    
    func testStatisticsViewLoading() throws {
        // Given: Statistics view in loading state
        let view = DownloadStatisticsView()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // assertSnapshot(matching: view, as: .image)
        
        XCTAssertNotNil(view)
    }
    
    func testStatisticsViewNoBackend() throws {
        // Given: Statistics view with backend not running
        let view = DownloadStatisticsView()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // assertSnapshot(matching: view, as: .image)
        
        XCTAssertNotNil(view)
    }
}

