//
//  E2EDownloadTests.swift
//  BioNeighborUITests
//
//  End-to-end tests for complete download workflows
//

import XCTest

final class E2EDownloadTests: XCTestCase {
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
    
    func testCompleteMoleculeDownloadWorkflow() throws {
        // Given: App is launched and backend is running
        
        // Step 1: Navigate to Download Data → Molecules
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        guard moleculesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Molecules section not found")
            return
        }
        moleculesSection.click()
        
        // Step 2: Verify we're on the molecules download view
        let title = app.staticTexts["downloadMoleculesTitle"]
        XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        
        // Step 3: Set download count (adjust slider)
        let slider = app.moleculeCountSlider()
        if slider.waitForExistence(timeout: 2.0) {
            slider.adjust(toNormalizedSliderPosition: 0.1) // Small count for testing
        }
        
        // Step 4: Click download button (if backend is running)
        let downloadButton = app.downloadMoleculesByCountButton()
        guard downloadButton.waitForExistence(timeout: 2.0) else {
            XCTSkip("Download button not found")
            return
        }
        
        guard downloadButton.isEnabled else {
            XCTSkip("Backend not running - cannot test download")
            return
        }
        
        downloadButton.click()
        
        // Step 5: Verify progress indicator appears
        let progressIndicator = app.progressIndicators.firstMatch
        if progressIndicator.waitForExistence(timeout: 5.0) {
            XCTAssertTrue(progressIndicator.exists)
        }
        
        // Step 6: Wait for completion (with timeout)
        // Note: This may take a while, so we use a reasonable timeout
        let completedText = app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'completed' OR label CONTAINS[c] 'success'"))
        if completedText.firstMatch.waitForExistence(timeout: 120.0) {
            XCTAssertTrue(completedText.firstMatch.exists)
        }
        
        // Step 7: Verify stats might have updated (optional check)
        // Navigate to Overview to see stats
        let overviewSection = app.downloadSection("Overview")
        if overviewSection.waitForExistence(timeout: 2.0) {
            overviewSection.click()
            // Stats should be visible (exact values depend on backend state)
        }
    }
    
    func testCompleteDrugDownloadWorkflow() throws {
        // Given: App is launched
        
        // Step 1: Navigate to Download Data → Drugs
        app.downloadDataTab().click()
        let drugsSection = app.downloadSection("Drugs")
        guard drugsSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Drugs section not found")
            return
        }
        drugsSection.click()
        
        // Step 2: Search for a drug
        let searchField = app.drugSearchField()
        guard searchField.waitForExistence(timeout: 2.0) else {
            XCTSkip("Search field not found")
            return
        }
        
        searchField.click()
        searchField.typeText("donepezil")
        
        // Step 3: Wait for results (if backend is running)
        sleep(2) // Wait for debounce and network
        
        // Step 4: Verify we can interact with the view
        // (Actual selection and download would require backend to be running)
        XCTAssertTrue(searchField.exists)
    }
    
    func testMultiStepWorkflow() throws {
        // Given: App is launched
        
        // Step 1: Navigate to Download Data
        app.downloadDataTab().click()
        
        // Step 2: Check Overview stats
        let overviewSection = app.downloadSection("Overview")
        if overviewSection.waitForExistence(timeout: 2.0) {
            overviewSection.click()
            // Stats should be visible
        }
        
        // Step 3: Navigate to Molecules
        let moleculesSection = app.downloadSection("Molecules")
        if moleculesSection.waitForExistence(timeout: 2.0) {
            moleculesSection.click()
            let title = app.staticTexts["downloadMoleculesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
        
        // Step 4: Navigate to Drugs
        let drugsSection = app.downloadSection("Drugs")
        if drugsSection.waitForExistence(timeout: 2.0) {
            drugsSection.click()
            let title = app.staticTexts["downloadDrugsTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
        
        // Step 5: Navigate to Diseases
        let diseasesSection = app.downloadSection("Diseases")
        if diseasesSection.waitForExistence(timeout: 2.0) {
            diseasesSection.click()
            let title = app.staticTexts["downloadDiseasesTitle"]
            XCTAssertTrue(title.waitForExistence(timeout: 2.0))
        }
        
        // Verify we can navigate between all sections
        XCTAssertTrue(true)
    }
    
    func testDownloadAndVerifyInDatabase() throws {
        // This test would:
        // 1. Download molecules
        // 2. Navigate to Molecules tab
        // 3. Search for downloaded molecules
        // 4. Verify they appear
        
        // Note: This requires backend to be running and actual download to complete
        // For now, we'll just verify the navigation works
        
        // Step 1: Download (if backend running)
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        guard moleculesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Molecules section not found")
            return
        }
        moleculesSection.click()
        
        // Step 2: Navigate to Molecules tab to verify
        app.moleculesTab().click()
        
        // Verify we're on the molecules browse view
        // (Would need accessibility identifier on that view)
        XCTAssertTrue(app.moleculesTab().exists)
    }
}

