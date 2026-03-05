//
//  TargetDetailView.swift
//  BioNeighbor
//
//  Detailed view for a target protein
//

import SwiftUI

struct TargetDetailView: View {
    let targetId: Int
    @State private var target: Target?
    @State private var ligands: [Ligand] = []
    @State private var isLoading = false
    @State private var isLoadingLigands = false
    @State private var errorMessage: String?
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if isLoading {
                    ProgressView("Loading target details...")
                        .frame(maxWidth: .infinity, minHeight: 400)
                } else if let error = errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 32))
                            .foregroundColor(.orange)
                        Text("Error loading target")
                            .font(.headline)
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                        Button("Retry") {
                            loadTarget()
                        }
                        .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity, minHeight: 400)
                    .padding()
                } else if let target = target {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(target.geneSymbol ?? target.proteinName ?? "Unknown Target")
                                .font(.largeTitle)
                                .fontWeight(.bold)
                            
                            Spacer()
                            
                            Button("Done") {
                                dismiss()
                            }
                            .buttonStyle(.bordered)
                        }
                        
                        if let proteinName = target.proteinName, proteinName != target.geneSymbol {
                            Text(proteinName)
                                .font(.title3)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding()
                    
                    Divider()
                    
                    // Basic Information
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Basic Information")
                            .font(.headline)
                        
                        if let uniprotId = target.uniprotId {
                            HStack {
                                Text("UniProt ID:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                Text(uniprotId)
                                    .font(.subheadline)
                                    .fontDesign(.monospaced)
                                
                                Spacer()
                                
                                if let url = URL(string: "https://www.uniprot.org/uniprot/\(uniprotId)") {
                                    Link(destination: url) {
                                        Label("View on UniProt", systemImage: "arrow.up.right.square")
                                            .font(.caption)
                                    }
                                }
                            }
                        }
                        
                        if let geneSymbol = target.geneSymbol {
                            HStack {
                                Text("Gene Symbol:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                Text(geneSymbol)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                            }
                        }
                        
                        if let location = target.cellularLocation {
                            HStack {
                                Text("Cellular Location:")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                Text(location)
                                    .font(.subheadline)
                            }
                        }
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))
                    .cornerRadius(8)
                    .padding(.horizontal)
                    
                    // Function
                    if let function = target.function {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Function")
                                .font(.headline)
                            Text(function)
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                    }
                    
                    // Role in Mechanism
                    if let role = target.roleInMechanism {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Role in Mechanism")
                                .font(.headline)
                            Text(role)
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                    }
                    
                    // Cancer Role
                    if let cancerRole = target.cancerRole {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Cancer Role")
                                .font(.headline)
                            Text(cancerRole)
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                    }
                    
                    // Ligand Types
                    if let ligandTypes = target.ligandTypes, !ligandTypes.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Ligand Types")
                                .font(.headline)
                            FlowLayout(spacing: 8) {
                                ForEach(ligandTypes, id: \.self) { type in
                                    Text(type)
                                        .font(.caption)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.accentColor.opacity(0.2))
                                        .cornerRadius(4)
                                }
                            }
                        }
                        .padding()
                    }
                    
                    // Related Ligands
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Ligands for this Target")
                                .font(.headline)
                            
                            Spacer()
                            
                            if isLoadingLigands {
                                ProgressView()
                                    .scaleEffect(0.7)
                            }
                        }
                        
                        if ligands.isEmpty && !isLoadingLigands {
                            Text("No ligands found for this target")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .padding(.vertical, 8)
                        } else {
                            ForEach(ligands) { ligand in
                                NavigationLink(destination: LigandDetailView(ligand: ligand)) {
                                    LigandRow(ligand: ligand)
                                        .padding(.vertical, 4)
                                        .padding(.horizontal, 8)
                                        .background(Color(NSColor.controlBackgroundColor))
                                        .cornerRadius(6)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .padding()
                    
                    // External Links
                    VStack(alignment: .leading, spacing: 8) {
                        Text("External Resources")
                            .font(.headline)
                        
                        HStack(spacing: 16) {
                            if let uniprotId = target.uniprotId,
                               let url = URL(string: "https://www.uniprot.org/uniprot/\(uniprotId)") {
                                Link(destination: url) {
                                    Label("UniProt", systemImage: "link")
                                }
                            }

                            if let geneSymbol = target.geneSymbol,
                               let encodedSymbol = geneSymbol.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
                               let url = URL(string: "https://www.guidetopharmacology.org/GRAC/DatabaseSearchForward?searchString=\(encodedSymbol)&searchCategories=target") {
                                Link(destination: url) {
                                    Label("IUPHAR", systemImage: "link")
                                }
                            }
                        }
                    }
                    .padding()
                }
            }
        }
        .navigationTitle("Target Details")
        .frame(minWidth: 600, minHeight: 500)
        .onAppear {
            loadTarget()
            loadLigands()
        }
    }
    
    private func loadTarget() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/targets/\(targetId)") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    errorMessage = error.localizedDescription
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response"
                    return
                }
                
                guard httpResponse.statusCode == 200 else {
                    errorMessage = "Server error: HTTP \(httpResponse.statusCode)"
                    return
                }
                
                guard let data = data else {
                    errorMessage = "No data received"
                    return
                }
                
                do {
                    let response = try JSONDecoder().decode(TargetResponse.self, from: data)
                    if response.success, let target = response.target {
                        self.target = target
                    } else {
                        errorMessage = response.error ?? "Failed to load target"
                    }
                } catch {
                    errorMessage = "Failed to decode response: \(error.localizedDescription)"
                }
            }
        }.resume()
    }
    
    private func loadLigands() {
        isLoadingLigands = true

        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/targets/\(targetId)/ligands") else {
            isLoadingLigands = false
            return
        }

        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoadingLigands = false

                if let error = error {
                    print("Failed to load ligands: \(error.localizedDescription)")
                    return
                }

                guard let data = data else { return }

                do {
                    let response = try JSONDecoder().decode(LigandsResponse.self, from: data)
                    if response.success, let ligands = response.ligands {
                        self.ligands = ligands
                    } else if let errorMsg = response.error {
                        print("Failed to load ligands: \(errorMsg)")
                    }
                } catch {
                    print("Failed to decode ligands response: \(error.localizedDescription)")
                }
            }
        }.resume()
    }
}

// Helper view for flow layout (tags)
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(
            in: proposal.replacingUnspecifiedDimensions().width,
            subviews: subviews,
            spacing: spacing
        )
        return result.size
    }
    
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(
            in: bounds.width,
            subviews: subviews,
            spacing: spacing
        )
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + result.frames[index].minX,
                                     y: bounds.minY + result.frames[index].minY),
                         proposal: .unspecified)
        }
    }
    
    struct FlowResult {
        var size: CGSize = .zero
        var frames: [CGRect] = []
        
        init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var currentX: CGFloat = 0
            var currentY: CGFloat = 0
            var lineHeight: CGFloat = 0
            
            for subview in subviews {
                let size = subview.sizeThatFits(.unspecified)
                
                if currentX + size.width > maxWidth && currentX > 0 {
                    currentX = 0
                    currentY += lineHeight + spacing
                    lineHeight = 0
                }
                
                frames.append(CGRect(x: currentX, y: currentY, width: size.width, height: size.height))
                lineHeight = max(lineHeight, size.height)
                currentX += size.width + spacing
            }
            
            self.size = CGSize(width: maxWidth, height: currentY + lineHeight)
        }
    }
}
