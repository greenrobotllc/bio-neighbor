//
//  WorkspaceStateManager.swift
//  BioNeighbor
//
//  Workspace state management and persistence
//

import Foundation
import SwiftUI
import Combine

class WorkspaceStateManager: ObservableObject {
    static let shared = WorkspaceStateManager()
    
    @Published var currentWorkspaceId: Int?
    @Published var filters: [String: Any] = [:]
    @Published var selections: [String: Any] = [:]
    @Published var notes: String = ""
    
    private let baseURL = "http://127.0.0.1:5000/cancer-research/workspaces"
    
    func loadWorkspace(for mechanismId: Int) {
        // Try to find existing workspace for this mechanism
        guard let url = URL(string: baseURL) else { return }
        
        URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            guard let data = data else { return }
            
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                guard let response = try? JSONDecoder().decode(WorkspacesResponse.self, from: data),
                      response.success,
                      let workspaces = response.workspaces else {
                    // Create new workspace if none found
                    await self.createWorkspace(for: mechanismId)
                    return
                }
                
                // Find workspace for this mechanism
                if let workspace = workspaces.first(where: { $0.mechanismId == mechanismId }) {
                    self.currentWorkspaceId = workspace.id
                    self.filters = workspace.filters?.mapValues { $0.value } ?? [:]
                    self.selections = workspace.selections?.mapValues { $0.value } ?? [:]
                    self.notes = workspace.notes ?? ""
                } else {
                    // Create new workspace
                    await self.createWorkspace(for: mechanismId)
                }
            }
        }.resume()
    }
    
    @MainActor
    func createWorkspace(for mechanismId: Int) async {
        do {
            let workspaceId = try await BackendService.shared.createWorkspace(
                mechanismId: mechanismId,
                filters: filters,
                selections: selections,
                notes: notes
            )
            currentWorkspaceId = workspaceId
        } catch {
            print("Error creating workspace: \(error)")
        }
    }
    
    func saveSection(_ section: String, for mechanismId: Int) {
        guard let workspaceId = currentWorkspaceId else {
            loadWorkspace(for: mechanismId)
            return
        }
        
        selections["current_section"] = section
        Task {
            await saveWorkspace(workspaceId: workspaceId)
        }
    }
    
    @MainActor
    func saveWorkspace(workspaceId: Int) async {
        do {
            try await BackendService.shared.updateWorkspace(
                id: workspaceId,
                filters: filters,
                selections: selections,
                notes: notes
            )
        } catch {
            print("Error saving workspace: \(error)")
        }
    }
}
