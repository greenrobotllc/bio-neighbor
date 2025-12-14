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
    
    @State private var thumbnail: NSImage?
    @State private var isLoadingThumbnail = false
    
    init(molecule: MoleculeBasic, showSimilarity: Bool = false, onTap: (() -> Void)? = nil) {
        self.molecule = molecule
        self.showSimilarity = showSimilarity
        self.onTap = onTap
    }
    
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Thumbnail icon
            if isLoadingThumbnail {
                ProgressView()
                    .frame(width: 60, height: 60)
            } else if let thumbnail = thumbnail {
                Image(nsImage: thumbnail)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 60, height: 60)
                    .background(Color.white)
                    .cornerRadius(4)
            } else {
                Rectangle()
                    .fill(Color.gray.opacity(0.2))
                    .frame(width: 60, height: 60)
                    .cornerRadius(4)
            }
            
            // Molecule info
            VStack(alignment: .leading, spacing: 6) {
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
                        
                        if let formula = molecule.formula, !formula.isEmpty {
                            Text(formula)
                                .font(.caption)
                                .foregroundColor(.blue)
                                .fontDesign(.monospaced)
                        }
                    }
                    
                    Spacer()
                    
                    if molecule.isApproved {
                        Label("Approved", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundColor(.green)
                    }
                }
                
                HStack(spacing: 12) {
                    Label {
                        Text("Molecular Weight (Da)")
                            .help("Daltons (Da) are atomic mass units. 1 Da ≈ 1.66 × 10⁻²⁷ kg")
                    } icon: {
                        Image(systemName: "scalemass")
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                    
                    Text("\(String(format: "%.1f", molecule.molecularWeight))")
                        .font(.caption)
                        .fontWeight(.medium)
                }
                
                if showSimilarity {
                    // This will be used when displaying similar molecules
                    // Similarity will be passed as part of Molecule type
                }
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
        .task {
            await loadThumbnail()
        }
    }
    
    private func loadThumbnail() async {
        guard thumbnail == nil && !isLoadingThumbnail else { return }
        isLoadingThumbnail = true
        
        do {
            let image = try await BackendService.shared.getMoleculeThumbnail(
                index: molecule.id,
                width: 100,
                height: 100
            )
            await MainActor.run {
                thumbnail = image
                isLoadingThumbnail = false
            }
        } catch {
            print("Error loading thumbnail for molecule \(molecule.id): \(error)")
            await MainActor.run {
                isLoadingThumbnail = false
            }
        }
    }
}

struct MoleculeCardWithSimilarity: View {
    let molecule: Molecule
    var onTap: (() -> Void)?
    
    @State private var thumbnail: NSImage?
    @State private var isLoadingThumbnail = false
    
    init(molecule: Molecule, onTap: (() -> Void)? = nil) {
        self.molecule = molecule
        self.onTap = onTap
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Thumbnail at top
            HStack {
                if isLoadingThumbnail {
                    ProgressView()
                        .frame(width: 80, height: 80)
                } else if let thumbnail = thumbnail {
                    Image(nsImage: thumbnail)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 80, height: 80)
                        .background(Color.white)
                        .cornerRadius(4)
                } else {
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .frame(width: 80, height: 80)
                        .cornerRadius(4)
                        .overlay {
                            Image(systemName: "molecule")
                                .foregroundColor(.gray)
                        }
                }
                
                Spacer()
            }
            
            // Molecule info - wider text area
            VStack(alignment: .leading, spacing: 6) {
                if !molecule.name.isEmpty {
                    Text(molecule.name)
                        .font(.headline)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                
                Text(molecule.chemblId)
                    .font(molecule.name.isEmpty ? .headline : .caption)
                    .foregroundColor(molecule.name.isEmpty ? .primary : .secondary)
                    .fontDesign(.monospaced)
                    .lineLimit(1)
                
                if let formula = molecule.formula, !formula.isEmpty {
                    Text(formula)
                        .font(.caption)
                        .foregroundColor(.blue)
                        .fontDesign(.monospaced)
                        .lineLimit(1)
                }
                
                HStack {
                    Label {
                        Text("Molecular Weight (Da)")
                            .help("Daltons (Da) are atomic mass units. 1 Da ≈ 1.66 × 10⁻²⁷ kg")
                    } icon: {
                        Image(systemName: "scalemass")
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                    
                    Text("\(String(format: "%.1f", molecule.molecularWeight))")
                        .font(.caption)
                        .fontWeight(.medium)
                }
                
                HStack {
                    Label("Similarity", systemImage: "chart.line.uptrend.xyaxis")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Text("\(String(format: "%.3f", molecule.similarity))")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(.blue)
                }
                
                if molecule.isApproved {
                    Label("Approved Drug", systemImage: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundColor(.green)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding()
        .frame(width: 220, alignment: .leading)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.1), radius: 2, x: 0, y: 1)
        .contentShape(Rectangle())
        .onTapGesture {
            onTap?()
        }
        .task {
            await loadThumbnail()
        }
    }
    
    private func loadThumbnail() async {
        guard thumbnail == nil && !isLoadingThumbnail else { return }
        isLoadingThumbnail = true
        
        do {
            let image = try await BackendService.shared.getMoleculeThumbnail(
                index: molecule.id,
                width: 100,
                height: 100
            )
            await MainActor.run {
                thumbnail = image
                isLoadingThumbnail = false
            }
        } catch {
            print("Error loading thumbnail for molecule \(molecule.id): \(error)")
            await MainActor.run {
                isLoadingThumbnail = false
            }
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
                isApproved: true,
                formula: "C9H8O4"
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
                isApproved: true,
                formula: "C13H18O2"
            )
        )
    }
    .padding()
}

