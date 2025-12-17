//
//  DrugCard.swift
//  BioNeighbor
//
//  Card component for displaying drugs
//

import SwiftUI

struct DrugCard: View {
    let drug: Drug
    var onTap: (() -> Void)?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Drug name header
            VStack(alignment: .leading, spacing: 4) {
                Text(drug.name)
                    .font(.headline)
                    .lineLimit(2)
                
                if let genericName = drug.genericName, genericName != drug.name {
                    Text(genericName)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                
                // Brand names
                if let brandNames = drug.brandNames, !brandNames.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(brandNames.prefix(3), id: \.self) { brand in
                            Text(brand)
                                .font(.caption)
                                .foregroundColor(.blue)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.blue.opacity(0.1))
                                .cornerRadius(4)
                        }
                        if brandNames.count > 3 {
                            Text("+\(brandNames.count - 3)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
            }
            
            Divider()
            
            // Indication
            if let indication = drug.indication, !indication.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Indication")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(indication)
                        .font(.caption)
                        .lineLimit(2)
                }
            }
            
            // Active ingredients count
            if let activeIndices = drug.activeIngredientMoleculeIndices, !activeIndices.isEmpty {
                HStack {
                    Image(systemName: "molecule")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("\(activeIndices.count) active ingredient\(activeIndices.count == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.1), radius: 2, x: 0, y: 1)
        .contentShape(Rectangle())
    }
}

#Preview {
    DrugCard(
        drug: Drug(
            id: 1,
            name: "Donepezil",
            genericName: "Donepezil",
            brandNames: ["Aricept"],
            pubchemCid: "3152",
            drugbankId: nil,
            description: "Acetylcholinesterase inhibitor",
            indication: "Alzheimer's disease",
            activeIngredientMoleculeIndices: [1, 2],
            inactiveIngredients: ["lactose", "starch"],
            dosageForm: "Tablet",
            route: "Oral"
        )
    )
    .padding()
}

