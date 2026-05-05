//
//  SubtypeDrugsView.swift
//  BioNeighbor
//
//  v2 disease-first browse: top drugs for a chosen cancer subtype. The list
//  is computed by the backend aggregator (ChEMBL drug_indication + cancer
//  mechanism ligands + multi_api enrichment) and cached for 30 days. A toolbar
//  Refresh button forces a fresh ChEMBL pull.
//

import SwiftUI

struct SubtypeDrugsView: View {
    let subtype: CancerSubtype

    @StateObject private var backendService = BackendService.shared
    @State private var drugs: [SubtypeTopDrug] = []
    @State private var mechanisms: [SubtypeMechanism] = []
    @State private var openMechanism: Mechanism?
    @State private var isLoading = false
    @State private var isRefreshing = false
    @State private var errorMessage: String?
    @State private var searchQuery = ""
    @FocusState private var searchFieldFocused: Bool

    private let columns = [
        GridItem(.adaptive(minimum: 220, maximum: 280), spacing: 12)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if !drugs.isEmpty {
                    searchField
                }

                if !mechanisms.isEmpty {
                    relatedMechanismsSection
                }

                if isLoading && drugs.isEmpty {
                    ProgressView("Loading top drugs…")
                        .frame(maxWidth: .infinity, minHeight: 200)
                } else if let error = errorMessage {
                    errorView(error)
                } else if drugs.isEmpty {
                    emptyView
                } else if filteredDrugs.isEmpty {
                    noMatchView
                } else {
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(filteredDrugs) { drug in
                            NavigationLink(value: drug) {
                                DrugTile(drug: drug)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(20)
        }
        .navigationTitle(subtype.shortName ?? subtype.name)
        .navigationDestination(for: SubtypeTopDrug.self) { drug in
            CancerDrugDetailView(drug: drug)
        }
        .sheet(item: $openMechanism) { mechanism in
            VStack(spacing: 0) {
                HStack {
                    Text(mechanism.name)
                        .font(.headline)
                    Spacer()
                    Button("Done") { openMechanism = nil }
                        .keyboardShortcut(.cancelAction)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                Divider()
                MechanismWorkspaceView(mechanism: mechanism)
            }
            .frame(minWidth: 900, minHeight: 600)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await refreshFromChEMBL() }
                } label: {
                    if isRefreshing {
                        ProgressView().scaleEffect(0.7)
                    } else {
                        Label("Refresh from ChEMBL", systemImage: "arrow.clockwise")
                    }
                }
                .disabled(isRefreshing)
                .help("Pulls fresh drug indications from the live ChEMBL API. Can take 30+ seconds.")
            }
        }
        .task {
            await loadDrugs()
            await loadMechanisms()
        }
        .onReceive(NotificationCenter.default.publisher(for: .cancerFindDrug)) { _ in
            searchFieldFocused = true
        }
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)
            TextField("Filter drugs by name or ChEMBL ID (⌘F)", text: $searchQuery)
                .textFieldStyle(.plain)
                .focused($searchFieldFocused)
                .onSubmit {
                    searchFieldFocused = false
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
            if !searchQuery.isEmpty {
                Text("\(filteredDrugs.count) of \(drugs.count)")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.leading, 4)
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

    private var noMatchView: some View {
        VStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 24))
                .foregroundColor(.secondary)
            Text("No drugs match \u{201C}\(searchQuery)\u{201D}")
                .font(.subheadline)
            Button("Clear filter") { searchQuery = "" }
                .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, minHeight: 120)
    }

    private var filteredDrugs: [SubtypeTopDrug] {
        let q = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return drugs }
        return drugs.filter { drug in
            drug.drugName.lowercased().contains(q) ||
            (drug.chemblId?.lowercased().contains(q) ?? false)
        }
    }

    private var relatedMechanismsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Related Mechanisms")
                .font(.headline)
            Text("Tap to open the full mechanism workspace (targets, ligands, assays, hypotheses).")
                .font(.caption)
                .foregroundColor(.secondary)
            FlowLayout(spacing: 8) {
                ForEach(mechanisms) { mechanism in
                    Button {
                        Task { await openMechanismWorkspace(mechanism.mechanismId) }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "atom")
                            Text(mechanism.mechanismName)
                            if let activity = mechanism.activityLevel {
                                Text(activity)
                                    .font(.caption2)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(activityColor(activity).opacity(0.18))
                                    .foregroundColor(activityColor(activity))
                                    .clipShape(Capsule())
                            }
                        }
                        .font(.caption)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.accentColor.opacity(0.10))
                        .foregroundColor(.accentColor)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(NSColor.controlBackgroundColor).opacity(0.6))
        )
    }

    private func activityColor(_ activity: String) -> Color {
        switch activity.lowercased() {
        case "high": return .red
        case "moderate": return .orange
        case "low": return .gray
        default: return .secondary
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(subtype.name)
                    .font(.title2)
                    .fontWeight(.semibold)
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
                if !drugs.isEmpty {
                    Text("\(drugs.count) drug\(drugs.count == 1 ? "" : "s")")
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

            Text("Drugs ranked by clinical phase (max_phase) and source agreement. Pulled from ChEMBL drug_indication, related mechanism ligands, and openFDA/ClinicalTrials.")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.top, 2)
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "pills")
                .font(.system(size: 36))
                .foregroundColor(.secondary)
            Text("No drugs cached yet")
                .font(.headline)
            Text("Tap “Refresh from ChEMBL” to pull the latest indications for this subtype.")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button {
                Task { await refreshFromChEMBL() }
            } label: {
                Label("Refresh from ChEMBL", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
            .disabled(isRefreshing)
        }
        .frame(maxWidth: .infinity, minHeight: 220)
        .padding()
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 28))
                .foregroundColor(.orange)
            Text("Couldn't load drugs")
                .font(.headline)
            Text(message)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") {
                Task { await loadDrugs() }
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    @MainActor
    private func loadDrugs() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            drugs = try await backendService.fetchSubtypeTopDrugs(subtypeId: subtype.id, limit: 30)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    private func loadMechanisms() async {
        do {
            mechanisms = try await backendService.fetchSubtypeMechanisms(subtypeId: subtype.id)
        } catch {
            // Best-effort; the chips just won't render.
            mechanisms = []
        }
    }

    @MainActor
    private func openMechanismWorkspace(_ mechanismId: Int) async {
        do {
            openMechanism = try await backendService.fetchMechanism(id: mechanismId)
        } catch {
            errorMessage = "Couldn't open mechanism: \(error.localizedDescription)"
        }
    }

    @MainActor
    private func refreshFromChEMBL() async {
        isRefreshing = true
        errorMessage = nil
        defer { isRefreshing = false }
        do {
            _ = try await backendService.refreshSubtypeDrugs(subtypeId: subtype.id)
            drugs = try await backendService.fetchSubtypeTopDrugs(subtypeId: subtype.id, limit: 30)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct DrugTile: View {
    let drug: SubtypeTopDrug

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(drug.drugName)
                    .font(.headline)
                    .lineLimit(2)
                Spacer()
                phaseBadge
            }

            if let chembl = drug.chemblId {
                Text(chembl)
                    .font(.caption.monospaced())
                    .foregroundColor(.secondary)
            }

            HStack(spacing: 8) {
                if let source = drug.source {
                    Label(prettySourceLabel(source), systemImage: sourceIcon(source))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if let count = drug.sourceCount, count > 1 {
                    Text("\(count) sources")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
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
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    @ViewBuilder
    private var phaseBadge: some View {
        if let phase = drug.maxPhase, phase > 0 {
            let label: String = {
                switch phase {
                case 4: return "Approved"
                case 3: return "Phase 3"
                case 2: return "Phase 2"
                case 1: return "Phase 1"
                default: return "Phase \(phase)"
                }
            }()
            let color: Color = {
                switch phase {
                case 4: return .green
                case 3: return .blue
                case 2: return .orange
                case 1: return .yellow
                default: return .gray
                }
            }()
            Text(label)
                .font(.caption2.bold())
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .clipShape(Capsule())
        }
    }

    private func prettySourceLabel(_ source: String) -> String {
        switch source {
        case "chembl_indication": return "ChEMBL"
        case "cancer_mechanism": return "Mechanism"
        default: return source.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func sourceIcon(_ source: String) -> String {
        switch source {
        case "chembl_indication": return "checkmark.seal.fill"
        case "cancer_mechanism": return "atom"
        default: return "circle.fill"
        }
    }
}
