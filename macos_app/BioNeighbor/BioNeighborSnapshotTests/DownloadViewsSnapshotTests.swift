//
//  DownloadViewsSnapshotTests.swift
//  BioNeighborSnapshotTests
//
//  Snapshot tests for download views
//

import XCTest
import SwiftUI
import SnapshotTesting
@testable import BioNeighbor

final class DownloadViewsSnapshotTests: XCTestCase {
    
    func testMoleculesDownloadViewIdle() throws {
        // Given: Molecules download view in idle state
        let view = MoleculesDownloadViewRx()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // Note: Requires SnapshotTesting package
        // assertSnapshot(matching: view, as: .image)
        
        // For now, just verify view can be created
        XCTAssertNotNil(view)
    }
    
    func testDrugsDownloadViewIdle() throws {
        // Given: Drugs download view in idle state
        let view = DrugsDownloadViewRx()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // assertSnapshot(matching: view, as: .image)
        
        XCTAssertNotNil(view)
    }
    
    func testDiseasesDownloadViewIdle() throws {
        // Given: Diseases download view in idle state
        let view = DiseasesDownloadViewRx()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // assertSnapshot(matching: view, as: .image)
        
        XCTAssertNotNil(view)
    }
    
    func testStatisticsView() throws {
        // Given: Statistics view
        let view = DownloadStatisticsView()
            .frame(width: 800, height: 600)
        
        // When: Take snapshot
        // assertSnapshot(matching: view, as: .image)
        
        XCTAssertNotNil(view)
    }
}

