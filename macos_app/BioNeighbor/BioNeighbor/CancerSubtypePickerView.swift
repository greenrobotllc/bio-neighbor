//
//  CancerSubtypePickerView.swift
//  BioNeighbor
//
//  v2 disease-first browse: list of subtypes for a chosen cancer type.
//  Each row shows molecular-marker chips (HER2+, BRCA-mut, etc.) parsed from
//  the markers JSON column, plus a drug-count badge once Phase 2 is wired.
//

import SwiftUI

struct CancerSubtypePickerView: View {
    let cancerType: CancerType

    @StateObject private var backendService = BackendService.shared
    @State private var subtypes: [CancerSubtype] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if isLoading {
                    ProgressView("Loading subtypes...")
                        .frame(maxWidth: .infinity, minHeight: 200)
                } else if let error = errorMessage {
                    errorView(error)
                } else if subtypes.isEmpty {
                    Text("No subtypes are curated yet for this cancer type.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 100)
                } else {
                    LazyVStack(spacing: 12) {
                        ForEach(subtypes) { subtype in
                            NavigationLink(value: subtype) {
                                SubtypeRow(subtype: subtype)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(20)
        }
        .navigationTitle(cancerType.displayName ?? cancerType.name)
        .navigationDestination(for: CancerSubtype.self) { subtype in
            SubtypeDrugsView(subtype: subtype)
        }
        .task {
            await loadSubtypes()
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Image(systemName: cancerType.icon ?? "circle.grid.cross.fill")
                    .font(.system(size: 22))
                    .foregroundColor(.accentColor)
                Text(cancerType.displayName ?? cancerType.name)
                    .font(.title2)
                    .fontWeight(.semibold)
                Spacer()
                if let mesh = cancerType.meshId {
                    Text("MeSH \(mesh)")
                        .font(.caption.monospaced())
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
            }
            if let description = cancerType.description {
                Text(description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            Text("Pick a subtype to see top drugs (coming next) and similar molecules.")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.top, 4)
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 28))
                .foregroundColor(.orange)
            Text("Couldn't load subtypes")
                .font(.headline)
            Text(message)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") {
                Task { await loadSubtypes() }
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    @MainActor
    private func loadSubtypes() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            subtypes = try await backendService.fetchSubtypes(forCancerTypeId: cancerType.id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct SubtypeRow: View {
    let subtype: CancerSubtype

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(subtype.name)
                    .font(.headline)
                if let short = subtype.shortName, short != subtype.name {
                    Text(short)
                        .font(.caption.monospaced())
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
                Spacer()
                if let count = subtype.drugCount, count > 0 {
                    Label("\(count) drugs", systemImage: "pills.fill")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            if let description = subtype.description {
                Text(description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let markers = subtype.markers, !markers.isEmpty {
                MarkerChipsView(markers: markers)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }
}

private struct MarkerChipsView: View {
    let markers: [String]

    // Reuses FlowLayout defined in TargetDetailView.swift so chips wrap on narrow widths.
    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(markers, id: \.self) { marker in
                Text(marker)
                    .font(.caption.monospaced())
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.accentColor.opacity(0.12))
                    .foregroundColor(.accentColor)
                    .clipShape(Capsule())
            }
        }
    }
}
