//
//  BrowseView.swift
//  BioNeighbor
//
//  Main browsing interface for exploring molecules
//

import SwiftUI

struct BrowseView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var molecules: [MoleculeBasic] = []
    @State private var selectedMolecule: MoleculeBasic?
    @State private var similarMolecules: [Molecule] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""
    @State private var currentPage = 1
    @State private var pagination: Pagination?
    @State private var isLoadingSimilar = false
    
    var body: some View {
        NavigationSplitView {
            // Sidebar with controls
            VStack(alignment: .leading, spacing: 20) {
                Text("BioNeighbor")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 10)
                
                Text("Explore molecules in the database")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Divider()
                
                // Search bar
                VStack(alignment: .leading, spacing: 8) {
                    Text("Search")
                        .font(.headline)
                    
                    HStack {
                        TextField("Name, ChEMBL ID, or SMILES", text: $searchText)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit {
                                performSearch()
                            }
                        
                        Button(action: performSearch) {
                            Image(systemName: "magnifyingglass")
                        }
                        .buttonStyle(.bordered)
                    }
                    
                    Text("Search by molecule name, ChEMBL ID, or SMILES string")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                // Controls
                HStack {
                    Button("Random Sample") {
                        loadRandomMolecules()
                    }
                    .buttonStyle(.bordered)
                    .disabled(isLoading || !backendService.isBackendRunning)
                    
                    Spacer()
                }
                
                // Pagination
                if let pagination = pagination {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Page \(pagination.page) of \(pagination.totalPages)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        HStack {
                            Button(action: previousPage) {
                                Image(systemName: "chevron.left")
                            }
                            .buttonStyle(.bordered)
                            .disabled(currentPage <= 1 || isLoading)
                            
                            Spacer()
                            
                            Button(action: nextPage) {
                                Image(systemName: "chevron.right")
                            }
                            .buttonStyle(.bordered)
                            .disabled(currentPage >= pagination.totalPages || isLoading)
                        }
                    }
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
            .frame(minWidth: 300)
        } detail: {
            // Main content area
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Selected molecule section
                    if let selected = selectedMolecule {
                        SelectedMoleculeSection(
                            molecule: selected,
                            similarMolecules: similarMolecules,
                            isLoadingSimilar: isLoadingSimilar,
                            onMoleculeTap: { molecule in
                                selectMolecule(molecule)
                            }
                        )
                        
                        Divider()
                    }
                    
                    // Browse section
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Molecules")
                                .font(.title2)
                                .fontWeight(.bold)
                            
                            Spacer()
                            
                            if isLoading {
                                ProgressView()
                                    .scaleEffect(0.8)
                            }
                        }
                        
                        if molecules.isEmpty && !isLoading {
                            VStack(spacing: 16) {
                                Image(systemName: "molecule")
                                    .font(.system(size: 60))
                                    .foregroundColor(.secondary)
                                Text("No molecules found")
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                                Text("Try searching or loading a random sample")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 40)
                        } else {
                            LazyVGrid(columns: [
                                GridItem(.adaptive(minimum: 200), spacing: 16)
                            ], spacing: 16) {
                                ForEach(molecules) { molecule in
                                    MoleculeCard(molecule: molecule) {
                                        selectMolecule(molecule)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding()
            }
        }
        .navigationTitle("Browse Molecules")
        .onAppear {
            backendService.checkBackendHealth()
            if molecules.isEmpty {
                loadMolecules()
            }
        }
    }
    
    private func loadMolecules() {
        guard backendService.isBackendRunning else { return }
        
        isLoading = true
        errorMessage = nil
        
        Task {
            do {
                let result = try await backendService.listMolecules(
                    page: currentPage,
                    perPage: 20,
                    search: searchText.isEmpty ? nil : searchText
                )
                await MainActor.run {
                    molecules = result.molecules
                    pagination = result.pagination
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
    
    private func loadRandomMolecules() {
        guard backendService.isBackendRunning else { return }
        
        isLoading = true
        errorMessage = nil
        currentPage = 1
        
        Task {
            do {
                let result = try await backendService.listMolecules(
                    page: 1,
                    perPage: 20,
                    search: nil,
                    random: true,
                    randomCount: 20
                )
                await MainActor.run {
                    molecules = result.molecules
                    pagination = nil // Random mode doesn't have pagination
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
    
    private func performSearch() {
        currentPage = 1
        loadMolecules()
    }
    
    private func previousPage() {
        guard let pagination = pagination, currentPage > 1 else { return }
        currentPage -= 1
        loadMolecules()
    }
    
    private func nextPage() {
        guard let pagination = pagination, currentPage < pagination.totalPages else { return }
        currentPage += 1
        loadMolecules()
    }
    
    private func selectMolecule(_ molecule: MoleculeBasic) {
        selectedMolecule = molecule
        similarMolecules = []
        isLoadingSimilar = true
        
        Task {
            do {
                let result = try await backendService.getMoleculeWithSimilar(
                    index: molecule.id,
                    topK: 10
                )
                await MainActor.run {
                    similarMolecules = result.similar
                    isLoadingSimilar = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingSimilar = false
                }
            }
        }
    }
}

struct SelectedMoleculeSection: View {
    let molecule: MoleculeBasic
    let similarMolecules: [Molecule]
    let isLoadingSimilar: Bool
    let onMoleculeTap: (MoleculeBasic) -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Selected molecule header
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        if !molecule.name.isEmpty {
                            Text(molecule.name)
                                .font(.title)
                                .fontWeight(.bold)
                        }
                        Text(molecule.chemblId)
                            .font(molecule.name.isEmpty ? .title : .title3)
                            .fontWeight(molecule.name.isEmpty ? .bold : .regular)
                            .foregroundColor(molecule.name.isEmpty ? .primary : .secondary)
                            .fontDesign(.monospaced)
                    }
                    
                    Spacer()
                    
                    if molecule.isApproved {
                        Label("Approved Drug", systemImage: "checkmark.circle.fill")
                            .font(.headline)
                            .foregroundColor(.green)
                    }
                }
                
                HStack(spacing: 20) {
                    Label("\(String(format: "%.2f", molecule.molecularWeight)) Da", systemImage: "scalemass")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            
            // Similar molecules section
            VStack(alignment: .leading, spacing: 12) {
                Text("Similar Molecules")
                    .font(.headline)
                
                if isLoadingSimilar {
                    HStack {
                        ProgressView()
                        Text("Loading similar molecules...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                } else if similarMolecules.isEmpty {
                    Text("No similar molecules found")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding()
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 12) {
                            ForEach(similarMolecules) { similarMolecule in
                                MoleculeCardWithSimilarity(molecule: similarMolecule) {
                                    // Convert Molecule to MoleculeBasic for selection
                                    let basic = MoleculeBasic(
                                        id: similarMolecule.id,
                                        chemblId: similarMolecule.chemblId,
                                        name: similarMolecule.name,
                                        smiles: similarMolecule.smiles,
                                        molecularWeight: similarMolecule.molecularWeight,
                                        isApproved: similarMolecule.isApproved
                                    )
                                    onMoleculeTap(basic)
                                }
                                .frame(width: 200)
                            }
                        }
                        .padding(.horizontal, 4)
                    }
                }
            }
        }
    }
}

#Preview {
    BrowseView()
}

