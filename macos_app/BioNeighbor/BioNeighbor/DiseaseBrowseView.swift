//
//  DiseaseBrowseView.swift
//  BioNeighbor
//
//  Disease-based molecule browsing interface
//

import SwiftUI

struct DiseaseBrowseView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var diseases: [Disease] = []
    @State private var selectedDisease: Disease?
    @State private var diseaseMolecules: [MoleculeBasic] = []
    @State private var similarMolecules: [Molecule] = []
    @State private var isLoadingDiseases = false
    @State private var isLoadingMolecules = false
    @State private var isLoadingSimilar = false
    @State private var errorMessage: String?
    @State private var diseaseSearchText = ""
    @State private var selectedMolecule: Molecule?
    @State private var showSimilarMolecules = false
    
    var filteredDiseases: [Disease] {
        if diseaseSearchText.isEmpty {
            return diseases
        }
        return diseases.filter { disease in
            disease.name.localizedCaseInsensitiveContains(diseaseSearchText)
        }
    }
    
    var body: some View {
        NavigationSplitView {
            // Sidebar with disease selector
            VStack(alignment: .leading, spacing: 20) {
                Text("Disease Browser")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 10)
                
                Text("Browse molecules by disease")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Divider()
                
                // Disease search
                VStack(alignment: .leading, spacing: 8) {
                    Text("Search Diseases")
                        .font(.headline)
                    
                    TextField("Type to search...", text: $diseaseSearchText)
                        .textFieldStyle(.roundedBorder)
                        .onChange(of: diseaseSearchText) { _ in
                            // Auto-select first match if search narrows to one result
                            if filteredDiseases.count == 1, selectedDisease?.id != filteredDiseases[0].id {
                                selectedDisease = filteredDiseases[0]
                                loadDiseaseMolecules()
                            }
                        }
                }
                
                // Disease list
                if isLoadingDiseases {
                    HStack {
                        ProgressView()
                        Text("Loading diseases...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                } else if diseases.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("No diseases found")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        
                        Text("Disease data may not be loaded yet.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Button("Load Diseases") {
                            loadDiseases()
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 8) {
                            ForEach(filteredDiseases) { disease in
                                DiseaseRow(
                                    disease: disease,
                                    isSelected: selectedDisease?.id == disease.id
                                ) {
                                    selectedDisease = disease
                                    loadDiseaseMolecules()
                                }
                            }
                        }
                        .padding(.vertical, 4)
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
            if let disease = selectedDisease {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Disease header
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(disease.name)
                                        .font(.title)
                                        .fontWeight(.bold)
                                    
                                    if let meshId = disease.meshId {
                                        Text("MeSH ID: \(meshId)")
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                            .fontDesign(.monospaced)
                                    }
                                    
                                    if let description = disease.description, !description.isEmpty {
                                        Text(description)
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                            .padding(.top, 4)
                                    }
                                }
                                
                                Spacer()
                                
                                if isLoadingMolecules {
                                    ProgressView()
                                } else {
                                    Text("\(diseaseMolecules.count) molecules")
                                        .font(.headline)
                                        .foregroundColor(.blue)
                                }
                            }
                        }
                        .padding()
                        .background(Color(NSColor.controlBackgroundColor))
                        .cornerRadius(8)
                        
                        // Toggle for similar molecules
                        HStack {
                            Toggle("Show Similar Molecules", isOn: $showSimilarMolecules)
                                .onChange(of: showSimilarMolecules) { newValue in
                                    if newValue && similarMolecules.isEmpty {
                                        loadSimilarMolecules()
                                    }
                                }
                            
                            Spacer()
                            
                            Button("Refresh") {
                                loadDiseaseMolecules()
                                if showSimilarMolecules {
                                    loadSimilarMolecules()
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(isLoadingMolecules || isLoadingSimilar)
                        }
                        
                        // Molecules section
                        if isLoadingMolecules {
                            ProgressView("Loading molecules...")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 40)
                        } else if diseaseMolecules.isEmpty {
                            VStack(spacing: 16) {
                                Image(systemName: "molecule")
                                    .font(.system(size: 60))
                                    .foregroundColor(.secondary)
                                Text("No molecules found for this disease")
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                                Text("Try loading disease data or check if molecules are matched in the database")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                    .multilineTextAlignment(.center)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 40)
                        } else {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Molecules for \(disease.name)")
                                    .font(.title2)
                                    .fontWeight(.bold)
                                
                                LazyVGrid(columns: [
                                    GridItem(.adaptive(minimum: 200), spacing: 16)
                                ], spacing: 16) {
                                    ForEach(diseaseMolecules) { molecule in
                                        MoleculeCard(molecule: molecule) {
                                            // Convert MoleculeBasic to Molecule for detail view
                                            selectedMolecule = Molecule(
                                                id: molecule.id,
                                                chemblId: molecule.chemblId,
                                                name: molecule.name,
                                                smiles: molecule.smiles,
                                                similarity: 1.0,
                                                similarityScore: 0.0,
                                                molecularWeight: molecule.molecularWeight,
                                                isApproved: molecule.isApproved,
                                                formula: molecule.formula
                                            )
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Similar molecules section
                        if showSimilarMolecules {
                            Divider()
                            
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Similar Molecules")
                                    .font(.title2)
                                    .fontWeight(.bold)
                                
                                if isLoadingSimilar {
                                    ProgressView("Finding similar molecules...")
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 40)
                                } else if similarMolecules.isEmpty {
                                    Text("No similar molecules found")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .padding()
                                } else {
                                    ScrollView(.horizontal, showsIndicators: false) {
                                        HStack(spacing: 16) {
                                            ForEach(similarMolecules) { molecule in
                                                MoleculeCardWithSimilarity(molecule: molecule) {
                                                    selectedMolecule = molecule
                                                }
                                            }
                                        }
                                        .padding(.horizontal, 4)
                                    }
                                }
                            }
                        }
                    }
                    .padding()
                }
            } else {
                VStack(spacing: 20) {
                    Image(systemName: "cross.case")
                        .font(.system(size: 60))
                        .foregroundColor(.secondary)
                    Text("Select a disease to view molecules")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    Text("Choose a disease from the sidebar to see molecules used to treat it")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle("Disease Browser")
        .sheet(item: $selectedMolecule) { molecule in
            MoleculeDetailView(molecule: molecule)
        }
        .onAppear {
            backendService.checkBackendHealth()
            if diseases.isEmpty {
                loadDiseases()
            }
        }
    }
    
    private func loadDiseases() {
        guard backendService.isBackendRunning else { return }
        
        isLoadingDiseases = true
        errorMessage = nil
        
        Task {
            do {
                let loadedDiseases = try await backendService.getAllDiseases()
                await MainActor.run {
                    diseases = loadedDiseases
                    isLoadingDiseases = false
                    
                    // Auto-select Alzheimer's if available
                    if selectedDisease == nil, let alzheimers = diseases.first(where: { $0.name.localizedCaseInsensitiveContains("alzheimer") }) {
                        selectedDisease = alzheimers
                        loadDiseaseMolecules()
                    }
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingDiseases = false
                }
            }
        }
    }
    
    private func loadDiseaseMolecules() {
        guard let disease = selectedDisease, backendService.isBackendRunning else { return }
        
        isLoadingMolecules = true
        errorMessage = nil
        diseaseMolecules = []
        
        Task {
            do {
                let molecules = try await backendService.getDiseaseTopMolecules(
                    diseaseName: disease.name,
                    topK: 50
                )
                await MainActor.run {
                    diseaseMolecules = molecules
                    isLoadingMolecules = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingMolecules = false
                }
            }
        }
    }
    
    private func loadSimilarMolecules() {
        guard let disease = selectedDisease, backendService.isBackendRunning else { return }
        
        isLoadingSimilar = true
        errorMessage = nil
        similarMolecules = []
        
        Task {
            do {
                let similar = try await backendService.searchByDisease(
                    diseaseName: disease.name,
                    topK: 20
                )
                await MainActor.run {
                    similarMolecules = similar
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

struct DiseaseRow: View {
    let disease: Disease
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(disease.name)
                        .font(.headline)
                        .foregroundColor(isSelected ? .white : .primary)
                    
                    if let meshId = disease.meshId {
                        Text(meshId)
                            .font(.caption)
                            .foregroundColor(isSelected ? .white.opacity(0.8) : .secondary)
                            .fontDesign(.monospaced)
                    }
                }
                
                Spacer()
                
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.white)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? Color.accentColor : Color.clear)
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    DiseaseBrowseView()
}

