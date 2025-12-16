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
    @Published var navigationPath: NavigationPath = NavigationPath()
    
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
            guard prepareForAppend(item) else {
                #if DEBUG
                print("🔴 Invalid breadcrumb append for \(item.title) after \(breadcrumbPath.last?.title ?? "nil")")
                #endif
                return
            }
            breadcrumbPath.append(item)
        }
        
        #if DEBUG
        print("🔵 Final breadcrumbPath: \(breadcrumbPath.map { "\($0.title)(\($0.type))" }.joined(separator: " > "))")
        #endif
        assert(breadcrumbPath.count > 0, "Breadcrumb path should never be empty")
    }
    
    func popToBreadcrumb(_ item: BreadcrumbItem) {
        guard let targetIndex = breadcrumbPath.firstIndex(where: { $0.id == item.id }) else { return }
        #if DEBUG
        print("🟠 popToBreadcrumb -> target index \(targetIndex) for \(item.title)")
        #endif
        breadcrumbPath = Array(breadcrumbPath.prefix(targetIndex + 1))
        
        let targetPathCount = max(0, targetIndex - 1) // Home and category sit outside the NavigationPath
        while navigationPath.count > targetPathCount {
            navigationPath.removeLast()
        }
    }
    
    private func prepareForAppend(_ item: BreadcrumbItem) -> Bool {
        let allowedParents: [BreadcrumbItem.BreadcrumbType]
        switch item.type {
        case .home:
            return false
        case .molecules, .diseases, .drugs:
            allowedParents = [.home]
        case .molecule:
            allowedParents = [.molecules, .diseases, .disease, .drugs, .drug, .home]
        case .drug:
            allowedParents = [.drugs]
        case .disease:
            allowedParents = [.diseases]
        case .comparison:
            allowedParents = [.molecule, .drug, .disease]
        }
        
        // If current tail satisfies hierarchy, allow append
        if let last = breadcrumbPath.last, allowedParents.contains(last.type) {
            return true
        }
        
        // Try to trim back to the nearest allowed parent
        if let parentIndex = breadcrumbPath.lastIndex(where: { allowedParents.contains($0.type) }) {
            breadcrumbPath = Array(breadcrumbPath.prefix(parentIndex + 1))
            return true
        }
        
        // If the only allowed parent is Home, trim to root
        if allowedParents.contains(.home), let root = breadcrumbPath.first {
            breadcrumbPath = [root]
            return true
        }
        
        return false
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

