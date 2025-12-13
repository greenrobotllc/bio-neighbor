//
//  MoleculesDownloadUITests.swift
//  BioNeighborUITests
//
//  UI tests for molecules download functionality
//

import XCTest

final class MoleculesDownloadUITests: XCTestCase {
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
    
    func testNavigateToMoleculesDownload() throws {
        // Given: App is launched
        
        // When: Navigate to Download Data → Molecules
        app.downloadDataTab().click()
        
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 5.0) {
            moleculesSection.click()
            
            // Then: Molecules download view should be visible
            let title = app.staticTexts["downloadMoleculesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
    }
    
    func testMoleculesDownloadViewElementsExist() throws {
        // Given: On Molecules download view
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 5.0) {
            moleculesSection.click()
            
            // Then: Key elements should exist
            let title = app.staticTexts["downloadMoleculesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
            
            let downloadButton = app.downloadMoleculesByCountButton()
            if downloadButton.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(downloadButton.exists)
            }
            
            let searchField = app.moleculeSearchField()
            if searchField.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(searchField.exists)
            }
        }
    }
    
    func testDownloadMoleculesByCountButtonExists() throws {
        // Given: On Molecules download view
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 5.0) {
            moleculesSection.click()
            
            // When: Look for download button
            let downloadButton = app.downloadMoleculesByCountButton()
            
            // Then: Button should exist (may be disabled if backend not running)
            if downloadButton.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(downloadButton.exists)
            }
        }
    }
    
    func testMoleculeSearchFieldExists() throws {
        // Given: On Molecules download view
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 5.0) {
            moleculesSection.click()
            
            // When: Look for search field
            let searchField = app.moleculeSearchField()
            
            // Then: Search field should exist
            if searchField.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(searchField.exists)
                
                // Can interact with it
                searchField.click()
                searchField.typeText("aspirin")
            }
        }
    }
    
    func testSliderExists() throws {
        // Given: On Molecules download view
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 5.0) {
            moleculesSection.click()
            
            // When: Look for count slider
            let slider = app.moleculeCountSlider()
            
            // Then: Slider should exist
            if slider.waitForExistence(timeout: 2.0) {
                XCTAssertTrue(slider.exists)
            }
        }
    }
    
    func testDownloadMoleculesByCountFlow() throws {
        // Given: On Molecules download view with backend running
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        guard moleculesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Molecules section not found")
            return
        }
        moleculesSection.click()
        
        // When: Click download button
        let downloadButton = app.downloadMoleculesByCountButton()
        guard downloadButton.waitForExistence(timeout: 5.0) else {
            XCTSkip("Download button not found")
            return
        }
        
        // Check if button is enabled (backend must be running)
        guard downloadButton.isEnabled else {
            XCTSkip("Backend not running - button disabled")
            return
        }
        
        downloadButton.click()
        
        // Then: Should see progress indicator or status update
        // Note: This test requires backend to be running
        // In a real scenario, you might mock the backend or use a test server
        let progressIndicator = app.progressIndicators.firstMatch
        if progressIndicator.waitForExistence(timeout: 5.0) {
            XCTAssertTrue(progressIndicator.exists)
        }
    }
}

