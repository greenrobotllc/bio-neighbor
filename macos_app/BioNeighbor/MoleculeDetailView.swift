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
    @State private var moleculeImage: NSImage?
    @State private var isLoadingImage = false
    
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
                    }
                    
                    Divider()
                    
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
                        
                        PropertyRow(label: "Similarity", value: String(format: "%.4f", molecule.similarity))
                        PropertyRow(label: "Distance", value: String(format: "%.4f", molecule.similarityScore))
                        PropertyRow(label: "Molecular Weight", value: "\(String(format: "%.2f", molecule.molecularWeight)) Da")
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
            isApproved: true
        )
    )
}

