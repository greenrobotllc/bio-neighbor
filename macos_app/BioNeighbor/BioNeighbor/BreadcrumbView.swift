//
//  BreadcrumbView.swift
//  BioNeighbor
//
//  Breadcrumb navigation components
//

import SwiftUI

// Original BreadcrumbView for use with NavigationCoordinator
struct BreadcrumbView: View {
    @ObservedObject var coordinator: NavigationCoordinator
    
    var body: some View {
        HStack(spacing: 8) {
            ForEach(coordinator.breadcrumbPath) { item in
                if item.id != coordinator.breadcrumbPath.first?.id {
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 4)
                }
                
                Button(action: {
                    coordinator.popToBreadcrumb(item)
                }) {
                    HStack(spacing: 4) {
                        if let icon = item.icon {
                            Image(systemName: icon)
                                .font(.caption2)
                        }
                        Text(item.title)
                            .font(.caption)
                    }
                    .foregroundColor(.blue)
                }
                .buttonStyle(.plain)
            }
            
            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(NSColor.controlBackgroundColor))
    }
}

// Cancer Research workspace breadcrumb component
struct CancerBreadcrumbItem: Identifiable {
    let id = UUID()
    let title: String
    let isClickable: Bool
    let action: (() -> Void)?
    
    init(_ title: String, isClickable: Bool = false, action: (() -> Void)? = nil) {
        self.title = title
        self.isClickable = isClickable
        self.action = action
    }
}

struct CancerBreadcrumbView: View {
    let items: [CancerBreadcrumbItem]
    
    var body: some View {
        HStack(spacing: 8) {
            ForEach(items) { item in
                if item.id != items.first?.id {
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 4)
                }
                
                if item.isClickable {
                    Button(action: {
                        item.action?()
                    }) {
                        Text(item.title)
                            .font(.caption)
                            .foregroundColor(.blue)
                    }
                    .buttonStyle(.plain)
                } else {
                    Text(item.title)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(NSColor.controlBackgroundColor))
    }
}
