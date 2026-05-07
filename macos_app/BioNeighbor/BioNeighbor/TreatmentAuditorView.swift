//
//  TreatmentAuditorView.swift
//  BioNeighbor
//
//  Treatment Auditor (issue #45). Single-screen workflow where the user
//  describes their cancer treatment plan — disease/subtype, prescribed
//  drugs, scheduled treatments, symptoms/side effects — and the on-device
//  AI cross-references ClinicalTrials.gov data to flag efficacy signals,
//  alternative regimens, and gaps.
//
//  v1 is ephemeral (state lives in @State; nothing persists across launches)
//  and cancer-only. Reuses the v2 cancer-types/subtypes endpoints, the
//  /search/drugs autocomplete, and the existing per-drug trials endpoint.
//  AI streaming goes through OllamaService.auditTreatmentPlan.
//

import SwiftUI

struct TreatmentAuditorView: View {
    @StateObject private var backendService = BackendService.shared
    @AppStorage("ollamaEnabled") private var ollamaEnabled: Bool = false

    // Disease selection
    @State private var selectedCancerType: CancerType?
    @State private var selectedSubtype: CancerSubtype?
    @State private var showDiseasePicker = false

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
    @State private var trialFetchProgress: String?

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
            Text("Research tool only. Not medical advice. Talk to your oncology team before changing any treatment. v1 uses ClinicalTrials.gov data only — adverse-event databases and drug-interaction sources are planned follow-ups.")
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
                VStack(alignment: .leading, spacing: 8) {
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
        selectedCancerType != nil && !prescribedDrugs.isEmpty && !isAuditing
    }

    private var auditSection: some View {
        sectionCard(title: "5. Audit", systemImage: "sparkles") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Button {
                        runAudit()
                    } label: {
                        Label(isAuditing ? "Auditing…" : "Run audit", systemImage: "sparkles")
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

                if let progress = trialFetchProgress {
                    Text(progress)
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }

                if !auditOutput.isEmpty || isAuditing || auditError != nil {
                    AISummaryCard(
                        summary: auditOutput,
                        isStreaming: isAuditing,
                        error: auditError,
                        onRegenerate: { runAudit() },
                        onDismiss: {
                            auditTask?.cancel()
                            auditTask = nil
                            auditOutput = ""
                            auditError = nil
                            isAuditing = false
                            trialFetchProgress = nil
                        }
                    )
                }

                if !canAudit && !isAuditing {
                    Text(disabledReason)
                        .appFont(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    private var disabledReason: String {
        if selectedCancerType == nil { return "Select a cancer type to enable auditing." }
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

    private func runAudit() {
        auditTask?.cancel()
        guard let cancerType = selectedCancerType else { return }

        let drugsSnapshot = prescribedDrugs
        let treatmentsSnapshot = treatments.map(\.text)
        let symptomsSnapshot = symptoms.map {
            TreatmentAuditPlan.Symptom(text: $0.text, severity: $0.severity.label)
        }
        let subtypeSnapshot = selectedSubtype

        auditOutput = ""
        auditError = nil
        isAuditing = true
        trialFetchProgress = "Fetching clinical trials for \(drugsSnapshot.count) drug\(drugsSnapshot.count == 1 ? "" : "s")…"

        auditTask = Task { @MainActor in
            defer {
                isAuditing = false
                trialFetchProgress = nil
            }

            // 1. Fetch trials per drug in parallel (cap concurrency at 5,
            //    matching backend MAX_PARALLEL).
            let drugTrials = await fetchTrialsForDrugs(drugsSnapshot)
            if Task.isCancelled { return }

            trialFetchProgress = nil

            // 2. Build the audit plan and stream the model output.
            let plan = TreatmentAuditPlan(
                cancerTypeName: cancerType.displayName ?? cancerType.name,
                subtypeName: subtypeSnapshot.map { $0.shortName ?? $0.name },
                subtypeMarkers: subtypeSnapshot?.markers,
                drugs: drugsSnapshot.map {
                    TreatmentAuditPlan.Drug(name: $0.name, chemblId: $0.chemblId)
                },
                treatments: treatmentsSnapshot,
                symptoms: symptomsSnapshot,
                drugTrials: drugTrials
            )

            do {
                let stream = OllamaService.shared.auditTreatmentPlan(plan: plan)
                for try await chunk in stream {
                    if Task.isCancelled { return }
                    auditOutput += chunk
                }
            } catch {
                if !Task.isCancelled {
                    auditError = error.localizedDescription
                }
            }
        }
    }

    /// Fetches trials for each prescribed drug that has a ChEMBL ID. Drugs
    /// without a ChEMBL ID are still included with an empty trials list so
    /// the prompt acknowledges them. Capped at 5 concurrent requests.
    private func fetchTrialsForDrugs(
        _ drugs: [PrescribedDrug]
    ) async -> [TreatmentAuditPlan.DrugTrials] {
        await withTaskGroup(of: (Int, TreatmentAuditPlan.DrugTrials).self) { group in
            let maxParallel = 5
            var results = Array<TreatmentAuditPlan.DrugTrials?>(repeating: nil, count: drugs.count)
            var nextIndex = 0
            var inflight = 0

            func enqueue() {
                while inflight < maxParallel && nextIndex < drugs.count {
                    let i = nextIndex
                    let drug = drugs[i]
                    nextIndex += 1
                    inflight += 1
                    group.addTask {
                        let trials: [ClinicalTrial]
                        if let chembl = drug.chemblId, !chembl.isEmpty {
                            do {
                                trials = try await BackendService.shared
                                    .fetchClinicalTrials(chemblId: chembl, limit: 10)
                            } catch {
                                trials = []
                            }
                        } else {
                            trials = []
                        }
                        return (i, TreatmentAuditPlan.DrugTrials(
                            drugName: drug.name,
                            chemblId: drug.chemblId,
                            trials: trials
                        ))
                    }
                }
            }

            enqueue()
            while let (i, payload) = await group.next() {
                results[i] = payload
                inflight -= 1
                enqueue()
            }
            return results.compactMap { $0 }
        }
    }
}

// MARK: - Local model types (ephemeral for v1)

private struct PrescribedDrug: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let chemblId: String?
}

private struct ScheduledTreatment: Identifiable, Hashable {
    let id = UUID()
    let text: String
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
