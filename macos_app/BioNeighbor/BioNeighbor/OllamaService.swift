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

    /// Streams a treatment-plan audit. Caller has already gathered the user's
    /// disease/subtype, drugs, scheduled treatments, symptoms/side effects,
    /// and per-drug clinical trials. We bundle those into a single prompt and
    /// stream the model's recommendations.
    func auditTreatmentPlan(
        plan: TreatmentAuditPlan
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard self.isEnabled else { throw OllamaError.disabled }
                    let prompt = Self.buildAuditPrompt(plan: plan)
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

    // MARK: - Treatment audit prompt

    static func buildAuditPrompt(plan: TreatmentAuditPlan) -> String {
        var lines: [String] = []
        lines.append("You are reviewing a cancer treatment plan for a researcher / patient advocate.")
        lines.append("Be specific and cite trial NCT IDs when you reference outcomes. Use plain English; flag uncertainty when trial data is sparse or absent. Do not invent trial data.")
        lines.append("")

        lines.append("== Disease ==")
        lines.append("Cancer type: \(plan.cancerTypeName)")
        if let subtype = plan.subtypeName, !subtype.isEmpty {
            lines.append("Subtype: \(subtype)")
        }
        if let markers = plan.subtypeMarkers, !markers.isEmpty {
            lines.append("Markers: \(markers.joined(separator: ", "))")
        }
        lines.append("")

        lines.append("== Prescribed drugs (\(plan.drugs.count)) ==")
        if plan.drugs.isEmpty {
            lines.append("(none provided)")
        } else {
            for drug in plan.drugs {
                let chembl = drug.chemblId.map { " [\($0)]" } ?? ""
                lines.append("- \(drug.name)\(chembl)")
            }
        }
        lines.append("")

        lines.append("== Scheduled treatments / procedures ==")
        if plan.treatments.isEmpty {
            lines.append("(none provided)")
        } else {
            for t in plan.treatments { lines.append("- \(t)") }
        }
        lines.append("")

        lines.append("== Symptoms / side effects ==")
        if plan.symptoms.isEmpty {
            lines.append("(none provided)")
        } else {
            for s in plan.symptoms {
                if let severity = s.severity, !severity.isEmpty {
                    lines.append("- \(s.text) (severity: \(severity))")
                } else {
                    lines.append("- \(s.text)")
                }
            }
        }
        lines.append("")

        lines.append("== Clinical trial digest (per drug) ==")
        if plan.drugTrials.isEmpty {
            lines.append("(no trials retrieved)")
        } else {
            for entry in plan.drugTrials {
                lines.append("--- Drug: \(entry.drugName)\(entry.chemblId.map { " [\($0)]" } ?? "") ---")
                if entry.trials.isEmpty {
                    lines.append("No linked trials found.")
                    continue
                }
                // Cap per-drug trials to avoid blowing context — keep the
                // first 6, which the backend already orders so multi-arm
                // outcome trials come first.
                let trials = Array(entry.trials.prefix(6))
                for trial in trials {
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
                }
            }
        }
        lines.append("")

        lines.append("Write a treatment-plan audit (300–500 words) addressing, in numbered sections:")
        lines.append("1. Efficacy signals: do the listed drugs have positive trial evidence in this cancer subtype?")
        lines.append("2. Alternative or adjunct regimens: are there trial arms that showed clearly better outcomes than what's prescribed? Reference NCT IDs.")
        lines.append("3. Symptom & side-effect concerns: any of the symptoms/side effects above that are notably associated with the listed drugs and worth flagging to the prescriber?")
        lines.append("4. Plan gaps: any treatments listed that don't appear in any trial arm — or any standard-of-care components for this subtype that appear missing?")
        lines.append("5. Uncertainty: where is the evidence thin, and what would you ask the oncology team?")
        lines.append("")
        lines.append("Conclude with EXACTLY two final lines:")
        lines.append("Source: ClinicalTrials.gov.")
        lines.append("Not medical advice. Discuss any plan changes with your oncologist.")
        return lines.joined(separator: "\n")
    }
}

// MARK: - Treatment audit input shapes

/// Inputs the auditor view passes to OllamaService. Kept here (next to
/// `buildAuditPrompt`) so the prompt and its data contract live together.
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

    let cancerTypeName: String
    let subtypeName: String?
    let subtypeMarkers: [String]?
    let drugs: [Drug]
    let treatments: [String]
    let symptoms: [Symptom]
    let drugTrials: [DrugTrials]
}
