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

    @State private var trials: [ClinicalTrial] = []
    @State private var isLoadingTrials = false
    @State private var trialsError: String?

    // Page-wide find — focused by ⌘F. Filters indications, trials, and the
    // similar drugs grid by case-insensitive substring match across the
    // searchable fields of each.
    @State private var findQuery: String = ""
    @FocusState private var findFocused: Bool

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
            findSection
            if let indications = detail?.indications, !indications.isEmpty {
                Divider()
                indicationsSection(filteredIndications(indications))
            }
            Divider()
            trialsSection
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
            trials = []
            trialsError = nil
            findQuery = ""

            async let detailTask: Void = loadDetail()
            async let similarTask: Void = loadSimilar()
            async let trialsTask: Void = loadTrials()
            _ = await (detailTask, similarTask, trialsTask)
        }
        .onReceive(NotificationCenter.default.publisher(for: .cancerFindDrug)) { _ in
            findFocused = true
        }
    }

    // MARK: - Page-wide find

    private var findSection: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)
            TextField("Find on this page — trials, indications, similar drugs (⌘F)", text: $findQuery)
                .textFieldStyle(.plain)
                .focused($findFocused)
            if !findQuery.isEmpty {
                Button {
                    findQuery = ""
                    findFocused = true
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(findFocused ? Color.accentColor : Color.secondary.opacity(0.2), lineWidth: 1)
        )
    }

    private var normalizedFind: String {
        findQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func filteredIndications(_ all: [ChEMBLIndication]) -> [ChEMBLIndication] {
        let q = normalizedFind
        guard !q.isEmpty else { return all }
        return all.filter { ind in
            (ind.meshHeading ?? "").lowercased().contains(q) ||
            (ind.efoTerm ?? "").lowercased().contains(q) ||
            (ind.meshId ?? "").lowercased().contains(q)
        }
    }

    private func filteredTrials(_ all: [ClinicalTrial]) -> [ClinicalTrial] {
        let q = normalizedFind
        guard !q.isEmpty else { return all }
        return all.filter { trial in
            if (trial.title ?? "").lowercased().contains(q) { return true }
            if trial.nctId.lowercased().contains(q) { return true }
            if (trial.status ?? "").lowercased().contains(q) { return true }
            if let arms = trial.arms {
                for arm in arms {
                    if (arm.label ?? "").lowercased().contains(q) { return true }
                    if let interventions = arm.interventions,
                       interventions.contains(where: { $0.lowercased().contains(q) }) {
                        return true
                    }
                }
            }
            if let outcomes = trial.primaryOutcomes {
                for outcome in outcomes {
                    if (outcome.title ?? "").lowercased().contains(q) { return true }
                }
            }
            return false
        }
    }

    private func filteredSimilar(_ all: [SimilarDrugHit]) -> [SimilarDrugHit] {
        let q = normalizedFind
        guard !q.isEmpty else { return all }
        return all.filter { hit in
            (hit.name ?? "").lowercased().contains(q) ||
            (hit.chemblId ?? "").lowercased().contains(q)
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
                    Image(systemName: "atom").appFont(.title2).foregroundColor(.secondary)
                    Text("No structure available")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private var propertiesPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Molecular Properties")
                .appFont(.headline)
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
                    .appFont(.caption)
                    .foregroundColor(.secondary)
            } else {
                Text("No properties available")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    @ViewBuilder
    private func propertyRow(_ label: String, _ value: String?) -> some View {
        if let value = value, !value.isEmpty {
            HStack(alignment: .firstTextBaseline) {
                Text(label)
                    .appFont(.caption)
                    .foregroundColor(.secondary)
                    .frame(width: 140, alignment: .leading)
                Text(value)
                    .appFont(.subheadline)
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
                .appFont(.headline)
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
                                .appFont(.caption, monospaced: true)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.secondary.opacity(0.10))
                                .foregroundColor(.secondary)
                                .clipShape(Capsule())
                        }
                    }
                    .padding(.top, 4)
                }
                .appFont(.caption)
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
                .appFont(.caption2)
                .foregroundColor(isBrand ? .green.opacity(0.9) : .secondary)
            Text(syn.name)
                .appFont(.caption, weight: .bold)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background((isBrand ? Color.green : Color.accentColor).opacity(0.12))
        .foregroundColor(isBrand ? .green : .accentColor)
        .clipShape(Capsule())
    }

    // MARK: - Indications

    private func indicationsSection(_ indications: [ChEMBLIndication]) -> some View {
        let total = detail?.indications?.count ?? indications.count
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Indications")
                    .appFont(.headline)
                Spacer()
                if !normalizedFind.isEmpty && total != indications.count {
                    Text("\(indications.count) of \(total)")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                } else {
                    Text("\(total) from ChEMBL")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Text("Conditions ChEMBL has linked to this drug, with the highest clinical phase reached. Sorted by phase.")
                .appFont(.caption)
                .foregroundColor(.secondary)

            if indications.isEmpty {
                Text("No indications match \u{201C}\(findQuery)\u{201D}.")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 40)
            } else {
                LazyVStack(spacing: 4) {
                    ForEach(indications) { ind in
                        IndicationRow(indication: ind)
                    }
                }
            }
        }
    }

    // MARK: - Clinical Trial Outcomes

    private var trialsSection: some View {
        let visibleTrials = filteredTrials(trials)
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Clinical Trial Outcomes")
                    .appFont(.headline)
                Spacer()
                if !trials.isEmpty {
                    if !normalizedFind.isEmpty {
                        Text("\(visibleTrials.count) of \(trials.count)")
                            .appFont(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text("\(trials.count) trial\(trials.count == 1 ? "" : "s")")
                            .appFont(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            Text("Trial arms with reported primary outcomes from ClinicalTrials.gov. Arms including this drug are highlighted; multi-arm trials let you compare regimens (e.g. backbone vs backbone + this drug).")
                .appFont(.caption)
                .foregroundColor(.secondary)

            if isLoadingTrials {
                ProgressView("Loading trials from ClinicalTrials.gov…")
                    .frame(maxWidth: .infinity, minHeight: 100)
            } else if let err = trialsError {
                VStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle").foregroundColor(.orange)
                    Text(err).appFont(.caption).foregroundColor(.secondary).multilineTextAlignment(.center)
                    Button("Retry") { Task { await loadTrials() } }.buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, minHeight: 100)
            } else if trials.isEmpty {
                Text("No linked clinical trials found for this drug.")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 60)
            } else if visibleTrials.isEmpty {
                Text("No trials match \u{201C}\(findQuery)\u{201D}.")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 60)
            } else {
                LazyVStack(spacing: 12) {
                    ForEach(visibleTrials) { trial in
                        TrialCard(trial: trial, currentDrugName: detail?.prefName ?? detail?.parentPrefName)
                    }
                }
            }
        }
    }

    @MainActor
    private func loadTrials() async {
        isLoadingTrials = true
        trialsError = nil
        defer { isLoadingTrials = false }
        do {
            trials = try await backendService.fetchClinicalTrials(chemblId: chemblId, limit: 15)
        } catch {
            trialsError = error.localizedDescription
        }
    }

    // MARK: - Similar Drugs

    private var similarSection: some View {
        let visibleSimilar = filteredSimilar(similar)
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Molecularly Similar Drugs")
                    .appFont(.headline)
                Spacer()
                if similarFetchedFromChEMBL {
                    Label("via ChEMBL", systemImage: "checkmark.seal")
                        .appFont(.caption2)
                        .foregroundColor(.secondary)
                }
                if !similar.isEmpty {
                    if !normalizedFind.isEmpty {
                        Text("\(visibleSimilar.count) of \(similar.count)")
                            .appFont(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text("\(similar.count) hits")
                            .appFont(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            Text("Top-K nearest neighbors from the local FAISS index using Morgan fingerprints (ECFP4).")
                .appFont(.caption)
                .foregroundColor(.secondary)

            if isLoadingSimilar {
                ProgressView("Searching local index…")
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if let error = similarError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundColor(.orange)
                    Text(error).appFont(.caption).foregroundColor(.secondary).multilineTextAlignment(.center)
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
                        .appFont(.subheadline)
                    Text("ChEMBL has no canonical structure for this drug. The similarity search needs a SMILES string.")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            } else if similar.isEmpty {
                Text("No similar drugs found.")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 80)
            } else if visibleSimilar.isEmpty {
                Text("No similar drugs match \u{201C}\(findQuery)\u{201D}.")
                    .foregroundColor(.secondary)
                    .appFont(.caption)
                    .frame(maxWidth: .infinity, minHeight: 60)
            } else {
                LazyVGrid(columns: similarColumns, spacing: 12) {
                    ForEach(visibleSimilar) { hit in
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
                .appFont(.subheadline)
                .lineLimit(2)
            if let mesh = indication.meshId {
                Text(mesh)
                    .appFont(.caption2, monospaced: true)
                    .foregroundColor(.secondary)
            }
            Spacer()
            if let refs = indication.refCount, refs > 0 {
                Text("\(refs) ref\(refs == 1 ? "" : "s")")
                    .appFont(.caption2)
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
                .appFont(.caption2, weight: .bold)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .clipShape(Capsule())
        }
    }
}

// MARK: - Trial card / arm row / outcome row

struct TrialCard: View {
    let trial: ClinicalTrial
    let currentDrugName: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header — title + NCT link + status chip
            HStack(alignment: .firstTextBaseline) {
                Text(trial.title ?? trial.nctId)
                    .appFont(.subheadline, weight: .bold)
                    .lineLimit(2)
                Spacer()
                statusChip
            }

            HStack(spacing: 10) {
                if let url = URL(string: "https://clinicaltrials.gov/study/\(trial.nctId)") {
                    Link(trial.nctId, destination: url)
                        .appFont(.caption, monospaced: true)
                }
                if let phases = trial.phase, !phases.isEmpty {
                    Text(phases.joined(separator: ", "))
                        .appFont(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .foregroundColor(.secondary)
                        .clipShape(Capsule())
                }
            }

            // Arms — current drug highlighted
            if let arms = trial.arms, !arms.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(arms) { arm in
                        TrialArmRow(arm: arm, currentDrugName: currentDrugName)
                    }
                }
            }

            // Primary outcomes with arm-level results
            if let outcomes = trial.primaryOutcomes, !outcomes.isEmpty {
                ForEach(outcomes) { outcome in
                    TrialOutcomeRow(outcome: outcome)
                }
            } else if !(trial.hasResults ?? false) {
                Text("Results not yet reported")
                    .appFont(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    @ViewBuilder
    private var statusChip: some View {
        if let status = trial.status {
            let color: Color = {
                switch status {
                case "COMPLETED": return .green
                case "ACTIVE_NOT_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION": return .blue
                case "TERMINATED", "WITHDRAWN", "SUSPENDED": return .orange
                default: return .gray
                }
            }()
            Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
                .appFont(.caption2, weight: .bold)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .clipShape(Capsule())
        }
    }
}

private struct TrialArmRow: View {
    let arm: ClinicalTrialArm
    let currentDrugName: String?

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: containsCurrentDrug ? "checkmark.circle.fill" : "circle")
                .foregroundColor(containsCurrentDrug ? .accentColor : .secondary.opacity(0.5))
                .appFont(.caption)
            VStack(alignment: .leading, spacing: 2) {
                Text(arm.label ?? "—")
                    .appFont(.caption, weight: .bold)
                if let interventions = arm.interventions, !interventions.isEmpty {
                    Text(interventions.joined(separator: " + "))
                        .appFont(.caption2)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }
            Spacer()
        }
    }

    private var containsCurrentDrug: Bool {
        guard let drugName = currentDrugName?.lowercased(), !drugName.isEmpty,
              let interventions = arm.interventions else { return false }
        // Match the drug name as a token within any intervention string. Trial
        // sponsors sometimes use research codes (LEE011 = ribociclib) which
        // won't match — that's fine, we just don't highlight.
        return interventions.contains { intervention in
            intervention.lowercased().contains(drugName)
        }
    }
}

private struct TrialOutcomeRow: View {
    let outcome: ClinicalTrialOutcome

    /// CI-overlap analysis across all arms with parseable numeric (value, lower, upper).
    /// nil → not enough numeric data to call.
    /// .distinct → no two arms have overlapping CIs (likely real difference).
    /// .overlap → at least one pair of arms has overlapping CIs (interpret with caution).
    private enum CIStatus { case distinct, overlap }

    private var ciStatus: CIStatus? {
        let parsed = (outcome.armResults ?? []).compactMap { r -> (lo: Double, hi: Double)? in
            guard let lo = Double(r.lower ?? ""),
                  let hi = Double(r.upper ?? ""),
                  lo.isFinite, hi.isFinite else { return nil }
            return (min(lo, hi), max(lo, hi))
        }
        guard parsed.count >= 2 else { return nil }
        for i in 0..<parsed.count {
            for j in (i + 1)..<parsed.count {
                let a = parsed[i], b = parsed[j]
                // Closed-interval overlap: a.lo <= b.hi && b.lo <= a.hi.
                if a.lo <= b.hi && b.lo <= a.hi { return .overlap }
            }
        }
        return .distinct
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text("Primary")
                    .appFont(.caption2, weight: .bold)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.blue.opacity(0.15))
                    .foregroundColor(.blue)
                    .clipShape(Capsule())
                Text(outcome.title ?? "—")
                    .appFont(.caption)
                    .lineLimit(2)
                if let unit = outcome.unit, !unit.isEmpty {
                    Text("(\(unit))")
                        .appFont(.caption2)
                        .foregroundColor(.secondary)
                }
                Spacer()
                ciStatusBadge
            }
            ForEach(outcome.armResults ?? [], id: \.armLabel) { result in
                HStack(alignment: .firstTextBaseline) {
                    Text(result.armLabel ?? "?")
                        .appFont(.caption2)
                        .lineLimit(2)
                    Spacer()
                    if let value = result.value, !value.isEmpty {
                        Text(value)
                            .appFont(.caption, monospaced: true)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 1)
                            .background(Color.green.opacity(0.12))
                            .foregroundColor(.green)
                            .clipShape(Capsule())
                    }
                    if let l = result.lower, let u = result.upper,
                       l.uppercased() != "NA" && u.uppercased() != "NA" {
                        Text("(\(l)–\(u))")
                            .appFont(.caption2, monospaced: true)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(6)
    }

    @ViewBuilder
    private var ciStatusBadge: some View {
        switch ciStatus {
        case .distinct:
            Label("Distinct CIs", systemImage: "checkmark.circle.fill")
                .appFont(.caption2, weight: .bold)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.green.opacity(0.15))
                .foregroundColor(.green)
                .clipShape(Capsule())
                .help("The 95% confidence intervals do not overlap — the difference between arms is likely real, not chance.")
        case .overlap:
            Label("CIs overlap", systemImage: "exclamationmark.triangle.fill")
                .appFont(.caption2, weight: .bold)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.yellow.opacity(0.18))
                .foregroundColor(.orange)
                .clipShape(Capsule())
                .help("The 95% confidence intervals overlap — the apparent difference between arms could be due to chance. Check the trial's reported p-value or hazard ratio for the formal call.")
        case .none:
            EmptyView()
        }
    }
}

struct SimilarDrugTile: View {
    let hit: SimilarDrugHit

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(hit.name ?? "Unknown")
                    .appFont(.subheadline, weight: .bold)
                    .lineLimit(2)
                Spacer()
                if let sim = displayedSimilarity {
                    Text(String(format: "%.2f", sim))
                        .appFont(.caption, monospaced: true)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .foregroundColor(.accentColor)
                        .clipShape(Capsule())
                }
            }
            if let chembl = hit.chemblId, isRealChemblId(chembl) {
                Text(chembl)
                    .appFont(.caption, monospaced: true)
                    .foregroundColor(.secondary)
            }
            if let smiles = hit.smiles {
                Text(smiles)
                    .appFont(.caption2, monospaced: true)
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
