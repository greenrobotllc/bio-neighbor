//
//  CancerResearchView.swift
//  BioNeighbor
//
//  Main Cancer Research tab view
//

import SwiftUI

struct CancerResearchView: View {
    @StateObject private var backendService = BackendService.shared
    @State private var mechanisms: [Mechanism] = []
    @State private var selectedMechanism: Mechanism?
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        NavigationSplitView {
            // Sidebar: Mechanism selector
            if isLoading {
                ProgressView("Loading mechanisms...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .navigationTitle("Cancer Research")
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text("Error loading mechanisms")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                    Button("Retry") {
                        loadMechanisms()
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
                .navigationTitle("Cancer Research")
            } else if mechanisms.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "flask")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text("No mechanisms found")
                        .font(.headline)
                    Text("Mechanisms will be initialized automatically when you refresh.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                    Button("Refresh") {
                        loadMechanisms()
                    }
                    .buttonStyle(.bordered)
                    .padding(.top, 8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
                .navigationTitle("Cancer Research")
            } else {
                VStack(spacing: 0) {
                    List {
                        ForEach(mechanisms, id: \.id) { mechanism in
                            Button(action: {
                                selectedMechanism = mechanism
                            }) {
                                HStack {
                                    Text(mechanism.name)
                                        .foregroundColor(selectedMechanism?.id == mechanism.id ? .white : .primary)
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .background(selectedMechanism?.id == mechanism.id ? Color.accentColor : Color.clear)
                                .cornerRadius(4)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .listStyle(.sidebar)
                    
                    Divider()
                    
                    HStack {
                        Button(action: {
                            initializeMechanisms()
                        }) {
                            Label("Initialize", systemImage: "plus.circle")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        
                        Button(action: {
                            loadMechanisms()
                        }) {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        
                        Spacer()
                        
                        Text("\(mechanisms.count) mechanism\(mechanisms.count == 1 ? "" : "s")")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 8)
                }
                .navigationTitle("Cancer Research")
                .frame(minWidth: 200)
            }
        } detail: {
            // Main workspace
            if let mechanism = selectedMechanism {
                MechanismWorkspaceView(mechanism: mechanism, onBackToSelector: {
                    selectedMechanism = nil
                })
            } else {
                VStack {
                    Image(systemName: "flask")
                        .font(.system(size: 64))
                        .foregroundColor(.secondary)
                    Text("Select a mechanism to begin")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    if !mechanisms.isEmpty {
                        Text("Click on a mechanism in the sidebar to explore it")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                    }
                    Text("Research Tool Only - Not for Medical Diagnosis or Treatment")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            loadMechanisms()
        }
    }
    
    private func loadMechanisms() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    errorMessage = "Network error: \(error.localizedDescription)\n\nMake sure the backend server is running."
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response from server"
                    return
                }
                
                guard httpResponse.statusCode == 200 else {
                    errorMessage = "Server error: HTTP \(httpResponse.statusCode)"
                    return
                }
                
                guard let data = data else {
                    errorMessage = "No data received from server"
                    return
                }
                
                do {
                    let response = try JSONDecoder().decode(MechanismsResponse.self, from: data)
                    
                    if !response.success {
                        errorMessage = response.error ?? "Failed to load mechanisms"
                        return
                    }
                    
                    guard let mechanisms = response.mechanisms else {
                        errorMessage = "No mechanisms in response"
                        return
                    }
                    
                    self.mechanisms = mechanisms
                    print("📊 Loaded \(mechanisms.count) mechanisms: \(mechanisms.map { $0.name }.joined(separator: ", "))")
                    
                    // Auto-select first mechanism if none selected
                    if selectedMechanism == nil && !mechanisms.isEmpty {
                        selectedMechanism = mechanisms[0]
                        print("✅ Auto-selected mechanism: \(mechanisms[0].name)")
                    }
                } catch {
                    // Try to decode error message
                    if let errorDict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let errorMsg = errorDict["error"] as? String {
                        errorMessage = errorMsg
                    } else {
                        errorMessage = "Failed to decode response: \(error.localizedDescription)"
                    }
                }
            }
        }.resume()
    }
    
    private func initializeMechanisms() {
        isLoading = true
        errorMessage = nil
        
        guard let url = URL(string: "http://127.0.0.1:5000/cancer-research/mechanisms/initialize") else {
            errorMessage = "Invalid URL"
            isLoading = false
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                isLoading = false
                
                if let error = error {
                    errorMessage = "Network error: \(error.localizedDescription)"
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response from server"
                    return
                }
                
                guard httpResponse.statusCode == 200 else {
                    errorMessage = "Server error: HTTP \(httpResponse.statusCode)"
                    return
                }
                
                // Reload mechanisms after initialization
                print("✅ Mechanisms initialized, reloading...")
                loadMechanisms()
            }
        }.resume()
    }
}
