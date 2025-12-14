//
//  MoleculeDetailView.swift
//  BioNeighbor
//
//  Detailed view of a molecule
//

import SwiftUI

struct MoleculeDetailView: View {
    let molecule: Molecule
    @Environment(\.dismiss) private var dismiss
    @StateObject private var backendService = BackendService.shared
    @State private var moleculeImage: NSImage?
    @State private var isLoadingImage = false
    @State private var bondData: MoleculeBondData?
    @State private var functionalGroups: [FunctionalGroup] = []
    @State private var isLoadingBondData = false
    @State private var isLoadingFunctionalGroups = false
    @State private var showBondAnalysis = false
    @State private var showFunctionalGroups = false
    @State private var errorMessage: String?
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(molecule.name.isEmpty ? molecule.chemblId : molecule.name)
                                .font(.largeTitle)
                                .fontWeight(.bold)
                            
                            Spacer()
                            
                            if molecule.isApproved {
                                Label("Approved Drug", systemImage: "checkmark.circle.fill")
                                    .font(.headline)
                                    .foregroundColor(.green)
                            }
                        }
                        
                        Text(molecule.chemblId)
                            .font(.title3)
                            .foregroundColor(.secondary)
                            .fontDesign(.monospaced)
                        
                        if let formula = molecule.formula, !formula.isEmpty {
                            Text(formula)
                                .font(.title2)
                                .foregroundColor(.blue)
                                .fontDesign(.monospaced)
                                .padding(.top, 4)
                        }
                    }
                    
                    Divider()
                    
                    // Error message
                    if let error = errorMessage {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.red)
                            Text(error)
                                .foregroundColor(.red)
                            Spacer()
                            Button("Dismiss") {
                                errorMessage = nil
                            }
                        }
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                    }
                    
                    // Molecule visualization
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Structure")
                            .font(.headline)
                        
                        if isLoadingImage {
                            ProgressView()
                                .frame(maxWidth: .infinity, minHeight: 200)
                        } else if let image = moleculeImage {
                            Image(nsImage: image)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(maxWidth: .infinity, minHeight: 200)
                                .background(Color.white)
                                .cornerRadius(8)
                        } else {
                            Rectangle()
                                .fill(Color.gray.opacity(0.2))
                                .frame(height: 200)
                                .overlay {
                                    Text("Structure visualization not available")
                                        .foregroundColor(.secondary)
                                }
                        }
                    }
                    
                    // Properties
                    VStack(alignment: .leading, spacing: 16) {
                        Text("Properties")
                            .font(.headline)
                        
                        if let formula = molecule.formula, !formula.isEmpty {
                            PropertyRow(label: "Formula", value: formula)
                        }
                        PropertyRow(label: "Similarity", value: String(format: "%.4f", molecule.similarity))
                        PropertyRow(label: "Distance", value: String(format: "%.4f", molecule.similarityScore))
                        PropertyRow(label: "Molecular Weight", value: "\(String(format: "%.2f", molecule.molecularWeight)) Da")
                            .help("Daltons (Da) are atomic mass units. 1 Da ≈ 1.66 × 10⁻²⁷ kg")
                        PropertyRow(label: "Status", value: molecule.isApproved ? "Approved Drug" : "Research Compound")
                    }
                    
                    // SMILES
                    VStack(alignment: .leading, spacing: 12) {
                        Text("SMILES")
                            .font(.headline)
                        
                        Text(molecule.smiles)
                            .font(.system(.body, design: .monospaced))
                            .padding()
                            .background(Color.gray.opacity(0.1))
                            .cornerRadius(8)
                            .textSelection(.enabled)
                    }
                    
                    Divider()
                        .padding(.vertical, 8)
                    
                    // Bond Analysis
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("Bond Analysis", systemImage: "atom")
                                .font(.headline)
                            Spacer()
                            Button(showBondAnalysis ? "Hide" : "Show") {
                                showBondAnalysis.toggle()
                                if showBondAnalysis && bondData == nil {
                                    loadBondData()
                                }
                            }
                        }
                        .padding(.top, 8)
                        
                        if showBondAnalysis {
                            if isLoadingBondData {
                                ProgressView("Loading bond data...")
                                    .frame(maxWidth: .infinity)
                                    .padding()
                            } else if let bonds = bondData {
                                VStack(alignment: .leading, spacing: 8) {
                                    HStack {
                                        Text("Atoms: \(bonds.atoms.count)")
                                        Spacer()
                                        Text("Bonds: \(bonds.bonds.count)")
                                    }
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                    
                                    // Atom details (first 10)
                                    if bonds.atoms.count > 0 {
                                        Text("Atom Details (showing first 10)")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                        
                                        ForEach(Array(bonds.atoms.prefix(10)), id: \.index) { atom in
                                            HStack {
                                                Text("Atom \(atom.index): \(atom.symbol)")
                                                    .font(.system(.caption, design: .monospaced))
                                                Spacer()
                                                Text("Charge: \(atom.formalCharge), Hybrid: \(atom.hybridization)")
                                                    .font(.caption)
                                                    .foregroundColor(.secondary)
                                            }
                                        }
                                        
                                        if bonds.atoms.count > 10 {
                                            Text("... and \(bonds.atoms.count - 10) more atoms")
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                }
                                .padding()
                                .background(Color.gray.opacity(0.05))
                                .cornerRadius(8)
                            } else if !backendService.isBackendRunning {
                                Text("Backend is not running. Please start the backend to load bond data.")
                                    .font(.caption)
                                    .foregroundColor(.orange)
                                    .padding()
                            } else {
                                // Show error if there was one, or empty state
                                if let error = errorMessage, error.contains("bond") {
                                    Text("Error: \(error)")
                                        .font(.caption)
                                        .foregroundColor(.red)
                                        .padding()
                                } else {
                                    Text("No bond data available")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .padding()
                                }
                            }
                        }
                    }
                    
                    // Functional Groups
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("Functional Groups", systemImage: "sparkles")
                                .font(.headline)
                            Spacer()
                            Button(showFunctionalGroups ? "Hide" : "Show") {
                                showFunctionalGroups.toggle()
                                if showFunctionalGroups && functionalGroups.isEmpty {
                                    loadFunctionalGroups()
                                }
                            }
                        }
                        .padding(.top, 8)
                        
                        if showFunctionalGroups {
                            if isLoadingFunctionalGroups {
                                ProgressView("Loading functional groups...")
                                    .frame(maxWidth: .infinity)
                                    .padding()
                            } else if !functionalGroups.isEmpty {
                                LazyVGrid(columns: [
                                    GridItem(.adaptive(minimum: 200), spacing: 12)
                                ], spacing: 12) {
                                    ForEach(functionalGroups) { group in
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(group.type.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.subheadline)
                                                .fontWeight(.medium)
                                            Text(group.description)
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                            Text("Atoms: \(group.atoms.map { String($0) }.joined(separator: ", "))")
                                                .font(.caption)
                                                .foregroundColor(.blue)
                                        }
                                        .padding()
                                        .background(Color.gray.opacity(0.1))
                                        .cornerRadius(8)
                                    }
                                }
                            } else if !backendService.isBackendRunning {
                                Text("Backend is not running. Please start the backend to load functional groups.")
                                    .font(.caption)
                                    .foregroundColor(.orange)
                                    .padding()
                            } else {
                                // Show error if there was one, or empty state
                                if let error = errorMessage, error.contains("functional") {
                                    Text("Error: \(error)")
                                        .font(.caption)
                                        .foregroundColor(.red)
                                        .padding()
                                } else if functionalGroups.isEmpty {
                                    Text("No functional groups found")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .padding()
                                }
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Molecule Details")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        dismiss()
                    }
                }
            }
        }
        .frame(minWidth: 600, minHeight: 500)
        .onAppear {
            loadMoleculeImage()
        }
    }
    
    private func loadBondData() {
        guard backendService.isBackendRunning else {
            errorMessage = "Backend is not running"
            return
        }
        
        isLoadingBondData = true
        errorMessage = nil
        
        Task {
            do {
                let data = try await backendService.getMoleculeBonds(index: molecule.id)
                await MainActor.run {
                    bondData = data
                    isLoadingBondData = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Failed to load bond data: \(error.localizedDescription)"
                    isLoadingBondData = false
                    print("Error loading bond data: \(error)")
                }
            }
        }
    }
    
    private func loadFunctionalGroups() {
        guard backendService.isBackendRunning else {
            errorMessage = "Backend is not running"
            return
        }
        
        isLoadingFunctionalGroups = true
        errorMessage = nil
        
        Task {
            do {
                let groups = try await backendService.getFunctionalGroups(index: molecule.id)
                await MainActor.run {
                    functionalGroups = groups
                    isLoadingFunctionalGroups = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Failed to load functional groups: \(error.localizedDescription)"
                    isLoadingFunctionalGroups = false
                    print("Error loading functional groups: \(error)")
                }
            }
        }
    }
    
    private func loadMoleculeImage() {
        isLoadingImage = true
        
        Task {
            do {
                let image = try await BackendService.shared.renderMolecule(smiles: molecule.smiles)
                await MainActor.run {
                    moleculeImage = image
                    isLoadingImage = false
                }
            } catch {
                await MainActor.run {
                    isLoadingImage = false
                }
            }
        }
    }
}

struct PropertyRow: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.medium)
        }
    }
}

#Preview {
    MoleculeDetailView(
        molecule: Molecule(
            id: 0,
            chemblId: "CHEMBL25",
            name: "Aspirin",
            smiles: "CC(=O)Oc1ccccc1C(=O)O",
            similarity: 0.95,
            similarityScore: 0.05,
            molecularWeight: 180.16,
            isApproved: true,
            formula: "C9H8O4"
        )
    )
}

