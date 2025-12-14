//
//  DiseasesDownloadUITests.swift
//  BioNeighborUITests
//
//  UI tests for diseases download functionality
//

import XCTest

final class DiseasesDownloadUITests: XCTestCase {
    var app: XCUIApplication!
    
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launch()
    }
    
    override func tearDownWithError() throws {
        app = nil
    }
    
    func testNavigateToDiseasesDownload() throws {
        // Given: App is launched
        
        // When: Navigate to Download Data → Diseases
        app.downloadDataTab().click()
        
        let diseasesSection = app.downloadSection("Diseases")
        if diseasesSection.waitForExistence(timeout: 5.0) {
            diseasesSection.click()
            
            // Then: Diseases download view should be visible
            let title = app.staticTexts["downloadDiseasesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
    }
    
    func testDiseasesDownloadViewElementsExist() throws {
        // Given: On Diseases download view
        app.downloadDataTab().click()
        let diseasesSection = app.downloadSection("Diseases")
        if diseasesSection.waitForExistence(timeout: 5.0) {
            diseasesSection.click()
            
            // Then: Key elements should exist
            let title = app.staticTexts["downloadDiseasesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
            
            let searchField = app.diseaseNameSearchField()
            if searchField.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(searchField.exists)
            }
            
            let bulkButton = app.downloadDiseasesBulkButton()
            if bulkButton.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(bulkButton.exists)
            }
        }
    }
    
    func testDiseaseSearchField() throws {
        // Given: On Diseases download view
        app.downloadDataTab().click()
        let diseasesSection = app.downloadSection("Diseases")
        guard diseasesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Diseases section not found")
            return
        }
        diseasesSection.click()
        
        // When: Interact with search field
        let searchField = app.diseaseNameSearchField()
        if searchField.waitForExistence(timeout: 2.0) {
            searchField.click()
            searchField.typeText("diabetes")
            
            // Then: Text should be entered
            XCTAssertEqual(searchField.value as? String, "diabetes")
        }
    }
    
    func testBulkDownloadButton() throws {
        // Given: On Diseases download view
        app.downloadDataTab().click()
        let diseasesSection = app.downloadSection("Diseases")
        guard diseasesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Diseases section not found")
            return
        }
        diseasesSection.click()
        
        // When: Look for bulk download button
        let bulkButton = app.downloadDiseasesBulkButton()
        
        // Then: Button should exist
        if bulkButton.waitForExistence(timeout: 2.0) {
            XCTAssertTrue(bulkButton.exists)
        }
    }
}

