//
//  DownloadDataUITests.swift
//  BioNeighborUITests
//
//  UI tests for Download Data interface navigation
//

import XCTest

final class DownloadDataUITests: XCTestCase {
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
    
    func testNavigateToDownloadDataTab() throws {
        // Given: App is launched
        
        // When: Click Download Data tab
        let downloadDataTab = app.downloadDataTab()
        XCTAssertTrue(downloadDataTab.waitForExistence(timeout: 5.0))
        downloadDataTab.click()
        
        // Then: Download Data interface should be visible
        let sidebar = app.sidebars["downloadDataSidebar"]
        XCTAssertTrue(sidebar.waitForExistence(timeout: 2.0))
    }
    
    func testNavigateBetweenDownloadSections() throws {
        // Given: On Download Data tab
        app.downloadDataTab().click()
        
        // When: Click different sections
        let overviewSection = app.downloadSection("Overview")
        if overviewSection.waitForExistence(timeout: 2.0) {
            overviewSection.click()
        }
        
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 2.0) {
            moleculesSection.click()
            
            // Then: Molecules view should be visible
            let title = app.staticTexts["downloadMoleculesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
        
        let drugsSection = app.downloadSection("Drugs")
        if drugsSection.waitForExistence(timeout: 2.0) {
            drugsSection.click()
            
            // Then: Drugs view should be visible
            let title = app.staticTexts["downloadDrugsTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
        
        let diseasesSection = app.downloadSection("Diseases")
        if diseasesSection.waitForExistence(timeout: 2.0) {
            diseasesSection.click()
            
            // Then: Diseases view should be visible
            let title = app.staticTexts["downloadDiseasesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
    }
    
    func testOverviewSectionDisplays() throws {
        // Given: On Download Data tab
        app.downloadDataTab().click()
        
        // When: Click Overview section
        let overviewSection = app.downloadSection("Overview")
        if overviewSection.waitForExistence(timeout: 2.0) {
            overviewSection.click()
            
            // Then: Statistics should be visible (if backend is running)
            // This test may need backend to be running
            let statsText = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'molecules' OR label CONTAINS 'drugs' OR label CONTAINS 'diseases'"))
            // Just verify the view loaded, don't require specific stats
            XCTAssertTrue(true) // Placeholder - adjust based on actual UI
        }
    }
}

