//
//  DrugsDownloadViewModelTests.swift
//  BioNeighborTests
//
//  Unit tests for DrugsDownloadViewModel
//

import XCTest
@testable import BioNeighbor

class DrugsDownloadViewModelTests: XCTestCase {
    var viewModel: DrugsDownloadViewModel!
    
    override func setUp() {
        super.setUp()
        viewModel = DrugsDownloadViewModel()
    }
    
    override func tearDown() {
        viewModel = nil
        super.tearDown()
    }
    
    func testInitialState() {
        XCTAssertEqual(viewModel.maxDrugsPerDisease, 10)
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

