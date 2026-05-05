//
//  DrugsView.swift
//  BioNeighbor
//
//  View for browsing all drugs
//

import SwiftUI

struct DrugsView: View {
    @StateObject private var backendService = BackendService.shared
    @StateObject private var navCoordinator = NavigationCoordinator.shared
    @State private var drugs: [Drug] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""

    // Live drug search — populated from /search/drugs (local + ChEMBL fallback)
    // when searchText is non-empty. Nil when no search is active so we fall
    // through to the full loaded `drugs` list.
    @State private var liveResults: [DrugSearchResult]? = nil
    @State private var isSearching = false
    @State private var lastChemblUsed = false
    
    var body: some View {
        NavigationSplitView {
            // Sidebar with search
            VStack(alignment: .leading, spacing: 16) {
                Text("Drugs")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                
                HStack(spacing: 6) {
                    TextField("Search drugs...", text: $searchText)
                        .textFieldStyle(.roundedBorder)
                    if isSearching {
                        ProgressView().scaleEffect(0.6)
                    }
                }
                if lastChemblUsed && !searchText.isEmpty {
                    Text("Includes live ChEMBL results")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                
                if !backendService.isBackendRunning {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("⚠️ Backend not running")
                            .font(.headline)
                            .foregroundColor(.orange)
                        
                        Text("The Python backend needs to be started.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Button("Start Backend") {
                            do {
                                try backendService.startBackend()
                                // Give backend time to start, then load
                                DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                                    loadDrugs()
                                }
                            } catch {
                                errorMessage = error.localizedDescription
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                }
                
                if isLoading {
                    ProgressView("Loading drugs...")
                        .frame(maxWidth: .infinity)
                } else {
                    let count = liveResults?.count ?? drugs.count
                    Text("\(count) drug\(count == 1 ? "" : "s")")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                
                if let error = errorMessage {
                    Text("Error: \(error)")
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
                
                Spacer()
            }
            .padding()
            .frame(minWidth: 250)
        } detail: {
            NavigationStack(path: $navCoordinator.navigationPath) {
                // Main content
                Group {
                    ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Breadcrumb
                        BreadcrumbView(coordinator: navCoordinator)
                        
                        Divider()
                        
                        if isLoading {
                    ProgressView("Loading drugs...")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                } else if let liveResults = liveResults {
                    // Search is active — render live results (local + ChEMBL).
                    if liveResults.isEmpty && !isSearching {
                        VStack(spacing: 16) {
                            Image(systemName: "pills")
                                .font(.system(size: 60))
                                .foregroundColor(.secondary)
                            Text("No drugs match your search")
                                .font(.headline)
                                .foregroundColor(.secondary)
                            Text("Tried local DB \(lastChemblUsed ? "and ChEMBL" : "")— nothing found.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    } else {
                        LazyVGrid(columns: [
                            GridItem(.adaptive(minimum: 300), spacing: 16)
                        ], spacing: 16) {
                            ForEach(liveResults) { hit in
                                LiveDrugSearchCard(hit: hit, onTap: { openLiveResult(hit) })
                            }
                        }
                        .padding()
                    }
                } else if drugs.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "pills")
                            .font(.system(size: 60))
                            .foregroundColor(.secondary)
                        Text("No drugs found")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        Text("Drug data may not be loaded yet. Try downloading drug information from the Download Data tab.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                } else {
                    LazyVGrid(columns: [
                        GridItem(.adaptive(minimum: 300), spacing: 16)
                    ], spacing: 16) {
                        ForEach(drugs) { drug in
                            NavigationLink(value: drug) {
                                DrugCard(drug: drug)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding()
                }
                }
                .padding()
                    }
                }
            .navigationTitle("All Drugs")
            .navigationDestination(for: Drug.self) { drug in
                DrugDetailView(drug: drug)
            }
            .navigationDestination(for: Molecule.self) { molecule in
                MoleculeDetailView(molecule: molecule)
            }
            .onAppear {
                // Push "Drugs" breadcrumb when view appears
                print("🟡 DrugsView onAppear - pushing 'Drugs' breadcrumb")
                navCoordinator.push(BreadcrumbItem(
                    title: "Drugs",
                    icon: "pills",
                    type: .drugs
                ))
                loadDrugs()
            }
        }
        }
        // Debounced live search. .task(id:) cancels prior runs when the
        // search text changes, so rapid typing only triggers one ChEMBL hit.
        .task(id: searchText) {
            await runLiveSearch()
        }
    }
    
    @MainActor
    private func runLiveSearch() async {
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        // 300ms debounce — prior task is auto-cancelled by .task(id:) when
        // searchText changes again.
        try? await Task.sleep(nanoseconds: 300_000_000)
        if Task.isCancelled { return }

        if q.isEmpty {
            liveResults = nil
            lastChemblUsed = false
            return
        }
        guard backendService.isBackendRunning else { return }

        isSearching = true
        defer { isSearching = false }
        do {
            let response = try await backendService.searchDrugsLive(query: q, limit: 30)
            if Task.isCancelled { return }
            liveResults = response.results
            lastChemblUsed = response.chemblUsed
        } catch {
            // Surface the error inline but keep showing whatever we had.
            if Task.isCancelled { return }
            errorMessage = "Search failed: \(error.localizedDescription)"
        }
    }

    @MainActor
    private func openLiveResult(_ hit: DrugSearchResult) {
        // If we know the local drug id, use full Drug navigation. Otherwise
        // there's nothing to navigate to yet (extremely rare — write-through
        // always populates an id).
        guard let drugId = hit.id else { return }
        Task {
            do {
                let drug = try await backendService.getDrug(id: drugId)
                await MainActor.run {
                    navCoordinator.push(BreadcrumbItem(
                        title: drug.name,
                        icon: "pills",
                        type: .drug
                    ))
                    navCoordinator.navigationPath.append(drug)
                }
            } catch {
                errorMessage = "Couldn't open \(hit.name): \(error.localizedDescription)"
            }
        }
    }

    private func loadDrugs() {
        guard backendService.isBackendRunning else { return }
        
        isLoading = true
        errorMessage = nil
        
        Task {
            do {
                print("🟡 Loading drugs from backend...")
                let loadedDrugs = try await backendService.getAllDrugs()
                print("🟡 Successfully loaded \(loadedDrugs.count) drugs")
                await MainActor.run {
                    drugs = loadedDrugs
                    isLoading = false
                    errorMessage = nil
                }
            } catch {
                print("🔴 Error loading drugs: \(error.localizedDescription)")
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

/// Card shown in the Drugs tab when a live search is active. Looks like
/// DrugCard but renders from the lightweight `DrugSearchResult` shape and
/// adds a small "ChEMBL" chip on rows freshly fetched from the live API.
private struct LiveDrugSearchCard: View {
    let hit: DrugSearchResult
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline) {
                    Text(hit.name)
                        .font(.headline)
                        .foregroundColor(.primary)
                        .lineLimit(2)
                    Spacer()
                    if hit.source == "chembl" {
                        Label("ChEMBL", systemImage: "checkmark.seal")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.12))
                            .foregroundColor(.accentColor)
                            .clipShape(Capsule())
                    }
                    phaseBadge
                }

                if let chembl = hit.chemblId {
                    Text(chembl)
                        .font(.caption.monospaced())
                        .foregroundColor(.secondary)
                }
                if let generic = hit.genericName, generic != hit.name {
                    Text(generic)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
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
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var phaseBadge: some View {
        if let phase = hit.maxPhase, phase > 0 {
            let label = phase == 4 ? "Approved" : "Phase \(phase)"
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
}

#Preview {
    DrugsView()
}

