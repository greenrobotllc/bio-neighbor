//
//  DrugDetailView.swift
//  BioNeighbor
//
//  Detailed view of a drug
//

import SwiftUI

struct DrugDetailView: View {
    let drug: Drug
    @Environment(\.dismiss) private var dismiss
    @StateObject private var backendService = BackendService.shared
    @State private var activeIngredientMolecules: [MoleculeBasic] = []
    @State private var isLoadingMolecules = false
    @State private var errorMessage: String?
    @State private var selectedMolecule: Molecule?
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(drug.name)
                                .font(.largeTitle)
                                .fontWeight(.bold)
                            
                            Spacer()
                        }
                        
                        if let genericName = drug.genericName, genericName != drug.name {
                            Text(genericName)
                                .font(.title3)
                                .foregroundColor(.secondary)
                        }
                        
                        // Brand names
                        if let brandNames = drug.brandNames, !brandNames.isEmpty {
                            HStack(spacing: 8) {
                                Text("Brand names:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                ForEach(brandNames, id: \.self) { brand in
                                    Text(brand)
                                        .font(.subheadline)
                                        .foregroundColor(.blue)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.blue.opacity(0.1))
                                        .cornerRadius(4)
                                }
                            }
                            .padding(.top, 4)
                        }
                    }
                    
                    Divider()
                    
                    // Description
                    if let description = drug.description, !description.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Description")
                                .font(.headline)
                            Text(description)
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Indication
                    if let indication = drug.indication, !indication.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Indication")
                                .font(.headline)
                            Text(indication)
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Dosage form and route
                    if let dosageForm = drug.dosageForm, let route = drug.route {
                        HStack(spacing: 16) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Dosage Form")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(dosageForm)
                                    .font(.body)
                            }
                            
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Route")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(route)
                                    .font(.body)
                            }
                        }
                    }
                    
                    // Active ingredients
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Active Ingredients")
                            .font(.headline)
                        
                        if isLoadingMolecules {
                            ProgressView("Loading active ingredients...")
                                .frame(maxWidth: .infinity)
                                .padding()
                        } else if activeIngredientMolecules.isEmpty {
                            Text("No active ingredient molecules found")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .padding()
                        } else {
                            LazyVGrid(columns: [
                                GridItem(.adaptive(minimum: 200), spacing: 16)
                            ], spacing: 16) {
                                ForEach(activeIngredientMolecules) { molecule in
                                    MoleculeCard(molecule: molecule) {
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
                    
                    // Inactive ingredients
                    if let inactiveIngredients = drug.inactiveIngredients, !inactiveIngredients.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Inactive Ingredients")
                                .font(.headline)
                            Text(inactiveIngredients.joined(separator: ", "))
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // IDs
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Identifiers")
                            .font(.headline)
                        
                        if let pubchemCid = drug.pubchemCid {
                            HStack {
                                Text("PubChem CID:")
                                    .foregroundColor(.secondary)
                                Text(pubchemCid)
                                    .fontDesign(.monospaced)
                            }
                        }
                        
                        if let drugbankId = drug.drugbankId {
                            HStack {
                                Text("DrugBank ID:")
                                    .foregroundColor(.secondary)
                                Text(drugbankId)
                                    .fontDesign(.monospaced)
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Drug Details")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        dismiss()
                    }
                }
            }
        }
        .frame(minWidth: 700, minHeight: 600)
        .sheet(item: $selectedMolecule) { molecule in
            MoleculeDetailView(molecule: molecule)
        }
        .onAppear {
            loadActiveIngredientMolecules()
        }
    }
    
    private func loadActiveIngredientMolecules() {
        guard backendService.isBackendRunning else { return }
        
        isLoadingMolecules = true
        errorMessage = nil
        
        Task {
            do {
                let (_, molecules) = try await backendService.getDrugMolecules(drugId: drug.id)
                await MainActor.run {
                    activeIngredientMolecules = molecules
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
}

#Preview {
    DrugDetailView(
        drug: Drug(
            id: 1,
            name: "Donepezil",
            genericName: "Donepezil",
            brandNames: ["Aricept"],
            pubchemCid: "3152",
            drugbankId: "DB00682",
            description: "Donepezil is an acetylcholinesterase inhibitor used in the treatment of Alzheimer's disease.",
            indication: "Alzheimer's disease",
            activeIngredientMoleculeIndices: [1],
            inactiveIngredients: ["lactose", "starch", "magnesium stearate"],
            dosageForm: "Tablet",
            route: "Oral"
        )
    )
}

