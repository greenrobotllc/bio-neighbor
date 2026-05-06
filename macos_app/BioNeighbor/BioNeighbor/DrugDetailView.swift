//
//  DrugDetailView.swift
//  BioNeighbor
//
//  Detailed view of a drug
//

import SwiftUI

struct DrugDetailView: View {
    let drug: Drug
    @StateObject private var backendService = BackendService.shared
    @StateObject private var navCoordinator = NavigationCoordinator.shared
    @State private var activeIngredientMolecules: [MoleculeBasic] = []
    @State private var isLoadingMolecules = false
    @State private var errorMessage: String?
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Breadcrumb
                BreadcrumbView(coordinator: navCoordinator)
                
                Divider()
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(drug.name)
                                .appFont(.largeTitle)
                                .fontWeight(.bold)
                            
                            Spacer()
                        }
                        
                        if let genericName = drug.genericName, genericName != drug.name {
                            Text(genericName)
                                .appFont(.title3)
                                .foregroundColor(.secondary)
                        }
                        
                        // Brand names
                        if let brandNames = drug.brandNames, !brandNames.isEmpty {
                            HStack(spacing: 8) {
                                Text("Brand names:")
                                    .appFont(.subheadline)
                                    .foregroundColor(.secondary)
                                ForEach(brandNames, id: \.self) { brand in
                                    Text(brand)
                                        .appFont(.subheadline)
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

                    // ChEMBL-driven rich detail (structure, properties, synonyms,
                    // indications, similar drugs). Appears for any drug with a
                    // ChEMBL ID — includes drugs newly cached via the live
                    // /search/drugs ChEMBL fallback. Loads in its own .task so
                    // it never blocks the rest of the page.
                    if let chembl = drug.chemblId, !chembl.isEmpty {
                        HStack(spacing: 12) {
                            Label(chembl, systemImage: "barcode")
                                .appFont(.caption, monospaced: true)
                                .foregroundColor(.secondary)
                            if let url = URL(string: "https://www.ebi.ac.uk/chembl/explore/compound/\(chembl)") {
                                Link(destination: url) {
                                    Label("Open in ChEMBL", systemImage: "arrow.up.right.square")
                                        .appFont(.caption)
                                }
                            }
                        }
                        ChEMBLDetailPanel(chemblId: chembl)
                        Divider()
                    }

                    // Description — hide when it's the auto-generated placeholder
                    // ("ChEMBL max_phase=...; Small molecule") that the live
                    // search write-through wrote, since the rich panel above
                    // already conveys that info more clearly.
                    if let description = drug.description, !description.isEmpty,
                       !description.hasPrefix("ChEMBL max_phase=") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Description")
                                .appFont(.headline)
                            Text(description)
                                .appFont(.body)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Indication
                    if let indication = drug.indication, !indication.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Indication")
                                .appFont(.headline)
                            Text(indication)
                                .appFont(.body)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Dosage form and route
                    if let dosageForm = drug.dosageForm, let route = drug.route {
                        HStack(spacing: 16) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Dosage Form")
                                    .appFont(.caption)
                                    .foregroundColor(.secondary)
                                Text(dosageForm)
                                    .appFont(.body)
                            }
                            
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Route")
                                    .appFont(.caption)
                                    .foregroundColor(.secondary)
                                Text(route)
                                    .appFont(.body)
                            }
                        }
                    }
                    
                    // Active ingredients — only render when the drug actually
                    // has active-ingredient molecule indices to load (legacy
                    // FDA-style drugs). For ChEMBL-cached drugs, the rich
                    // panel above already shows the molecular structure.
                    if let indices = drug.activeIngredientMoleculeIndices, !indices.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Active Ingredients")
                                .appFont(.headline)

                            if isLoadingMolecules {
                                ProgressView("Loading active ingredients...")
                                    .frame(maxWidth: .infinity)
                                    .padding()
                            } else if !backendService.isBackendRunning {
                                Text("Backend is not running. Please start the backend to load active ingredients.")
                                    .appFont(.caption)
                                    .foregroundColor(.orange)
                                    .padding()
                            } else if let error = errorMessage {
                                Text("Error: \(error)")
                                    .appFont(.caption)
                                    .foregroundColor(.red)
                                    .padding()
                            } else if activeIngredientMolecules.isEmpty {
                                Text("No active ingredient molecules found")
                                    .appFont(.caption)
                                    .foregroundColor(.secondary)
                                    .padding()
                            } else {
                                LazyVGrid(columns: [
                                    GridItem(.adaptive(minimum: 200), spacing: 16)
                                ], spacing: 16) {
                                    ForEach(activeIngredientMolecules) { molecule in
                                        NavigationLink(value: Molecule(
                                            id: molecule.id,
                                            chemblId: molecule.chemblId,
                                            name: molecule.name,
                                            smiles: molecule.smiles,
                                            similarity: 1.0,
                                            similarityScore: 0.0,
                                            molecularWeight: molecule.molecularWeight,
                                            isApproved: molecule.isApproved,
                                            formula: molecule.formula
                                        )) {
                                            MoleculeCard(molecule: molecule) {
                                                // Navigation handled by NavigationLink
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    
                    // Inactive ingredients
                    if let inactiveIngredients = drug.inactiveIngredients, !inactiveIngredients.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Inactive Ingredients")
                                .appFont(.headline)
                            Text(inactiveIngredients.joined(separator: ", "))
                                .appFont(.body)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // External identifiers (PubChem CID / DrugBank). Hide the
                    // whole section when neither is set — the ChEMBL ID is
                    // already surfaced by the rich panel above.
                    if drug.pubchemCid != nil || drug.drugbankId != nil {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Identifiers")
                                .appFont(.headline)

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
                }
                .padding()
            }
        .navigationTitle("Drug Details")
        .frame(minWidth: 700, minHeight: 600)
        .onAppear {
            print("🟡 DrugDetailView onAppear - pushing drug breadcrumb: \(drug.name)")
            navCoordinator.push(BreadcrumbItem(
                title: drug.name,
                icon: "pills",
                type: .drug
            ))
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

