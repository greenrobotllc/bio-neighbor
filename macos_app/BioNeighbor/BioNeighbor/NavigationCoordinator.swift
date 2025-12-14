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
        case comparison
    }
    
    init(title: String, icon: String? = nil, type: BreadcrumbType) {
        self.id = UUID()
        self.title = title
        self.icon = icon
        self.type = type
    }
}

class NavigationCoordinator: ObservableObject {
    static let shared = NavigationCoordinator()
    
    @Published var breadcrumbPath: [BreadcrumbItem] = []
    
    private init() {
        // Initialize with home
        breadcrumbPath = [BreadcrumbItem(title: "Home", icon: "house", type: .home)]
    }
    
    func push(_ item: BreadcrumbItem) {
        // Remove any items after the current position if we're not at the end
        // This handles the case where user navigates back then forward
        if let currentIndex = breadcrumbPath.firstIndex(where: { $0.id == item.id }) {
            breadcrumbPath = Array(breadcrumbPath.prefix(currentIndex + 1))
        } else {
            breadcrumbPath.append(item)
        }
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

