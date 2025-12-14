//
//  DiseasesDownloadViewModelTests.swift
//  BioNeighborTests
//
//  Unit tests for DiseasesDownloadViewModel
//

import XCTest
@testable import BioNeighbor

class DiseasesDownloadViewModelTests: XCTestCase {
    var viewModel: DiseasesDownloadViewModel!
    
    override func setUp() {
        super.setUp()
        viewModel = DiseasesDownloadViewModel()
    }
    
    override func tearDown() {
        viewModel = nil
        super.tearDown()
    }
    
    func testInitialState() {
        XCTAssertEqual(viewModel.bulkCount, 100)
        XCTAssertEqual(viewModel.currentDownloadState, .idle)
        XCTAssertFalse(viewModel.isDownloading)
    }
    
    func testIsDownloadingState() {
        viewModel.currentDownloadState = .idle
        XCTAssertFalse(viewModel.isDownloading)
        
        viewModel.currentDownloadState = .inProgress(message: "Downloading...")
        XCTAssertTrue(viewModel.isDownloading)
    }
}

