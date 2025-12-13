//
//  MoleculesDownloadViewRx.swift
//  BioNeighbor
//
//  RxSwift-based molecules download view
//

import SwiftUI
import RxSwift
import RxCocoa
import Combine

class MoleculesDownloadViewModel: ObservableObject {
    @Published var stats: DatabaseStats?
    @Published var downloadCount = 1000
    @Published var selectedSource = "pubchem"
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
    
    var buttonText: String {
        switch currentDownloadState {
        case .starting:
            return "Starting..."
        case .inProgress(let message):
            return message
        case .completed:
            return "Download Completed"
        case .failed:
            return "Download Failed"
        case .idle:
            return "Download Molecules"
        }
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
                onError: { error in
                    // Silently fail
                }
            )
            .disposed(by: disposeBag)
        
        // Subscribe to download progress
        downloadService.downloadProgress
            .observe(on: MainScheduler.instance)
            .subscribe(onNext: { [weak self] progress in
                self?.currentDownloadState = progress.state
            })
            .disposed(by: disposeBag)
        
        // Search molecules with debouncing using a Subject
        let searchTextSubject = PublishSubject<String>()
        
        // Bridge @Published to RxSwift Subject
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
                return self.downloadService.searchMolecules(query: query)
            }
            .observe(on: MainScheduler.instance)
            .subscribe(onNext: { [weak self] results in
                self?.searchResults = results
            })
            .disposed(by: disposeBag)
    }
    
    func downloadByCount() {
        guard backendService.isBackendRunning else { return }
        
        downloadService.downloadMolecules(count: downloadCount, source: selectedSource)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { taskId in
                    // Task started, status polling will update UI
                },
                onError: { [weak self] error in
                    self?.errorMessage = error.localizedDescription
                    self?.currentDownloadState = .failed(error: error.localizedDescription)
                }
            )
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
        
        downloadService.downloadMolecules(names: names)
            .observe(on: MainScheduler.instance)
            .subscribe(
                onNext: { taskId in
                    // Task started
                },
                onError: { [weak self] error in
                    self?.errorMessage = error.localizedDescription
                    self?.currentDownloadState = .failed(error: error.localizedDescription)
                }
            )
            .disposed(by: disposeBag)
        
        selectedNames.removeAll()
        batchNames = ""
    }
}

struct MoleculesDownloadViewRx: View {
    @StateObject private var viewModel = MoleculesDownloadViewModel()
    @StateObject private var backendService = BackendService.shared
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                Text("Download Molecules")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                
                // Current count
                if let stats = viewModel.stats {
                    HStack {
                        Text("Current molecules in database:")
                            .font(.headline)
                        Text("\(stats.molecules)")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(.blue)
                    }
                    .padding()
                    .background(Color.blue.opacity(0.1))
                    .cornerRadius(8)
                }
                
                Divider()
                
                // Download by count
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Count")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Download \(viewModel.downloadCount) more molecules")
                            .font(.headline)
                        
                        HStack {
                            Slider(value: Binding(
                                get: { Double(viewModel.downloadCount) },
                                set: { viewModel.downloadCount = Int($0) }
                            ), in: 100...10000, step: 100)
                            
                            TextField("Count", value: $viewModel.downloadCount, format: .number)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 100)
                        }
                    }
                    
                    Picker("Source", selection: $viewModel.selectedSource) {
                        Text("PubChem").tag("pubchem")
                        Text("ChEMBL").tag("chembl")
                        Text("ZINC").tag("zinc")
                    }
                    .pickerStyle(.segmented)
                    
                    Button(action: { viewModel.downloadByCount() }) {
                        HStack {
                            if case .inProgress = viewModel.currentDownloadState {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.down.circle.fill")
                            }
                            Text(viewModel.buttonText)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isDownloading || !backendService.isBackendRunning)
                }
                
                Divider()
                
                // Download by name
                VStack(alignment: .leading, spacing: 16) {
                    Text("Download by Name")
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    // Search field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Search molecules:")
                            .font(.headline)
                        
                        TextField("Enter molecule name...", text: $viewModel.searchText)
                            .textFieldStyle(.roundedBorder)
                    }
                    
                    // Search results
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
                    
                    // Batch input
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Or enter names (one per line or comma-separated):")
                            .font(.headline)
                        
                        TextEditor(text: $viewModel.batchNames)
                            .frame(height: 100)
                            .border(Color.gray.opacity(0.3))
                    }
                    
                    // Selected names
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
                                        .background(Color.blue.opacity(0.1))
                                        .cornerRadius(8)
                                    }
                                }
                            }
                        }
                    }
                    
                    Button(action: { viewModel.downloadByName() }) {
                        HStack {
                            if case .inProgress = viewModel.currentDownloadState {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.down.circle.fill")
                            }
                            Text(viewModel.buttonText)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isDownloading || !backendService.isBackendRunning || (viewModel.selectedNames.isEmpty && viewModel.batchNames.isEmpty))
                }
                
                // Progress/Error
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

#Preview {
    MoleculesDownloadViewRx()
}

