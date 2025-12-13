//
//  ResultsView.swift
//  BioNeighbor
//
//  Display search results
//

import SwiftUI

struct ResultsView: View {
    let results: [Molecule]
    @Binding var selectedMolecule: Molecule?
    
    var body: some View {
        List(results) { molecule in
            MoleculeRow(molecule: molecule)
                .contentShape(Rectangle())
                .onTapGesture {
                    selectedMolecule = molecule
                }
        }
        .navigationTitle("Search Results")
        .navigationSubtitle("\(results.count) molecules found")
    }
}

struct MoleculeRow: View {
    let molecule: Molecule
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(molecule.name.isEmpty ? molecule.chemblId : molecule.name)
                    .font(.headline)
                
                Spacer()
                
                if molecule.isApproved {
                    Label("Approved", systemImage: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundColor(.green)
                }
            }
            
            HStack {
                Text("ChEMBL ID:")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text(molecule.chemblId)
                    .font(.caption)
                    .fontDesign(.monospaced)
            }
            
            HStack(spacing: 16) {
                Label("\(String(format: "%.2f", molecule.similarity))", systemImage: "chart.line.uptrend.xyaxis")
                    .font(.caption)
                
                Label("\(String(format: "%.1f", molecule.molecularWeight)) Da", systemImage: "scalemass")
                    .font(.caption)
            }
            
            Text(molecule.smiles)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.secondary)
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    ResultsView(
        results: [
            Molecule(
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
        ],
        selectedMolecule: .constant(nil)
    )
}

