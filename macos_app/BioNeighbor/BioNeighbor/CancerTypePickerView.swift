//
//  CancerTypePickerView.swift
//  BioNeighbor
//
//  v2 disease-first browse: grid of cancer types. Tap a card to drill into
//  the subtype picker. Loaded from /cancer-research/v2/cancer-types.
//

import SwiftUI

struct CancerTypePickerView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var cancerTypes: [CancerType] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    private let columns = [
        GridItem(.adaptive(minimum: 220, maximum: 280), spacing: 16)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if isLoading {
                    ProgressView("Loading cancer types...")
                        .frame(maxWidth: .infinity, minHeight: 200)
                } else if let error = errorMessage {
                    errorView(error)
                } else {
                    LazyVGrid(columns: columns, spacing: 16) {
                        ForEach(groupedTypes, id: \.category) { group in
                            Section {
                                ForEach(group.types) { type in
                                    NavigationLink(value: type) {
                                        CancerTypeCard(type: type)
                                    }
                                    .buttonStyle(.plain)
                                }
                            } header: {
                                Text(group.category)
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.top, 8)
                            }
                        }
                    }
                }
            }
            .padding(20)
        }
        .navigationTitle("Cancer Research")
        .navigationDestination(for: CancerType.self) { type in
            CancerSubtypePickerView(cancerType: type)
        }
        .task {
            await loadCancerTypes()
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Browse by Cancer Type")
                .font(.title2)
                .fontWeight(.semibold)
            Text("Pick a cancer type to explore its subtypes, top treatments, and similar drugs.")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 32))
                .foregroundColor(.orange)
            Text("Couldn't load cancer types")
                .font(.headline)
            Text(message)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") {
                Task { await loadCancerTypes() }
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .padding()
    }

    private struct CategoryGroup {
        let category: String
        let types: [CancerType]
    }

    private var groupedTypes: [CategoryGroup] {
        let grouped = Dictionary(grouping: cancerTypes) { $0.category ?? "Other" }
        // Keep solid tumors first, hematologic next, others trailing.
        let order = ["Solid tumor", "Hematologic"]
        return grouped
            .map { CategoryGroup(category: $0.key, types: $0.value.sorted { ($0.sortOrder ?? 0) < ($1.sortOrder ?? 0) }) }
            .sorted { lhs, rhs in
                let li = order.firstIndex(of: lhs.category) ?? Int.max
                let ri = order.firstIndex(of: rhs.category) ?? Int.max
                if li != ri { return li < ri }
                return lhs.category < rhs.category
            }
    }

    @MainActor
    private func loadCancerTypes() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            cancerTypes = try await backendService.fetchCancerTypes()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct CancerTypeCard: View {
    let type: CancerType

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: type.icon ?? "circle.grid.cross.fill")
                    .font(.system(size: 24))
                    .foregroundColor(.accentColor)
                Spacer()
                if let count = type.subtypeCount {
                    Text("\(count) subtypes")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
            }

            Text(type.displayName ?? type.name)
                .font(.title3)
                .fontWeight(.semibold)
                .foregroundColor(.primary)

            if let description = type.description {
                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(3)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }
}
