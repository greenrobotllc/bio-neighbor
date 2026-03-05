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
    @Published var filters: [String: AnyCodable] = [:]
    @Published var selections: [String: AnyCodable] = [:]
    @Published var notes: String = ""

    @MainActor
    func loadWorkspace(for mechanismId: Int) async {
        let workspaces: [Workspace]
        do {
            workspaces = try await BackendService.shared.listWorkspaces()
        } catch {
            print("Error loading workspaces: \(error)")
            await createWorkspace(for: mechanismId)
            return
        }

        if let workspace = workspaces.first(where: { $0.mechanismId == mechanismId }) {
            currentWorkspaceId = workspace.id
            filters = workspace.filters ?? [:]
            selections = workspace.selections ?? [:]
            notes = workspace.notes ?? ""
        } else {
            await createWorkspace(for: mechanismId)
        }
    }

    @MainActor
    func createWorkspace(for mechanismId: Int) async {
        do {
            let filtersDict = filters.mapValues { $0.value }
            let selectionsDict = selections.mapValues { $0.value }
            let workspaceId = try await BackendService.shared.createWorkspace(
                mechanismId: mechanismId,
                filters: filtersDict,
                selections: selectionsDict,
                notes: notes
            )
            currentWorkspaceId = workspaceId
        } catch {
            print("Error creating workspace: \(error)")
        }
    }

    func saveSection(_ section: String, for mechanismId: Int) {
        selections["current_section"] = AnyCodable(section)
        Task { @MainActor in
            if currentWorkspaceId == nil {
                await loadWorkspace(for: mechanismId)
            }
            if let workspaceId = currentWorkspaceId {
                await saveWorkspace(workspaceId: workspaceId)
            }
        }
    }

    @MainActor
    func saveWorkspace(workspaceId: Int) async {
        do {
            let filtersDict = filters.mapValues { $0.value }
            let selectionsDict = selections.mapValues { $0.value }
            try await BackendService.shared.updateWorkspace(
                id: workspaceId,
                filters: filtersDict,
                selections: selectionsDict,
                notes: notes
            )
        } catch {
            print("Error saving workspace: \(error)")
        }
    }
}
