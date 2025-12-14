//
//  UIElementHelpers.swift
//  BioNeighborUITests
//
//  Helper methods for finding UI elements in tests
//

import XCTest

extension XCUIApplication {
    func downloadDataTab() -> XCUIElement {
        return tabs["Download Data"]
    }
    
    func moleculesTab() -> XCUIElement {
        return tabs["Molecules"]
    }
    
    func drugsTab() -> XCUIElement {
        return tabs["Drugs"]
    }
    
    func diseasesTab() -> XCUIElement {
        return tabs["Diseases"]
    }
    
    func downloadSection(_ section: String) -> XCUIElement {
        return sidebars.buttons["downloadSection_\(section)"]
    }
    
    func downloadMoleculesByCountButton() -> XCUIElement {
        return buttons["downloadMoleculesByCountButton"]
    }
    
    func downloadMoleculesByNameButton() -> XCUIElement {
        return buttons["downloadMoleculesByNameButton"]
    }
    
    func downloadDrugsByNameButton() -> XCUIElement {
        return buttons["downloadDrugsByNameButton"]
    }
    
    func downloadDrugsByDiseaseButton() -> XCUIElement {
        return buttons["downloadDrugsByDiseaseButton"]
    }
    
    func downloadDiseasesByNameButton() -> XCUIElement {
        return buttons["downloadDiseasesByNameButton"]
    }
    
    func downloadDiseasesBulkButton() -> XCUIElement {
        return buttons["downloadDiseasesBulkButton"]
    }
    
    func moleculeSearchField() -> XCUIElement {
        return textFields["moleculeSearchField"]
    }
    
    func drugSearchField() -> XCUIElement {
        return textFields["drugSearchField"]
    }
    
    func diseaseSearchField() -> XCUIElement {
        return textFields["diseaseSearchField"]
    }
    
    func moleculeCountSlider() -> XCUIElement {
        return sliders["moleculeCountSlider"]
    }
    
    func waitForElement(_ element: XCUIElement, timeout: TimeInterval = 10.0) -> Bool {
        return element.waitForExistence(timeout: timeout)
    }
    
    func waitForDownloadCompletion(timeout: TimeInterval = 60.0) -> Bool {
        let completedText = staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'completed'"))
        return completedText.firstMatch.waitForExistence(timeout: timeout)
    }
    
    func waitForDownloadProgress(timeout: TimeInterval = 10.0) -> Bool {
        let progressText = staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'progress' OR label CONTAINS[c] 'downloading'"))
        return progressText.firstMatch.waitForExistence(timeout: timeout)
    }
}

