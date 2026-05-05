//
//  ChEMBLDetailPanel.swift
//  BioNeighbor
//
//  Reusable rich-detail panel for any drug we know by ChEMBL ID. Embedded by
//  both CancerDrugDetailView (Cancer Research tab) and DrugDetailView (global
//  Drugs tab) so a single ChEMBL fetch powers structure preview, molecular
//  properties, synonyms (brand names), indications, and similarity.
//

import SwiftUI

struct ChEMBLDetailPanel: View {
    let chemblId: String

    @StateObject private var backendService = BackendService.shared

    @State private var detail: ChEMBLDrugDetail?
    @State private var detailError: String?
    @State private var isLoadingDetail = false

    @State private var structureImage: NSImage?
    @State private var isLoadingStructure = false

    @State private var similar: [SimilarDrugHit] = []
    @State private var isLoadingSimilar = false
    @State private var similarFetchedFromChEMBL = false
    @State private var similarNotInLocalIndex = false
    @State private var similarError: String?

    private let similarColumns = [
        GridItem(.adaptive(minimum: 200, maximum: 240), spacing: 12)
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            structureAndPropertiesSection
            if let synonyms = detail?.synonyms, !synonyms.isEmpty {
                Divider()
                synonymsSection(synonyms)
            }
            if let indications = detail?.indications, !indications.isEmpty {
                Divider()
                indicationsSection(indications)
            }
            Divider()
            similarSection
        }
        .task(id: chemblId) {
            // Reset when the input changes (panel is reused across drug pushes).
            detail = nil
            detailError = nil
            structureImage = nil
            similar = []
            similarError = nil
            similarFetchedFromChEMBL = false
            similarNotInLocalIndex = false

            async let detailTask: Void = loadDetail()
            async let similarTask: Void = loadSimilar()
            _ = await (detailTask, similarTask)
        }
    }

    // MARK: - Structure + properties

    private var structureAndPropertiesSection: some View {
        HStack(alignment: .top, spacing: 24) {
            structureImageBox
            propertiesPanel
            Spacer()
        }
    }

    private var structureImageBox: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.white)
                .frame(width: 240, height: 240)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
                )

            if let image = structureImage {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 220, height: 220)
            } else if isLoadingStructure || isLoadingDetail {
                ProgressView().scaleEffect(0.8)
            } else if detail?.smiles == nil {
                VStack(spacing: 6) {
                    Image(systemName: "atom").font(.title2).foregroundColor(.secondary)
                    Text("No structure available")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private var propertiesPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Molecular Properties")
                .font(.headline)
                .padding(.bottom, 4)

            if isLoadingDetail && detail == nil {
                ProgressView().scaleEffect(0.7)
            } else if let p = detail?.properties {
                propertyRow("Formula", p.molecularFormula)
                propertyRow("MW", p.molecularWeight.map { String(format: "%.2f g/mol", $0) })
                propertyRow("LogP", p.alogp.map { String(format: "%.2f", $0) })
                if p.hba != nil || p.hbd != nil {
                    propertyRow("HBA / HBD", "\(p.hba?.description ?? "—") / \(p.hbd?.description ?? "—")")
                }
                propertyRow("PSA", p.psa.map { String(format: "%.1f Å²", $0) })
                propertyRow("Lipinski violations", p.ro5Violations.map { "\($0)" })
                propertyRow("Rotatable bonds", p.rotatableBonds.map { "\($0)" })
                propertyRow("QED", p.qedWeighted.map { String(format: "%.2f", $0) })
            } else if let err = detailError {
                Text(err)
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                Text("No properties available")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    @ViewBuilder
    private func propertyRow(_ label: String, _ value: String?) -> some View {
        if let value = value, !value.isEmpty {
            HStack(alignment: .firstTextBaseline) {
                Text(label)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(width: 140, alignment: .leading)
                Text(value)
                    .font(.subheadline)
                    .textSelection(.enabled)
            }
        }
    }

    // MARK: - Synonyms

    private func synonymsSection(_ synonyms: [ChEMBLSynonym]) -> some View {
        let priority: [String] = ["TRADE_NAME", "INN", "USAN", "BAN", "JAN", "ATC", "MERCK_INDEX"]
        let grouped = Dictionary(grouping: synonyms) { $0.type }
        let primaryTypes = priority.filter { grouped[$0] != nil }
        let researchCodes = grouped["RESEARCH_CODE"] ?? []

        return VStack(alignment: .leading, spacing: 8) {
            Text("Names")
                .font(.headline)
            FlowLayout(spacing: 6) {
                ForEach(primaryTypes, id: \.self) { type in
                    if let entries = grouped[type] {
                        ForEach(uniqueByName(entries), id: \.name) { syn in
                            synonymChip(syn, isBrand: type == "TRADE_NAME")
                        }
                    }
                }
            }
            if !researchCodes.isEmpty {
                DisclosureGroup("\(researchCodes.count) research code\(researchCodes.count == 1 ? "" : "s")") {
                    FlowLayout(spacing: 6) {
                        ForEach(uniqueByName(researchCodes), id: \.name) { syn in
                            Text(syn.name)
                                .font(.caption.monospaced())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.secondary.opacity(0.10))
                                .foregroundColor(.secondary)
                                .clipShape(Capsule())
                        }
                    }
                    .padding(.top, 4)
                }
                .font(.caption)
                .foregroundColor(.secondary)
            }
        }
    }

    private func uniqueByName(_ syns: [ChEMBLSynonym]) -> [ChEMBLSynonym] {
        var seen = Set<String>()
        var out: [ChEMBLSynonym] = []
        for s in syns {
            let k = s.name.lowercased()
            if seen.insert(k).inserted { out.append(s) }
        }
        return out
    }

    private func synonymChip(_ syn: ChEMBLSynonym, isBrand: Bool) -> some View {
        HStack(spacing: 4) {
            Text(syn.type.replacingOccurrences(of: "_", with: " "))
                .font(.caption2)
                .foregroundColor(isBrand ? .green.opacity(0.9) : .secondary)
            Text(syn.name)
                .font(.caption.bold())
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background((isBrand ? Color.green : Color.accentColor).opacity(0.12))
        .foregroundColor(isBrand ? .green : .accentColor)
        .clipShape(Capsule())
    }

    // MARK: - Indications

    private func indicationsSection(_ indications: [ChEMBLIndication]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Indications")
                    .font(.headline)
                Spacer()
                Text("\(indications.count) from ChEMBL")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Text("Conditions ChEMBL has linked to this drug, with the highest clinical phase reached. Sorted by phase.")
                .font(.caption)
                .foregroundColor(.secondary)

            LazyVStack(spacing: 4) {
                ForEach(indications) { ind in
                    IndicationRow(indication: ind)
                }
            }
        }
    }

    // MARK: - Similar Drugs

    private var similarSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Molecularly Similar Drugs")
                    .font(.headline)
                Spacer()
                if similarFetchedFromChEMBL {
                    Label("via ChEMBL", systemImage: "checkmark.seal")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if !similar.isEmpty {
                    Text("\(similar.count) hits")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Text("Top-K nearest neighbors from the local FAISS index using Morgan fingerprints (ECFP4).")
                .font(.caption)
                .foregroundColor(.secondary)

            if isLoadingSimilar {
                ProgressView("Searching local index…")
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if let error = similarError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundColor(.orange)
                    Text(error).font(.caption).foregroundColor(.secondary).multilineTextAlignment(.center)
                    Button("Retry") { Task { await loadSimilar() } }
                        .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else if similarNotInLocalIndex {
                VStack(spacing: 6) {
                    Image(systemName: "questionmark.circle")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("Couldn't fetch SMILES from ChEMBL")
                        .font(.subheadline)
                    Text("ChEMBL has no canonical structure for this drug. The similarity search needs a SMILES string.")
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
                LazyVGrid(columns: similarColumns, spacing: 12) {
                    ForEach(similar) { hit in
                        SimilarDrugTile(hit: hit)
                    }
                }
            }
        }
    }

    // MARK: - Loaders

    @MainActor
    private func loadDetail() async {
        isLoadingDetail = true
        detailError = nil
        defer { isLoadingDetail = false }
        do {
            let result = try await backendService.fetchChEMBLDrugDetail(chemblId: chemblId)
            detail = result
            if let smiles = result.smiles {
                await renderStructure(smiles: smiles)
            }
        } catch {
            detailError = error.localizedDescription
        }
    }

    @MainActor
    private func renderStructure(smiles: String) async {
        isLoadingStructure = true
        defer { isLoadingStructure = false }
        do {
            structureImage = try await backendService.renderMolecule(smiles: smiles, width: 440, height: 440)
        } catch {
            structureImage = nil
        }
    }

    @MainActor
    private func loadSimilar() async {
        isLoadingSimilar = true
        similarError = nil
        similarNotInLocalIndex = false
        defer { isLoadingSimilar = false }
        do {
            let result = try await backendService.fetchSimilarDrugs(chemblId: chemblId, topK: 20)
            similar = result.drugs
            similarNotInLocalIndex = result.notInLocalIndex
            similarFetchedFromChEMBL = !result.drugs.isEmpty
        } catch {
            similarError = error.localizedDescription
        }
    }
}

// MARK: - Supporting views (shared with CancerDrugDetailView etc.)

struct IndicationRow: View {
    let indication: ChEMBLIndication

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(indication.meshHeading ?? indication.efoTerm ?? "Unknown")
                .font(.subheadline)
                .lineLimit(2)
            if let mesh = indication.meshId {
                Text(mesh)
                    .font(.caption2.monospaced())
                    .foregroundColor(.secondary)
            }
            Spacer()
            if let refs = indication.refCount, refs > 0 {
                Text("\(refs) ref\(refs == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            phaseChip
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color(NSColor.controlBackgroundColor).opacity(0.5))
        )
    }

    @ViewBuilder
    private var phaseChip: some View {
        if let phase = indication.maxPhase, phase > 0 {
            let label = phase == 4 ? "Approved" : "Phase \(phase)"
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
                .font(.caption2.bold())
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .clipShape(Capsule())
        }
    }
}

struct SimilarDrugTile: View {
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
            if let chembl = hit.chemblId, isRealChemblId(chembl) {
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
        if let s = hit.similarity { return s }
        return hit.similarityScore
    }

    /// The local FAISS index uses numeric placeholders for many molecules
    /// (e.g. "2187"). Only show the chembl_id label when it's a real ChEMBL ID.
    private func isRealChemblId(_ value: String) -> Bool {
        guard value.uppercased().hasPrefix("CHEMBL") else { return false }
        let suffix = value.dropFirst("CHEMBL".count)
        return !suffix.isEmpty && suffix.allSatisfy { $0.isNumber }
    }
}
