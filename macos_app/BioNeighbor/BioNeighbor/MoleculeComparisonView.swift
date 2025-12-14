//
//  MoleculeComparisonView.swift
//  BioNeighbor
//
//  Side-by-side and overlay comparison of two molecules with scaffold highlighting
//

import SwiftUI

struct MoleculeComparisonView: View {
    let molecule1: Molecule
    let molecule2: Molecule
    @StateObject private var backendService = BackendService.shared
    @StateObject private var navCoordinator = NavigationCoordinator.shared
    @State private var comparisonData: MoleculeComparisonResponse?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var comparisonMode: ComparisonMode = .sideBySide
    @State private var coordinates1: Molecule3DCoordinates?
    @State private var coordinates2: Molecule3DCoordinates?
    
    enum ComparisonMode {
        case sideBySide
        case overlay
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Breadcrumb
            BreadcrumbView(coordinator: navCoordinator)
                .padding(.top, 8)
            
            Divider()
            
            // Mode selector
            Picker("Comparison Mode", selection: $comparisonMode) {
                    Text("Side by Side").tag(ComparisonMode.sideBySide)
                    Text("Overlay").tag(ComparisonMode.overlay)
                }
                .pickerStyle(.segmented)
                .padding()
                
                if isLoading {
                    ProgressView("Comparing molecules...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = errorMessage {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                            .foregroundColor(.orange)
                        Text("Error")
                            .font(.headline)
                        Text(error)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .padding()
                } else if let comparison = comparisonData {
                    ScrollView {
                        VStack(spacing: 20) {
                            // MCS Summary
                            if let mcs = comparison.mcs {
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("Shared Scaffold (MCS)")
                                        .font(.headline)
                                    
                                    VStack(alignment: .leading, spacing: 8) {
                                        HStack(spacing: 16) {
                                            Text("Common Atoms: \(mcs.numAtoms)")
                                            Text("Common Bonds: \(mcs.numBonds)")
                                        }
                                        .font(.subheadline)
                                        
                                        ScrollView(.horizontal, showsIndicators: false) {
                                            Text(mcs.mcsSmiles)
                                                .font(.system(.body, design: .monospaced))
                                                .padding(8)
                                                .background(Color.gray.opacity(0.1))
                                                .cornerRadius(4)
                                        }
                                    }
                                }
                                .padding()
                                .background(Color.blue.opacity(0.1))
                                .cornerRadius(8)
                            }
                            
                            // Comparison visualization
                            if comparisonMode == .sideBySide {
                                sideBySideView(comparison: comparison)
                            } else {
                                overlayView(comparison: comparison)
                            }
                            
                            // Functional groups
                            if let fg1 = comparison.functionalGroups1, !fg1.isEmpty {
                                functionalGroupsSection(title: "Functional Groups - \(molecule1.name)", groups: fg1)
                            }
                            
                            if let fg2 = comparison.functionalGroups2, !fg2.isEmpty {
                                functionalGroupsSection(title: "Functional Groups - \(molecule2.name)", groups: fg2)
                            }
                        }
                        .padding()
                    }
                } else {
                    Text("No comparison data available")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        .navigationTitle("Compare Molecules")
        .frame(minWidth: 1000, minHeight: 700)
        .onAppear {
            navCoordinator.push(BreadcrumbItem(
                title: "Compare with \(molecule2.name.isEmpty ? molecule2.chemblId : molecule2.name)",
                icon: "square.grid.2x2",
                type: .comparison
            ))
            loadComparison()
            load3DCoordinates()
        }
    }
    
    private func sideBySideView(comparison: MoleculeComparisonResponse) -> some View {
        HStack(spacing: 20) {
            // Molecule 1
            VStack(alignment: .leading, spacing: 0) {
                Text(molecule1.name.isEmpty ? molecule1.chemblId : molecule1.name)
                    .font(.headline)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
                    .padding(.bottom, 24)
                
                if let coords1 = coordinates1 {
                    Molecule3DView(
                        coordinates: coords1,
                        highlightedAtoms: comparison.mcs?.sharedAtoms1,
                        highlightColor: "green",
                        highlightMode: .sharedScaffold
                    )
                    .frame(height: 400)
                } else {
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .frame(height: 400)
                        .overlay {
                            ProgressView()
                        }
                }
            }
            .frame(maxWidth: .infinity)
            
            // Molecule 2
            VStack(alignment: .leading, spacing: 0) {
                Text(molecule2.name.isEmpty ? molecule2.chemblId : molecule2.name)
                    .font(.headline)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
                    .padding(.bottom, 24)
                
                if let coords2 = coordinates2 {
                    Molecule3DView(
                        coordinates: coords2,
                        highlightedAtoms: comparison.mcs?.sharedAtoms2,
                        highlightColor: "green",
                        highlightMode: .sharedScaffold
                    )
                    .frame(height: 400)
                } else {
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .frame(height: 400)
                        .overlay {
                            ProgressView()
                        }
                }
            }
            .frame(maxWidth: .infinity)
        }
    }
    
    private func overlayView(comparison: MoleculeComparisonResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Overlay View")
                .font(.headline)
            
            // For overlay, we'll show molecule 1 with highlights
            // In a full implementation, this would align both molecules
            if let coords1 = coordinates1 {
                Molecule3DView(
                    coordinates: coords1,
                    highlightedAtoms: comparison.mcs?.sharedAtoms1,
                    highlightColor: "green",
                    highlightMode: .sharedScaffold
                )
                .frame(height: 500)
            } else {
                Rectangle()
                    .fill(Color.gray.opacity(0.2))
                    .frame(height: 500)
                    .overlay {
                        ProgressView()
                    }
            }
            
            // Legend
            HStack(spacing: 20) {
                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 12, height: 12)
                    Text("Shared Scaffold")
                }
                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.red)
                        .frame(width: 12, height: 12)
                    Text("Differences")
                }
            }
            .padding()
            .background(Color.gray.opacity(0.1))
            .cornerRadius(8)
        }
    }
    
    private func functionalGroupsSection(title: String, groups: [FunctionalGroup]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            
            LazyVGrid(columns: [
                GridItem(.adaptive(minimum: 200), spacing: 12)
            ], spacing: 12) {
                ForEach(groups) { group in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(group.type.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .lineLimit(1)
                        Text(group.description)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                            .fixedSize(horizontal: false, vertical: true)
                        ScrollView(.horizontal, showsIndicators: false) {
                            Text("Atoms: \(group.atoms.map { String($0) }.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundColor(.blue)
                        }
                    }
                    .padding()
                    .frame(minHeight: 80)
                    .background(Color.gray.opacity(0.1))
                    .cornerRadius(8)
                }
            }
        }
        .padding()
        .background(Color.gray.opacity(0.05))
        .cornerRadius(8)
    }
    
    private func loadComparison() {
        guard backendService.isBackendRunning else {
            errorMessage = "Backend is not running"
            return
        }
        
        isLoading = true
        errorMessage = nil
        
        Task {
            do {
                let comparison = try await backendService.compareMolecules(
                    smiles1: molecule1.smiles,
                    smiles2: molecule2.smiles
                )
                await MainActor.run {
                    comparisonData = comparison
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
    
    private func load3DCoordinates() {
        Task {
            // Load 3D coordinates for both molecules
            do {
                // Find molecule indices - we'll need to search for them
                // For now, use SMILES directly
                let coords1 = try await backendService.getMolecule3D(index: molecule1.id)
                await MainActor.run {
                    coordinates1 = coords1
                }
            } catch {
                // If index-based lookup fails, we could generate from SMILES
                print("Could not load 3D coordinates for molecule 1: \(error)")
            }
            
            do {
                let coords2 = try await backendService.getMolecule3D(index: molecule2.id)
                await MainActor.run {
                    coordinates2 = coords2
                }
            } catch {
                print("Could not load 3D coordinates for molecule 2: \(error)")
            }
        }
    }
}

#Preview {
    MoleculeComparisonView(
        molecule1: Molecule(
            id: 0,
            chemblId: "CHEMBL25",
            name: "Aspirin",
            smiles: "CC(=O)Oc1ccccc1C(=O)O",
            similarity: 1.0,
            similarityScore: 0.0,
            molecularWeight: 180.16,
            isApproved: true,
            formula: "C9H8O4"
        ),
        molecule2: Molecule(
            id: 1,
            chemblId: "CHEMBL112",
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

