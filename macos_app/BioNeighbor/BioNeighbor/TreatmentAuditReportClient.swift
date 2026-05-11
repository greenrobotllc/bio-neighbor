//
//  TreatmentAuditReportClient.swift
//  BioNeighbor
//
//  Renders a completed Treatment Auditor run (issue #67) as a PDF by POSTing
//  the audit data to the backend's /treatment-auditor/report.pdf endpoint and
//  writing the response bytes to disk. Replaces the in-Swift PDF builder so
//  the Python CLI and the macOS app share one source of truth for layout,
//  copy, and styling — the HTML + CSS + WeasyPrint pipeline now lives in
//  backend/treatment_auditor_report.py.
//
//  This file owns three things:
//    1. `ReportPayload` — the Encodable wire format the backend expects.
//    2. `renderPDF(snapshot:to:)` — POSTs the payload, writes the PDF to disk.
//    3. `defaultFilename(for:)` — picks a sensible default for NSSavePanel,
//       moved here unchanged from the deleted exporter so callers don't break.
//

import Foundation

// MARK: - Snapshot the auditor view passes in
//
// These two types lived in the deleted `TreatmentAuditReportExporter.swift`
// before #67 moved PDF rendering into the backend. They are part of the
// auditor's public surface — `TreatmentAuditorView` builds a snapshot when
// the run finishes and hands it to `renderPDF(snapshot:to:)` — so they
// stay in the report-client file rather than the view file.

/// One per-source mini-summary as captured during the audit run.
struct AuditSourceSummary: Hashable {
    let label: String
    let summary: String
}

/// Frozen snapshot of a finished audit. Held by `TreatmentAuditorView` so
/// the "Save as PDF…" button can render exactly what the user just saw,
/// even if they edit the form afterwards.
///
/// `plan` carries the deterministic findings the PDF renders alongside the
/// inputs (drug interactions, target overlap, FAERS matches). `mergeNotes`
/// is captured separately because the merge happens *before* `plan.drugs`
/// is populated — by the time the plan exists, the original brand/generic
/// duplicates have already been collapsed and we need the audit history to
/// recover what was merged.
struct CompletedAuditSnapshot {
    let plan: TreatmentAuditPlan
    let sourceSummaries: [AuditSourceSummary]
    let finalAudit: String
    let steps: [AuditStep]
    let generatedAt: Date
    /// Brand→generic merges flagged by the RxNorm dedupe step (issue #55).
    /// Empty when no inputs collapsed.
    var mergeNotes: [DrugMergeNote] = []
    /// FAERS per-drug top events captured for the report (issue #46).
    /// Stored on the snapshot rather than the plan because the LLM prompt
    /// only needs the symptom→reaction matches; the full per-drug top
    /// list is for the human reader of the PDF.
    var faersPanels: [FAERSDrugPanel] = []
}

@MainActor
enum TreatmentAuditReportClient {

    /// Default backend base URL — mirrors `BackendService.baseURL`. Kept as
    /// a constant here rather than reaching into BackendService so the
    /// report client stays self-contained and easy to point at a remote
    /// backend for testing.
    static let backendBaseURL = "http://127.0.0.1:5000"
    static let reportPath = "/cancer-research/v2/treatment-auditor/report.pdf"

    /// Render the supplied snapshot as PDF and write it to `outputURL`.
    /// Throws on transport failures or non-2xx backend responses.
    static func renderPDF(snapshot: CompletedAuditSnapshot, to outputURL: URL) async throws {
        guard let url = URL(string: backendBaseURL + reportPath) else {
            throw NSError(
                domain: "TreatmentAuditReportClient",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Invalid backend URL."]
            )
        }
        let payload = ReportPayload(snapshot: snapshot)
        let encoder = JSONEncoder()
        // Backend tolerates either field order, but stable output makes
        // request bodies easier to diff in network logs while debugging.
        encoder.outputFormatting = [.sortedKeys]
        let body = try encoder.encode(payload)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/pdf", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 120
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw NSError(
                domain: "TreatmentAuditReportClient",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "No HTTP response from backend."]
            )
        }
        if http.statusCode != 200 {
            // Backend returns JSON error bodies — surface the message instead
            // of dumping the raw HTML Flask emits on unexpected exceptions.
            let message: String
            if let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let err = parsed["error"] as? String {
                message = err
            } else {
                message = "HTTP \(http.statusCode)"
            }
            throw NSError(
                domain: "TreatmentAuditReportClient",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: "PDF render failed: \(message)"]
            )
        }
        // Defensive: a 200 from a misconfigured proxy (or a backend regression
        // that returns JSON with a 200) would otherwise be written verbatim
        // to the user's chosen .pdf path. Confirm by Content-Type or PDF magic
        // before persisting.
        let contentType = (http.value(forHTTPHeaderField: "Content-Type") ?? "").lowercased()
        let pdfMagic: [UInt8] = [0x25, 0x50, 0x44, 0x46, 0x2D] // "%PDF-"
        let hasPDFMagic = data.count >= pdfMagic.count
            && [UInt8](data.prefix(pdfMagic.count)) == pdfMagic
        if !contentType.contains("application/pdf") && !hasPDFMagic {
            let message: String
            if let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let err = parsed["error"] as? String {
                message = err
            } else {
                let snippet = String(data: data.prefix(200), encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                message = snippet.isEmpty ? "Backend returned a non-PDF response." : "Backend returned non-PDF content: \(snippet)"
            }
            throw NSError(
                domain: "TreatmentAuditReportClient",
                code: 3,
                userInfo: [NSLocalizedDescriptionKey: "PDF render failed: \(message)"]
            )
        }
        try data.write(to: outputURL, options: .atomic)
    }

    /// Suggested filename for NSSavePanel — `treatment-audit-<slug>-<stamp>.pdf`.
    /// Carried over verbatim from the deleted local exporter so the UX
    /// of the "Save as PDF…" panel is unchanged.
    static func defaultFilename(for snapshot: CompletedAuditSnapshot) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmm"
        let stamp = formatter.string(from: snapshot.generatedAt)
        let raw = snapshot.plan.subtypeName ?? snapshot.plan.cancerTypeName
        let slug = sanitizeForFilename(raw)
        let base = slug.isEmpty ? "audit" : slug
        return "treatment-audit-\(base)-\(stamp).pdf"
    }

    private static func sanitizeForFilename(_ raw: String) -> String {
        let lowered = raw.lowercased()
        var out = ""
        var lastWasDash = false
        for scalar in lowered.unicodeScalars {
            let c = Character(scalar)
            if c.isLetter || c.isNumber {
                out.append(c)
                lastWasDash = false
            } else if !lastWasDash {
                out.append("-")
                lastWasDash = true
            }
        }
        return out.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    }
}

// MARK: - Wire format
//
// Encodable structs that map onto the schema in
// backend/treatment_auditor_report.py. Field names use snake_case
// CodingKeys throughout so the JSON the backend sees is identical
// to what the Python CLI POSTs. Optional fields are encoded only when
// non-nil (the backend treats every section past `plan` as optional and
// elides missing ones gracefully).

private struct ReportPayload: Encodable {
    let generatedAt: String
    let plan: WirePlan
    let steps: [WireStep]
    let mergeNotes: [WireMergeNote]
    let pdqSummary: WirePDQSummary?
    let modalityTrials: [WireModalityTrials]
    let drugTrials: [WireDrugTrials]
    let drugInteractions: [WireInteraction]
    let drugInteractionDataAvailable: Bool
    let targetOverlaps: [WireTargetOverlap]
    let faersPanels: [FAERSDrugPanel]
    let faersSymptomMatches: [FAERSSymptomMatch]
    let sourceSummaries: [WireSourceSummary]
    let finalAudit: String

    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at"
        case plan
        case steps
        case mergeNotes = "merge_notes"
        case pdqSummary = "pdq_summary"
        case modalityTrials = "modality_trials"
        case drugTrials = "drug_trials"
        case drugInteractions = "drug_interactions"
        case drugInteractionDataAvailable = "drug_interaction_data_available"
        case targetOverlaps = "target_overlaps"
        case faersPanels = "faers_panels"
        case faersSymptomMatches = "faers_symptom_matches"
        case sourceSummaries = "source_summaries"
        case finalAudit = "final_audit"
    }

    init(snapshot: CompletedAuditSnapshot) {
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime]
        self.generatedAt = isoFormatter.string(from: snapshot.generatedAt)

        let plan = snapshot.plan
        self.plan = WirePlan(
            cancerType: plan.cancerTypeName,
            cancerTypeDisplay: plan.cancerTypeName,
            subtype: plan.subtypeName,
            subtypeDisplay: plan.subtypeName,
            subtypeMarkers: plan.subtypeMarkers ?? [],
            stage: plan.stage ?? "",
            stageDetail: plan.stageDetail ?? "",
            drugs: plan.drugs.map { WireDrug(name: $0.name, chemblId: $0.chemblId) },
            treatments: plan.treatments,
            symptoms: plan.symptoms.map { WireSymptom(text: $0.text, severity: $0.severity) }
        )

        self.steps = snapshot.steps.map { WireStep(step: $0) }
        self.mergeNotes = snapshot.mergeNotes.map {
            WireMergeNote(originalNames: $0.originalNames, ingredientName: $0.ingredientName)
        }
        if let pdq = plan.pdqSummary {
            self.pdqSummary = WirePDQSummary(
                slug: pdq.slug,
                sourceUrl: pdq.sourceURL,
                stage: pdq.stage,
                stageDetail: pdq.stageDetail,
                sections: pdq.sections.map { WirePDQSection(title: $0.title, level: $0.level, parent: $0.parent, text: $0.text) }
            )
        } else {
            self.pdqSummary = nil
        }
        self.modalityTrials = plan.modalityTrials.map {
            WireModalityTrials(modality: $0.modality, condition: $0.condition, trials: $0.trials)
        }
        self.drugTrials = plan.drugTrials.map {
            WireDrugTrials(drugName: $0.drugName, chemblId: $0.chemblId, trials: $0.trials)
        }
        self.drugInteractions = plan.drugInteractions.map {
            WireInteraction(drugA: $0.drugA, drugB: $0.drugB, severity: $0.severity, description: $0.description)
        }
        self.drugInteractionDataAvailable = plan.drugInteractionDataAvailable

        // Flatten ChEMBL target overlap rows: one wire row per shared target,
        // carrying the parent pair's drug names. Mirrors the report builder's
        // expectation (TreatmentAuditPlan.TargetOverlapRow in the Swift type
        // hierarchy is already row-per-target; this matches it in JSON).
        var flatOverlaps: [WireTargetOverlap] = []
        for row in plan.targetOverlaps {
            flatOverlaps.append(WireTargetOverlap(
                drugA: row.drugA,
                drugB: row.drugB,
                geneSymbol: row.geneSymbol,
                proteinName: row.proteinName,
                actionTypeA: row.actionTypeA,
                actionTypeB: row.actionTypeB
            ))
        }
        self.targetOverlaps = flatOverlaps

        self.faersPanels = snapshot.faersPanels
        self.faersSymptomMatches = plan.faersSymptomMatches.map {
            FAERSSymptomMatch(
                drugName: $0.drugName,
                symptom: $0.symptom,
                matchedTerm: $0.matchedTerm,
                count: $0.count,
                rankInTop: $0.rankInTop,
                totalReports: $0.totalReports
            )
        }
        self.sourceSummaries = snapshot.sourceSummaries.map {
            WireSourceSummary(label: $0.label, summary: $0.summary)
        }
        self.finalAudit = snapshot.finalAudit
    }
}

private struct WirePlan: Encodable {
    let cancerType: String
    let cancerTypeDisplay: String
    let subtype: String?
    let subtypeDisplay: String?
    let subtypeMarkers: [String]
    let stage: String
    let stageDetail: String
    let drugs: [WireDrug]
    let treatments: [String]
    let symptoms: [WireSymptom]

    enum CodingKeys: String, CodingKey {
        case cancerType = "cancer_type"
        case cancerTypeDisplay = "cancer_type_display"
        case subtype
        case subtypeDisplay = "subtype_display"
        case subtypeMarkers = "subtype_markers"
        case stage
        case stageDetail = "stage_detail"
        case drugs
        case treatments
        case symptoms
    }
}

private struct WireDrug: Encodable {
    let name: String
    let chemblId: String?

    enum CodingKeys: String, CodingKey {
        case name
        case chemblId = "chembl_id"
    }
}

private struct WireSymptom: Encodable {
    let text: String
    let severity: String?
}

private struct WireStep: Encodable {
    let label: String
    let state: String
    let detail: String?

    init(step: AuditStep) {
        self.label = step.label
        // The explicit `step.detail` field wins when set — used with .done
        // for "ran cleanly, here's what happened" annotations. Falls back
        // to the associated value on .skipped / .failed when no explicit
        // detail was supplied. Mirrors `AuditStepList.renderedDetail(_:)`.
        let preferred = step.detail?.isEmpty == false ? step.detail : nil
        switch step.state {
        case .running:
            self.state = "running"
            self.detail = preferred
        case .done:
            self.state = "done"
            self.detail = preferred
        case .skipped(let reason):
            self.state = "skipped"
            self.detail = preferred ?? reason
        case .failed(let message):
            self.state = "failed"
            self.detail = preferred ?? message
        }
    }
}

private struct WireMergeNote: Encodable {
    let originalNames: [String]
    let ingredientName: String

    enum CodingKeys: String, CodingKey {
        case originalNames = "original_names"
        case ingredientName = "ingredient_name"
    }
}

private struct WirePDQSummary: Encodable {
    let slug: String
    let sourceUrl: String
    let stage: String?
    let stageDetail: String?
    let sections: [WirePDQSection]

    enum CodingKeys: String, CodingKey {
        case slug
        case sourceUrl = "source_url"
        case stage
        case stageDetail = "stage_detail"
        case sections
    }
}

private struct WirePDQSection: Encodable {
    let title: String
    let level: Int
    let parent: String?
    let text: String
}

private struct WireModalityTrials: Encodable {
    let modality: String
    let condition: String?
    let trials: [ClinicalTrial]
}

private struct WireDrugTrials: Encodable {
    let drugName: String
    let chemblId: String?
    let trials: [ClinicalTrial]

    enum CodingKeys: String, CodingKey {
        case drugName = "drug_name"
        case chemblId = "chembl_id"
        case trials
    }
}

private struct WireInteraction: Encodable {
    let drugA: String
    let drugB: String
    let severity: String?
    let description: String?

    enum CodingKeys: String, CodingKey {
        case drugA = "drug_a"
        case drugB = "drug_b"
        case severity
        case description
    }
}

private struct WireTargetOverlap: Encodable {
    let drugA: String
    let drugB: String
    let geneSymbol: String?
    let proteinName: String?
    let actionTypeA: String?
    let actionTypeB: String?

    enum CodingKeys: String, CodingKey {
        case drugA = "drug_a"
        case drugB = "drug_b"
        case geneSymbol = "gene_symbol"
        case proteinName = "protein_name"
        case actionTypeA = "action_type_a"
        case actionTypeB = "action_type_b"
    }
}

private struct WireSourceSummary: Encodable {
    let label: String
    let summary: String
}
