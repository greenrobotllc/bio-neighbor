//
//  NavigationCoordinator.swift
//  BioNeighbor
//
//  Manages navigation state and breadcrumbs
//

import Foundation
import SwiftUI
import Combine

struct BreadcrumbItem: Identifiable, Hashable {
    let id: UUID
    let title: String
    let icon: String?
    let type: BreadcrumbType
    
    enum BreadcrumbType {
        case home
        case molecules
        case diseases
        case drugs
        case molecule
        case drug
        case disease  // Individual disease (not the category)
        case comparison
    }
    
    init(title: String, icon: String? = nil, type: BreadcrumbType) {
        self.id = UUID()
        self.title = title
        self.icon = icon
        self.type = type
    }
}

@MainActor
class NavigationCoordinator: ObservableObject {
    static let shared = NavigationCoordinator()
    
    @Published var breadcrumbPath: [BreadcrumbItem] = []
    
    private init() {
        // Initialize with home
        breadcrumbPath = [BreadcrumbItem(title: "Home", icon: "house", type: .home)]
    }
    
    func push(_ item: BreadcrumbItem) {
        #if DEBUG
        print("🔵 NavigationCoordinator.push: title='\(item.title)', type=\(item.type)")
        print("🔵 Current breadcrumbPath before push: \(breadcrumbPath.map { "\($0.title)(\($0.type))" }.joined(separator: " > "))")
        #endif
        
        // Check if an item with the same title and type already exists
        if let existingIndex = breadcrumbPath.firstIndex(where: { $0.title == item.title && $0.type == item.type }) {
            // If it exists, remove everything after it and keep it
            breadcrumbPath = Array(breadcrumbPath.prefix(existingIndex + 1))
            #if DEBUG
            print("🔵 Item already exists at index \(existingIndex), trimmed path")
            #endif
        } else {
            // If it's a category type (diseases, drugs, molecules), remove ALL other category types
            // AND all individual items (disease, drug, molecule) AND comparison breadcrumbs
            // This ensures only one category appears in breadcrumbs at a time, without individual items
            if item.type == .diseases || item.type == .drugs || item.type == .molecules {
                let removedCategories = breadcrumbPath.filter { 
                    $0.type == .diseases || $0.type == .drugs || $0.type == .molecules 
                }
                let removedIndividuals = breadcrumbPath.filter {
                    $0.type == .disease || $0.type == .drug || $0.type == .molecule
                }
                let removedComparisons = breadcrumbPath.filter {
                    $0.type == .comparison
                }
                breadcrumbPath = breadcrumbPath.filter { 
                    $0.type != .diseases && $0.type != .drugs && $0.type != .molecules &&
                    $0.type != .disease && $0.type != .drug && $0.type != .molecule &&
                    $0.type != .comparison
                }
                #if DEBUG
                print("🔵 Removed all category breadcrumbs: \(removedCategories.map { $0.title })")
                print("🔵 Removed all individual items: \(removedIndividuals.map { $0.title })")
                print("🔵 Removed comparison breadcrumbs: \(removedComparisons.map { $0.title })")
                #endif
            }
            // If it's an individual item type (disease, drug, molecule), remove any other items of the same type
            // AND remove all category breadcrumbs (diseases, drugs, molecules) since we're now viewing a specific item
            if item.type == .disease || item.type == .drug || item.type == .molecule {
                let removedIndividuals = breadcrumbPath.filter { $0.type == item.type }
                let removedCategories = breadcrumbPath.filter { 
                    $0.type == .diseases || $0.type == .drugs || $0.type == .molecules 
                }
                breadcrumbPath = breadcrumbPath.filter { 
                    $0.type != item.type &&
                    $0.type != .diseases && $0.type != .drugs && $0.type != .molecules
                }
                #if DEBUG
                print("🔵 Removed individual items: \(removedIndividuals.map { $0.title })")
                print("🔵 Removed category breadcrumbs: \(removedCategories.map { $0.title })")
                #endif
            }
            breadcrumbPath.append(item)
        }
        
        #if DEBUG
        print("🔵 Final breadcrumbPath: \(breadcrumbPath.map { "\($0.title)(\($0.type))" }.joined(separator: " > "))")
        #endif
        assert(breadcrumbPath.count > 0, "Breadcrumb path should never be empty")
    }
    
    func pop() {
        guard breadcrumbPath.count > 1 else { return }
        breadcrumbPath.removeLast()
    }
    
    func popToRoot() {
        guard let root = breadcrumbPath.first else { return }
        breadcrumbPath = [root]
    }
    
    func popTo(_ item: BreadcrumbItem) {
        guard let index = breadcrumbPath.firstIndex(where: { $0.id == item.id }) else { return }
        breadcrumbPath = Array(breadcrumbPath.prefix(index + 1))
    }
    
    func clear() {
        breadcrumbPath = [BreadcrumbItem(title: "Home", icon: "house", type: .home)]
    }
}

