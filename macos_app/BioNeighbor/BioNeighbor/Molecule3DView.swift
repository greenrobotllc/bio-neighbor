//
//  Molecule3DView.swift
//  BioNeighbor
//
//  3D interactive molecule viewer using WebView and 3Dmol.js
//

import SwiftUI
import WebKit

struct Molecule3DView: View {
    let coordinates: Molecule3DCoordinates
    @State private var representation: RepresentationType = .ballAndStick
    @State private var isLoading = true
    var highlightedAtoms: [Int]? = nil
    var highlightColor: String = "green"
    var highlightMode: HighlightMode = .none
    var differenceAtoms: [Int]? = nil
    var differenceColor: String = "red"
    
    enum RepresentationType: String, CaseIterable {
        case ballAndStick = "stick"
        case spaceFilling = "sphere"
        case wireframe = "line"
        case surface = "surface"
    }
    
    enum HighlightMode {
        case none
        case sharedScaffold
        case functionalGroup
        case differences
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Controls
            VStack(alignment: .leading, spacing: 6) {
                Text("Representation")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Picker("Representation", selection: $representation) {
                    Text("Ball & Stick").tag(RepresentationType.ballAndStick)
                    Text("Space Filling").tag(RepresentationType.spaceFilling)
                    Text("Wireframe").tag(RepresentationType.wireframe)
                    Text("Surface").tag(RepresentationType.surface)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }
            .padding(.horizontal)
            .padding(.top, 20)
            .padding(.bottom, 8)
            
            // WebView
            if isLoading {
                ProgressView("Loading 3D structure...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                WebViewRepresentable(
                    coordinates: coordinates,
                    representation: representation,
                    highlightedAtoms: highlightedAtoms,
                    highlightColor: highlightColor,
                    highlightMode: highlightMode,
                    differenceAtoms: differenceAtoms,
                    differenceColor: differenceColor
                )
                .frame(minHeight: 400)
            }
        }
        .onAppear {
            // Small delay to ensure WebView is ready
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                isLoading = false
            }
        }
    }
}

struct WebViewRepresentable: NSViewRepresentable {
    let coordinates: Molecule3DCoordinates
    let representation: Molecule3DView.RepresentationType
    let highlightedAtoms: [Int]?
    let highlightColor: String
    let highlightMode: Molecule3DView.HighlightMode
    let differenceAtoms: [Int]?
    let differenceColor: String
    
    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        
        // Load HTML with 3Dmol.js from local bundle
        let html = generateHTML(
            coordinates: coordinates,
            representation: representation,
            highlightedAtoms: highlightedAtoms,
            highlightColor: highlightColor,
            differenceAtoms: differenceAtoms,
            differenceColor: differenceColor
        )
        
        // Get the bundle URL for loading local resources
        if let bundleURL = Bundle.main.resourceURL {
            webView.loadHTMLString(html, baseURL: bundleURL)
        } else {
            webView.loadHTMLString(html, baseURL: nil)
        }
        
        return webView
    }
    
    func updateNSView(_ webView: WKWebView, context: Context) {
        // Update when representation or highlighting inputs change
        let needsUpdate = representation != context.coordinator.lastRepresentation ||
            highlightedAtoms != context.coordinator.lastHighlightedAtoms ||
            differenceAtoms != context.coordinator.lastDifferenceAtoms ||
            highlightColor != context.coordinator.lastHighlightColor ||
            differenceColor != context.coordinator.lastDifferenceColor
        
        if needsUpdate {
            updateRepresentation(
                webView: webView,
                representation: representation,
                highlightedAtoms: highlightedAtoms,
                highlightColor: highlightColor,
                differenceAtoms: differenceAtoms,
                differenceColor: differenceColor,
                highlightMode: highlightMode
            ) { didApply in
                if didApply {
                    context.coordinator.lastRepresentation = representation
                    context.coordinator.lastHighlightedAtoms = highlightedAtoms
                    context.coordinator.lastDifferenceAtoms = differenceAtoms
                    context.coordinator.lastHighlightColor = highlightColor
                    context.coordinator.lastDifferenceColor = differenceColor
                }
            }
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        var lastRepresentation: Molecule3DView.RepresentationType = .ballAndStick
        var lastHighlightedAtoms: [Int]?
        var lastDifferenceAtoms: [Int]?
        var lastHighlightColor: String = "green"
        var lastDifferenceColor: String = "red"
    }
    
    private func generateHTML(
        coordinates: Molecule3DCoordinates,
        representation: Molecule3DView.RepresentationType,
        highlightedAtoms: [Int]?,
        highlightColor: String,
        differenceAtoms: [Int]?,
        differenceColor: String
    ) -> String {
        // Convert coordinates to PDB format string
        let pdbString = generatePDBString(coordinates: coordinates)
        
        // Encode the PDB string as base64 for safe JS injection (avoids template literal injection)
        let pdbBase64 = Data(pdbString.utf8).base64EncodedString()
        
        // Determine initial style based on representation
        let highlightScript = generateHighlightScript(
            highlightedAtoms: highlightedAtoms,
            highlightColor: highlightColor,
            representation: representation,
            differenceAtoms: differenceAtoms,
            differenceColor: differenceColor,
            highlightMode: highlightMode
        )
        
        let initialScript: String
        switch representation {
        case .surface:
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.addSurface($3Dmol.SurfaceType.VDW, {opacity: 0.7, color: 'white'}, {});
                \(highlightScript)
                viewer.zoomTo();
                viewer.render();
            """
        case .ballAndStick:
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {stick: {radius: 0.1}, sphere: {scale: 0.3}});
                \(highlightScript)
                viewer.zoomTo();
                viewer.render();
            """
        case .spaceFilling:
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {sphere: {scale: 1.0}});
                \(highlightScript)
                viewer.zoomTo();
                viewer.render();
            """
        case .wireframe:
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {line: {}});
                \(highlightScript)
                viewer.zoomTo();
                viewer.render();
            """
        }
        
        // Load 3Dmol.js from local bundle (3Dmol-min.js is included in app resources)
        // This ensures offline functionality and eliminates CDN dependency
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <script src="3Dmol-min.js"></script>
            <style>
                body { margin: 0; padding: 0; overflow: hidden; }
                #container { width: 100%; height: 100vh; }
            </style>
        </head>
        <body>
            <div id="container"></div>
            <script>
                var element = document.getElementById('container');
                var viewer = $3Dmol.createViewer(element, {});
                
                var pdb = atob("\(pdbBase64)");
                
                \(initialScript)
                
                // Handle mouse interactions
                viewer.zoom(0.8);
            </script>
        </body>
        </html>
        """
    }
    
    private func generateHighlightScript(
        highlightedAtoms: [Int]?,
        highlightColor: String,
        representation: Molecule3DView.RepresentationType,
        differenceAtoms: [Int]?,
        differenceColor: String,
        highlightMode: Molecule3DView.HighlightMode
    ) -> String {
        let safeHighlightColor = sanitizeColor(highlightColor)
        let safeDifferenceColor = sanitizeColor(differenceColor)
        var scripts: [String] = []
        
        switch highlightMode {
        case .none:
            break
        case .sharedScaffold, .functionalGroup:
            if let atoms = highlightedAtoms, !atoms.isEmpty {
                let atomIndices = atoms.map { $0 + 1 }
                let atomList = atomIndices.map { String($0) }.joined(separator: ",")
                
                let sphereStyle: String
                switch representation {
                case .ballAndStick:
                    sphereStyle = "sphere: {color: '\(safeHighlightColor)', scale: 0.3}"
                case .spaceFilling:
                    sphereStyle = "sphere: {color: '\(safeHighlightColor)', scale: 1.0}"
                default:
                    sphereStyle = "sphere: {color: '\(safeHighlightColor)'}"
                }
                
                scripts.append("""
                    var highlightAtoms = [\(atomList)];
                    viewer.setStyle({serial: highlightAtoms}, {stick: {color: '\(safeHighlightColor)', radius: 0.1}, \(sphereStyle)});
                """)
            }
            if highlightMode == .sharedScaffold, let diffAtoms = differenceAtoms, !diffAtoms.isEmpty {
                let atomIndices = diffAtoms.map { $0 + 1 }
                let atomList = atomIndices.map { String($0) }.joined(separator: ",")
                
                let diffSphereStyle: String
                switch representation {
                case .ballAndStick:
                    diffSphereStyle = "sphere: {color: '\(safeDifferenceColor)', scale: 0.3}"
                case .spaceFilling:
                    diffSphereStyle = "sphere: {color: '\(safeDifferenceColor)', scale: 1.0}"
                default:
                    diffSphereStyle = "sphere: {color: '\(safeDifferenceColor)'}"
                }
                
                scripts.append("""
                    var differenceAtoms = [\(atomList)];
                    viewer.setStyle({serial: differenceAtoms}, {stick: {color: '\(safeDifferenceColor)', radius: 0.1}, \(diffSphereStyle)});
                """)
            }
        case .differences:
            if let diffAtoms = differenceAtoms, !diffAtoms.isEmpty {
                let atomIndices = diffAtoms.map { $0 + 1 }
                let atomList = atomIndices.map { String($0) }.joined(separator: ",")
                
                let diffSphereStyle: String
                switch representation {
                case .ballAndStick:
                    diffSphereStyle = "sphere: {color: '\(safeDifferenceColor)', scale: 0.3}"
                case .spaceFilling:
                    diffSphereStyle = "sphere: {color: '\(safeDifferenceColor)', scale: 1.0}"
                default:
                    diffSphereStyle = "sphere: {color: '\(safeDifferenceColor)'}"
                }
                
                scripts.append("""
                    var differenceAtoms = [\(atomList)];
                    viewer.setStyle({serial: differenceAtoms}, {stick: {color: '\(safeDifferenceColor)', radius: 0.1}, \(diffSphereStyle)});
                """)
            }
        }
        
        return scripts.joined(separator: "\n")
    }
    
    private func sanitizeColor(_ color: String) -> String {
        let filtered = color.filter { $0.isLetter || $0.isNumber || $0 == "#" }
        let trimmed = String(filtered.prefix(32))
        return trimmed.isEmpty ? "black" : trimmed
    }
    
    private func generatePDBString(coordinates: Molecule3DCoordinates) -> String {
        var pdb = "HEADER    MOLECULE\n"
        
        // Add atoms
        for atom in coordinates.atoms {
            let x = String(format: "%8.3f", atom.x)
            let y = String(format: "%8.3f", atom.y)
            let z = String(format: "%8.3f", atom.z)
            let index = atom.index + 1
            let symbol = atom.symbol.padding(toLength: 2, withPad: " ", startingAt: 0)
            
            pdb += String(format: "ATOM  %5d  %@  MOL A   1    %@ %@ %@  1.00  0.00           %@  \n",
                         index, symbol, x, y, z, atom.symbol)
        }
        
        // Add bonds as CONECT records
        for bond in coordinates.bonds {
            let atom1 = bond.atom1 + 1
            let atom2 = bond.atom2 + 1
            pdb += String(format: "CONECT%5d%5d\n", atom1, atom2)
        }
        
        pdb += "END\n"
        return pdb
    }
    
    private func updateRepresentation(
        webView: WKWebView,
        representation: Molecule3DView.RepresentationType,
        highlightedAtoms: [Int]?,
        highlightColor: String,
        differenceAtoms: [Int]?,
        differenceColor: String,
        highlightMode: Molecule3DView.HighlightMode,
        completion: @escaping (Bool) -> Void
    ) {
        let highlightScript = generateHighlightScript(
            highlightedAtoms: highlightedAtoms,
            highlightColor: highlightColor,
            representation: representation,
            differenceAtoms: differenceAtoms,
            differenceColor: differenceColor,
            highlightMode: highlightMode
        )
        
        let script: String
        switch representation {
        case .surface:
            // Surface representation requires addSurface API, not setStyle
            script = """
            (() => {
              if (typeof viewer === 'undefined') return false;
              viewer.removeAllSurfaces();
              viewer.addSurface($3Dmol.SurfaceType.VDW, {opacity: 0.7, color: 'white'}, {});
              \(highlightScript)
              viewer.render();
              return true;
            })();
            """
        case .ballAndStick:
            script = """
            (() => {
              if (typeof viewer === 'undefined') return false;
              viewer.removeAllSurfaces();
              viewer.setStyle({}, {stick: {radius: 0.1}, sphere: {scale: 0.3}});
              \(highlightScript)
              viewer.render();
              return true;
            })();
            """
        case .spaceFilling:
            script = """
            (() => {
              if (typeof viewer === 'undefined') return false;
              viewer.removeAllSurfaces();
              viewer.setStyle({}, {sphere: {scale: 1.0}});
              \(highlightScript)
              viewer.render();
              return true;
            })();
            """
        case .wireframe:
            script = """
            (() => {
              if (typeof viewer === 'undefined') return false;
              viewer.removeAllSurfaces();
              viewer.setStyle({}, {line: {}});
              \(highlightScript)
              viewer.render();
              return true;
            })();
            """
        }
        webView.evaluateJavaScript(script) { result, error in
            guard error == nil else {
                completion(false)
                return
            }
            completion((result as? Bool) == true)
        }
    }
}

#Preview {
    Molecule3DView(
        coordinates: Molecule3DCoordinates(
            atoms: [
                Atom3D(symbol: "C", x: 0.0, y: 0.0, z: 0.0, index: 0),
                Atom3D(symbol: "C", x: 1.5, y: 0.0, z: 0.0, index: 1),
                Atom3D(symbol: "O", x: 0.75, y: 1.3, z: 0.0, index: 2)
            ],
            bonds: [
                Bond3D(atom1: 0, atom2: 1, order: 1),
                Bond3D(atom1: 0, atom2: 2, order: 1),
                Bond3D(atom1: 1, atom2: 2, order: 1)
            ],
            smiles: "CCO"
        )
    )
    .frame(width: 600, height: 500)
}


