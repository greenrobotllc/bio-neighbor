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
}
