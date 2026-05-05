//
//  CancerDrugDetailView.swift
//  BioNeighbor
//
//  v2 disease-first browse: detail page for a single drug picked from
//  SubtypeDrugsView. Shows drug header (name, ChEMBL ID, phase) and a
//  "Similar Drugs" section powered by the existing FAISS+RDKit engine via
//  /cancer-research/v2/drugs/<chembl_id>/similar.
//

import SwiftUI

struct CancerDrugDetailView: View {
    let drug: SubtypeTopDrug

    @StateObject private var backendService = BackendService.shared
    @State private var similar: [SimilarDrugHit] = []
    @State private var isLoading = false
    @State private var notInLocalIndex = false
    @State private var errorMessage: String?

    private let columns = [
        GridItem(.adaptive(minimum: 200, maximum: 240), spacing: 12)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                Divider()
                similarSection
            }
            .padding(20)
        }
        .navigationTitle(drug.drugName)
        .task { await loadSimilar() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(drug.drugName)
                    .font(.title2)
                    .fontWeight(.semibold)
                Spacer()
                phaseBadge
            }

            HStack(spacing: 12) {
                if let chembl = drug.chemblId {
                    Label(chembl, systemImage: "barcode")
                        .font(.caption.monospaced())
                        .foregroundColor(.secondary)
                }
                if let source = drug.source {
                    Label(source.replacingOccurrences(of: "_", with: " ").capitalized,
                          systemImage: "checkmark.seal")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                if let count = drug.sourceCount, count > 1 {
                    Text("\(count) sources agree")
                        .font(.caption)
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
                        .font(.caption)
                }
            }
        }
    }

    @ViewBuilder
    private var phaseBadge: some View {
        if let phase = drug.maxPhase, phase > 0 {
            let label: String = {
                switch phase {
                case 4: return "FDA Approved"
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
                .font(.caption.bold())
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .clipShape(Capsule())
        }
    }

    private var similarSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Molecularly Similar Drugs")
                    .font(.headline)
                Spacer()
                if !similar.isEmpty {
                    Text("\(similar.count) hits")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Text("Top-K nearest neighbors from the local FAISS index using Morgan fingerprints (ECFP4).")
                .font(.caption)
                .foregroundColor(.secondary)

            if isLoading {
                ProgressView("Searching local index…")
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if let error = errorMessage {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundColor(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { Task { await loadSimilar() } }
                        .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else if notInLocalIndex {
                VStack(spacing: 6) {
                    Image(systemName: "questionmark.circle")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("Not in the local molecule index")
                        .font(.subheadline)
                    Text("This drug exists in ChEMBL but hasn't been ingested into the local FAISS index. Use Download Data → Molecules to add ChEMBL compounds.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else if similar.isEmpty {
                Text("No similar drugs found.")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 80)
            } else {
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(similar) { hit in
                        SimilarDrugTile(hit: hit)
                    }
                }
            }
        }
    }

    @MainActor
    private func loadSimilar() async {
        guard let chembl = drug.chemblId, !chembl.isEmpty else {
            notInLocalIndex = true
            return
        }
        isLoading = true
        errorMessage = nil
        notInLocalIndex = false
        defer { isLoading = false }
        do {
            let result = try await backendService.fetchSimilarDrugs(chemblId: chembl, topK: 20)
            similar = result.drugs
            notInLocalIndex = result.notInLocalIndex
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct SimilarDrugTile: View {
    let hit: SimilarDrugHit

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(hit.name ?? "Unknown")
                    .font(.subheadline.bold())
                    .lineLimit(2)
                Spacer()
                if let sim = displayedSimilarity {
                    Text(String(format: "%.2f", sim))
                        .font(.caption.monospaced())
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .foregroundColor(.accentColor)
                        .clipShape(Capsule())
                }
            }
            if let chembl = hit.chemblId {
                Text(chembl)
                    .font(.caption.monospaced())
                    .foregroundColor(.secondary)
            }
            if let smiles = hit.smiles {
                Text(smiles)
                    .font(.caption2.monospaced())
                    .foregroundColor(.secondary)
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    private var displayedSimilarity: Double? {
        // Engine returns either `similarity` or `similarity_score` depending on path.
        if let s = hit.similarity { return s }
        return hit.similarityScore
    }
}
