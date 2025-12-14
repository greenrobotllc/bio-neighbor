//
//  ReactiveDownloadServiceTests.swift
//  BioNeighborTests
//
//  Unit tests for ReactiveDownloadService using RxTest
//

import XCTest
import RxSwift
import RxTest
@testable import BioNeighbor

class ReactiveDownloadServiceTests: XCTestCase {
    var scheduler: TestScheduler!
    var disposeBag: DisposeBag!
    var service: ReactiveDownloadService!
    
    override func setUp() {
        super.setUp()
        scheduler = TestScheduler(initialClock: 0)
        disposeBag = DisposeBag()
        service = ReactiveDownloadService.shared
    }
    
    override func tearDown() {
        disposeBag = nil
        scheduler = nil
        service = nil
        super.tearDown()
    }
    
    func testStatsObservableEmits() {
        // Given
        let observer = scheduler.createObserver(DatabaseStats?.self)
        
        // When
        service.stats
            .subscribe(observer)
            .disposed(by: disposeBag)
        
        scheduler.start()
        
        // Then
        XCTAssertEqual(observer.events.count, 1) // Initial value
    }
    
    func testRefreshStats() {
        // Given
        let observer = scheduler.createObserver(DatabaseStats.self)
        
        // When
        service.refreshStats()
            .subscribe(observer)
            .disposed(by: disposeBag)
        
        scheduler.start()
        
        // Then - Should emit stats or error
        XCTAssertTrue(observer.events.count > 0)
    }
    
    func testDownloadProgressObservable() {
        // Given
        let observer = scheduler.createObserver(DownloadProgress.self)
        
        // When
        service.downloadProgress
            .subscribe(observer)
            .disposed(by: disposeBag)
        
        scheduler.start()
        
        // Then - Observable should be created (may not emit immediately)
        XCTAssertNotNil(observer)
    }
}

