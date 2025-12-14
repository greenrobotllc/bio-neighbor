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
    @StateObject private var navCoordinator = NavigationCoordinator.shared
    @State private var navigationPath = NavigationPath()
    
    var body: some View {
        NavigationStack(path: $navigationPath) {
            HStack(spacing: 0) {
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
                .frame(minWidth: 220, idealWidth: 250, maxWidth: 280)
                .background(Color(NSColor.controlBackgroundColor))
                
                Divider()
                
                // Main content area
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Selected molecule section
                        if let selected = selectedMolecule {
                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        if !selected.name.isEmpty {
                                            Text(selected.name)
                                                .font(.title)
                                                .fontWeight(.bold)
                                        }
                                        Text(selected.chemblId)
                                            .font(selected.name.isEmpty ? .title : .title3)
                                            .fontWeight(selected.name.isEmpty ? .bold : .regular)
                                            .foregroundColor(selected.name.isEmpty ? .primary : .secondary)
                                            .fontDesign(.monospaced)
                                        
                                        if let formula = selected.formula, !formula.isEmpty {
                                            Text(formula)
                                                .font(.title3)
                                                .foregroundColor(.blue)
                                                .fontDesign(.monospaced)
                                                .padding(.top, 4)
                                        }
                                    }
                                    
                                    Spacer()
                                    
                                    HStack(spacing: 12) {
                                        NavigationLink(value: selected) {
                                            Text("View Details")
                                        }
                                        .buttonStyle(.borderedProminent)
                                        
                                        if selected.isApproved {
                                            Label("Approved Drug", systemImage: "checkmark.circle.fill")
                                                .font(.headline)
                                                .foregroundColor(.green)
                                        }
                                    }
                                }
                                
                                HStack(spacing: 20) {
                                    Label {
                                        Text("Molecular Weight (Da)")
                                            .help("Daltons (Da) are atomic mass units. 1 Da ≈ 1.66 × 10⁻²⁷ kg")
                                    } icon: {
                                        Image(systemName: "scalemass")
                                    }
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                    
                                    Text("\(String(format: "%.2f", selected.molecularWeight))")
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                }
                            }
                            .padding()
                            .background(Color(NSColor.controlBackgroundColor))
                            .cornerRadius(8)
                            
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
                                    ForEach(molecules.filter { molecule in
                                        // Filter out the selected molecule to avoid duplicates
                                        selectedMolecule?.id != molecule.id
                                    }) { molecule in
                                        NavigationLink(value: molecule) {
                                            MoleculeCard(molecule: molecule) {
                                                selectMolecule(molecule)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .padding()
                }
                .navigationTitle("Browse Molecules")
                .navigationDestination(for: MoleculeBasic.self) { molecule in
                    // Convert MoleculeBasic to Molecule for detail view
                    let moleculeForDetail = Molecule(
                        id: molecule.id,
                        chemblId: molecule.chemblId,
                        name: molecule.name,
                        smiles: molecule.smiles,
                        similarity: 0.0,
                        similarityScore: 1.0,
                        molecularWeight: molecule.molecularWeight,
                        isApproved: molecule.isApproved,
                        formula: molecule.formula
                    )
                    MoleculeDetailView(molecule: moleculeForDetail)
                }
            }
        }
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
                    // Deduplicate molecules by ID
                    var seen = Set<Int>()
                    molecules = result.molecules.filter { molecule in
                        seen.insert(molecule.id).inserted
                    }
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
        guard pagination != nil, currentPage > 1 else { return }
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
    
    @State private var selectedTab = 0
    @State private var molecule2DImage: NSImage?
    @State private var isLoading2D = false
    @State private var molecule3DCoords: Molecule3DCoordinates?
    @State private var isLoading3D = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Tabbed interface
            TabView(selection: $selectedTab) {
                // 2D Structure tab
                VStack {
                    if isLoading2D {
                        ProgressView("Loading structure...")
                            .frame(maxWidth: .infinity, minHeight: 400)
                    } else if let image = molecule2DImage {
                        Image(nsImage: image)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxWidth: .infinity, minHeight: 400)
                            .background(Color.white)
                            .cornerRadius(8)
                    } else {
                        Rectangle()
                            .fill(Color.gray.opacity(0.2))
                            .frame(minHeight: 400)
                            .overlay {
                                Text("2D structure not available")
                                    .foregroundColor(.secondary)
                            }
                    }
                }
                .tabItem {
                    Label("2D Structure", systemImage: "square.grid.2x2")
                }
                .tag(0)
                
                // 3D Structure tab
                Group {
                    if isLoading3D {
                        ProgressView("Generating 3D coordinates...")
                            .frame(maxWidth: .infinity, minHeight: 400)
                    } else if let coords = molecule3DCoords {
                        Molecule3DView(coordinates: coords)
                            .frame(minHeight: 400)
                    } else {
                        Rectangle()
                            .fill(Color.gray.opacity(0.2))
                            .frame(minHeight: 400)
                            .overlay {
                                VStack {
                                    Text("3D structure not available")
                                        .foregroundColor(.secondary)
                                    Button("Load 3D View") {
                                        load3DCoordinates()
                                    }
                                    .buttonStyle(.bordered)
                                    .padding(.top, 8)
                                }
                            }
                    }
                }
                .tabItem {
                    Label("3D Structure", systemImage: "cube")
                }
                .tag(1)
                
                // Properties tab
                VStack(alignment: .leading, spacing: 16) {
                    PropertyRow(label: "ChEMBL ID", value: molecule.chemblId)
                    if let formula = molecule.formula, !formula.isEmpty {
                        PropertyRow(label: "Formula", value: formula)
                    }
                    PropertyRow(label: "Molecular Weight", value: "\(String(format: "%.2f", molecule.molecularWeight)) Da")
                    PropertyRow(label: "SMILES", value: molecule.smiles)
                    PropertyRow(label: "Status", value: molecule.isApproved ? "Approved Drug" : "Research Compound")
                }
                .padding()
                .tabItem {
                    Label("Properties", systemImage: "info.circle")
                }
                .tag(2)
            }
            .frame(minHeight: 450)
            .onChange(of: selectedTab) { newValue in
                if newValue == 0 && molecule2DImage == nil {
                    load2DImage()
                } else if newValue == 1 && molecule3DCoords == nil && !isLoading3D {
                    load3DCoordinates()
                }
            }
            .onAppear {
                if selectedTab == 0 {
                    load2DImage()
                }
            }
            
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
                        HStack(spacing: 16) {
                            ForEach(similarMolecules) { similarMolecule in
                                MoleculeCardWithSimilarity(molecule: similarMolecule) {
                                    // Convert Molecule to MoleculeBasic for selection
                                    let basic = MoleculeBasic(
                                        id: similarMolecule.id,
                                        chemblId: similarMolecule.chemblId,
                                        name: similarMolecule.name,
                                        smiles: similarMolecule.smiles,
                                        molecularWeight: similarMolecule.molecularWeight,
                                        isApproved: similarMolecule.isApproved,
                                        formula: similarMolecule.formula
                                    )
                                    onMoleculeTap(basic)
                                }
                            }
                        }
                        .padding(.horizontal, 4)
                    }
                }
            }
        }
    }
    
    private func load2DImage() {
        guard molecule2DImage == nil && !isLoading2D else { return }
        isLoading2D = true
        
        Task {
            do {
                let image = try await BackendService.shared.renderMolecule(
                    smiles: molecule.smiles,
                    width: 400,
                    height: 400
                )
                await MainActor.run {
                    molecule2DImage = image
                    isLoading2D = false
                }
            } catch {
                await MainActor.run {
                    isLoading2D = false
                }
            }
        }
    }
    
    private func load3DCoordinates() {
        guard molecule3DCoords == nil && !isLoading3D else { return }
        isLoading3D = true
        
        Task {
            do {
                let coords = try await BackendService.shared.getMolecule3D(index: molecule.id)
                await MainActor.run {
                    molecule3DCoords = coords
                    isLoading3D = false
                }
            } catch {
                await MainActor.run {
                    isLoading3D = false
                }
            }
        }
    }
}

#Preview {
    BrowseView()
}

