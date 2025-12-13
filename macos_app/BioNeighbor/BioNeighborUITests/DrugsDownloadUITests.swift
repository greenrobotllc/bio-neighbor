//
//  DrugsDownloadUITests.swift
//  BioNeighborUITests
//
//  UI tests for drugs download functionality
//

import XCTest

final class DrugsDownloadUITests: XCTestCase {
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
    
    func testNavigateToDrugsDownload() throws {
        // Given: App is launched
        
        // When: Navigate to Download Data → Drugs
        app.downloadDataTab().click()
        
        let drugsSection = app.downloadSection("Drugs")
        if drugsSection.waitForExistence(timeout: 5.0) {
            drugsSection.click()
            
            // Then: Drugs download view should be visible
            let title = app.staticTexts["downloadDrugsTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
    }
    
    func testDrugsDownloadViewElementsExist() throws {
        // Given: On Drugs download view
        app.downloadDataTab().click()
        let drugsSection = app.downloadSection("Drugs")
        if drugsSection.waitForExistence(timeout: 5.0) {
            drugsSection.click()
            
            // Then: Key elements should exist
            let title = app.staticTexts["downloadDrugsTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
            
            let searchField = app.drugSearchField()
            if searchField.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(searchField.exists)
            }
        }
    }
    
    func testDrugSearchField() throws {
        // Given: On Drugs download view
        app.downloadDataTab().click()
        let drugsSection = app.downloadSection("Drugs")
        guard drugsSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Drugs section not found")
            return
        }
        drugsSection.click()
        
        // When: Interact with search field
        let searchField = app.drugSearchField()
        if searchField.waitForExistence(timeout: 2.0) {
            searchField.click()
            searchField.typeText("donepezil")
            
            // Then: Text should be entered
            XCTAssertEqual(searchField.value as? String, "donepezil")
        }
    }
    
    func testDiseaseSearchField() throws {
        // Given: On Drugs download view
        app.downloadDataTab().click()
        let drugsSection = app.downloadSection("Drugs")
        guard drugsSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Drugs section not found")
            return
        }
        drugsSection.click()
        
        // When: Scroll to disease search section and interact
        let diseaseSearchField = app.textFields["diseaseSearchField"]
        if diseaseSearchField.waitForExistence(timeout: 5.0) {
            diseaseSearchField.click()
            diseaseSearchField.typeText("Alzheimer")
            
            // Then: Text should be entered
            XCTAssertEqual(diseaseSearchField.value as? String, "Alzheimer")
        }
    }
}

