//
//  DiseasesDownloadViewRx.swift
//  BioNeighbor
//
//  RxSwift-based diseases download view
//

import SwiftUI
import RxSwift
import Combine


class DiseasesDownloadViewModel: ObservableObject {
    @Published var stats: DatabaseStats?
    @Published var searchText = ""
    @Published var searchResults: [SearchResult] = []
    @Published var selectedNames: Set<String> = []
    @Published var batchNames = ""
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
        
        // Search diseases with debouncing
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
                return self.downloadService.searchDiseases(query: query)
            }
            .observe(on: MainScheduler.instance)
            .subscribe(onNext: { [weak self] results in
                self?.searchResults = results
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
        
        downloadService.downloadDiseases(names: names)
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
    
    func downloadAllDiseases() {
        guard backendService.isBackendRunning else { return }
        
        downloadService.downloadAllDiseases()
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

struct DiseasesDownloadViewRx: View {
    @StateObject private var viewModel = DiseasesDownloadViewModel()
    @StateObject private var backendService = BackendService.shared
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Download Diseases")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .accessibilityIdentifier("downloadDiseasesTitle")
                
                if let stats = viewModel.stats {
                    HStack {
                        Text("Current diseases in database:")
                            .font(.headline)
                        Text("\(stats.diseases)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(.orange)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                }
                
                Divider()
                
                // Download by name
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Name")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Search diseases:")
                            .font(.headline)
                        
                        TextField("Enter disease name...", text: $viewModel.searchText)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("diseaseNameSearchField")
                        
                        if !viewModel.searchResults.isEmpty {
                            List(viewModel.searchResults) { result in
                                HStack {
                                    Text(result.name)
                                    Spacer()
                                    if viewModel.selectedNames.contains(result.name) {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundColor(.orange)
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
                                        .background(Color.orange.opacity(0.1))
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
                            Text("Download Selected Diseases")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isDownloading || !backendService.isBackendRunning || (viewModel.selectedNames.isEmpty && viewModel.batchNames.isEmpty))
                    .accessibilityIdentifier("downloadDiseasesByNameButton")
                }
                
                Divider()
                
                // Download all diseases from NLM
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download All Diseases")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Download complete NLM medical conditions dataset")
                            .font(.headline)
                        
                        VStack(alignment: .leading, spacing: 8) {
                            Text("• Downloads 2,400+ medical conditions from NLM")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("• Includes ICD-10-CM and ICD-9-CM codes")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("• Includes synonyms and consumer-friendly names")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("• Downloads from gzipped JSON file")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(Color.blue.opacity(0.1))
                        .cornerRadius(8)
                        
                        Button(action: { viewModel.downloadAllDiseases() }) {
                            HStack {
                                if viewModel.isDownloading {
                                    ProgressView()
                                        .progressViewStyle(.circular)
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "arrow.down.circle.fill")
                                }
                                Text("Download All Diseases (2,400+)")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.isDownloading || !backendService.isBackendRunning)
                        .accessibilityIdentifier("downloadAllDiseasesButton")
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
    DiseasesDownloadViewRx()
}

