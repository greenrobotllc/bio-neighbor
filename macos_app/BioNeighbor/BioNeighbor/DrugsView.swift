//
//  DrugsView.swift
//  BioNeighbor
//
//  View for browsing all drugs
//

import SwiftUI

struct DrugsView: View {
    @StateObject private var backendService = BackendService.shared
    @StateObject private var navCoordinator = NavigationCoordinator.shared
    @State private var drugs: [Drug] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""
    @State private var navigationPath = NavigationPath()
    
    var filteredDrugs: [Drug] {
        if searchText.isEmpty {
            return drugs
        }
        return drugs.filter { drug in
            drug.name.localizedCaseInsensitiveContains(searchText) ||
            drug.genericName?.localizedCaseInsensitiveContains(searchText) ?? false ||
            drug.brandNames?.contains { $0.localizedCaseInsensitiveContains(searchText) } ?? false
        }
    }
    
    var body: some View {
        NavigationSplitView {
            // Sidebar with search
            VStack(alignment: .leading, spacing: 16) {
                Text("Drugs")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                
                TextField("Search drugs...", text: $searchText)
                    .textFieldStyle(.roundedBorder)
                
                if !backendService.isBackendRunning {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("⚠️ Backend not running")
                            .font(.headline)
                            .foregroundColor(.orange)
                        
                        Text("The Python backend needs to be started.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Button("Start Backend") {
                            do {
                                try backendService.startBackend()
                                // Give backend time to start, then load
                                DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                                    loadDrugs()
                                }
                            } catch {
                                errorMessage = error.localizedDescription
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                }
                
                if isLoading {
                    ProgressView("Loading drugs...")
                        .frame(maxWidth: .infinity)
                } else {
                    Text("\(filteredDrugs.count) drug\(filteredDrugs.count == 1 ? "" : "s")")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                
                if let error = errorMessage {
                    Text("Error: \(error)")
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
                
                Spacer()
            }
            .padding()
            .frame(minWidth: 250)
        } detail: {
            NavigationStack(path: $navigationPath) {
                // Main content
                Group {
                    ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Breadcrumb
                        BreadcrumbView(coordinator: navCoordinator)
                        
                        Divider()
                        
                        if isLoading {
                    ProgressView("Loading drugs...")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                } else if filteredDrugs.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "pills")
                            .font(.system(size: 60))
                            .foregroundColor(.secondary)
                        Text(searchText.isEmpty ? "No drugs found" : "No drugs match your search")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        if searchText.isEmpty {
                            Text("Drug data may not be loaded yet. Try downloading drug information from the Download Data tab.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                } else {
                    LazyVGrid(columns: [
                        GridItem(.adaptive(minimum: 300), spacing: 16)
                    ], spacing: 16) {
                        ForEach(filteredDrugs) { drug in
                            NavigationLink(value: drug) {
                                DrugCard(drug: drug)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding()
                }
                }
                .padding()
                    }
                }
            .navigationTitle("All Drugs")
            .navigationDestination(for: Drug.self) { drug in
                DrugDetailView(drug: drug)
            }
            .navigationDestination(for: Molecule.self) { molecule in
                MoleculeDetailView(molecule: molecule)
            }
            .onAppear {
                // Push "Drugs" breadcrumb when view appears
                print("🟡 DrugsView onAppear - pushing 'Drugs' breadcrumb")
                navCoordinator.push(BreadcrumbItem(
                    title: "Drugs",
                    icon: "pills",
                    type: .drugs
                ))
                loadDrugs()
            }
        }
        }
    }
    
    private func loadDrugs() {
        guard backendService.isBackendRunning else { return }
        
        isLoading = true
        errorMessage = nil
        
        Task {
            do {
                print("🟡 Loading drugs from backend...")
                let loadedDrugs = try await backendService.getAllDrugs()
                print("🟡 Successfully loaded \(loadedDrugs.count) drugs")
                await MainActor.run {
                    drugs = loadedDrugs
                    isLoading = false
                    errorMessage = nil
                }
            } catch {
                print("🔴 Error loading drugs: \(error.localizedDescription)")
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

#Preview {
    DrugsView()
}

