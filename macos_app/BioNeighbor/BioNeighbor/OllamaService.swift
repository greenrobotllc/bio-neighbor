//
//  OllamaService.swift
//  BioNeighbor
//
//  Direct client for a local Ollama server. Used by the clinical-trial AI
//  summary feature on the drug detail screen. Talks to Ollama over loopback
//  HTTP — no Python backend in the path. Settings (endpoint, model, enabled)
//  are read from @AppStorage on every call so changes apply immediately.
//

import Foundation
import SwiftUI

enum OllamaError: LocalizedError {
    case disabled
    case invalidEndpoint(String)
    case unreachable(String)
    case http(Int, String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .disabled:
            return "On-device AI summaries are turned off in Settings."
        case .invalidEndpoint(let s):
            return "Invalid Ollama endpoint: \(s)"
        case .unreachable(let s):
            return "Could not reach Ollama at \(s). Is `ollama serve` running?"
        case .http(let code, let body):
            return "Ollama returned HTTP \(code): \(body)"
        case .decoding(let msg):
            return "Could not decode Ollama response: \(msg)"
        }
    }
}

final class OllamaService {
    static let shared = OllamaService()

    // Default endpoint/model. The same defaults are referenced from
    // SettingsView so the picker placeholder matches what the service uses
    // when @AppStorage hasn't been written yet.
    static let defaultEndpoint = "http://127.0.0.1:11434"
    static let defaultModel = "gemma4:26b"

    private init() {}

    // MARK: - Settings access

    private var endpoint: String {
        let raw = UserDefaults.standard.string(forKey: "ollamaEndpoint")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let raw, !raw.isEmpty { return raw }
        return Self.defaultEndpoint
    }

    private var model: String {
        let raw = UserDefaults.standard.string(forKey: "ollamaModel")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let raw, !raw.isEmpty { return raw }
        return Self.defaultModel
    }

    private var isEnabled: Bool {
        UserDefaults.standard.bool(forKey: "ollamaEnabled")
    }

    // MARK: - Public API

    /// `GET /api/tags` — used by the Settings "Test connection" button to
    /// confirm Ollama is reachable and surface which models are pulled.
    func listModels() async throws -> [String] {
        let base = endpoint
        guard let url = URL(string: base + "/api/tags") else {
            throw OllamaError.invalidEndpoint(base)
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = 5
        let (data, resp): (Data, URLResponse)
        do {
            (data, resp) = try await URLSession.shared.data(for: req)
        } catch {
            throw OllamaError.unreachable(base)
        }
        guard let http = resp as? HTTPURLResponse else {
            throw OllamaError.unreachable(base)
        }
        guard http.statusCode == 200 else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw OllamaError.http(http.statusCode, body)
        }
        struct TagsResponse: Decodable {
            struct Model: Decodable { let name: String }
            let models: [Model]
        }
        do {
            let parsed = try JSONDecoder().decode(TagsResponse.self, from: data)
            return parsed.models.map(\.name)
        } catch {
            throw OllamaError.decoding(error.localizedDescription)
        }
    }

    /// Streams plain-English summary text for the supplied trials. Yields
    /// chunks as they arrive so callers can render incrementally. Throws if
    /// Ollama is disabled in Settings, unreachable, or returns an HTTP error.
    func summarizeClinicalTrials(
        trials: [ClinicalTrial],
        drugName: String?
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard self.isEnabled else { throw OllamaError.disabled }
                    let prompt = Self.buildPrompt(trials: trials, drugName: drugName)
                    for try await chunk in self.generate(prompt: prompt) {
                        continuation.yield(chunk)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Streams a per-source mini-summary used in multi-pass audits.
    /// Caller passes a self-contained `sourceBody` string (e.g. a PDQ
    /// section excerpt or a trial digest) plus a short `planContext` that
    /// tells the model what the user's plan looks like, so the mini-summary
    /// can be relevance-filtered against the plan rather than summarizing
    /// the source in the abstract.
    func summarizeAuditSource(
        sourceLabel: String,
        sourceBody: String,
        planContext: String
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard self.isEnabled else { throw OllamaError.disabled }
                    let prompt = Self.buildSourceSummaryPrompt(
                        sourceLabel: sourceLabel,
                        sourceBody: sourceBody,
                        planContext: planContext
                    )
                    for try await chunk in self.generate(prompt: prompt) {
                        continuation.yield(chunk)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Final synthesis pass. Given the user's plan plus the keyed
    /// mini-summaries from `summarizeAuditSource`, produces the long-form
    /// audit shown in the UI.
    func synthesizeAuditFromSummaries(
        plan: TreatmentAuditPlan,
        sourceSummaries: [(label: String, summary: String)]
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard self.isEnabled else { throw OllamaError.disabled }
                    let prompt = Self.buildSynthesisPrompt(
                        plan: plan,
                        sourceSummaries: sourceSummaries
                    )
                    for try await chunk in self.generate(prompt: prompt) {
                        continuation.yield(chunk)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    // MARK: - Internals

    /// `POST /api/generate` with `stream: true`. Ollama emits NDJSON — one
    /// JSON object per line, each containing a `response` chunk and a final
    /// `done: true` line. We yield the `response` field of each line.
    private func generate(prompt: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                let base = self.endpoint
                guard let url = URL(string: base + "/api/generate") else {
                    continuation.finish(throwing: OllamaError.invalidEndpoint(base))
                    return
                }
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.timeoutInterval = 600
                let body: [String: Any] = [
                    "model": self.model,
                    "prompt": prompt,
                    "stream": true,
                ]
                req.httpBody = try? JSONSerialization.data(withJSONObject: body)

                let (bytes, resp): (URLSession.AsyncBytes, URLResponse)
                do {
                    (bytes, resp) = try await URLSession.shared.bytes(for: req)
                } catch {
                    continuation.finish(throwing: OllamaError.unreachable(base))
                    return
                }
                if let http = resp as? HTTPURLResponse, http.statusCode != 200 {
                    var body = ""
                    for try await line in bytes.lines { body += line; if body.count > 2000 { break } }
                    continuation.finish(throwing: OllamaError.http(http.statusCode, body))
                    return
                }

                struct Chunk: Decodable {
                    let response: String?
                    let done: Bool?
                    let error: String?
                }
                do {
                    for try await line in bytes.lines {
                        if Task.isCancelled { break }
                        guard !line.isEmpty, let data = line.data(using: .utf8) else { continue }
                        let parsed = try JSONDecoder().decode(Chunk.self, from: data)
                        if let err = parsed.error {
                            continuation.finish(throwing: OllamaError.http(200, err))
                            return
                        }
                        if let piece = parsed.response, !piece.isEmpty {
                            continuation.yield(piece)
                        }
                        if parsed.done == true { break }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: OllamaError.decoding(error.localizedDescription))
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    // MARK: - Prompt construction

    /// Pure function so it can be eyeballed and tweaked without standing up a
    /// model. Compresses the structured trial data into something the model
    /// can reason over without exceeding sensible context — Gemma 4's 256K
    /// window is huge but we don't need to fill it.
    static func buildPrompt(trials: [ClinicalTrial], drugName: String?) -> String {
        var lines: [String] = []
        lines.append("You are summarizing clinical trial outcomes for a researcher.")
        lines.append("Be concise, factual, and call out uncertainty. Use plain English (no medical-school jargon when a simpler word works).")
        lines.append("")
        if let drugName, !drugName.isEmpty {
            lines.append("Drug: \(drugName)")
        }
        lines.append("Trials (\(trials.count)) below — each block is one trial.")
        lines.append("")

        for trial in trials {
            lines.append("--- NCT: \(trial.nctId) ---")
            if let title = trial.title { lines.append("Title: \(title)") }
            if let status = trial.status { lines.append("Status: \(status)") }
            if let phases = trial.phase, !phases.isEmpty {
                lines.append("Phase: \(phases.joined(separator: ", "))")
            }
            if let arms = trial.arms, !arms.isEmpty {
                lines.append("Arms:")
                for arm in arms {
                    let label = arm.label ?? "—"
                    let interventions = arm.interventions?.joined(separator: " + ") ?? ""
                    lines.append("  - \(label): \(interventions)")
                }
            }
            if let outcomes = trial.primaryOutcomes, !outcomes.isEmpty {
                lines.append("Primary outcomes:")
                for outcome in outcomes {
                    let title = outcome.title ?? "(unnamed)"
                    let unit = outcome.unit.map { " [\($0)]" } ?? ""
                    lines.append("  • \(title)\(unit)")
                    for r in outcome.armResults ?? [] {
                        let arm = r.armLabel ?? "?"
                        let val = r.value ?? "?"
                        let lo = r.lower ?? "?"
                        let hi = r.upper ?? "?"
                        lines.append("      \(arm): value=\(val), 95% CI [\(lo), \(hi)]")
                    }
                }
            } else if !(trial.hasResults ?? false) {
                lines.append("Results: not yet reported")
            }
            lines.append("")
        }

        lines.append("Write a summary in 150–200 words covering:")
        lines.append("1. Overall efficacy signal across these trials.")
        lines.append("2. Which trials or arms looked clearly positive vs. negative or were terminated.")
        lines.append("3. Cross-trial consistency — do results agree, or is the picture mixed?")
        lines.append("4. Any notable termination, withdrawal, or safety signals.")
        lines.append("")
        lines.append("End with one line: \"Source: ClinicalTrials.gov. Not medical advice.\"")
        return lines.joined(separator: "\n")
    }

    // MARK: - Treatment audit prompts (multi-pass)

    /// Compact representation of the user's plan, included with every
    /// per-source mini-summary so the model can filter the source for what's
    /// relevant to *this* patient (right subtype, right stage, etc.) rather
    /// than summarizing the source in the abstract.
    ///
    /// Deliberately omits the DDInter / target-overlap / FAERS deterministic
    /// findings — those are only relevant in the final synthesis (where the
    /// model is asked to restate them verbatim). Including them per-source
    /// would (a) waste tokens on every mini-summary call and (b) tempt the
    /// model to repeat them in each digest, leading to duplicated lines in
    /// the final report. `deterministicFindingsSummary(_:)` builds that
    /// section separately for `buildSynthesisPrompt(...)`.
    static func planContextSummary(_ plan: TreatmentAuditPlan) -> String {
        var lines: [String] = []
        lines.append("Cancer: \(plan.cancerTypeName)")
        if let subtype = plan.subtypeName, !subtype.isEmpty {
            lines.append("Subtype: \(subtype)")
        }
        if let markers = plan.subtypeMarkers, !markers.isEmpty {
            lines.append("Markers: \(markers.joined(separator: ", "))")
        }
        if let stage = plan.stage, !stage.isEmpty {
            lines.append("Stage: \(stage)")
        }
        if let detail = plan.stageDetail, !detail.isEmpty {
            lines.append("Stage detail: \(detail)")
        }
        if !plan.drugs.isEmpty {
            let drugList = plan.drugs.map(\.name).joined(separator: ", ")
            lines.append("Prescribed drugs: \(drugList)")
        }
        if !plan.treatments.isEmpty {
            lines.append("Scheduled treatments: \(plan.treatments.joined(separator: "; "))")
        }
        if !plan.symptoms.isEmpty {
            let formatted = plan.symptoms.map { sym -> String in
                if let severity = sym.severity, !severity.isEmpty {
                    return "\(sym.text) (\(severity))"
                }
                return sym.text
            }
            lines.append("Symptoms / side effects: \(formatted.joined(separator: "; "))")
        }
        return lines.joined(separator: "\n")
    }

    /// Pre-LLM deterministic findings (DDInter interactions, ChEMBL
    /// target overlap, FAERS symptom→reaction matches). Returns "" when
    /// nothing was found AND no data-availability hint is needed, so the
    /// caller can append unconditionally.
    ///
    /// Used ONLY by the final-synthesis prompt — per-source mini-summaries
    /// don't get this block, so the same facts aren't re-emitted N times
    /// across digests.
    static func deterministicFindingsSummary(_ plan: TreatmentAuditPlan) -> String {
        var lines: [String] = []
        // DDInter pairwise interactions (issue #47). Always emits a
        // status line — three distinct states (data unavailable /
        // checked-none-found / findings present) so the LLM has explicit
        // input for section 4 of the synthesis. Without the
        // "checked, none found" line the model would silently fall back
        // to "the plan does not provide information," which falsely
        // implies the user forgot to supply data.
        if !plan.drugInteractionDataAvailable {
            lines.append("Drug-drug interaction data: unavailable (DDInter not loaded server-side).")
        } else if !plan.drugInteractions.isEmpty {
            lines.append("Known pairwise drug-drug interactions (DDInter):")
            for row in plan.drugInteractions {
                let sev = (row.severity?.isEmpty == false) ? row.severity! : "unknown"
                let desc = row.description ?? ""
                lines.append("- \(row.drugA) ↔ \(row.drugB) [severity: \(sev)]: \(desc)")
            }
        } else {
            lines.append(
                "Pairwise drug-drug interactions (DDInter): checked, "
                + "no interactions found among the prescribed drugs."
            )
        }
        // Mechanism-of-action target overlap (issue #53). Always emits a
        // status line — same rationale as the DDInter block above.
        if !plan.targetOverlaps.isEmpty {
            lines.append("Mechanism/target overlap among prescribed drugs (ChEMBL):")
            for row in plan.targetOverlaps {
                let target = row.geneSymbol ?? row.proteinName ?? "shared target"
                let actionA = row.actionTypeA ?? "?"
                let actionB = row.actionTypeB ?? "?"
                lines.append("- \(row.drugA) (\(actionA)) and \(row.drugB) (\(actionB)) both act on \(target).")
            }
        } else {
            lines.append(
                "Mechanism/target overlap (ChEMBL): checked, "
                + "no shared targets found among the prescribed drugs."
            )
        }
        // FAERS symptom→reaction matches (issue #46). Only surface the
        // matches — top-events tables are too noisy for the prompt and
        // the matched rows are what's actually load-bearing for
        // "your symptom is/isn't a known reaction".
        if !plan.faersSymptomMatches.isEmpty {
            lines.append("OpenFDA FAERS post-market reporting matches (symptom → top reaction term):")
            for row in plan.faersSymptomMatches {
                let rankSnippet = row.rankInTop.map { "#\($0) of top reactions, " } ?? ""
                lines.append("- \(row.drugName): \"\(row.symptom)\" ↔ \"\(row.matchedTerm)\" — \(rankSnippet)\(row.count) reports out of \(row.totalReports) total for this drug.")
            }
        }
        return lines.joined(separator: "\n")
    }

    /// Builds the prompt for one mini-summary pass. The model gets a
    /// self-contained source body plus the plan context, and is asked for a
    /// short, factual digest pointed at the audit's downstream synthesis.
    static func buildSourceSummaryPrompt(
        sourceLabel: String,
        sourceBody: String,
        planContext: String
    ) -> String {
        var lines: [String] = []
        lines.append("You are summarizing one evidence source for a multi-source cancer treatment audit.")
        lines.append("Be concise and factual. Do not invent data — only summarize what's in the source below.")
        lines.append("")
        lines.append("== Patient plan (for relevance) ==")
        lines.append(planContext)
        lines.append("")
        lines.append("== Source: \(sourceLabel) ==")
        lines.append(sourceBody)
        lines.append("")
        lines.append("Write a 120-180 word digest covering:")
        lines.append("- What this source says that's relevant to *this* patient's subtype/stage.")
        lines.append("- Specific findings worth surfacing in the final audit (cite NCT IDs if the source is trial data, or section titles if it's a guideline/PDQ).")
        lines.append("- Anything notably missing — modalities or drug classes the source mentions that the patient's plan doesn't include.")
        lines.append("")
        lines.append("Plain prose, no preamble, no headings.")
        return lines.joined(separator: "\n")
    }

    /// Final synthesis prompt. Inputs: the user's plan + the per-source
    /// mini-summaries already produced. Output is the audit shown in the UI.
    static func buildSynthesisPrompt(
        plan: TreatmentAuditPlan,
        sourceSummaries: [(label: String, summary: String)]
    ) -> String {
        var lines: [String] = []
        lines.append("You are writing the final audit of a cancer treatment plan, drawing on per-source summaries already produced.")
        lines.append("Be specific. Cite NCT IDs and the PDQ source URL inline when the answer rests on those sources. Use plain English. Flag uncertainty when evidence is thin. Do not invent trials, NCT IDs, or guidelines.")
        lines.append("")

        lines.append("== Patient plan ==")
        lines.append(planContextSummary(plan))
        lines.append("")

        // Deterministic findings (DDInter / ChEMBL target / FAERS) live in
        // their own block so the synthesis prompt sees them ONCE — they
        // were intentionally omitted from `planContextSummary` to avoid
        // duplicating the same facts across every per-source mini-summary.
        let deterministic = deterministicFindingsSummary(plan)
        if !deterministic.isEmpty {
            lines.append("== Deterministic findings ==")
            lines.append(deterministic)
            lines.append("")
        }

        if let pdq = plan.pdqSummary {
            lines.append("== Citation hint ==")
            lines.append("PDQ source URL (use this when citing standard-of-care text): \(pdq.sourceURL)")
            lines.append("")
        }

        lines.append("== Per-source summaries (\(sourceSummaries.count)) ==")
        if sourceSummaries.isEmpty {
            lines.append("(none — proceed with caution and explicitly note the lack of supporting evidence)")
        } else {
            for entry in sourceSummaries {
                lines.append("--- \(entry.label) ---")
                lines.append(entry.summary)
                lines.append("")
            }
        }
        lines.append("")

        lines.append("Write a treatment-plan audit (400-650 words) addressing, in numbered sections:")
        lines.append("1. Efficacy signals: do the listed drugs have positive trial evidence in this subtype/stage? Cite NCT IDs.")
        lines.append("2. Alternative or adjunct regimens: across the modality summaries (radiation / surgery / chemotherapy / targeted), what trial arms showed clearly better outcomes than drug-only approaches? Compare drug-only vs drug+modality arms when the summaries surface them. Cite NCT IDs.")
        lines.append("3. Symptom & side-effect concerns: any of the patient's symptoms/side effects notably associated with the listed drugs? If the plan section above includes OpenFDA FAERS reaction matches, restate the top one or two specifically (drug, symptom→term, rank, raw counts). Frame these as post-market reporting (association, not causation) — do NOT invent counts.")
        lines.append("4. Drug-drug interactions: restate exactly what the deterministic findings block above says about drug-drug interactions. If it lists DDInter pairwise interactions, restate them verbatim and prioritize Major-severity ones for the prescriber. If it says 'checked, no interactions found', say that explicitly — the audit checked DDInter and no concerning pairs surfaced; do NOT say 'the plan does not provide information.' If it says interaction data was unavailable, say that. Do NOT invent interactions.")
        lines.append("5. Mechanism overlap: restate exactly what the deterministic findings block above says about target overlap. If it lists shared targets, briefly note whether that's likely intentional combination therapy (e.g. CDK4/6 + AI in HR+ breast cancer) or potentially redundant. If it says 'checked, no shared targets found', say that explicitly — the audit checked ChEMBL and no overlap surfaced; do NOT say 'the plan does not provide information.' Do NOT invent overlaps.")
        lines.append("6. Surgical & radiation considerations: address surgery and radiation explicitly when they are part of standard of care for this subtype/stage (use the PDQ summary as the authoritative source — surgery is primary for most early-stage solid tumours including breast, colon, and many lung cancers). Comment on: (a) whether the patient's plan includes the surgical/radiation steps PDQ identifies as standard, (b) timing and sequencing relative to the listed systemic therapy (neoadjuvant vs adjuvant), (c) lymph node assessment when applicable, and (d) any scheduled surgical or radiation treatments the patient supplied — name each one and comment on PDQ alignment. If PDQ doesn't cover surgical/radiation guidance for this cancer (hematologic / advanced metastatic / unmapped), say so. Use \"discuss with your surgical oncologist / radiation oncologist\" framing.")
        lines.append("7. Plan gaps: drug classes AND treatment modalities the standard of care for this subtype/stage typically includes that aren't in the plan. Use the PDQ summary as the authoritative source for SOC framing. Use \"discuss with your oncology team\" language.")
        lines.append("8. Uncertainty: where is evidence thin? What would you ask the oncology team?")
        lines.append("")
        lines.append("Then add a final \"Further reading\" block listing:")
        if let pdq = plan.pdqSummary {
            lines.append("- NCI PDQ summary: \(pdq.sourceURL)")
        }
        lines.append("- Up to 3 key NCT IDs from the summaries above, formatted as https://clinicaltrials.gov/study/{NCT}.")
        lines.append("")
        lines.append("End with EXACTLY this line as the final line:")
        lines.append("Not medical advice. Discuss any plan changes with your oncologist.")
        return lines.joined(separator: "\n")
    }

    // MARK: - Source-body builders (pure helpers used by the auditor view)

    /// Compresses a `PDQSummary` into a prompt-ready text body. Includes the
    /// source URL up top so the model can cite it.
    static func compressPDQ(_ pdq: PDQSummary) -> String {
        var lines: [String] = []
        lines.append("NCI PDQ — \(pdq.slug.capitalized) (Health Professional)")
        lines.append("Source URL: \(pdq.sourceURL)")
        if let stage = pdq.stage, !stage.isEmpty {
            lines.append("Filtered for stage: \(stage)")
        }
        if let detail = pdq.stageDetail, !detail.isEmpty {
            lines.append("Stage detail filter: \(detail)")
        }
        lines.append("")
        for section in pdq.sections {
            lines.append("### \(section.title)")
            if let parent = section.parent, !parent.isEmpty, parent != section.title {
                lines.append("(under: \(parent))")
            }
            lines.append(section.text)
            lines.append("")
        }
        return lines.joined(separator: "\n")
    }

    /// Compresses a list of trials into the same digest format the old
    /// single-pass prompt used. `header` is a free-form description of the
    /// query that produced the list (e.g. "Radiation trials for HER2+ breast
    /// cancer" or "Trials linked to Anastrozole").
    static func compressTrials(_ trials: [ClinicalTrial], header: String) -> String {
        var lines: [String] = []
        lines.append(header)
        lines.append("\(trials.count) trial\(trials.count == 1 ? "" : "s") below.")
        lines.append("")
        // Cap to avoid context blow-up; backend already orders most-informative first.
        for trial in trials.prefix(6) {
            lines.append("NCT: \(trial.nctId)")
            if let title = trial.title { lines.append("  Title: \(title)") }
            if let status = trial.status { lines.append("  Status: \(status)") }
            if let phases = trial.phase, !phases.isEmpty {
                lines.append("  Phase: \(phases.joined(separator: ", "))")
            }
            if let arms = trial.arms, !arms.isEmpty {
                lines.append("  Arms:")
                for arm in arms {
                    let label = arm.label ?? "—"
                    let interventions = arm.interventions?.joined(separator: " + ") ?? ""
                    lines.append("    - \(label): \(interventions)")
                }
            }
            if let outcomes = trial.primaryOutcomes, !outcomes.isEmpty {
                lines.append("  Primary outcomes:")
                for outcome in outcomes {
                    let title = outcome.title ?? "(unnamed)"
                    let unit = outcome.unit.map { " [\($0)]" } ?? ""
                    lines.append("    • \(title)\(unit)")
                    for r in outcome.armResults ?? [] {
                        let arm = r.armLabel ?? "?"
                        let val = r.value ?? "?"
                        lines.append("      \(arm): \(val)")
                    }
                }
            } else if !(trial.hasResults ?? false) {
                lines.append("  Results: not yet reported")
            }
            lines.append("")
        }
        return lines.joined(separator: "\n")
    }
}

// MARK: - Treatment audit input shapes

/// Inputs the auditor view passes to OllamaService. Kept here so the
/// prompt builders and their data contract live together.
struct TreatmentAuditPlan {
    struct Drug {
        let name: String
        let chemblId: String?
    }
    struct Symptom {
        let text: String
        let severity: String?
    }
    struct DrugTrials {
        let drugName: String
        let chemblId: String?
        let trials: [ClinicalTrial]
    }
    /// Trials retrieved by `BackendService.fetchModalityTrials` keyed by the
    /// modality (radiation / surgery / chemotherapy / targeted).
    struct ModalityTrials {
        let modality: String
        let condition: String?
        let trials: [ClinicalTrial]
    }

    /// One pairwise DDInter interaction row included in the audit context
    /// (issue #47). The LLM is instructed to *acknowledge* these
    /// deterministic findings, not infer new ones.
    struct InteractionRow {
        let drugA: String
        let drugB: String
        let severity: String?
        let description: String?
    }

    /// One pairwise target overlap row (issue #53). Each shared target
    /// becomes its own line in the prompt so the LLM can speak about
    /// each one specifically (e.g. "both inhibit CYP19A1").
    struct TargetOverlapRow {
        let drugA: String
        let drugB: String
        let geneSymbol: String?
        let proteinName: String?
        let actionTypeA: String?
        let actionTypeB: String?
    }

    /// One symptom→FAERS reaction match (issue #46). The LLM is asked
    /// to acknowledge these specifically — they connect the user's
    /// reported symptoms to real-world post-market reporting frequency.
    struct FAERSSymptomMatchRow {
        let drugName: String
        let symptom: String
        let matchedTerm: String
        let count: Int
        let rankInTop: Int?
        let totalReports: Int
    }

    let cancerTypeName: String
    let subtypeName: String?
    let subtypeMarkers: [String]?
    let stage: String?
    let stageDetail: String?
    let drugs: [Drug]
    let treatments: [String]
    let symptoms: [Symptom]
    let drugTrials: [DrugTrials]
    let modalityTrials: [ModalityTrials]
    let pdqSummary: PDQSummary?
    /// DDInter pairwise interactions among the prescribed drugs. Empty
    /// when DDInter wasn't loaded or no pairs interact. Treated as
    /// deterministic facts in the prompt — the LLM should not invent new
    /// rows.
    var drugInteractions: [InteractionRow] = []
    /// True when DDInter was loaded server-side. False means
    /// the audit can't speak to interactions at all (different from
    /// "no interactions found").
    var drugInteractionDataAvailable: Bool = true
    /// Mechanism-of-action target overlap among prescribed drugs (issue
    /// #53). Empty when no pairs share a target; surfaced in the prompt
    /// so the LLM can speak to redundancy/combo intent.
    var targetOverlaps: [TargetOverlapRow] = []
    /// Symptom→FAERS reaction matches (issue #46) — one row per
    /// (drug, symptom) where the symptom matched a top reported term.
    var faersSymptomMatches: [FAERSSymptomMatchRow] = []
}
