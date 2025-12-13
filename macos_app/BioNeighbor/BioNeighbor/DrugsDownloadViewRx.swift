//
//  DrugsDownloadViewRx.swift
//  BioNeighbor
//
//  RxSwift-based drugs download view
//

import SwiftUI
import RxSwift
import Combine


class DrugsDownloadViewModel: ObservableObject {
    @Published var stats: DatabaseStats?
    @Published var searchText = ""
    @Published var searchResults: [SearchResult] = []
    @Published var selectedNames: Set<String> = []
    @Published var batchNames = ""
    @Published var selectedDisease = ""
    @Published var diseaseSearchText = ""
    @Published var diseaseSearchResults: [SearchResult] = []
    @Published var maxDrugsPerDisease = 10
    @Published var bulkDownloadCount: Int? = nil
    @Published var useBulkDownload = false
    @Published var currentDownloadState: DownloadState = .idle
    @Published var errorMessage: String?
    
    private let downloadService = ReactiveDownloadService.shared
    private let backendService = BackendService.shared
    private let disposeBag = DisposeBag()
    private var cancellables = Set<AnyCancellable>()
    
    var isDownloading: Bool {
        if case .inProgress = currentDownloadState {
            return true
        }
        if case .starting = currentDownloadState {
            return true
        }
        return false
    }
    
    init() {
        setupRxBindings()
    }
    
    private func setupRxBindings() {
        // Load stats
        downloadService.refreshStats()
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { [weak self] stats in
                    self?.stats = stats
                },
                onError: { _ in }
            )
            .disposed(by: disposeBag)
        
        // Subscribe to download progress
        downloadService.downloadProgress
            .observe(on: MainScheduler.instance)
            .subscribe(onNext: { [weak self] progress in
                self?.currentDownloadState = progress.state
            })
            .disposed(by: disposeBag)
        
        // Search drugs with debouncing
        let searchTextSubject = PublishSubject<String>()
        $searchText
            .sink { value in
                searchTextSubject.onNext(value)
            }
            .store(in: &cancellables)
        
        searchTextSubject
            .debounce(.milliseconds(300), scheduler: MainScheduler.instance)
            .distinctUntilChanged()
            .filter { $0.count >= 2 }
            .flatMapLatest { [weak self] query -> Observable<[SearchResult]> in
                guard let self = self else { return Observable.just([]) }
                return self.downloadService.searchDrugs(query: query)
            }
            .observe(on: MainScheduler.instance)
            .subscribe(onNext: { [weak self] results in
                self?.searchResults = results
            })
            .disposed(by: disposeBag)
        
        // Search diseases with debouncing
        let diseaseSearchSubject = PublishSubject<String>()
        $diseaseSearchText
            .sink { value in
                diseaseSearchSubject.onNext(value)
            }
            .store(in: &cancellables)
        
        diseaseSearchSubject
            .debounce(.milliseconds(300), scheduler: MainScheduler.instance)
            .distinctUntilChanged()
            .filter { $0.count >= 2 }
            .flatMapLatest { [weak self] query -> Observable<[SearchResult]> in
                guard let self = self else { return Observable.just([]) }
                return self.downloadService.searchDiseases(query: query)
            }
            .observe(on: MainScheduler.instance)
            .subscribe(onNext: { [weak self] results in
                self?.diseaseSearchResults = results
            })
            .disposed(by: disposeBag)
    }
    
    func downloadByName() {
        guard backendService.isBackendRunning else { return }
        
        var names: [String] = []
        names.append(contentsOf: selectedNames)
        
        if !batchNames.isEmpty {
            let batch = batchNames.components(separatedBy: CharacterSet(charactersIn: ",\n"))
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
            names.append(contentsOf: batch)
        }
        
        if names.isEmpty {
            errorMessage = "No names selected"
            return
        }
        
        downloadService.downloadDrugs(names: names)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { _ in },
                onError: { [weak self] error in
                    self?.errorMessage = error.localizedDescription
                    self?.currentDownloadState = .failed(error: error.localizedDescription)
                }
            )
            .disposed(by: disposeBag)
        
        selectedNames.removeAll()
        batchNames = ""
    }
    
    func downloadByDisease() {
        guard backendService.isBackendRunning, !selectedDisease.isEmpty else { return }
        
        downloadService.downloadDrugs(disease: selectedDisease, count: maxDrugsPerDisease)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { _ in },
                onError: { [weak self] error in
                    self?.errorMessage = error.localizedDescription
                    self?.currentDownloadState = .failed(error: error.localizedDescription)
                }
            )
            .disposed(by: disposeBag)
    }
    
    func downloadBulk() {
        guard backendService.isBackendRunning else { return }
        
        downloadService.downloadDrugsBulk(maxDrugs: bulkDownloadCount)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { _ in },
                onError: { [weak self] error in
                    self?.errorMessage = error.localizedDescription
                    self?.currentDownloadState = .failed(error: error.localizedDescription)
                }
            )
            .disposed(by: disposeBag)
    }
}

struct DrugsDownloadViewRx: View {
    @StateObject private var viewModel = DrugsDownloadViewModel()
    @StateObject private var backendService = BackendService.shared
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Download Drugs")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .accessibilityIdentifier("downloadDrugsTitle")
                
                if let stats = viewModel.stats {
                    HStack {
                        Text("Current drugs in database:")
                            .font(.headline)
                        Text("\(stats.drugs)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(.green)
                    }
                    .padding()
                    .background(Color.green.opacity(0.1))
                    .cornerRadius(8)
                }
                
                Divider()
                
                // Bulk download section
                VStack(alignment: .leading, spacing: 16) {
                    Text("Bulk Download")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Download common drugs from PubChem")
                            .font(.headline)
                        
                        VStack(alignment: .leading, spacing: 8) {
                            Text("• Downloads ~50+ common prescription drugs")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("• Includes pain relievers, antibiotics, cardiovascular, diabetes, mental health drugs")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("• Automatically matches to existing molecules")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(Color.blue.opacity(0.1))
                        .cornerRadius(8)
                        
                        HStack {
                            Text("Max drugs (optional):")
                            TextField("No limit", value: $viewModel.bulkDownloadCount, format: .number)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 100)
                        }
                        
                        Button(action: { viewModel.downloadBulk() }) {
                            HStack {
                                if case .inProgress = viewModel.currentDownloadState {
                                    ProgressView()
                                        .progressViewStyle(.circular)
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "arrow.down.circle.fill")
                                }
                                Text("Download Common Drugs")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.isDownloading || !backendService.isBackendRunning)
                        .accessibilityIdentifier("downloadDrugsBulkButton")
                    }
                }
                
                Divider()
                
                // Download by name section
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Name")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Search drugs:")
                            .font(.headline)
                        
                        TextField("Enter drug name...", text: $viewModel.searchText)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("drugSearchField")
                        
                        if !viewModel.searchResults.isEmpty {
                            List(viewModel.searchResults) { result in
                                HStack {
                                    Text(result.name)
                                    Spacer()
                                    if viewModel.selectedNames.contains(result.name) {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundColor(.green)
                                    }
                                }
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    if viewModel.selectedNames.contains(result.name) {
                                        viewModel.selectedNames.remove(result.name)
                                    } else {
                                        viewModel.selectedNames.insert(result.name)
                                    }
                                }
                            }
                            .frame(height: 200)
                        }
                    }
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Or enter names (one per line or comma-separated):")
                            .font(.headline)
                        
                        TextEditor(text: $viewModel.batchNames)
                            .frame(height: 100)
                            .border(Color.gray.opacity(0.3))
                    }
                    
                    if !viewModel.selectedNames.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Selected (\(viewModel.selectedNames.count)):")
                                .font(.headline)
                            
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack {
                                    ForEach(Array(viewModel.selectedNames), id: \.self) { name in
                                        HStack {
                                            Text(name)
                                            Button(action: {
                                                viewModel.selectedNames.remove(name)
                                            }) {
                                                Image(systemName: "xmark.circle.fill")
                                                    .foregroundColor(.red)
                                            }
                                            .buttonStyle(.plain)
                                        }
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.green.opacity(0.1))
                                        .cornerRadius(8)
                                    }
                                }
                            }
                        }
                    }
                    
                    Button(action: { viewModel.downloadByName() }) {
                        HStack {
                            if viewModel.isDownloading {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.down.circle.fill")
                            }
                            Text("Download Selected Drugs")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isDownloading || !backendService.isBackendRunning || (viewModel.selectedNames.isEmpty && viewModel.batchNames.isEmpty))
                    .accessibilityIdentifier("downloadDrugsByNameButton")
                }
                
                Divider()
                
                // Download by disease section
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Disease")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Search disease:")
                            .font(.headline)
                        
                        TextField("Enter disease name...", text: $viewModel.diseaseSearchText)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("diseaseSearchField")
                        
                        if !viewModel.diseaseSearchResults.isEmpty {
                            List(viewModel.diseaseSearchResults) { result in
                                Text(result.name)
                                    .contentShape(Rectangle())
                                    .onTapGesture {
                                        viewModel.selectedDisease = result.name
                                        viewModel.diseaseSearchText = result.name
                                        viewModel.diseaseSearchResults = []
                                    }
                            }
                            .frame(height: 150)
                        }
                    }
                    
                    if !viewModel.selectedDisease.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Selected disease: \(viewModel.selectedDisease)")
                                .font(.headline)
                            
                            Text("Max drugs per disease: \(viewModel.maxDrugsPerDisease)")
                                .font(.subheadline)
                            
                            Slider(value: Binding(
                                get: { Double(viewModel.maxDrugsPerDisease) },
                                set: { viewModel.maxDrugsPerDisease = Int($0) }
                            ), in: 5...50, step: 5)
                        }
                        
                        Button(action: { viewModel.downloadByDisease() }) {
                            HStack {
                                if viewModel.isDownloading {
                                    ProgressView()
                                        .progressViewStyle(.circular)
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "arrow.down.circle.fill")
                                }
                                Text("Download Drugs for \(viewModel.selectedDisease)")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.isDownloading || !backendService.isBackendRunning)
                        .accessibilityIdentifier("downloadDrugsByDiseaseButton")
                    }
                }
                
                // Status messages
                if case .inProgress(let message) = viewModel.currentDownloadState {
                    Text(message)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding()
                        .background(Color.green.opacity(0.1))
                        .cornerRadius(8)
                }
                
                if case .completed(let message) = viewModel.currentDownloadState {
                    Text(message)
                        .font(.caption)
                        .foregroundColor(.green)
                        .padding()
                        .background(Color.green.opacity(0.1))
                        .cornerRadius(8)
                }
                
                if case .failed(let error) = viewModel.currentDownloadState {
                    Text("Error: \(error)")
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
                
                if let error = viewModel.errorMessage {
                    Text("Error: \(error)")
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
            }
            .padding()
        }
    }
}

#Preview {
    DrugsDownloadViewRx()
}

