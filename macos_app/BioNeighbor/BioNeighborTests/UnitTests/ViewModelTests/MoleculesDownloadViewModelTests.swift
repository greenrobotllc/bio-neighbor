//
//  MoleculesDownloadViewModelTests.swift
//  BioNeighborTests
//
//  Unit tests for MoleculesDownloadViewModel
//

import XCTest
import RxSwift
import RxTest
import Combine
@testable import BioNeighbor

class MoleculesDownloadViewModelTests: XCTestCase {
    var viewModel: MoleculesDownloadViewModel!
    var scheduler: TestScheduler!
    var disposeBag: DisposeBag!
    var cancellables: Set<AnyCancellable>!
    
    override func setUp() {
        super.setUp()
        scheduler = TestScheduler(initialClock: 0)
        disposeBag = DisposeBag()
        cancellables = Set<AnyCancellable>()
        viewModel = MoleculesDownloadViewModel()
    }
    
    override func tearDown() {
        cancellables = nil
        disposeBag = nil
        scheduler = nil
        viewModel = nil
        super.tearDown()
    }
    
    func testInitialState() {
        XCTAssertEqual(viewModel.downloadCount, 1000)
        XCTAssertEqual(viewModel.selectedSource, "pubchem")
        XCTAssertEqual(viewModel.currentDownloadState, .idle)
        XCTAssertFalse(viewModel.isDownloading)
    }
    
    func testIsDownloadingState() {
        // Given
        viewModel.currentDownloadState = .idle
        
        // When
        XCTAssertFalse(viewModel.isDownloading)
        
        viewModel.currentDownloadState = .starting
        XCTAssertTrue(viewModel.isDownloading)
        
        viewModel.currentDownloadState = .inProgress(message: "Downloading...")
        XCTAssertTrue(viewModel.isDownloading)
        
        viewModel.currentDownloadState = .completed(message: "Done")
        XCTAssertFalse(viewModel.isDownloading)
        
        viewModel.currentDownloadState = .failed(error: "Error")
        XCTAssertFalse(viewModel.isDownloading)
    }
    
    func testButtonText() {
        viewModel.currentDownloadState = .idle
        XCTAssertEqual(viewModel.buttonText, "Download Molecules")
        
        viewModel.currentDownloadState = .starting
        XCTAssertEqual(viewModel.buttonText, "Starting...")
        
        viewModel.currentDownloadState = .inProgress(message: "Downloading 50%")
        XCTAssertEqual(viewModel.buttonText, "Downloading 50%")
        
        viewModel.currentDownloadState = .completed(message: "Done")
        XCTAssertEqual(viewModel.buttonText, "Download Completed")
        
        viewModel.currentDownloadState = .failed(error: "Error")
        XCTAssertEqual(viewModel.buttonText, "Download Failed")
    }
    
    func testDownloadCountRange() {
        viewModel.downloadCount = 100
        XCTAssertEqual(viewModel.downloadCount, 100)
        
        viewModel.downloadCount = 10000
        XCTAssertEqual(viewModel.downloadCount, 10000)
    }
}

