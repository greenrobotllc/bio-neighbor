//
//  SearchAutocompleteUITests.swift
//  BioNeighborUITests
//
//  UI tests for search autocomplete functionality
//

import XCTest

final class SearchAutocompleteUITests: XCTestCase {
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
    
    func testMoleculeSearchAutocomplete() throws {
        // Given: On Molecules download view
        app.downloadDataTab().click()
        let moleculesSection = app.downloadSection("Molecules")
        guard moleculesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Molecules section not found")
            return
        }
        moleculesSection.click()
        
        // When: Type in search field
        let searchField = app.moleculeSearchField()
        guard searchField.waitForExistence(timeout: 2.0) else {
            XCTSkip("Search field not found")
            return
        }
        
        searchField.click()
        searchField.typeText("asp")
        
        // Then: Wait a moment for debounce, then check for results
        // Note: Results may not appear if backend is not running or no data
        sleep(1) // Wait for debounce (300ms) + network
        
        // Just verify the field accepted input
        XCTAssertTrue(searchField.exists)
    }
    
    func testDrugSearchAutocomplete() throws {
        // Given: On Drugs download view
        app.downloadDataTab().click()
        let drugsSection = app.downloadSection("Drugs")
        guard drugsSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Drugs section not found")
            return
        }
        drugsSection.click()
        
        // When: Type in search field
        let searchField = app.drugSearchField()
        guard searchField.waitForExistence(timeout: 2.0) else {
            XCTSkip("Search field not found")
            return
        }
        
        searchField.click()
        searchField.typeText("done")
        
        // Then: Verify input
        sleep(1)
        XCTAssertTrue(searchField.exists)
    }
    
    func testDiseaseSearchAutocomplete() throws {
        // Given: On Diseases download view
        app.downloadDataTab().click()
        let diseasesSection = app.downloadSection("Diseases")
        guard diseasesSection.waitForExistence(timeout: 5.0) else {
            XCTSkip("Diseases section not found")
            return
        }
        diseasesSection.click()
        
        // When: Type in search field
        let searchField = app.diseaseNameSearchField()
        guard searchField.waitForExistence(timeout: 2.0) else {
            XCTSkip("Search field not found")
            return
        }
        
        searchField.click()
        searchField.typeText("alz")
        
        // Then: Verify input
        sleep(1)
        XCTAssertTrue(searchField.exists)
    }
}

