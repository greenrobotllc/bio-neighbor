//
//  BreadcrumbView.swift
//  BioNeighbor
//
//  Displays navigation breadcrumb path
//

import SwiftUI

struct BreadcrumbView: View {
    @ObservedObject var coordinator: NavigationCoordinator
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(coordinator.breadcrumbPath.enumerated()), id: \.element.id) { index, item in
                HStack(spacing: 4) {
                    if let icon = item.icon {
                        Image(systemName: icon)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    if index == coordinator.breadcrumbPath.count - 1 {
                        // Current item - not clickable
                        Text(item.title)
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(.primary)
                    } else {
                        // Previous items - clickable
                        Button(action: {
                            // Pop to the selected item
                            let targetIndex = coordinator.breadcrumbPath.firstIndex(where: { $0.id == item.id }) ?? 0
                            let popsNeeded = coordinator.breadcrumbPath.count - targetIndex - 1
                            
                            // Pop the coordinator state to the target
                            for _ in 0..<popsNeeded {
                                coordinator.pop()
                            }
                            // Dismiss once (or navigate programmatically via NavigationPath)
                            dismiss()
                        }) {
                            Text(item.title)
                                .font(.caption)
                                .foregroundColor(.blue)
                        }
                        .buttonStyle(.plain)
                    }
                    
                    // Chevron separator (not after last item)
                    if index < coordinator.breadcrumbPath.count - 1 {
                        Image(systemName: "chevron.right")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 2)
                    }
                }
            }
            
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(NSColor.controlBackgroundColor))
    }
}

#Preview {
    let coordinator = NavigationCoordinator.shared
    coordinator.breadcrumbPath = [
        BreadcrumbItem(title: "Home", icon: "house", type: .home),
        BreadcrumbItem(title: "Molecules", icon: "atom", type: .molecules),
        BreadcrumbItem(title: "Aspirin", icon: "atom", type: .molecule)
    ]
    return BreadcrumbView(coordinator: coordinator)
        .frame(width: 600)
}

