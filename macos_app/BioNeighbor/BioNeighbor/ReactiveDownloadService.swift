//
//  ReactiveDownloadService.swift
//  BioNeighbor
//
//  RxSwift-based reactive download service
//

import Foundation
import RxSwift
import Combine

enum DownloadState {
    case idle
    case starting
    case inProgress(message: String)
    case completed(message: String)
    case failed(error: String)
}

struct DownloadProgress {
    let taskId: String
    let state: DownloadState
    let timestamp: Date
}

class ReactiveDownloadService {
    static let shared = ReactiveDownloadService()
    
    private let backendService = BackendService.shared
    private let disposeBag = DisposeBag()
    
    // Observable for download progress
    private let downloadProgressSubject = PublishSubject<DownloadProgress>()
    var downloadProgress: Observable<DownloadProgress> {
        return downloadProgressSubject.asObservable()
    }
    
    // Observable for database stats
    private let statsSubject = BehaviorSubject<DatabaseStats?>(value: nil)
    var stats: Observable<DatabaseStats?> {
        return statsSubject.asObservable()
    }
    
    private init() {
        // Auto-refresh stats periodically
        Observable<Int>
            .interval(.seconds(30), scheduler: MainScheduler.instance)
            .flatMap { [weak self] _ -> Observable<DatabaseStats> in
                guard let self = self, self.backendService.isBackendRunning else {
                    return Observable.empty()
                }
                return self.fetchStats()
            }
            .subscribe(onNext: { [weak self] stats in
                self?.statsSubject.onNext(stats)
            })
            .disposed(by: disposeBag)
    }
    
    // MARK: - Stats
    
    func refreshStats() -> Observable<DatabaseStats> {
        return fetchStats()
            .do(onNext: { [weak self] stats in
                self?.statsSubject.onNext(stats)
            })
    }
    
    private func fetchStats() -> Observable<DatabaseStats> {
        return Observable.create { [weak self] observer in
            guard let self = self, self.backendService.isBackendRunning else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            Task {
                do {
                    let stats = try await self.backendService.getDatabaseStats()
                    observer.onNext(stats)
                    observer.onCompleted()
                } catch {
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    // MARK: - Molecule Downloads
    
    func downloadMolecules(count: Int? = nil, source: String = "pubchem", fullFile: Bool = false) -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    let response = try await self.backendService.downloadMolecules(
                        count: count,
                        source: source,
                        fullFile: fullFile
                    )
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        
                        // Start polling status
                        self.pollDownloadStatus(taskId: taskId, type: "molecules")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    func downloadMolecules(names: [String]) -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    let response = try await self.backendService.downloadMolecules(names: names)
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        self.pollDownloadStatus(taskId: taskId, type: "molecules")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    // MARK: - Drug Downloads
    
    func downloadDrugs(names: [String]) -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    let response = try await self.backendService.downloadDrugs(names: names)
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        self.pollDownloadStatus(taskId: taskId, type: "drugs")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    func downloadDrugsBulk(maxDrugs: Int? = nil) -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    let response = try await self.backendService.downloadDrugs(count: maxDrugs, bulk: true)
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        self.pollDownloadStatus(taskId: taskId, type: "drugs")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    func downloadDrugs(disease: String, count: Int) -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    let response = try await self.backendService.downloadDrugs(
                        disease: disease,
                        count: count
                    )
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        self.pollDownloadStatus(taskId: taskId, type: "drugs")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    // MARK: - Disease Downloads
    
    func downloadDiseases(names: [String]) -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    let response = try await self.backendService.downloadDiseases(names: names)
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        self.pollDownloadStatus(taskId: taskId, type: "diseases")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    func downloadAllDiseases() -> Observable<String> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            let progress = DownloadProgress(
                taskId: UUID().uuidString,
                state: .starting,
                timestamp: Date()
            )
            self.downloadProgressSubject.onNext(progress)
            
            Task {
                do {
                    // Download all diseases (no count = all from NLM dataset)
                    let response = try await self.backendService.downloadDiseases(count: nil)
                    
                    if let taskId = response.taskId {
                        observer.onNext(taskId)
                        observer.onCompleted()
                        self.pollDownloadStatus(taskId: taskId, type: "diseases")
                    } else {
                        let completed = DownloadProgress(
                            taskId: progress.taskId,
                            state: .completed(message: response.message ?? "Download started"),
                            timestamp: Date()
                        )
                        self.downloadProgressSubject.onNext(completed)
                        observer.onNext(progress.taskId)
                        observer.onCompleted()
                    }
                } catch {
                    let failed = DownloadProgress(
                        taskId: progress.taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(failed)
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
    
    // MARK: - Search
    
    func searchMolecules(query: String, limit: Int = 20) -> Observable<[SearchResult]> {
        return Observable.create { [weak self] observer in
            guard let self = self, self.backendService.isBackendRunning else {
                observer.onNext([])
                observer.onCompleted()
                return Disposables.create()
            }
            
            Task {
                do {
                    let results = try await self.backendService.searchMolecules(
                        query: query,
                        limit: limit
                    )
                    observer.onNext(results)
                    observer.onCompleted()
                } catch {
                    observer.onNext([])
                    observer.onCompleted()
                }
            }
            
            return Disposables.create()
        }
        .debounce(.milliseconds(300), scheduler: MainScheduler.instance)
        .distinctUntilChanged { $0 == $1 }
    }
    
    func searchDrugs(query: String, limit: Int = 20) -> Observable<[SearchResult]> {
        return Observable.create { [weak self] observer in
            guard let self = self, self.backendService.isBackendRunning else {
                observer.onNext([])
                observer.onCompleted()
                return Disposables.create()
            }
            
            Task {
                do {
                    let results = try await self.backendService.searchDrugs(
                        query: query,
                        limit: limit
                    )
                    observer.onNext(results)
                    observer.onCompleted()
                } catch {
                    observer.onNext([])
                    observer.onCompleted()
                }
            }
            
            return Disposables.create()
        }
        .debounce(.milliseconds(300), scheduler: MainScheduler.instance)
        .distinctUntilChanged { $0 == $1 }
    }
    
    func searchDiseases(query: String, limit: Int = 20) -> Observable<[SearchResult]> {
        return Observable.create { [weak self] observer in
            guard let self = self, self.backendService.isBackendRunning else {
                observer.onNext([])
                observer.onCompleted()
                return Disposables.create()
            }
            
            Task {
                do {
                    let results = try await self.backendService.searchDiseases(
                        query: query,
                        limit: limit
                    )
                    observer.onNext(results)
                    observer.onCompleted()
                } catch {
                    observer.onNext([])
                    observer.onCompleted()
                }
            }
            
            return Disposables.create()
        }
        .debounce(.milliseconds(300), scheduler: MainScheduler.instance)
        .distinctUntilChanged { $0 == $1 }
    }
    
    // MARK: - Status Polling
    
    private func pollDownloadStatus(taskId: String, type: String) {
        Observable<Int>
            .interval(.seconds(2), scheduler: MainScheduler.instance)
            .flatMap { [weak self] _ -> Observable<DownloadStatusResponse> in
                guard let self = self else {
                    return Observable.empty()
                }
                return self.checkStatus(taskId: taskId)
            }
            .take(until: { response in
                // Stop polling when download completes or fails
                guard let running = response.running else { return true }
                return !running
            })
            .subscribe(
                onNext: { [weak self] status in
                    guard let self = self else { return }
                    
                    let state: DownloadState
                    if let running = status.running {
                        if running {
                            state = .inProgress(message: status.message ?? "Download in progress...")
                        } else {
                            if let exitCode = status.exitCode, exitCode == 0 {
                                state = .completed(message: status.message ?? "Download completed")
                                // Refresh stats after completion
                                self.refreshStats().subscribe().disposed(by: self.disposeBag)
                            } else {
                                state = .failed(error: status.message ?? "Download failed")
                            }
                        }
                    } else {
                        state = .inProgress(message: status.message ?? "Download in progress...")
                    }
                    
                    let progress = DownloadProgress(
                        taskId: taskId,
                        state: state,
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(progress)
                },
                onError: { [weak self] error in
                    guard let self = self else { return }
                    let progress = DownloadProgress(
                        taskId: taskId,
                        state: .failed(error: error.localizedDescription),
                        timestamp: Date()
                    )
                    self.downloadProgressSubject.onNext(progress)
                }
            )
            .disposed(by: disposeBag)
    }
    
    private func checkStatus(taskId: String) -> Observable<DownloadStatusResponse> {
        return Observable.create { [weak self] observer in
            guard let self = self else {
                observer.onError(BackendError.backendNotAvailable)
                return Disposables.create()
            }
            
            Task {
                do {
                    let status = try await self.backendService.getDownloadStatus(taskId: taskId)
                    observer.onNext(status)
                    observer.onCompleted()
                } catch {
                    observer.onError(error)
                }
            }
            
            return Disposables.create()
        }
    }
}

