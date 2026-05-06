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

    // Drug-search (reverse lookup) state
    @State private var searchQuery = ""
    @State private var searchResults: [DrugSearchSubtypeMatch] = []
    @State private var uncachedSubtypeCount: Int = 0
    @State private var isSearching = false
    @State private var searchError: String?
    @FocusState private var searchFieldFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                searchField

                if !searchQuery.isEmpty {
                    drugSearchResults
                } else if isLoading {
                    ProgressView("Loading subtypes...")
                        .frame(maxWidth: .infinity, minHeight: 200)
                } else if let error = errorMessage {
                    errorView(error)
                } else if subtypes.isEmpty {
                    Text("No subtypes are curated yet for this cancer type.")
                        .appFont(.subheadline)
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
        // Debounced search — re-runs whenever the query changes. The 300ms
        // sleep means rapid typing only triggers one network call.
        .task(id: searchQuery) {
            await runDrugSearch()
        }
        .onReceive(NotificationCenter.default.publisher(for: .cancerFindDrug)) { _ in
            searchFieldFocused = true
        }
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)
            TextField("Find a drug across \(cancerType.displayName ?? cancerType.name) subtypes (⌘F)", text: $searchQuery)
                .textFieldStyle(.plain)
                .focused($searchFieldFocused)
            if isSearching {
                ProgressView().scaleEffect(0.6)
            }
            if !searchQuery.isEmpty {
                Button {
                    searchQuery = ""
                    searchFieldFocused = true
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(searchFieldFocused ? Color.accentColor : Color.secondary.opacity(0.2), lineWidth: 1)
        )
    }

    @ViewBuilder
    private var drugSearchResults: some View {
        if let err = searchError {
            VStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle").foregroundColor(.orange)
                Text(err).appFont(.caption).foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 80)
        } else if searchQuery.count < 2 {
            Text("Type at least 2 characters.")
                .appFont(.caption)
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else if searchResults.isEmpty && !isSearching {
            VStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 24))
                    .foregroundColor(.secondary)
                Text("No \(cancerType.displayName ?? cancerType.name) subtype has \u{201C}\(searchQuery)\u{201D} cached.")
                    .appFont(.subheadline)
                    .multilineTextAlignment(.center)
                if uncachedSubtypeCount > 0 {
                    Text("\(uncachedSubtypeCount) subtype\(uncachedSubtypeCount == 1 ? " has" : "s have") not been indexed yet — visit them to populate the search.")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 120)
            .padding()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Matched in \(searchResults.count) subtype\(searchResults.count == 1 ? "" : "s")")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                    if uncachedSubtypeCount > 0 {
                        Text("\(uncachedSubtypeCount) not yet indexed")
                            .appFont(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                LazyVStack(spacing: 12) {
                    ForEach(searchResults) { match in
                        // Prefer the fully-loaded subtype object so we can show
                        // markers/description; fall back to a minimal subtype
                        // synthesized from the match metadata so a row never
                        // disappears just because the subtypes list hasn't
                        // finished loading yet.
                        let subtype = subtypes.first(where: { $0.id == match.subtypeId })
                            ?? CancerSubtype(
                                id: match.subtypeId,
                                name: match.subtypeName,
                                shortName: match.subtypeShortName,
                                description: nil,
                                meshId: nil,
                                efoId: nil,
                                markers: nil,
                                chemblIndicationTerms: nil,
                                prevalenceNote: nil,
                                drugCount: nil,
                                cancerType: nil
                            )
                        NavigationLink(value: subtype) {
                            DrugSearchMatchRow(subtype: subtype, match: match)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    @MainActor
    private func runDrugSearch() async {
        let q = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        // Debounce: short sleep at the start of every key change. Task(id:)
        // cancels prior runs automatically when the id changes again.
        try? await Task.sleep(nanoseconds: 300_000_000)
        if Task.isCancelled { return }
        guard q.count >= 2 else {
            searchResults = []
            searchError = nil
            uncachedSubtypeCount = 0
            return
        }
        isSearching = true
        searchError = nil
        defer { isSearching = false }
        do {
            let response = try await backendService.searchDrugsInCancerType(typeId: cancerType.id, query: q)
            if Task.isCancelled { return }
            searchResults = response.subtypeMatches ?? []
            uncachedSubtypeCount = response.uncachedSubtypeCount ?? 0
        } catch is CancellationError {
            // Task(id:) cancellation is the normal "user is still typing"
            // path — silently abandon, don't flash an error banner.
            return
        } catch {
            if Task.isCancelled { return }
            searchError = error.localizedDescription
            searchResults = []
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Image(systemName: cancerType.icon ?? "circle.grid.cross.fill")
                    .font(.system(size: 22))
                    .foregroundColor(.accentColor)
                Text(cancerType.displayName ?? cancerType.name)
                    .appFont(.title2)
                    .fontWeight(.semibold)
                Spacer()
                if let mesh = cancerType.meshId {
                    Text("MeSH \(mesh)")
                        .appFont(.caption, monospaced: true)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
            }
            if let description = cancerType.description {
                Text(description)
                    .appFont(.subheadline)
                    .foregroundColor(.secondary)
            }
            Text("Pick a subtype to see top drugs (coming next) and similar molecules.")
                .appFont(.caption)
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
                .appFont(.headline)
            Text(message)
                .appFont(.caption)
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
                    .appFont(.headline)
                if let short = subtype.shortName, short != subtype.name {
                    Text(short)
                        .appFont(.caption, monospaced: true)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
                Spacer()
                if let count = subtype.drugCount, count > 0 {
                    Label("\(count) drugs", systemImage: "pills.fill")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
            }

            if let description = subtype.description {
                Text(description)
                    .appFont(.subheadline)
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
                    .appFont(.caption, monospaced: true)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.accentColor.opacity(0.12))
                    .foregroundColor(.accentColor)
                    .clipShape(Capsule())
            }
        }
    }
}

/// Row used in drug-search results — shows the subtype plus the actual drug
/// names that matched the query, so the user understands why each subtype
/// appeared in the result set.
private struct DrugSearchMatchRow: View {
    let subtype: CancerSubtype
    let match: DrugSearchSubtypeMatch

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(subtype.name)
                    .appFont(.headline)
                if let short = subtype.shortName, short != subtype.name {
                    Text(short)
                        .appFont(.caption, monospaced: true)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
            }

            FlowLayout(spacing: 6) {
                // `\.self` uses the full Hashable struct as identity — two
                // drugs with the same name but different chembl_id (or phase)
                // remain distinct. Avoids SwiftUI duplicate-id warnings and
                // chip rendering glitches when a subtype lists multiple
                // formulations of the "same" drug.
                ForEach(match.matchedDrugs, id: \.self) { drug in
                    HStack(spacing: 4) {
                        Image(systemName: "pills.fill")
                            .appFont(.caption2)
                        Text(drug.drugName)
                        if let phase = drug.maxPhase, phase == 4 {
                            Text("Approved")
                                .appFont(.caption2, weight: .bold)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.green.opacity(0.18))
                                .foregroundColor(.green)
                                .clipShape(Capsule())
                        } else if let phase = drug.maxPhase, phase > 0 {
                            Text("P\(phase)")
                                .appFont(.caption2, weight: .bold)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.blue.opacity(0.18))
                                .foregroundColor(.blue)
                                .clipShape(Capsule())
                        }
                    }
                    .appFont(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.accentColor.opacity(0.12))
                    .foregroundColor(.accentColor)
                    .clipShape(Capsule())
                }
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
                .stroke(Color.accentColor.opacity(0.35), lineWidth: 1)
        )
    }
}
