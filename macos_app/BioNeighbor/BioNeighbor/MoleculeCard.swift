//
//  MoleculeCard.swift
//  BioNeighbor
//
//  Reusable card component for displaying molecules
//

import SwiftUI

struct MoleculeCard: View {
    let molecule: MoleculeBasic
    let showSimilarity: Bool
    var onTap: (() -> Void)?
    
    init(molecule: MoleculeBasic, showSimilarity: Bool = false, onTap: (() -> Void)? = nil) {
        self.molecule = molecule
        self.showSimilarity = showSimilarity
        self.onTap = onTap
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    if !molecule.name.isEmpty {
                        Text(molecule.name)
                            .font(.headline)
                            .lineLimit(1)
                    }
                    Text(molecule.chemblId)
                        .font(molecule.name.isEmpty ? .headline : .caption)
                        .foregroundColor(molecule.name.isEmpty ? .primary : .secondary)
                        .fontDesign(.monospaced)
                }
                
                Spacer()
                
                if molecule.isApproved {
                    Label("Approved", systemImage: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundColor(.green)
                }
            }
            
            HStack(spacing: 12) {
                Label("\(String(format: "%.1f", molecule.molecularWeight)) Da", systemImage: "scalemass")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if showSimilarity {
                // This will be used when displaying similar molecules
                // Similarity will be passed as part of Molecule type
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.1), radius: 2, x: 0, y: 1)
        .contentShape(Rectangle())
        .onTapGesture {
            onTap?()
        }
    }
}

struct MoleculeCardWithSimilarity: View {
    let molecule: Molecule
    var onTap: (() -> Void)?
    
    init(molecule: Molecule, onTap: (() -> Void)? = nil) {
        self.molecule = molecule
        self.onTap = onTap
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(molecule.name.isEmpty ? molecule.chemblId : molecule.name)
                    .font(.headline)
                    .lineLimit(1)
                
                Spacer()
                
                if molecule.isApproved {
                    Label("Approved", systemImage: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundColor(.green)
                }
            }
            
            Text(molecule.chemblId)
                .font(.caption)
                .foregroundColor(.secondary)
                .fontDesign(.monospaced)
            
            HStack(spacing: 12) {
                Label("\(String(format: "%.1f", molecule.molecularWeight)) Da", systemImage: "scalemass")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Label("\(String(format: "%.3f", molecule.similarity))", systemImage: "chart.line.uptrend.xyaxis")
                    .font(.caption)
                    .foregroundColor(.blue)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.1), radius: 2, x: 0, y: 1)
        .contentShape(Rectangle())
        .onTapGesture {
            onTap?()
        }
    }
}

#Preview {
    HStack {
        MoleculeCard(
            molecule: MoleculeBasic(
                id: 0,
                chemblId: "CHEMBL25",
                name: "Aspirin",
                smiles: "CC(=O)Oc1ccccc1C(=O)O",
                molecularWeight: 180.16,
                isApproved: true
            )
        )
        
        MoleculeCardWithSimilarity(
            molecule: Molecule(
                id: 1,
                chemblId: "CHEMBL100",
                name: "Ibuprofen",
                smiles: "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
                similarity: 0.85,
                similarityScore: 0.15,
                molecularWeight: 206.29,
                isApproved: true
            )
        )
    }
    .padding()
}

