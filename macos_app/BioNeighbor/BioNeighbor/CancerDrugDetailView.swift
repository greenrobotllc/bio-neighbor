//
//  CancerDrugDetailView.swift
//  BioNeighbor
//
//  v2 disease-first browse: detail page for a single drug picked from
//  SubtypeDrugsView. The header carries cancer-research-specific context
//  (the cached phase + source + ChEMBL link); everything below is rendered
//  by the shared ChEMBLDetailPanel which also powers the Drugs tab.
//

import SwiftUI

struct CancerDrugDetailView: View {
    let drug: SubtypeTopDrug

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                Divider()
                if let chembl = drug.chemblId, !chembl.isEmpty {
                    ChEMBLDetailPanel(chemblId: chembl)
                } else {
                    Text("This drug has no ChEMBL ID, so we can't fetch structural or indication detail.")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .padding(20)
        }
        .navigationTitle(drug.drugName)
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(drug.drugName)
                    .appFont(.title2)
                    .fontWeight(.semibold)
                Spacer()
                phaseBadge
            }

            HStack(spacing: 12) {
                Label(drug.chemblId ?? "—", systemImage: "barcode")
                    .appFont(.caption, monospaced: true)
                    .foregroundColor(.secondary)
                if let source = drug.source {
                    Label(source.replacingOccurrences(of: "_", with: " ").capitalized,
                          systemImage: "checkmark.seal")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
                if let count = drug.sourceCount, count > 1 {
                    Text("\(count) sources agree")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }
            }

            if let chembl = drug.chemblId,
               let url = URL(string: "https://www.ebi.ac.uk/chembl/explore/compound/\(chembl)") {
                Link(destination: url) {
                    Label("Open in ChEMBL", systemImage: "arrow.up.right.square")
                        .appFont(.caption)
                }
            }
        }
    }

    @ViewBuilder
    private var phaseBadge: some View {
        if let phase = drug.maxPhase, phase > 0 {
            let label: String = {
                switch phase {
                // ChEMBL's max_phase=4 means "approved/marketed" by *some*
                // regulator, not necessarily FDA — keep the label neutral.
                case 4: return "Approved"
                case 3: return "Phase 3"
                case 2: return "Phase 2"
                case 1: return "Phase 1"
                default: return "Phase \(phase)"
                }
            }()
            let color: Color = {
                switch phase {
                case 4: return .green
                case 3: return .blue
                case 2: return .orange
                case 1: return .yellow
                default: return .gray
                }
            }()
            Text(label)
                .appFont(.caption, weight: .bold)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .clipShape(Capsule())
        }
    }
}
