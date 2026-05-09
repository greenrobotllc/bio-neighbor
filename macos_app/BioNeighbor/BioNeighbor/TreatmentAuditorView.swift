//
//  TreatmentAuditorView.swift
//  BioNeighbor
//
//  Treatment Auditor (issue #45 + #49 + multi-source modality search).
//  Single-screen workflow where the user describes their cancer treatment
//  plan — disease/subtype, stage + free-text stage detail, prescribed
//  drugs, scheduled treatments, symptoms/side effects — and the on-device
//  AI runs a multi-pass audit:
//    1. Fetches NCI PDQ standard-of-care text for the cancer type.
//    2. Searches ClinicalTrials.gov for radiation / surgery / chemo /
//       targeted-therapy trials in the subtype (independent of the
//       prescribed drugs).
//    3. Fetches per-drug trials for each prescribed drug.
//    4. Streams a per-source mini-summary from Ollama for each source.
//    5. Streams a final synthesis combining all summaries with explicit
//       "Further reading" citations.
//
//  Each step is shown as a progress row so the wait feels like work.
//  State is ephemeral (@State); nothing persists across launches.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct TreatmentAuditorView: View {
    @StateObject private var backendService = BackendService.shared
    @AppStorage("ollamaEnabled") private var ollamaEnabled: Bool = false

    // Disease selection
    @State private var selectedCancerType: CancerType?
    @State private var selectedSubtype: CancerSubtype?
    @State private var showDiseasePicker = false

    // Stage (v2)
    @State private var selectedStage: StageOption = .unspecified
    @State private var stageDetail: String = ""

    // Drug selection
    @State private var drugQuery: String = ""
    @State private var drugResults: [DrugSearchResult] = []
    @State private var isSearchingDrugs = false
    @State private var drugSearchError: String?
    @State private var prescribedDrugs: [PrescribedDrug] = []

    // Treatments + symptoms
    @State private var treatmentDraft: String = ""
    @State private var treatments: [ScheduledTreatment] = []
    @State private var symptomDraft: String = ""
    @State private var symptomSeverity: SymptomSeverity = .moderate
    @State private var symptoms: [SymptomEntry] = []

    // Audit run state
    @State private var auditTask: Task<Void, Never>?
    @State private var isAuditing = false
    @State private var auditOutput: String = ""
    @State private var auditError: String?
    @State private var auditSteps: [AuditStep] = []
    /// Identifies the in-flight audit run. Cancellation is cooperative —
    /// stale background work (Ollama still flushing buffered chunks, an
    /// in-flight modality fetch, etc.) can land *after* a new audit starts.
    /// Every shared-state mutation guards on this token so an old run can't
    /// clobber the new run's output, steps, or error state.
    @State private var currentAuditRunID: UUID?

    /// Frozen snapshot of the most recent successful audit. Drives the
    /// "Save as PDF…" button (issue #58) — captured at synthesis-success so
    /// the report reflects exactly what the user saw, even if they edit the
    /// form afterwards.
    @State private var completedAudit: CompletedAuditSnapshot?
    @State private var isExportingPDF: Bool = false
    @State private var pdfExportError: String?

    /// Result of the most recent RxNorm dedupe pass (issue #55) — drives
    /// the "Combined" callout above the audit output. Cleared when the
    /// audit is dismissed or a new audit run starts.
    @State private var drugMergeNotes: [DrugMergeNote] = []

    /// Result of the DDInter pairwise drug-drug interaction lookup
    /// (issue #47). Drives a deterministic safety callout above the AI
    /// output. `drugInteractionDataAvailable` distinguishes "no interactions
    /// found" from "DDInter wasn't loaded" — those need very different
    /// UI treatment.
    @State private var drugInteractions: [DrugInteraction] = []
    @State private var drugInteractionUnmatched: [String] = []
    @State private var drugInteractionDataAvailable: Bool = true

    /// Result of the mechanism-of-action target overlap pass (issue #53).
    /// Drives a deterministic callout above the audit output and feeds
    /// the LLM prompt.
    @State private var targetOverlaps: [DrugTargetOverlap] = []
    @State private var targetsByDrug: [DrugTargetsByDrug] = []

    /// Result of the OpenFDA FAERS adverse-event lookup (issue #46) —
    /// per-drug top reactions and symptom→reaction matches. Drives a
    /// UI callout above the audit output and feeds the LLM prompt.
    @State private var faersPanels: [FAERSDrugPanel] = []
    @State private var faersSymptomMatches: [FAERSSymptomMatch] = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                disclaimer
                diseaseSection
                drugsSection
                treatmentsSection
                symptomsSection
                auditSection
            }
            .padding(20)
            .frame(maxWidth: 900, alignment: .leading)
        }
        .frame(maxWidth: .infinity)
        .navigationTitle("Treatment Auditor")
        .sheet(isPresented: $showDiseasePicker) {
            DiseasePickerSheet(
                isPresented: $showDiseasePicker,
                onSelect: { type, subtype in
                    selectedCancerType = type
                    selectedSubtype = subtype
                    showDiseasePicker = false
                }
            )
        }
        .task(id: drugQuery) {
            await runDrugSearch()
        }
    }

    // MARK: - Header / disclaimer

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Treatment Auditor")
                .appFont(.title2, weight: .semibold)
            Text("Describe your treatment plan — disease, drugs, scheduled treatments, side effects — and the on-device AI will cross-reference ClinicalTrials.gov for efficacy signals, alternative regimens, and gaps.")
                .appFont(.subheadline)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var disclaimer: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle")
                .foregroundColor(.secondary)
            Text("Research tool only. Not medical advice. Talk to your oncology team before changing any treatment. Sources: NCI PDQ standard-of-care text + ClinicalTrials.gov (per-drug trials and modality-specific searches), RxNorm (brand→generic dedupe), DDInter (pairwise drug-drug interactions, CC BY-NC-SA, loaded locally), ChEMBL (mechanism-of-action target overlap), and openFDA FAERS (post-market adverse-event reporting). Tumor-mutation matching is a planned follow-up.")
                .appFont(.caption)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.08))
        )
    }

    // MARK: - Disease section

    private var diseaseSection: some View {
        sectionCard(title: "1. Disease", systemImage: "cross.case") {
            if let type = selectedCancerType {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(type.displayName ?? type.name)
                                .appFont(.headline)
                            if let subtype = selectedSubtype {
                                Text(subtype.shortName ?? subtype.name)
                                    .appFont(.subheadline)
                                    .foregroundColor(.secondary)
                            } else {
                                Text("No subtype selected")
                                    .appFont(.caption)
                                    .foregroundColor(.orange)
                            }
                        }
                        Spacer()
                        Button("Change") { showDiseasePicker = true }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    }
                    if let markers = selectedSubtype?.markers, !markers.isEmpty {
                        FlowChips(items: markers)
                    }

                    Divider()
                    stageEntry
                }
            } else {
                Button {
                    showDiseasePicker = true
                } label: {
                    Label("Select cancer type and subtype", systemImage: "plus.circle")
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    /// Stage Picker + free-text "Stage details" field. The free-text field is
    /// always editable (regardless of the picker) so users can describe
    /// metastasis sites, T/N/M codes, recurrence timing, etc. — anything the
    /// picker's coarse buckets can't capture. Both feed the audit prompt.
    private var stageEntry: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text("Stage")
                    .appFont(.subheadline, weight: .semibold)
                Spacer()
                Picker("Stage", selection: $selectedStage) {
                    ForEach(StageOption.allCases) { option in
                        Text(option.label).tag(option)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 220)
                .labelsHidden()
            }

            TextField(
                "Stage details (e.g. metastasized to bone, T2N1M0, recurrent after 3 years)",
                text: $stageDetail,
                axis: .vertical
            )
            .textFieldStyle(.roundedBorder)
            .lineLimit(1...3)

            Text("Both fields are passed to the audit. Leave them blank if unknown — the audit still runs but with weaker stage-specific guidance.")
                .appFont(.caption)
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Drugs section

    private var drugsSection: some View {
        sectionCard(title: "2. Prescribed drugs", systemImage: "pills") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search drug name (e.g. anastrozole)", text: $drugQuery)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit {
                            if let first = drugResults.first { add(drugResult: first) }
                        }
                    if isSearchingDrugs {
                        ProgressView().controlSize(.small)
                    }
                }

                if let err = drugSearchError {
                    Label(err, systemImage: "exclamationmark.triangle")
                        .appFont(.caption)
                        .foregroundColor(.orange)
                }

                if !drugQuery.trimmingCharacters(in: .whitespaces).isEmpty {
                    if drugResults.isEmpty && !isSearchingDrugs && drugSearchError == nil {
                        Text("No matches.")
                            .appFont(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(drugResults.prefix(6)) { result in
                                Button {
                                    add(drugResult: result)
                                } label: {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(result.name.capitalized)
                                                .appFont(.body)
                                            HStack(spacing: 6) {
                                                if let chembl = result.chemblId {
                                                    Text(chembl)
                                                        .appFont(.caption2, monospaced: true)
                                                        .foregroundColor(.secondary)
                                                }
                                                Text(result.source)
                                                    .appFont(.caption2)
                                                    .foregroundColor(.secondary)
                                            }
                                        }
                                        Spacer()
                                        Image(systemName: "plus.circle")
                                            .foregroundColor(.accentColor)
                                    }
                                    .padding(.vertical, 4)
                                    .padding(.horizontal, 8)
                                    .background(
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(Color.secondary.opacity(0.06))
                                    )
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }

                if !prescribedDrugs.isEmpty {
                    Divider()
                    Text("Selected (\(prescribedDrugs.count))")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                    FlowChips(items: prescribedDrugs.map(\.name)) { index in
                        prescribedDrugs.remove(at: index)
                    }
                }

                Text("Drug names link to ChEMBL for trial lookup. Free-text-only entries (no ChEMBL ID) are still included in the audit but won't fetch trials.")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    // MARK: - Treatments section

    private var treatmentsSection: some View {
        sectionCard(title: "3. Scheduled treatments", systemImage: "calendar") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    TextField("e.g. Radiation, 4 weeks; Mastectomy on May 12; AC-T chemo", text: $treatmentDraft)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { addTreatment() }
                    Button("Add") { addTreatment() }
                        .buttonStyle(.bordered)
                        .disabled(treatmentDraft.trimmingCharacters(in: .whitespaces).isEmpty)
                }

                if treatments.isEmpty {
                    Text("None added yet.")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(treatments) { t in
                            HStack {
                                Image(systemName: "calendar.badge.clock")
                                    .foregroundColor(.secondary)
                                Text(t.text)
                                    .appFont(.body)
                                Spacer()
                                Button {
                                    treatments.removeAll { $0.id == t.id }
                                } label: {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundColor(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.vertical, 4)
                            .padding(.horizontal, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.secondary.opacity(0.06))
                            )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Symptoms section

    private var symptomsSection: some View {
        sectionCard(title: "4. Symptoms / side effects", systemImage: "stethoscope") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    TextField("e.g. Fatigue, hot flashes, neuropathy", text: $symptomDraft)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { addSymptom() }
                    Picker("Severity", selection: $symptomSeverity) {
                        ForEach(SymptomSeverity.allCases) { s in
                            Text(s.label).tag(s)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 130)
                    Button("Add") { addSymptom() }
                        .buttonStyle(.bordered)
                        .disabled(symptomDraft.trimmingCharacters(in: .whitespaces).isEmpty)
                }

                if symptoms.isEmpty {
                    Text("None added yet.")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(symptoms) { s in
                            HStack {
                                Image(systemName: "waveform.path.ecg")
                                    .foregroundColor(.secondary)
                                Text(s.text)
                                    .appFont(.body)
                                Text(s.severity.label)
                                    .appFont(.caption2)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(s.severity.color.opacity(0.18))
                                    .foregroundColor(s.severity.color)
                                    .clipShape(Capsule())
                                Spacer()
                                Button {
                                    symptoms.removeAll { $0.id == s.id }
                                } label: {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundColor(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.vertical, 4)
                            .padding(.horizontal, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.secondary.opacity(0.06))
                            )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Audit section

    private var canAudit: Bool {
        selectedCancerType != nil
            && selectedSubtype != nil   // v2 deep audit endpoints (PDQ, modality trials) key on subtype id
            && !prescribedDrugs.isEmpty
            && !isAuditing
    }

    private var auditSection: some View {
        sectionCard(title: "5. Audit", systemImage: "sparkles") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Button {
                        runDeepAudit()
                    } label: {
                        Label(isAuditing ? "Auditing…" : "Run deep audit", systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canAudit)

                    if isAuditing {
                        Button("Cancel") {
                            auditTask?.cancel()
                            auditTask = nil
                            isAuditing = false
                        }
                        .buttonStyle(.bordered)
                    }

                    Spacer()

                    if !ollamaEnabled {
                        Label("On-device AI is off — enable in Settings (⌘,)", systemImage: "exclamationmark.circle")
                            .appFont(.caption)
                            .foregroundColor(.orange)
                    }
                }

                if !auditSteps.isEmpty {
                    AuditStepList(steps: auditSteps)
                }

                if !drugMergeNotes.isEmpty {
                    DrugMergeNotesCallout(notes: drugMergeNotes)
                }

                if !drugInteractions.isEmpty || (!drugInteractionDataAvailable && prescribedDrugs.count >= 2) {
                    DrugInteractionsCallout(
                        interactions: drugInteractions,
                        dataAvailable: drugInteractionDataAvailable,
                        unmatched: drugInteractionUnmatched
                    )
                }

                if !targetOverlaps.isEmpty {
                    TargetOverlapCallout(overlaps: targetOverlaps)
                }

                if !faersPanels.isEmpty || !faersSymptomMatches.isEmpty {
                    FAERSCallout(
                        panels: faersPanels,
                        symptomMatches: faersSymptomMatches
                    )
                }

                if !auditOutput.isEmpty || isAuditing || auditError != nil {
                    AISummaryCard(
                        summary: auditOutput,
                        isStreaming: isAuditing && auditOutput.isEmpty == false,
                        error: auditError,
                        onRegenerate: { runDeepAudit() },
                        onDismiss: {
                            auditTask?.cancel()
                            auditTask = nil
                            auditOutput = ""
                            auditError = nil
                            isAuditing = false
                            auditSteps = []
                            completedAudit = nil
                            pdfExportError = nil
                            drugMergeNotes = []
                            drugInteractions = []
                            drugInteractionUnmatched = []
                            drugInteractionDataAvailable = true
                            targetOverlaps = []
                            targetsByDrug = []
                            faersPanels = []
                            faersSymptomMatches = []
                        }
                    )
                }

                if let snapshot = completedAudit, !isAuditing {
                    HStack(spacing: 8) {
                        Button {
                            exportPDF(snapshot: snapshot)
                        } label: {
                            Label("Save as PDF…", systemImage: "square.and.arrow.down")
                        }
                        .buttonStyle(.bordered)
                        .disabled(isExportingPDF)

                        if isExportingPDF {
                            ProgressView().controlSize(.small)
                            Text("Rendering report…")
                                .appFont(.caption)
                                .foregroundColor(.secondary)
                        }

                        Spacer()

                        if let err = pdfExportError {
                            Label(err, systemImage: "exclamationmark.triangle")
                                .appFont(.caption)
                                .foregroundColor(.orange)
                                .lineLimit(2)
                        }
                    }
                }

                if !canAudit && !isAuditing {
                    Text(disabledReason)
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }

                if isAuditing {
                    Text("This deep audit can take a few minutes — it's running multiple searches and on-device AI passes per source.")
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    private var disabledReason: String {
        if selectedCancerType == nil { return "Select a cancer type to enable auditing." }
        if selectedSubtype == nil {
            return "Select a subtype — the deep audit needs it for the NCI PDQ and modality-trial searches."
        }
        if prescribedDrugs.isEmpty { return "Add at least one prescribed drug." }
        return ""
    }

    // MARK: - Helpers

    private func sectionCard<Content: View>(
        title: String,
        systemImage: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: systemImage)
                .appFont(.headline)
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    private func add(drugResult: DrugSearchResult) {
        // De-dupe by chembl ID when present; otherwise by lowercased name.
        let key = drugResult.chemblId?.uppercased() ?? drugResult.name.lowercased()
        if prescribedDrugs.contains(where: { ($0.chemblId?.uppercased() ?? $0.name.lowercased()) == key }) {
            return
        }
        prescribedDrugs.append(PrescribedDrug(
            name: drugResult.name.capitalized,
            chemblId: drugResult.chemblId
        ))
        drugQuery = ""
        drugResults = []
    }

    private func addTreatment() {
        let trimmed = treatmentDraft.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        treatments.append(ScheduledTreatment(text: trimmed))
        treatmentDraft = ""
    }

    private func addSymptom() {
        let trimmed = symptomDraft.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        symptoms.append(SymptomEntry(text: trimmed, severity: symptomSeverity))
        symptomDraft = ""
    }

    @MainActor
    private func runDrugSearch() async {
        let trimmed = drugQuery.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 2 else {
            drugResults = []
            drugSearchError = nil
            isSearchingDrugs = false
            return
        }
        // Debounce — if the user keeps typing, the .task(id:) re-runs and
        // this sleep gets cancelled before the request fires.
        try? await Task.sleep(nanoseconds: 300_000_000)
        if Task.isCancelled { return }

        isSearchingDrugs = true
        drugSearchError = nil
        defer { isSearchingDrugs = false }
        do {
            let (results, _) = try await backendService.searchDrugsLive(query: trimmed, limit: 10)
            if Task.isCancelled { return }
            drugResults = results
        } catch is CancellationError {
            return
        } catch {
            if Task.isCancelled { return }
            drugSearchError = error.localizedDescription
            drugResults = []
        }
    }

    /// Multi-pass audit orchestrator. Runs in this order:
    ///   - Fetch NCI PDQ summary for the parent cancer type (1 call)
    ///   - Fetch modality trials × 4 in parallel (radiation/surgery/chemo/targeted)
    ///   - Fetch per-drug trials in parallel (capped at 5 concurrent)
    ///   - For each non-empty source, stream a per-source mini-summary
    ///   - Stream the final synthesis combining all summaries
    /// Each step appends to `auditSteps` so the UI can render live progress.
    /// Every state mutation is guarded by a per-run UUID so a cancelled run
    /// can't clobber the new run's output mid-flight.
    private func runDeepAudit() {
        auditTask?.cancel()
        // The audit button is disabled when these are nil (`canAudit`), so
        // these guards are belt-and-suspenders.
        guard let cancerType = selectedCancerType,
              let subtype = selectedSubtype else { return }

        // Snapshot inputs at run-start so edits during the audit don't
        // mutate the in-flight prompt.
        let drugsSnapshot = prescribedDrugs
        let treatmentsSnapshot = treatments.map(\.text)
        let symptomsSnapshot = symptoms.map {
            TreatmentAuditPlan.Symptom(text: $0.text, severity: $0.severity.label)
        }
        let stageSnapshot = selectedStage.promptValue
        let stageDetailSnapshot = stageDetail.trimmingCharacters(in: .whitespaces)

        let runID = UUID()
        currentAuditRunID = runID
        auditOutput = ""
        auditError = nil
        isAuditing = true
        auditSteps = []
        completedAudit = nil
        pdfExportError = nil
        drugMergeNotes = []
        drugInteractions = []
        drugInteractionUnmatched = []
        drugInteractionDataAvailable = true
        targetOverlaps = []
        targetsByDrug = []
        faersPanels = []
        faersSymptomMatches = []

        auditTask = Task { @MainActor in
            defer {
                // Only the active run owns the isAuditing/UI state. A stale
                // run finishing late must not flip isAuditing back to false
                // mid-way through a fresh run.
                if self.currentAuditRunID == runID {
                    self.isAuditing = false
                    self.currentAuditRunID = nil
                }
            }

            // 1. PDQ
            let pdq = await runStep(
                runID: runID,
                label: "Pulling NCI PDQ for \(cancerType.displayName ?? cancerType.name)"
            ) {
                try await BackendService.shared.fetchPDQSummary(
                    subtypeId: subtype.id,
                    stage: stageSnapshot,
                    stageDetail: stageDetailSnapshot.isEmpty ? nil : stageDetailSnapshot
                )
            } skipReason: { error in
                if case BackendError.pdqUnavailable(let cancerType) = error {
                    return "PDQ summary not available for \(cancerType)"
                }
                return nil
            }
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 2. Modality trials (4 in parallel).
            let modalityTrials = await fetchModalityTrialsParallel(
                subtypeId: subtype.id,
                runID: runID
            )
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 2.5. RxNorm normalize + dedupe brand-vs-generic entries
            //      (issue #55). Best-effort: on backend failure we treat
            //      every input as its own group so the audit keeps running.
            let dedupedDrugs = await normalizeAndDedupeDrugs(drugsSnapshot, runID: runID)
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 2.6. DDInter pairwise interactions among the deduped drugs
            //      (issue #47). Deterministic safety callout — runs in the
            //      foreground because it blocks the prompt assembly we
            //      want it included in.
            await fetchDrugInteractionsStep(dedupedDrugs, runID: runID)
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 2.7. Mechanism-of-action target overlap (issue #53).
            //      Deterministic findings — same treatment as
            //      interactions: surfaced as a callout AND fed into the
            //      prompt context.
            await fetchTargetOverlapStep(dedupedDrugs, runID: runID)
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 2.8. OpenFDA FAERS adverse-event frequencies (issue #46).
            //      Surfaces real-world reporting data so the audit can say
            //      "your fatigue matches the #1 reported reaction for X".
            await fetchAdverseEventStep(
                drugs: dedupedDrugs,
                symptoms: symptomsSnapshot.map { $0.text },
                runID: runID
            )
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 3. Per-drug trials (cap 5).
            let drugTrials = await fetchTrialsForDrugs(dedupedDrugs, runID: runID)
            if Task.isCancelled || self.currentAuditRunID != runID { return }

            // 4. Build the plan that gets passed to the LLM helpers.
            //    `dedupedDrugs` (post-RxNorm) drives the prompt so the LLM
            //    doesn't see duplicate brand/generic rows.
            var plan = TreatmentAuditPlan(
                cancerTypeName: cancerType.displayName ?? cancerType.name,
                subtypeName: subtype.shortName ?? subtype.name,
                subtypeMarkers: subtype.markers,
                stage: stageSnapshot,
                stageDetail: stageDetailSnapshot.isEmpty ? nil : stageDetailSnapshot,
                drugs: dedupedDrugs.map {
                    TreatmentAuditPlan.Drug(name: $0.name, chemblId: $0.chemblId)
                },
                treatments: treatmentsSnapshot,
                symptoms: symptomsSnapshot,
                drugTrials: drugTrials,
                modalityTrials: modalityTrials,
                pdqSummary: pdq
            )
            plan.drugInteractions = self.drugInteractions.map {
                TreatmentAuditPlan.InteractionRow(
                    drugA: $0.drugAName,
                    drugB: $0.drugBName,
                    severity: $0.severity,
                    description: $0.description
                )
            }
            plan.drugInteractionDataAvailable = self.drugInteractionDataAvailable
            // Flatten each pairwise overlap into one prompt row per shared
            // target so the LLM can speak to each gene specifically.
            plan.targetOverlaps = self.targetOverlaps.flatMap { overlap in
                overlap.sharedTargets.map { shared in
                    TreatmentAuditPlan.TargetOverlapRow(
                        drugA: overlap.drugA,
                        drugB: overlap.drugB,
                        geneSymbol: shared.geneSymbol,
                        proteinName: shared.proteinName,
                        actionTypeA: shared.actionTypeA,
                        actionTypeB: shared.actionTypeB
                    )
                }
            }
            plan.faersSymptomMatches = self.faersSymptomMatches.map {
                TreatmentAuditPlan.FAERSSymptomMatchRow(
                    drugName: $0.drugName,
                    symptom: $0.symptom,
                    matchedTerm: $0.matchedTerm,
                    count: $0.count,
                    rankInTop: $0.rankInTop,
                    totalReports: $0.totalReports
                )
            }

            let planContext = OllamaService.planContextSummary(plan)

            // 5. Per-source mini-summaries.
            var summaries: [(label: String, summary: String)] = []

            // PDQ mini-summary
            if let pdq = pdq, !pdq.sections.isEmpty {
                let body = OllamaService.compressPDQ(pdq)
                let label = "NCI PDQ — \(pdq.slug.capitalized)"
                let summary = await runSummaryStep(
                    runID: runID,
                    label: "Summarizing \(label)",
                    sourceLabel: label,
                    sourceBody: body,
                    planContext: planContext
                )
                if let summary { summaries.append((label, summary)) }
                if Task.isCancelled || self.currentAuditRunID != runID { return }
            }

            // Modality summaries
            for entry in modalityTrials where !entry.trials.isEmpty {
                let header = "Modality: \(entry.modality.capitalized) trials" +
                    (entry.condition.map { " — condition: \($0)" } ?? "")
                let body = OllamaService.compressTrials(entry.trials, header: header)
                let label = "\(entry.modality.capitalized) trials"
                let summary = await runSummaryStep(
                    runID: runID,
                    label: "Summarizing \(label)",
                    sourceLabel: label,
                    sourceBody: body,
                    planContext: planContext
                )
                if let summary { summaries.append((label, summary)) }
                if Task.isCancelled || self.currentAuditRunID != runID { return }
            }

            // Per-drug summaries
            for entry in drugTrials where !entry.trials.isEmpty {
                let header = "Trials linked to \(entry.drugName)" +
                    (entry.chemblId.map { " [\($0)]" } ?? "")
                let body = OllamaService.compressTrials(entry.trials, header: header)
                let label = "\(entry.drugName) trials"
                let summary = await runSummaryStep(
                    runID: runID,
                    label: "Summarizing \(label)",
                    sourceLabel: label,
                    sourceBody: body,
                    planContext: planContext
                )
                if let summary { summaries.append((label, summary)) }
                if Task.isCancelled || self.currentAuditRunID != runID { return }
            }

            // 6. Final synthesis.
            let synthesisStepIndex = appendStep(
                runID: runID,
                label: "Synthesizing final audit",
                state: .running
            )
            do {
                let stream = OllamaService.shared.synthesizeAuditFromSummaries(
                    plan: plan,
                    sourceSummaries: summaries
                )
                for try await chunk in stream {
                    if Task.isCancelled || self.currentAuditRunID != runID { return }
                    self.auditOutput += chunk
                }
                if let idx = synthesisStepIndex {
                    updateStep(runID: runID, at: idx, state: .done)
                }
                // Snapshot for PDF export (issue #58). Built after the
                // synthesis step is marked .done so the captured step list
                // mirrors the final UI state.
                var snapshot = CompletedAuditSnapshot(
                    plan: plan,
                    sourceSummaries: summaries.map {
                        AuditSourceSummary(label: $0.label, summary: $0.summary)
                    },
                    finalAudit: self.auditOutput,
                    steps: self.auditSteps,
                    generatedAt: Date()
                )
                // Carry the deterministic-finding extras the plan can't
                // hold (merges happen pre-plan; FAERS top-events panels
                // are PDF-only context the LLM doesn't need).
                snapshot.mergeNotes = self.drugMergeNotes
                snapshot.faersPanels = self.faersPanels
                self.completedAudit = snapshot
            } catch {
                guard !Task.isCancelled, self.currentAuditRunID == runID else { return }
                self.auditError = error.localizedDescription
                if let idx = synthesisStepIndex {
                    updateStep(runID: runID, at: idx, state: .failed(error.localizedDescription))
                }
            }
        }
    }

    // MARK: - PDF export (issues #58, #67)

    /// Save the most recent audit as a printable PDF. Opens NSSavePanel for
    /// the destination, then renders via the backend's report.pdf endpoint
    /// (issue #67 — the HTML+CSS builder lives in
    /// backend/treatment_auditor_report.py so the Python CLI and the macOS
    /// app produce visually identical output). Includes inputs, methodology,
    /// per-source summaries, final synthesis, and references — enough for
    /// someone to repeat the audit by hand.
    private func exportPDF(snapshot: CompletedAuditSnapshot) {
        pdfExportError = nil

        let panel = NSSavePanel()
        panel.title = "Save Treatment Audit Report"
        panel.message = "Choose where to save the printable PDF report."
        panel.allowedContentTypes = [UTType.pdf]
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = TreatmentAuditReportClient.defaultFilename(for: snapshot)

        guard panel.runModal() == .OK, let url = panel.url else { return }

        isExportingPDF = true
        Task { @MainActor in
            defer { isExportingPDF = false }
            do {
                try await TreatmentAuditReportClient.renderPDF(snapshot: snapshot, to: url)
                NSWorkspace.shared.activateFileViewerSelecting([url])
            } catch {
                pdfExportError = "PDF export failed: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Step helpers

    /// Returns true when the supplied run is still the active audit. Used by
    /// every shared-state mutator to guard against stale work landing after
    /// the user kicked off a new audit.
    private func isActiveRun(_ runID: UUID) -> Bool {
        currentAuditRunID == runID
    }

    /// Returns the new step's index, or nil if the supplied run is no longer
    /// active (in which case the caller should bail out — the array it's
    /// indexing into has been reset by a fresh run).
    @MainActor
    @discardableResult
    private func appendStep(runID: UUID, label: String, state: AuditStep.State) -> Int? {
        guard isActiveRun(runID) else { return nil }
        auditSteps.append(AuditStep(label: label, state: state))
        return auditSteps.count - 1
    }

    @MainActor
    private func updateStep(runID: UUID, at index: Int, state: AuditStep.State) {
        guard isActiveRun(runID), auditSteps.indices.contains(index) else { return }
        auditSteps[index] = AuditStep(label: auditSteps[index].label, state: state)
    }

    /// Runs an async fetch as one progress-tracked step. `skipReason`, when
    /// non-nil, lets the caller convert specific errors into a "skipped"
    /// state instead of "failed" (e.g. PDQ unavailable for hematologic
    /// cancers — expected, not a failure).
    @MainActor
    private func runStep<T>(
        runID: UUID,
        label: String,
        operation: () async throws -> T,
        skipReason: (Error) -> String? = { _ in nil }
    ) async -> T? {
        guard let index = appendStep(runID: runID, label: label, state: .running) else {
            return nil
        }
        do {
            let value = try await operation()
            updateStep(runID: runID, at: index, state: .done)
            return value
        } catch is CancellationError {
            updateStep(runID: runID, at: index, state: .failed("Cancelled"))
            return nil
        } catch {
            if let reason = skipReason(error) {
                updateStep(runID: runID, at: index, state: .skipped(reason))
            } else {
                updateStep(runID: runID, at: index, state: .failed(error.localizedDescription))
            }
            return nil
        }
    }

    /// Runs one mini-summary LLM streaming call as a progress-tracked step.
    /// Returns the accumulated text on success; nil on failure (the failure
    /// is recorded as a step state, but the audit continues with the
    /// remaining sources).
    @MainActor
    private func runSummaryStep(
        runID: UUID,
        label: String,
        sourceLabel: String,
        sourceBody: String,
        planContext: String
    ) async -> String? {
        guard let index = appendStep(runID: runID, label: label, state: .running) else {
            return nil
        }
        var accumulated = ""
        do {
            let stream = OllamaService.shared.summarizeAuditSource(
                sourceLabel: sourceLabel,
                sourceBody: sourceBody,
                planContext: planContext
            )
            for try await chunk in stream {
                if Task.isCancelled || !isActiveRun(runID) { break }
                accumulated += chunk
            }
            if Task.isCancelled || !isActiveRun(runID) {
                updateStep(runID: runID, at: index, state: .failed("Cancelled"))
                return nil
            }
            updateStep(runID: runID, at: index, state: .done)
            return accumulated.trimmingCharacters(in: .whitespacesAndNewlines)
        } catch {
            updateStep(runID: runID, at: index, state: .failed(error.localizedDescription))
            return nil
        }
    }

    // MARK: - Fetch helpers

    /// Normalizes prescribed drugs via RxNorm and collapses brand-vs-generic
    /// entries onto a single representative (issue #55). The returned list is
    /// what every downstream fetch (trials, modality, AE, …) sees, so we
    /// don't pay 2× the API cost for "Taxol" + "paclitaxel".
    ///
    /// Best-effort: a normalization failure surfaces as a `.failed` step but
    /// doesn't block the audit — we fall back to the raw input list so the
    /// rest of the pipeline still runs.
    @MainActor
    private func normalizeAndDedupeDrugs(
        _ drugs: [PrescribedDrug],
        runID: UUID
    ) async -> [PrescribedDrug] {
        guard drugs.count > 0 else { return drugs }
        // Skip the RxNorm round-trip when there's nothing to dedupe — the
        // step would just confuse the user with "Normalizing 1 drug".
        guard drugs.count >= 2 else { return drugs }

        let stepIndex = appendStep(
            runID: runID,
            label: "Normalizing drug names (RxNorm)",
            state: .running
        )

        let payload = drugs.map { (name: $0.name, chemblId: $0.chemblId) }
        let normalizations: [DrugNormalization]
        do {
            normalizations = try await BackendService.shared.normalizeDrugs(payload)
        } catch is CancellationError {
            if let i = stepIndex { updateStep(runID: runID, at: i, state: .failed("Cancelled")) }
            return drugs
        } catch {
            // RxNorm is best-effort — every other audit pass still runs on
            // the raw input list.
            if let i = stepIndex {
                updateStep(runID: runID, at: i, state: .failed(error.localizedDescription))
            }
            return drugs
        }

        guard !Task.isCancelled, isActiveRun(runID) else { return drugs }

        // Pair each prescribed drug to its normalization row, lining them up
        // by index. The backend preserves order; pad with nil for safety.
        let paired: [(PrescribedDrug, DrugNormalization?)] = drugs.enumerated().map { (i, drug) in
            i < normalizations.count ? (drug, normalizations[i]) : (drug, nil)
        }

        // Group by groupKey, preserving first-seen order so the chip layout
        // doesn't reshuffle when a brand entry merges with a generic.
        var groupOrder: [String] = []
        var groups: [String: [(PrescribedDrug, DrugNormalization?)]] = [:]
        for entry in paired {
            // Drugs with no normalization match (or empty group_key) fall
            // back to a per-drug key so they remain distinct rows.
            let key = entry.1?.groupKey ?? "name:\(entry.0.name.lowercased())"
            if groups[key] == nil {
                groups[key] = []
                groupOrder.append(key)
            }
            groups[key]?.append(entry)
        }

        var deduped: [PrescribedDrug] = []
        var notes: [DrugMergeNote] = []
        for key in groupOrder {
            let bucket = groups[key] ?? []
            // Single-row groups pass through untouched.
            if bucket.count == 1 {
                deduped.append(bucket[0].0)
                continue
            }
            // Multi-row group: pick a representative row. Prefer one with a
            // ChEMBL ID so the downstream trial fetch still has a valid key.
            let representative = bucket.first(where: { $0.0.chemblId != nil })?.0 ?? bucket[0].0
            // Display name: prefer the RxNorm ingredient name (the canonical
            // generic) so the chip reads "Paclitaxel" instead of either of
            // the original inputs.
            let ingredientName = bucket.compactMap { $0.1?.ingredientName }
                .first(where: { !$0.isEmpty })
            let displayName = ingredientName?.capitalized ?? representative.name
            deduped.append(PrescribedDrug(
                name: displayName,
                chemblId: representative.chemblId
            ))
            notes.append(DrugMergeNote(
                ingredientName: displayName,
                originalNames: bucket.map { $0.0.name }
            ))
        }

        self.drugMergeNotes = notes
        if let i = stepIndex {
            let merged = drugs.count - deduped.count
            let state: AuditStep.State
            if merged > 0 {
                state = .done
            } else {
                state = .skipped("No duplicates found")
            }
            updateStep(runID: runID, at: i, state: state)
        }
        return deduped
    }

    /// Fetches pairwise DDInter drug-drug interactions for the deduped
    /// drug list (issue #47) and stashes the result in `drugInteractions`
    /// for the UI callout + the LLM prompt context. Best-effort: on
    /// failure we mark the step `.failed` but the audit keeps running.
    @MainActor
    private func fetchDrugInteractionsStep(
        _ drugs: [PrescribedDrug],
        runID: UUID
    ) async {
        // Single drug = no pairs to flag. Skip silently — adding a step
        // here would just be noise.
        guard drugs.count >= 2 else { return }

        let stepIndex = appendStep(
            runID: runID,
            label: "Checking pairwise drug interactions (DDInter)",
            state: .running
        )

        let payload: [(name: String, chemblId: String?)] = drugs.map {
            ($0.name, $0.chemblId)
        }

        let outcome: BackendService.DrugInteractionsOutcome
        do {
            outcome = try await BackendService.shared.fetchDrugInteractions(payload)
        } catch is CancellationError {
            if let i = stepIndex { updateStep(runID: runID, at: i, state: .failed("Cancelled")) }
            return
        } catch {
            if let i = stepIndex {
                updateStep(runID: runID, at: i, state: .failed(error.localizedDescription))
            }
            return
        }

        guard !Task.isCancelled, isActiveRun(runID) else { return }

        self.drugInteractions = outcome.interactions
        self.drugInteractionUnmatched = outcome.unmatched
        self.drugInteractionDataAvailable = outcome.drugbankLoaded

        if let i = stepIndex {
            let state: AuditStep.State
            if !outcome.drugbankLoaded {
                state = .skipped("DDInter not loaded")
            } else if outcome.interactions.isEmpty {
                state = .skipped("No interactions among prescribed drugs")
            } else {
                state = .done
            }
            updateStep(runID: runID, at: i, state: state)
        }
    }

    /// Fetches mechanism-of-action target overlap among the deduped
    /// drugs (issue #53) and stashes the result for the UI callout +
    /// LLM prompt. Best-effort: failure marks the step `.failed` but
    /// the audit continues.
    @MainActor
    private func fetchTargetOverlapStep(
        _ drugs: [PrescribedDrug],
        runID: UUID
    ) async {
        guard drugs.count >= 2 else { return }

        let stepIndex = appendStep(
            runID: runID,
            label: "Checking mechanism/target overlap (ChEMBL)",
            state: .running
        )

        let payload: [(name: String, chemblId: String?)] = drugs.map { ($0.name, $0.chemblId) }

        let outcome: BackendService.TargetOverlapOutcome
        do {
            outcome = try await BackendService.shared.fetchTargetOverlap(payload)
        } catch is CancellationError {
            if let i = stepIndex { updateStep(runID: runID, at: i, state: .failed("Cancelled")) }
            return
        } catch {
            if let i = stepIndex {
                updateStep(runID: runID, at: i, state: .failed(error.localizedDescription))
            }
            return
        }

        guard !Task.isCancelled, isActiveRun(runID) else { return }

        self.targetsByDrug = outcome.targetsByDrug
        self.targetOverlaps = outcome.overlaps

        if let i = stepIndex {
            let state: AuditStep.State
            if outcome.overlaps.isEmpty {
                let coverage = outcome.targetsByDrug.filter { !$0.targets.isEmpty }.count
                if coverage == 0 {
                    state = .skipped("No target data found in ChEMBL for these drugs")
                } else {
                    state = .skipped("No target overlap among prescribed drugs")
                }
            } else {
                state = .done
            }
            updateStep(runID: runID, at: i, state: state)
        }
    }

    /// Fetches OpenFDA FAERS adverse-event panels for the deduped drug
    /// list and matches the user's symptoms against the top reactions
    /// (issue #46). Best-effort: failure marks the step `.failed` but
    /// the audit continues.
    @MainActor
    private func fetchAdverseEventStep(
        drugs: [PrescribedDrug],
        symptoms: [String],
        runID: UUID
    ) async {
        guard !drugs.isEmpty else { return }

        let stepIndex = appendStep(
            runID: runID,
            label: "Pulling FAERS adverse-event reports (OpenFDA)",
            state: .running
        )

        let payload: [(name: String, chemblId: String?)] = drugs.map { ($0.name, $0.chemblId) }

        let outcome: BackendService.FAERSPanelOutcome
        do {
            outcome = try await BackendService.shared.fetchAdverseEventPanel(
                drugs: payload, symptoms: symptoms
            )
        } catch is CancellationError {
            if let i = stepIndex { updateStep(runID: runID, at: i, state: .failed("Cancelled")) }
            return
        } catch {
            if let i = stepIndex {
                updateStep(runID: runID, at: i, state: .failed(error.localizedDescription))
            }
            return
        }

        guard !Task.isCancelled, isActiveRun(runID) else { return }

        self.faersPanels = outcome.perDrug
        self.faersSymptomMatches = outcome.symptomMatches

        if let i = stepIndex {
            let coverage = outcome.perDrug.filter { !$0.topEvents.isEmpty }.count
            let state: AuditStep.State
            if coverage == 0 {
                state = .skipped("No FAERS reports for these drugs")
            } else {
                state = .done
            }
            updateStep(runID: runID, at: i, state: state)
        }
    }

    /// Per-modality fetch outcome — keeps the trial list and any error
    /// returned by the backend so the step UI can distinguish a true
    /// no-results response from a backend failure.
    private struct ModalityFetchOutcome {
        let modality: String
        let trials: [ClinicalTrial]
        let error: Error?
    }

    /// Fetches trials per modality (radiation, surgery, chemotherapy,
    /// targeted) in parallel. Each modality is its own progress step; a
    /// network/backend failure now surfaces as `.failed` (with the original
    /// error message) rather than being mis-reported as "no trials".
    @MainActor
    private func fetchModalityTrialsParallel(
        subtypeId: Int,
        runID: UUID
    ) async -> [TreatmentAuditPlan.ModalityTrials] {
        let modalities = ["radiation", "surgery", "chemotherapy", "targeted"]
        let stepIndices: [Int?] = modalities.map {
            appendStep(runID: runID, label: "Searching \($0) trials", state: .running)
        }

        return await withTaskGroup(of: (Int, ModalityFetchOutcome).self) { group in
            var results = Array<TreatmentAuditPlan.ModalityTrials?>(
                repeating: nil, count: modalities.count
            )
            for (i, modality) in modalities.enumerated() {
                group.addTask {
                    do {
                        let trials = try await BackendService.shared.fetchModalityTrials(
                            subtypeId: subtypeId,
                            modality: modality,
                            limit: 8
                        )
                        return (i, ModalityFetchOutcome(modality: modality, trials: trials, error: nil))
                    } catch {
                        return (i, ModalityFetchOutcome(modality: modality, trials: [], error: error))
                    }
                }
            }
            while let (i, outcome) = await group.next() {
                results[i] = TreatmentAuditPlan.ModalityTrials(
                    modality: outcome.modality,
                    condition: nil,
                    trials: outcome.trials
                )
                let state: AuditStep.State
                if let err = outcome.error {
                    state = .failed(err.localizedDescription)
                } else if outcome.trials.isEmpty {
                    state = .skipped("No \(outcome.modality) trials returned")
                } else {
                    state = .done
                }
                if let stepIndex = stepIndices[i] {
                    updateStep(runID: runID, at: stepIndex, state: state)
                }
            }
            return results.compactMap { $0 }
        }
    }

    /// Per-drug fetch outcome — keeps the trial list and any error returned
    /// by the backend so the aggregate step state can distinguish a real
    /// "no trials reported" response from a backend failure.
    private struct DrugFetchOutcome {
        let drugTrials: TreatmentAuditPlan.DrugTrials
        let error: Error?
        /// Drugs without a ChEMBL ID legitimately have no trials to fetch —
        /// not an error, not even a "skipped fetch". The aggregate step
        /// reports counts excluding these so we don't claim a backend failure
        /// when there was simply nothing to query.
        let attempted: Bool
    }

    /// Fetches trials for each prescribed drug that has a ChEMBL ID. Drugs
    /// without a ChEMBL ID are still included with an empty trials list so
    /// the prompt acknowledges them. Capped at 5 concurrent requests. The
    /// aggregate step's state distinguishes:
    ///   - `.failed`  — at least one drug fetch raised
    ///   - `.skipped` — every attempted fetch returned an empty list (no
    ///     attempts at all also lands here)
    ///   - `.done`    — at least one drug returned trials and no fetch errored
    @MainActor
    private func fetchTrialsForDrugs(
        _ drugs: [PrescribedDrug],
        runID: UUID
    ) async -> [TreatmentAuditPlan.DrugTrials] {
        // One progress step covers the whole drug-trial fetch — per-drug
        // rows would explode the step list when many drugs are listed.
        let stepIndex = appendStep(
            runID: runID,
            label: "Fetching trials for \(drugs.count) drug\(drugs.count == 1 ? "" : "s")",
            state: .running
        )

        let outcomes: [DrugFetchOutcome] = await withTaskGroup(
            of: (Int, DrugFetchOutcome).self
        ) { group in
            let maxParallel = 5
            var results = Array<DrugFetchOutcome?>(repeating: nil, count: drugs.count)
            var nextIndex = 0
            var inflight = 0

            func enqueue() {
                while inflight < maxParallel && nextIndex < drugs.count {
                    let i = nextIndex
                    let drug = drugs[i]
                    nextIndex += 1
                    inflight += 1
                    group.addTask {
                        guard let chembl = drug.chemblId, !chembl.isEmpty else {
                            return (i, DrugFetchOutcome(
                                drugTrials: TreatmentAuditPlan.DrugTrials(
                                    drugName: drug.name,
                                    chemblId: drug.chemblId,
                                    trials: []
                                ),
                                error: nil,
                                attempted: false
                            ))
                        }
                        do {
                            let trials = try await BackendService.shared
                                .fetchClinicalTrials(chemblId: chembl, limit: 10)
                            return (i, DrugFetchOutcome(
                                drugTrials: TreatmentAuditPlan.DrugTrials(
                                    drugName: drug.name,
                                    chemblId: drug.chemblId,
                                    trials: trials
                                ),
                                error: nil,
                                attempted: true
                            ))
                        } catch {
                            return (i, DrugFetchOutcome(
                                drugTrials: TreatmentAuditPlan.DrugTrials(
                                    drugName: drug.name,
                                    chemblId: drug.chemblId,
                                    trials: []
                                ),
                                error: error,
                                attempted: true
                            ))
                        }
                    }
                }
            }

            enqueue()
            while let (i, outcome) = await group.next() {
                results[i] = outcome
                inflight -= 1
                enqueue()
            }
            return results.compactMap { $0 }
        }

        let failed = outcomes.compactMap { o -> (String, Error)? in
            if let err = o.error { return (o.drugTrials.drugName, err) }
            return nil
        }
        let attemptedCount = outcomes.filter(\.attempted).count
        let nonEmptyCount = outcomes.filter { !$0.drugTrials.trials.isEmpty }.count

        if let stepIndex = stepIndex {
            let state: AuditStep.State
            if !failed.isEmpty {
                let drugList = failed.map(\.0).joined(separator: ", ")
                let firstMessage = failed[0].1.localizedDescription
                state = .failed(
                    "Trial fetch failed for \(failed.count) of \(attemptedCount) drug\(attemptedCount == 1 ? "" : "s") (\(drugList)): \(firstMessage)"
                )
            } else if nonEmptyCount == 0 {
                state = .skipped("No trials returned for any prescribed drug")
            } else {
                state = .done
            }
            updateStep(runID: runID, at: stepIndex, state: state)
        }

        return outcomes.map(\.drugTrials)
    }
}

// MARK: - Local model types (ephemeral for v1)

private struct PrescribedDrug: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let chemblId: String?
}

/// One brand→generic merge surfaced by the RxNorm dedupe step (issue #55).
/// Drives the "Combined" callout above the audit output so the user sees
/// when their inputs were collapsed.
struct DrugMergeNote: Identifiable, Hashable {
    let id = UUID()
    let ingredientName: String
    let originalNames: [String]
}

private struct ScheduledTreatment: Identifiable, Hashable {
    let id = UUID()
    let text: String
}

/// Coarse stage Picker options. The free-text "Stage details" field captures
/// anything finer (substages, metastasis sites, recurrence timing). Both are
/// passed into the audit prompt; PDQ section selection uses the Picker value
/// for keyword matching against headings, and the free-text for token-level
/// matching against headings + section text.
private enum StageOption: String, CaseIterable, Identifiable, Hashable {
    case unspecified
    case stageI
    case stageII
    case stageIII
    case stageIV
    case recurrent
    case metastatic
    case otherCustom

    var id: String { rawValue }

    var label: String {
        switch self {
        case .unspecified: return "Unspecified / Unknown"
        case .stageI: return "Stage I"
        case .stageII: return "Stage II"
        case .stageIII: return "Stage III"
        case .stageIV: return "Stage IV"
        case .recurrent: return "Recurrent"
        case .metastatic: return "Metastatic"
        case .otherCustom: return "Other / Custom"
        }
    }

    /// String fed into PDQ search and the audit prompt. `unspecified` and
    /// `otherCustom` return nil so the free-text field becomes authoritative.
    var promptValue: String? {
        switch self {
        case .unspecified, .otherCustom: return nil
        default: return label
        }
    }
}

/// One row in the audit progress list. Each fetch / per-source mini-summary /
/// final synthesis step writes its state here so the user can watch the deep
/// audit make progress instead of staring at a spinner.
struct AuditStep: Identifiable, Hashable {
    let id = UUID()
    let label: String
    let state: State

    enum State: Hashable {
        case running
        case done
        case skipped(String)
        case failed(String)
    }
}

private struct AuditStepList: View {
    let steps: [AuditStep]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(steps) { step in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    icon(for: step.state)
                    Text(step.label)
                        .appFont(.caption)
                        .foregroundColor(.primary)
                    if let detail = stateDetail(step.state) {
                        Text("— \(detail)")
                            .appFont(.caption2)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                    }
                    Spacer()
                }
                .padding(.vertical, 2)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.secondary.opacity(0.06))
        )
    }

    @ViewBuilder
    private func icon(for state: AuditStep.State) -> some View {
        switch state {
        case .running:
            ProgressView().controlSize(.small)
        case .done:
            Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
        case .skipped:
            Image(systemName: "minus.circle").foregroundColor(.secondary)
        case .failed:
            Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.orange)
        }
    }

    private func stateDetail(_ state: AuditStep.State) -> String? {
        switch state {
        case .skipped(let reason): return reason
        case .failed(let message): return message
        case .running, .done: return nil
        }
    }
}

/// Renders a small callout above the audit output explaining which inputs
/// were collapsed onto a single ingredient by the RxNorm dedupe step
/// (issue #55). Deterministic and factual — surfaced as its own block,
/// distinct from the AI-inferred audit text below.
private struct DrugMergeNotesCallout: View {
    let notes: [DrugMergeNote]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.merge")
                    .foregroundColor(.accentColor)
                Text("Combined brand-vs-generic entries")
                    .appFont(.caption, weight: .semibold)
            }
            ForEach(notes) { note in
                let originals = note.originalNames.joined(separator: " + ")
                Text("\(originals) → \(note.ingredientName)")
                    .appFont(.caption2)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("RxNorm normalized these to the same active ingredient. Per-drug fetches use the merged entry.")
                .appFont(.caption2)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.accentColor.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.accentColor.opacity(0.25), lineWidth: 1)
        )
    }
}

/// Renders pairwise DDInter drug-drug interactions as a deterministic
/// safety callout (issue #47). Distinct from the AI-inferred audit text
/// — these rows are factual lookups from DDInter, sorted Major →
/// Moderate → Minor → unknown by the backend.
///
/// When `dataAvailable=false` the view renders a "DDInter not loaded"
/// hint instead of "no interactions" — those are very different
/// statements and conflating them would be a safety hazard.
private struct DrugInteractionsCallout: View {
    let interactions: [DrugInteraction]
    let dataAvailable: Bool
    let unmatched: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: dataAvailable ? "exclamationmark.triangle.fill" : "questionmark.circle")
                    .foregroundColor(dataAvailable && hasSevere ? .red : .orange)
                Text(headerText)
                    .appFont(.caption, weight: .semibold)
            }

            if !dataAvailable {
                Text("DDInter hasn't been loaded into the local database, so interactions can't be checked. Run `python backend/load_ddinter_interactions.py` to fetch the eight ATC-class CSVs from ddinter.scbdd.com (no registration required). DDInter is licensed CC BY-NC-SA 4.0 — non-commercial use only.")
                    .appFont(.caption2)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                ForEach(interactions) { row in
                    interactionRow(row)
                }
                if !unmatched.isEmpty {
                    Text("Couldn't match in DDInter: \(unmatched.joined(separator: ", "))")
                        .appFont(.caption2)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text("Source: DDInter (ddinter.scbdd.com), CC BY-NC-SA 4.0. Severity (Major / Moderate / Minor) is curated by the DDInter team — confirm with the prescribing clinician.")
                    .appFont(.caption2)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(calloutColor.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(calloutColor.opacity(0.3), lineWidth: 1)
        )
    }

    private var hasSevere: Bool {
        interactions.contains { $0.severity?.lowercased() == "severe" }
    }

    private var calloutColor: Color {
        if !dataAvailable { return .secondary }
        return hasSevere ? .red : .orange
    }

    private var headerText: String {
        if !dataAvailable {
            return "Drug-drug interactions: data unavailable"
        }
        if interactions.isEmpty {
            return "Drug-drug interactions: none found"
        }
        let severeCount = interactions.filter { $0.severity?.lowercased() == "severe" }.count
        if severeCount > 0 {
            return "Drug-drug interactions (\(interactions.count) found, \(severeCount) severe)"
        }
        return "Drug-drug interactions (\(interactions.count) found)"
    }

    @ViewBuilder
    private func interactionRow(_ row: DrugInteraction) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Text("\(row.drugAName) ↔ \(row.drugBName)")
                    .appFont(.caption, weight: .semibold)
                if let sev = row.severity, !sev.isEmpty {
                    Text(sev.uppercased())
                        .appFont(.caption2, weight: .semibold)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(severityColor(sev).opacity(0.18))
                        .foregroundColor(severityColor(sev))
                        .clipShape(Capsule())
                }
            }
            if let desc = row.description, !desc.isEmpty {
                Text(desc)
                    .appFont(.caption2)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 2)
    }

    private func severityColor(_ severity: String) -> Color {
        switch severity.lowercased() {
        case "severe": return .red
        case "moderate": return .orange
        case "minor": return .yellow
        default: return .secondary
        }
    }
}

/// Renders mechanism-of-action target overlap pairs as a deterministic
/// callout (issue #53). Distinct from the AI-inferred audit text — these
/// rows come from ChEMBL's `mechanism` resource. Could be intentional
/// combination therapy or redundant — the audit text below should
/// disambiguate.
private struct TargetOverlapCallout: View {
    let overlaps: [DrugTargetOverlap]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "scope")
                    .foregroundColor(.purple)
                Text("Mechanism / target overlap")
                    .appFont(.caption, weight: .semibold)
            }

            ForEach(overlaps) { overlap in
                ForEach(Array(overlap.sharedTargets.enumerated()), id: \.offset) { _, shared in
                    overlapRow(overlap: overlap, shared: shared)
                }
            }

            Text("Source: ChEMBL mechanism-of-action data. Overlap doesn't imply a problem — combo therapy is often intentional. Confirm with the prescribing clinician.")
                .appFont(.caption2)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.purple.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.purple.opacity(0.3), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func overlapRow(
        overlap: DrugTargetOverlap,
        shared: DrugTargetOverlap.SharedTarget
    ) -> some View {
        let target = shared.geneSymbol ?? shared.proteinName ?? "shared target"
        let actionA = shared.actionTypeA?.lowercased() ?? "—"
        let actionB = shared.actionTypeB?.lowercased() ?? "—"
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Text("\(overlap.drugA) ↔ \(overlap.drugB)")
                    .appFont(.caption, weight: .semibold)
                Text(target)
                    .appFont(.caption2, weight: .semibold)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.purple.opacity(0.18))
                    .foregroundColor(.purple)
                    .clipShape(Capsule())
            }
            Text("\(overlap.drugA): \(actionA) — \(overlap.drugB): \(actionB)")
                .appFont(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 2)
    }
}

/// Renders OpenFDA FAERS post-market adverse-event data (issue #46) as
/// two stacked sections: the symptom→reaction matches first (the
/// load-bearing finding for an audit), then a short per-drug top-events
/// list for context. Source labelled — these are *reports*, not
/// causation.
private struct FAERSCallout: View {
    let panels: [FAERSDrugPanel]
    let symptomMatches: [FAERSSymptomMatch]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "chart.bar.doc.horizontal")
                    .foregroundColor(.teal)
                Text("OpenFDA post-market reporting (FAERS)")
                    .appFont(.caption, weight: .semibold)
            }

            if !symptomMatches.isEmpty {
                Text("Your symptoms vs. top reported reactions:")
                    .appFont(.caption2, weight: .semibold)
                    .foregroundColor(.secondary)
                ForEach(symptomMatches) { match in
                    matchRow(match)
                }
            }

            if !panels.isEmpty {
                Divider().padding(.vertical, 2)
                Text("Top reactions per drug (any source):")
                    .appFont(.caption2, weight: .semibold)
                    .foregroundColor(.secondary)
                ForEach(panels) { panel in
                    panelSummary(panel)
                }
            }

            Text("Source: openFDA FAERS. Reports are voluntary and do not establish causation; counts reflect what's been reported, not actual incidence.")
                .appFont(.caption2)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.teal.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.teal.opacity(0.3), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func matchRow(_ m: FAERSSymptomMatch) -> some View {
        let rankText: String = {
            if let rank = m.rankInTop { return "#\(rank) of top reactions" }
            return "in reports"
        }()
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Text("\(m.drugName): \(m.symptom)")
                    .appFont(.caption, weight: .semibold)
                Text("→ \(m.matchedTerm)")
                    .appFont(.caption2, weight: .semibold)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.teal.opacity(0.18))
                    .foregroundColor(.teal)
                    .clipShape(Capsule())
            }
            Text("\(rankText) — \(m.count.formatted()) of \(m.totalReports.formatted()) reports")
                .appFont(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func panelSummary(_ p: FAERSDrugPanel) -> some View {
        let preview = p.topEvents.prefix(5).map { "\($0.term.lowercased()) (\($0.count.formatted()))" }
            .joined(separator: ", ")
        VStack(alignment: .leading, spacing: 2) {
            Text("\(p.drugName) — \(p.totalReports.formatted()) total reports")
                .appFont(.caption, weight: .semibold)
            Text(preview.isEmpty ? "No reports found in FAERS." : preview)
                .appFont(.caption2)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }
}

private struct SymptomEntry: Identifiable, Hashable {
    let id = UUID()
    let text: String
    let severity: SymptomSeverity
}

private enum SymptomSeverity: String, CaseIterable, Identifiable, Hashable {
    case mild, moderate, severe
    var id: String { rawValue }
    var label: String {
        switch self {
        case .mild: return "Mild"
        case .moderate: return "Moderate"
        case .severe: return "Severe"
        }
    }
    var color: Color {
        switch self {
        case .mild: return .green
        case .moderate: return .orange
        case .severe: return .red
        }
    }
}

// MARK: - Disease picker sheet

/// Two-step picker: cancer type → subtype. Self-contained so it doesn't
/// share NavigationStack state with the rest of the app.
private struct DiseasePickerSheet: View {
    @Binding var isPresented: Bool
    let onSelect: (CancerType, CancerSubtype?) -> Void

    @StateObject private var backendService = BackendService.shared
    @State private var cancerTypes: [CancerType] = []
    @State private var typesError: String?
    @State private var loadingTypes = false

    @State private var selectedType: CancerType?
    @State private var subtypes: [CancerSubtype] = []
    @State private var subtypesError: String?
    @State private var loadingSubtypes = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                if selectedType != nil {
                    Button {
                        selectedType = nil
                        subtypes = []
                        subtypesError = nil
                    } label: {
                        Label("Back", systemImage: "chevron.left")
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
                Text(selectedType?.displayName ?? selectedType?.name ?? "Select cancer type")
                    .appFont(.headline)
                Spacer()
                Button("Cancel") { isPresented = false }
                    .keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            Divider()

            ScrollView {
                if let type = selectedType {
                    subtypesList(for: type)
                } else {
                    typesList
                }
            }
        }
        .frame(minWidth: 600, minHeight: 500)
        .task { await loadTypes() }
    }

    private var typesList: some View {
        VStack(alignment: .leading, spacing: 8) {
            if loadingTypes {
                ProgressView("Loading cancer types…")
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else if let err = typesError {
                errorBlock(err) { Task { await loadTypes() } }
            } else {
                ForEach(cancerTypes) { type in
                    Button {
                        selectedType = type
                        Task { await loadSubtypes(for: type) }
                    } label: {
                        HStack {
                            Image(systemName: type.icon ?? "circle.grid.cross.fill")
                                .foregroundColor(.accentColor)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(type.displayName ?? type.name)
                                    .appFont(.body, weight: .semibold)
                                if let desc = type.description {
                                    Text(desc)
                                        .appFont(.caption)
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                }
                            }
                            Spacer()
                            if let count = type.subtypeCount {
                                Text("\(count) subtypes")
                                    .appFont(.caption2)
                                    .foregroundColor(.secondary)
                            }
                            Image(systemName: "chevron.right")
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 6)
                        .padding(.horizontal, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.secondary.opacity(0.06))
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
    }

    private func subtypesList(for type: CancerType) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                onSelect(type, nil)
            } label: {
                HStack {
                    Image(systemName: "circle.dashed")
                        .foregroundColor(.secondary)
                    Text("Skip subtype — use \(type.displayName ?? type.name) only")
                        .appFont(.body)
                    Spacer()
                }
                .padding(.vertical, 6)
                .padding(.horizontal, 10)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.secondary.opacity(0.06))
                )
            }
            .buttonStyle(.plain)

            if loadingSubtypes {
                ProgressView("Loading subtypes…")
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else if let err = subtypesError {
                errorBlock(err) { Task { await loadSubtypes(for: type) } }
            } else if subtypes.isEmpty {
                Text("No subtypes are curated yet for this type — pick \"Skip subtype\" above.")
                    .appFont(.caption)
                    .foregroundColor(.secondary)
            } else {
                ForEach(subtypes) { subtype in
                    Button {
                        onSelect(type, subtype)
                    } label: {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(subtype.shortName ?? subtype.name)
                                    .appFont(.body, weight: .semibold)
                                if let desc = subtype.description {
                                    Text(desc)
                                        .appFont(.caption)
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                }
                                if let markers = subtype.markers, !markers.isEmpty {
                                    FlowChips(items: markers)
                                }
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 6)
                        .padding(.horizontal, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.secondary.opacity(0.06))
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(16)
    }

    private func errorBlock(_ message: String, retry: @escaping () -> Void) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundColor(.orange)
            Text(message)
                .appFont(.caption)
                .multilineTextAlignment(.center)
            Button("Retry", action: retry)
                .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    @MainActor
    private func loadTypes() async {
        loadingTypes = true
        typesError = nil
        defer { loadingTypes = false }
        do {
            cancerTypes = try await backendService.fetchCancerTypes()
        } catch {
            typesError = error.localizedDescription
        }
    }

    @MainActor
    private func loadSubtypes(for type: CancerType) async {
        loadingSubtypes = true
        subtypesError = nil
        defer { loadingSubtypes = false }
        do {
            subtypes = try await backendService.fetchSubtypes(forCancerTypeId: type.id)
        } catch {
            subtypesError = error.localizedDescription
        }
    }
}

// MARK: - Flow chips

/// Wraps a list of short string labels into a flowing chip layout. Optional
/// `onRemove` shows an X on each chip — used for the selected-drugs list.
private struct FlowChips: View {
    let items: [String]
    var onRemove: ((Int) -> Void)? = nil

    var body: some View {
        // SwiftUI doesn't have a built-in flow layout pre-iOS 16; the macOS
        // target is 13+ so we use Layout-free wrapping via a horizontal-then-
        // vertical fallback. Simple approach: HStack with wrap by line break
        // doesn't exist, so use LazyVGrid with adaptive minimum.
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 100, maximum: 220), spacing: 6, alignment: .leading)],
            alignment: .leading,
            spacing: 6
        ) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(spacing: 4) {
                    Text(item)
                        .appFont(.caption)
                        .lineLimit(1)
                    if let onRemove = onRemove {
                        Button {
                            onRemove(index)
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    Capsule().fill(Color.accentColor.opacity(0.12))
                )
            }
        }
    }
}
