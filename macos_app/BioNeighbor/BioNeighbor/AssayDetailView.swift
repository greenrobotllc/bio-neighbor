//
//  AssayDetailView.swift
//  BioNeighbor
//
//  Detailed view for an assay
//

import SwiftUI

struct AssayDetailView: View {
    let assay: Assay
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(assay.assayType ?? "Unknown Assay")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                        
                        Spacer()
                        
                        Button("Done") {
                            dismiss()
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding()
                
                Divider()
                
                // Basic Information
                VStack(alignment: .leading, spacing: 12) {
                    Text("Basic Information")
                        .font(.headline)
                    
                    if let dataSource = assay.dataSource {
                        HStack {
                            Text("Data Source:")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            Text(dataSource)
                                .font(.subheadline)
                                .fontWeight(.medium)
                        }
                    }
                    
                    if let pubchemId = assay.pubchemAssayId {
                        HStack {
                            Text("PubChem Assay ID:")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            Text(pubchemId)
                                .font(.subheadline)
                                .fontDesign(.monospaced)
                            
                            Spacer()
                            
                            if let url = URL(string: "https://pubchem.ncbi.nlm.nih.gov/bioassay/\(pubchemId)") {
                                Link(destination: url) {
                                    Label("View on PubChem", systemImage: "arrow.up.right.square")
                                        .font(.caption)
                                }
                            }
                        }
                    }
                    
                    if let chemblId = assay.chemblAssayId {
                        HStack {
                            Text("ChEMBL Assay ID:")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            Text(chemblId)
                                .font(.subheadline)
                                .fontDesign(.monospaced)
                            
                            Spacer()
                            
                            if let url = URL(string: "https://www.ebi.ac.uk/chembl/assay_report_card/\(chemblId)/") {
                                Link(destination: url) {
                                    Label("View on ChEMBL", systemImage: "arrow.up.right.square")
                                        .font(.caption)
                                }
                            }
                        }
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
                .padding(.horizontal)
                
                // Readout
                if let readout = assay.readout {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Readout")
                            .font(.headline)
                        Text(readout)
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                }
                
                // Limitations
                if let limitations = assay.limitations {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Limitations")
                            .font(.headline)
                        Text(limitations)
                            .font(.body)
                            .foregroundColor(.orange)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                    .padding(.horizontal)
                }
                
                // Target Link
                if let targetId = assay.targetId {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Related Target")
                            .font(.headline)
                        
                        NavigationLink(destination: TargetDetailView(targetId: targetId)) {
                            HStack {
                                Text("View Target Details")
                                    .font(.subheadline)
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .foregroundColor(.secondary)
                            }
                            .padding()
                            .background(Color(NSColor.controlBackgroundColor))
                            .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding()
                }
            }
        }
        .navigationTitle("Assay Details")
        .frame(minWidth: 600, minHeight: 500)
    }
}
