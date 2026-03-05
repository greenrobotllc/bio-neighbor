//
//  HypothesisGenerationView.swift
//  BioNeighbor
//
//  Section 8: Hypothesis Generation
//

import SwiftUI

struct HypothesisGenerationView: View {
    let mechanism: Mechanism
    @State private var hypotheses: [Hypothesis] = []
    @State private var isLoading = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Hypothesis Generation")
                .font(.title2)
                .bold()
                .padding()
            
            Text("Research hypotheses based on neighbor analysis")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.horizontal)
            
            // Disclaimer
            HStack {
                Image(systemName: "exclamationmark.triangle")
                Text("These are research hypotheses only - not medical advice or treatment recommendations")
                    .font(.caption)
                    .foregroundColor(.orange)
            }
            .padding()
            .background(Color.orange.opacity(0.1))
            .cornerRadius(8)
            .padding(.horizontal)
            
            if isLoading {
                ProgressView("Generating hypotheses...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if hypotheses.isEmpty {
                Text("No hypotheses generated yet")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(hypotheses) { hypothesis in
                    HypothesisRow(hypothesis: hypothesis)
                }
            }
        }
        .onAppear {
            generateHypotheses()
        }
    }
    
    private func generateHypotheses() {
        isLoading = true
        hypotheses = []

        let baseURL = "http://127.0.0.1:5000/cancer-research/mechanisms/\(mechanism.id)"
        let group = DispatchGroup()

        var targets: [[String: Any]] = []
        var ligands: [[String: Any]] = []
        var cancers: [[String: Any]] = []

        // Fetch targets
        group.enter()
        if let url = URL(string: "\(baseURL)/targets") {
            URLSession.shared.dataTask(with: url) { data, _, error in
                defer { group.leave() }
                if let error = error {
                    print("Failed to fetch targets for hypotheses: \(error.localizedDescription)")
                    return
                }
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let items = json["targets"] as? [[String: Any]] {
                    targets = items
                }
            }.resume()
        } else { group.leave() }

        // Fetch ligands
        group.enter()
        if let url = URL(string: "\(baseURL)/ligands") {
            URLSession.shared.dataTask(with: url) { data, _, error in
                defer { group.leave() }
                if let error = error {
                    print("Failed to fetch ligands for hypotheses: \(error.localizedDescription)")
                    return
                }
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let items = json["ligands"] as? [[String: Any]] {
                    ligands = items
                }
            }.resume()
        } else { group.leave() }

        // Fetch cancers
        group.enter()
        if let url = URL(string: "\(baseURL)/cancers") {
            URLSession.shared.dataTask(with: url) { data, _, error in
                defer { group.leave() }
                if let error = error {
                    print("Failed to fetch cancers for hypotheses: \(error.localizedDescription)")
                    return
                }
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let items = json["cancers"] as? [[String: Any]] {
                    cancers = items
                }
            }.resume()
        } else { group.leave() }

        group.notify(queue: .main) {
            self.isLoading = false
            self.hypotheses = self.buildHypotheses(targets: targets, ligands: ligands, cancers: cancers)
        }
    }

    private func buildHypotheses(targets: [[String: Any]], ligands: [[String: Any]], cancers: [[String: Any]]) -> [Hypothesis] {
        var results: [Hypothesis] = []
        let mechanismName = mechanism.name

        // Hypothesis 1: Target coverage
        let targetNames = targets.compactMap { $0["gene_symbol"] as? String }
        if !targetNames.isEmpty {
            results.append(Hypothesis(
                id: "target-coverage",
                label: "Multi-target therapeutic potential",
                description: "\(mechanismName) involves \(targetNames.count) known targets (\(targetNames.prefix(3).joined(separator: ", "))\(targetNames.count > 3 ? "..." : "")). Compounds interacting with multiple targets in this pathway may show enhanced efficacy through synergistic modulation.",
                supportingNeighbors: Array(targetNames.prefix(5)),
                mechanismId: mechanism.id,
                confidence: min(Double(targetNames.count) / 10.0, 0.8)
            ))
        }

        // Hypothesis 2: Ligand diversity
        let ligandTypes = Set(ligands.compactMap { $0["interaction_type"] as? String })
        if ligands.count > 1 {
            results.append(Hypothesis(
                id: "ligand-diversity",
                label: "Structural diversity suggests multiple binding modes",
                description: "\(ligands.count) ligands have been identified for the \(mechanismName) pathway\(ligandTypes.isEmpty ? "" : " with interaction types: \(ligandTypes.joined(separator: ", "))"). This structural diversity suggests the mechanism can be modulated through multiple distinct binding modes.",
                supportingNeighbors: ligands.prefix(3).compactMap { $0["name"] as? String },
                mechanismId: mechanism.id,
                confidence: min(Double(ligands.count) / 50.0, 0.7)
            ))
        }

        // Hypothesis 3: Cross-cancer relevance
        let highActivityCancers = cancers.filter { ($0["activity_level"] as? String) == "High" }
        if !cancers.isEmpty {
            let cancerNames = cancers.prefix(4).compactMap { $0["cancer_type"] as? String }
            results.append(Hypothesis(
                id: "cross-cancer",
                label: "Cross-cancer therapeutic opportunity",
                description: "The \(mechanismName) pathway shows activity across \(cancers.count) cancer types\(highActivityCancers.isEmpty ? "" : " with high activity in \(highActivityCancers.count)"). Drugs targeting this mechanism may have broad applicability, warranting basket trial investigation.",
                supportingNeighbors: cancerNames,
                mechanismId: mechanism.id,
                confidence: min(Double(cancers.count) / 8.0, 0.75)
            ))
        }

        // Hypothesis 4: Immune modulation (if mechanism has immune effects)
        if let immuneEffects = mechanism.immuneEffects, !immuneEffects.isEmpty {
            results.append(Hypothesis(
                id: "immune-modulation",
                label: "Immunotherapy combination potential",
                description: "The \(mechanismName) pathway has known immune effects: \(immuneEffects). This suggests potential synergy with existing immunotherapy approaches such as checkpoint inhibitors.",
                supportingNeighbors: targetNames.prefix(3).map { String($0) },
                mechanismId: mechanism.id,
                confidence: 0.6
            ))
        }

        return results
    }
}

struct HypothesisRow: View {
    let hypothesis: Hypothesis
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(hypothesis.label)
                .font(.headline)
            
            Text(hypothesis.description)
                .font(.body)
            
            if !hypothesis.supportingNeighbors.isEmpty {
                Text("Supporting neighbors: \(hypothesis.supportingNeighbors.joined(separator: ", "))")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if let confidence = hypothesis.confidence {
                HStack {
                    Text("Confidence:")
                    ProgressView(value: confidence)
                        .frame(width: 100)
                    Text(String(format: "%.0f%%", confidence * 100))
                        .font(.caption)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
