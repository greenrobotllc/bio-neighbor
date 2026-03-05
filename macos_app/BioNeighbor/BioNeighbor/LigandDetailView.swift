//
//  LigandDetailView.swift
//  BioNeighbor
//
//  Detailed view for a ligand/compound
//

import SwiftUI

struct LigandDetailView: View {
    let ligand: Ligand
    @State private var target: Target?
    @State private var moleculeImage: NSImage?
    @State private var isLoadingImage = false
    @State private var showSimilarityAnalysis = false
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(ligand.name ?? "Unknown Ligand")
                                .font(.largeTitle)
                                .fontWeight(.bold)
                            
                            Spacer()
                            
                            Button("Done") {
                                dismiss()
                            }
                            .buttonStyle(.bordered)
                            .keyboardShortcut(.escape, modifiers: [])
                        }
                        
                        if let chemblId = ligand.chemblId {
                            Text(chemblId)
                                .font(.title3)
                                .foregroundColor(.secondary)
                                .fontDesign(.monospaced)
                        }
                    }
                    .padding()
                    
                    Divider()
                    
                    // Structure Visualization
                    if ligand.smiles != nil {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Structure")
                                .font(.headline)
                            
                            if isLoadingImage {
                                ProgressView()
                                    .frame(maxWidth: .infinity, minHeight: 200)
                            } else if let image = moleculeImage {
                                Image(nsImage: image)
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .frame(maxWidth: .infinity, minHeight: 200)
                                    .background(Color.white)
                                    .cornerRadius(8)
                            } else {
                                Rectangle()
                                    .fill(Color.gray.opacity(0.2))
                                    .frame(height: 200)
                                    .overlay {
                                        Text("Structure visualization not available")
                                            .foregroundColor(.secondary)
                                    }
                            }
                        }
                        .padding()
                    }
                    
                    // Basic Information
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Basic Information")
                            .font(.headline)
                        
                        if let chemblId = ligand.chemblId {
                            HStack {
                                Text("ChEMBL ID:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                Text(chemblId)
                                    .font(.subheadline)
                                    .fontDesign(.monospaced)
                                
                                Spacer()
                                
                                if let url = URL(string: "https://www.ebi.ac.uk/chembl/compound_report_card/\(chemblId)/") {
                                    Link(destination: url) {
                                        Label("View on ChEMBL", systemImage: "arrow.up.right.square")
                                            .font(.caption)
                                    }
                                }
                            }
                        }
                        
                        if let pubchemCid = ligand.pubchemCid {
                            HStack {
                                Text("PubChem CID:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                Text(pubchemCid)
                                    .font(.subheadline)
                                    .fontDesign(.monospaced)
                                
                                Spacer()
                                
                                if let url = URL(string: "https://pubchem.ncbi.nlm.nih.gov/compound/\(pubchemCid)") {
                                    Link(destination: url) {
                                        Label("View on PubChem", systemImage: "arrow.up.right.square")
                                            .font(.caption)
                                    }
                                }
                            }
                        }
                        
                        if let interactionType = ligand.interactionType {
                            HStack {
                                Text("Interaction Type:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                Text(interactionType.capitalized)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                            }
                        }
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))
                    .cornerRadius(8)
                    .padding(.horizontal)
                    
                    // Target Information
                    if let targetId = ligand.targetId {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Target")
                                .font(.headline)
                            
                            if let target = target {
                                NavigationLink(destination: TargetDetailView(targetId: target.id)) {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(target.geneSymbol ?? target.proteinName ?? "Unknown Target")
                                                .font(.headline)
                                            if let proteinName = target.proteinName {
                                                Text(proteinName)
                                                    .font(.caption)
                                                    .foregroundColor(.secondary)
                                            }
                                        }
                                        Spacer()
                                        Image(systemName: "chevron.right")
                                            .foregroundColor(.secondary)
                                    }
                                    .padding()
                                    .background(Color(NSColor.controlBackgroundColor))
                                    .cornerRadius(6)
                                }
                                .buttonStyle(.plain)
                            } else {
                                Text("Loading target information...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding()
                    }

                    // SMILES
                    if let smiles = ligand.smiles {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("SMILES")
                                .font(.headline)
                            
                            Text(smiles)
                                .font(.system(.body, design: .monospaced))
                                .padding()
                                .background(Color.gray.opacity(0.1))
                                .cornerRadius(8)
                                .textSelection(.enabled)
                        }
                        .padding()
                    }
                    
                    // Similarity Analysis Link
                    if ligand.smiles != nil {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Similarity Analysis")
                                .font(.headline)
                            
                            Text("Use the Similarity Analysis section in the mechanism workspace to find similar ligands.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                    }
                }
        }
        .navigationTitle("Ligand Details")
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            if let smiles = ligand.smiles {
                loadMoleculeImage(smiles: smiles)
            }
            if let targetId = ligand.targetId {
                loadTarget(targetId: targetId)
            }
        }
    }
    
    private func loadTarget(targetId: Int) {
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/targets/\(targetId)") else {
            return
        }
        
        let task = URLSession.shared.dataTask(with: url) { (data: Data?, response: URLResponse?, error: Error?) -> Void in
            DispatchQueue.main.async {
                guard let data = data,
                      let response = try? JSONDecoder().decode(TargetResponse.self, from: data),
                      response.success,
                      let target = response.target else {
                    return
                }
                
                self.target = target
            }
        }
        task.resume()
    }
    
    private func loadMoleculeImage(smiles: String) {
        isLoadingImage = true
        
        guard let url = URL(string: "http://127.0.0.1:5000/api/render-molecule") else {
            isLoadingImage = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = ["smiles": smiles, "width": 400, "height": 400, "enhanced": true]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                isLoadingImage = false
                
                guard let data = data,
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let imageBase64 = json["image"] as? String,
                      let imageData = Data(base64Encoded: imageBase64),
                      let image = NSImage(data: imageData) else {
                    return
                }
                
                self.moleculeImage = image
            }
        }.resume()
    }
}

