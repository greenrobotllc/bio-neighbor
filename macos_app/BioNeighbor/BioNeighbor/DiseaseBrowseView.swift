//
//  DiseaseBrowseView.swift
//  BioNeighbor
//
//  Disease-based molecule browsing interface
//

import SwiftUI

struct DiseaseBrowseView: View {
    @StateObject private var backendService = BackendService.shared
    @StateObject private var navCoordinator = NavigationCoordinator.shared
    @State private var diseases: [Disease] = []
    @State private var selectedDisease: Disease?
    @State private var diseaseMolecules: [MoleculeBasic] = []
    @State private var diseaseDrugs: [Drug] = []
    @State private var similarMolecules: [Molecule] = []
    @State private var isLoadingDiseases = false
    @State private var isLoadingMolecules = false
    @State private var isLoadingDrugs = false
    @State private var isLoadingSimilar = false
    @State private var errorMessage: String?
    @State private var diseaseSearchText = ""
    @State private var showSimilarMolecules = false
    @State private var showDrugs = true  // Default to showing drugs
    @State private var isDownloadingDrugs = false
    @State private var downloadProgress: String?
    @State private var navigationPath = NavigationPath()
    
    var filteredDiseases: [Disease] {
        if diseaseSearchText.isEmpty {
            return diseases
        }
        return diseases.filter { disease in
            disease.name.localizedCaseInsensitiveContains(diseaseSearchText)
        }
    }
    
    var body: some View {
        NavigationSplitView {
            // Sidebar with disease selector
            VStack(alignment: .leading, spacing: 20) {
                Text("Disease Browser")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 10)
                
                Text("Browse molecules by disease")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Divider()
                
                // Disease search
                VStack(alignment: .leading, spacing: 8) {
                    Text("Search Diseases")
                        .font(.headline)
                    
                    TextField("Type to search...", text: $diseaseSearchText)
                        .textFieldStyle(.roundedBorder)
                        .onChange(of: diseaseSearchText) { _ in
                            // Auto-select first match if search narrows to one result
                            if filteredDiseases.count == 1, selectedDisease?.id != filteredDiseases[0].id {
                                selectedDisease = filteredDiseases[0]
                                loadDiseaseMolecules()
                            }
                        }
                }
                
                // Disease list
                if isLoadingDiseases {
                    HStack {
                        ProgressView()
                        Text("Loading diseases...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                } else if diseases.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("No diseases found")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        
                        Text("Disease data may not be loaded yet.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        Button("Load Diseases") {
                            loadDiseases()
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 8) {
                            ForEach(filteredDiseases) { disease in
                                DiseaseRow(
                                    disease: disease,
                                    isSelected: selectedDisease?.id == disease.id
                                ) {
                                selectedDisease = disease
                            // Push disease breadcrumb when selected
                            print("🟡 Disease selected: \(disease.name)")
                            navCoordinator.push(BreadcrumbItem(
                                title: disease.name,
                                icon: "cross.case",
                                type: .disease
                            ))
                            if showDrugs {
                                loadDiseaseDrugs()
                            }
                            loadDiseaseMolecules()
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
                
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
            .frame(minWidth: 300)
        } detail: {
            NavigationStack(path: $navigationPath) {
                // Main content area
                if let disease = selectedDisease {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            // Breadcrumb
                            BreadcrumbView(coordinator: navCoordinator)
                            
                            Divider()
                        
                        // Disease header
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(disease.name)
                                        .font(.title)
                                        .fontWeight(.bold)
                                    
                                    if let meshId = disease.meshId {
                                        Text("MeSH ID: \(meshId)")
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                            .fontDesign(.monospaced)
                                    }
                                    
                                    if let description = disease.description, !description.isEmpty {
                                        Text(description)
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                            .padding(.top, 4)
                                    }
                                }
                                
                                Spacer()
                                
                                if isLoadingDrugs || isLoadingMolecules {
                                    ProgressView()
                                } else {
                                    VStack(alignment: .trailing, spacing: 4) {
                                        if showDrugs {
                                            Text("\(diseaseDrugs.count) drugs")
                                                .font(.headline)
                                                .foregroundColor(.blue)
                                        }
                                        Text("\(diseaseMolecules.count) molecules")
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }
                        .padding()
                        .background(Color(NSColor.controlBackgroundColor))
                        .cornerRadius(8)
                        
                        // Toggle for drugs vs molecules
                        HStack {
                            Toggle("Show Drugs", isOn: $showDrugs)
                                .onChange(of: showDrugs) { newValue in
                                    if newValue && diseaseDrugs.isEmpty {
                                        loadDiseaseDrugs()
                                    }
                                }
                            
                            Toggle("Show Similar Molecules", isOn: $showSimilarMolecules)
                                .onChange(of: showSimilarMolecules) { newValue in
                                    if newValue && similarMolecules.isEmpty {
                                        loadSimilarMolecules()
                                    }
                                }
                            
                            Spacer()
                            
                            Button("Refresh") {
                                if showDrugs {
                                    loadDiseaseDrugs()
                                }
                                loadDiseaseMolecules()
                                if showSimilarMolecules {
                                    loadSimilarMolecules()
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(isLoadingMolecules || isLoadingDrugs || isLoadingSimilar)
                        }
                        
                        // Drugs section (if enabled)
                        if showDrugs {
                            if isLoadingDrugs {
                                ProgressView("Loading drugs...")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 40)
                            } else if diseaseDrugs.isEmpty {
                                VStack(spacing: 16) {
                                    Image(systemName: "pills")
                                        .font(.system(size: 60))
                                        .foregroundColor(.secondary)
                                    Text("No drugs found for this disease")
                                        .font(.headline)
                                        .foregroundColor(.secondary)
                                    Text("Drug data may not be loaded yet. Download drugs for this disease from PubChem.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .multilineTextAlignment(.center)
                                    
                                    if isDownloadingDrugs {
                                        VStack(spacing: 8) {
                                            ProgressView()
                                            if let progress = downloadProgress {
                                                Text(progress)
                                                    .font(.caption)
                                                    .foregroundColor(.secondary)
                                            }
                                        }
                                        .padding(.top, 8)
                                    } else {
                                        Button(action: {
                                            downloadDrugsForDisease()
                                        }) {
                                            Label("Download Drugs for \(disease.name)", systemImage: "arrow.down.circle.fill")
                                        }
                                        .buttonStyle(.borderedProminent)
                                        .padding(.top, 8)
                                    }
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 40)
                            } else {
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("Drugs for \(disease.name)")
                                        .font(.title2)
                                        .fontWeight(.bold)
                                    
                                    LazyVGrid(columns: [
                                        GridItem(.adaptive(minimum: 250), spacing: 16)
                                    ], spacing: 16) {
                                        ForEach(diseaseDrugs) { drug in
                                            NavigationLink(value: drug) {
                                                DrugCard(drug: drug)
                                                    .contentShape(Rectangle())
                                            }
                                            .buttonStyle(.plain)
                                        }
                                    }
                                }
                            }
                            
                            Divider()
                        }
                        
                        // Molecules section - only show if drugs exist (molecules are active ingredients of drugs)
                        if !diseaseDrugs.isEmpty {
                            if isLoadingMolecules {
                                ProgressView("Loading molecules...")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 40)
                            } else if diseaseMolecules.isEmpty {
                                VStack(spacing: 16) {
                                    Image(systemName: "molecule")
                                        .font(.system(size: 60))
                                        .foregroundColor(.secondary)
                                    Text("No molecules found for this disease")
                                        .font(.headline)
                                        .foregroundColor(.secondary)
                                    Text("Try loading disease data or check if molecules are matched in the database")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .multilineTextAlignment(.center)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 40)
                            } else {
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("Active Ingredient Molecules")
                                        .font(.title2)
                                        .fontWeight(.bold)
                                    
                                    LazyVGrid(columns: [
                                        GridItem(.adaptive(minimum: 200), spacing: 16)
                                    ], spacing: 16) {
                                        ForEach(diseaseMolecules) { molecule in
                                            NavigationLink(value: Molecule(
                                                id: molecule.id,
                                                chemblId: molecule.chemblId,
                                                name: molecule.name,
                                                smiles: molecule.smiles,
                                                similarity: 1.0,
                                                similarityScore: 0.0,
                                                molecularWeight: molecule.molecularWeight,
                                                isApproved: molecule.isApproved,
                                                formula: molecule.formula
                                            )) {
                                                MoleculeCard(molecule: molecule)
                                                    .contentShape(Rectangle())
                                            }
                                            .buttonStyle(.plain)
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Similar molecules section
                        if showSimilarMolecules {
                            Divider()
                            
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Similar Molecules")
                                    .font(.title2)
                                    .fontWeight(.bold)
                                
                                if isLoadingSimilar {
                                    ProgressView("Finding similar molecules...")
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 40)
                                } else if similarMolecules.isEmpty {
                                    Text("No similar molecules found")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .padding()
                                } else {
                                    ScrollView(.horizontal, showsIndicators: false) {
                                        HStack(spacing: 16) {
                                            ForEach(similarMolecules) { molecule in
                                                NavigationLink(value: molecule) {
                                                    MoleculeCardWithSimilarity(molecule: molecule)
                                                        .contentShape(Rectangle())
                                                }
                                                .buttonStyle(.plain)
                                            }
                                        }
                                        .padding(.horizontal, 4)
                                    }
                                }
                            }
                        }
                    }
                    .padding()
                }
            } else {
                VStack(spacing: 20) {
                    Image(systemName: "cross.case")
                        .font(.system(size: 60))
                        .foregroundColor(.secondary)
                    Text("Select a disease to continue")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    Text("Choose a disease from the sidebar to see molecules and drugs used to treat it")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            }
            .navigationTitle("Disease Browser")
            .navigationDestination(for: Molecule.self) { molecule in
                MoleculeDetailView(molecule: molecule)
                    .onAppear {
                        print("🟢 NavigationDestination reached for molecule: \(molecule.name.isEmpty ? molecule.chemblId : molecule.name)")
                    }
            }
            .navigationDestination(for: Drug.self) { drug in
                DrugDetailView(drug: drug)
                    .onAppear {
                        print("🟢 NavigationDestination reached for drug: \(drug.name)")
                    }
            }
            .onAppear {
                backendService.checkBackendHealth()
                // Push "Diseases" breadcrumb when view appears
                print("🟡 DiseaseBrowseView onAppear - pushing 'Diseases' breadcrumb")
                navCoordinator.push(BreadcrumbItem(
                    title: "Diseases",
                    icon: "cross.case",
                    type: .diseases
                ))
                if diseases.isEmpty {
                    loadDiseases()
                }
            }
        }
    }
    
    private func loadDiseases() {
        guard backendService.isBackendRunning else { return }
        
        isLoadingDiseases = true
        errorMessage = nil
        
        Task {
            do {
                let loadedDiseases = try await backendService.getAllDiseases()
                await MainActor.run {
                    diseases = loadedDiseases
                    isLoadingDiseases = false
                    
                    // Don't auto-select - let user choose a disease
                    // This ensures a clean "select a disease" state when first opening the view
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingDiseases = false
                }
            }
        }
    }
    
    private func loadDiseaseDrugs() {
        guard let disease = selectedDisease, backendService.isBackendRunning else { return }
        
        isLoadingDrugs = true
        errorMessage = nil
        diseaseDrugs = []
        
        Task {
            do {
                let (drugs, _) = try await backendService.getDiseaseDrugs(
                    diseaseName: disease.name,
                    limit: 50
                )
                await MainActor.run {
                    diseaseDrugs = drugs
                    isLoadingDrugs = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingDrugs = false
                }
            }
        }
    }
    
    private func loadDiseaseMolecules() {
        guard let disease = selectedDisease, backendService.isBackendRunning else { return }
        
        isLoadingMolecules = true
        errorMessage = nil
        diseaseMolecules = []
        
        Task {
            do {
                let molecules = try await backendService.getDiseaseTopMolecules(
                    diseaseName: disease.name,
                    topK: 50
                )
                await MainActor.run {
                    diseaseMolecules = molecules
                    isLoadingMolecules = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingMolecules = false
                }
            }
        }
    }
    
    private func loadSimilarMolecules() {
        guard let disease = selectedDisease, backendService.isBackendRunning else { return }
        
        isLoadingSimilar = true
        errorMessage = nil
        similarMolecules = []
        
        Task {
            do {
                let similar = try await backendService.searchByDisease(
                    diseaseName: disease.name,
                    topK: 20
                )
                await MainActor.run {
                    similarMolecules = similar
                    isLoadingSimilar = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoadingSimilar = false
                }
            }
        }
    }
    
    private func downloadDrugsForDisease() {
        guard let disease = selectedDisease, backendService.isBackendRunning else { return }
        
        isDownloadingDrugs = true
        downloadProgress = "Starting download..."
        errorMessage = nil
        
        Task {
            do {
                // Download drugs for this disease (default: 50 drugs)
                let response = try await backendService.downloadDrugs(
                    names: nil,
                    disease: disease.name,
                    count: 50,
                    bulk: false
                )
                
                await MainActor.run {
                    if let taskId = response.taskId {
                        downloadProgress = "Download started (task ID: \(taskId))"
                        
                        // Poll for completion
                        pollDownloadStatus(taskId: taskId)
                    } else {
                        errorMessage = "No task ID returned from download"
                        isDownloadingDrugs = false
                        downloadProgress = nil
                    }
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isDownloadingDrugs = false
                    downloadProgress = nil
                }
            }
        }
    }
    
    private func pollDownloadStatus(taskId: String) {
        Task {
            var attempts = 0
            let maxAttempts = 300 // 5 minutes max (1 second intervals)
            
            while attempts < maxAttempts {
                do {
                    let status = try await backendService.getDownloadStatus(taskId: taskId)
                    
                    await MainActor.run {
                        if let running = status.running {
                            if !running {
                                // Download completed
                                isDownloadingDrugs = false
                                
                                if let exitCode = status.exitCode, exitCode == 0 {
                                    // Success
                                    downloadProgress = status.progress?.message ?? "Download complete! Refreshing..."
                                    
                                    // Reload drugs after a short delay
                                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                                        loadDiseaseDrugs()
                                    }
                                } else {
                                    // Failed
                                    downloadProgress = nil
                                    errorMessage = status.error ?? status.progress?.message ?? "Download failed"
                                }
                            } else {
                                // Still running - show detailed progress
                                if let progress = status.progress {
                                    var progressText = progress.message ?? "Downloading..."
                                    
                                    // Add details if available
                                    if let details = progress.details {
                                        // Disease progress
                                        if let diseaseIndex = details.diseaseIndex,
                                           let totalDiseases = details.totalDiseases {
                                            progressText += " (\(diseaseIndex)/\(totalDiseases) diseases)"
                                        }
                                        
                                        // Drug loading progress
                                        if let drugsLoaded = details.drugsLoaded,
                                           let totalDrugs = details.totalDrugs {
                                            progressText += " - \(drugsLoaded)/\(totalDrugs) drugs"
                                        }
                                        
                                        // Overall progress percentage
                                        if let progressPct = details.progressPercent {
                                            progressText += String(format: " (%.0f%%)", progressPct)
                                        }
                                        
                                        // Stage indicator
                                        if let stage = details.stage {
                                            let stageEmoji: String
                                            switch stage {
                                            case "api_search": stageEmoji = "🔍"
                                            case "loading_drug_details": stageEmoji = "📦"
                                            default: stageEmoji = "⏳"
                                            }
                                            progressText = "\(stageEmoji) \(progressText)"
                                        }
                                        
                                        // Current disease name
                                        if let currentDisease = details.currentDisease {
                                            progressText = "\(progressText) - \(currentDisease)"
                                        }
                                    }
                                    
                                    downloadProgress = progressText
                                } else {
                                    downloadProgress = status.message ?? "Downloading drugs..."
                                }
                            }
                        } else {
                            // Status unknown, use message
                            downloadProgress = status.message ?? "Checking download status..."
                        }
                    }
                    
                    // Break if download is complete (not running)
                    if let running = status.running, !running {
                        break
                    }
                    
                    // Wait 1 second before next poll
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                    attempts += 1
                } catch {
                    await MainActor.run {
                        errorMessage = error.localizedDescription
                        isDownloadingDrugs = false
                        downloadProgress = nil
                    }
                    break
                }
            }
            
            // Timeout
            if attempts >= maxAttempts {
                await MainActor.run {
                    downloadProgress = nil
                    isDownloadingDrugs = false
                    errorMessage = "Download timed out. It may still be running in the background."
                }
            }
        }
    }
}

struct DiseaseRow: View {
    let disease: Disease
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(disease.name)
                        .font(.headline)
                        .foregroundColor(isSelected ? .white : .primary)
                    
                    if let meshId = disease.meshId {
                        Text(meshId)
                            .font(.caption)
                            .foregroundColor(isSelected ? .white.opacity(0.8) : .secondary)
                            .fontDesign(.monospaced)
                    }
                }
                
                Spacer()
                
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.white)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? Color.accentColor : Color.clear)
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    DiseaseBrowseView()
}

