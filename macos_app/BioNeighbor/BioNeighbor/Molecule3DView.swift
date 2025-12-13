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
    
    enum RepresentationType: String, CaseIterable {
        case ballAndStick = "stick"
        case spaceFilling = "sphere"
        case wireframe = "line"
        case surface = "surface"
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Controls
            HStack {
                Picker("Representation", selection: $representation) {
                    Text("Ball & Stick").tag(RepresentationType.ballAndStick)
                    Text("Space Filling").tag(RepresentationType.spaceFilling)
                    Text("Wireframe").tag(RepresentationType.wireframe)
                    Text("Surface").tag(RepresentationType.surface)
                }
                .pickerStyle(.segmented)
                .frame(width: 400)
                
                Spacer()
            }
            .padding()
            
            // WebView
            if isLoading {
                ProgressView("Loading 3D structure...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                WebViewRepresentable(
                    coordinates: coordinates,
                    representation: representation
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
    
    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        
        // Load HTML with 3Dmol.js
        let html = generateHTML(coordinates: coordinates, representation: representation)
        webView.loadHTMLString(html, baseURL: nil)
        
        return webView
    }
    
    func updateNSView(_ webView: WKWebView, context: Context) {
        // Update representation when it changes
        if representation != context.coordinator.lastRepresentation {
            updateRepresentation(webView: webView, representation: representation)
            context.coordinator.lastRepresentation = representation
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        var lastRepresentation: Molecule3DView.RepresentationType = .ballAndStick
    }
    
    private func generateHTML(coordinates: Molecule3DCoordinates, representation: Molecule3DView.RepresentationType) -> String {
        // Convert coordinates to PDB format string
        let pdbString = generatePDBString(coordinates: coordinates)
        
        // Escape the PDB string for JavaScript template literal
        // Escape backticks and ${ to prevent breaking the template literal
        let escapedPDB = pdbString
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "`", with: "\\`")
            .replacingOccurrences(of: "${", with: "\\${")
        
        // Determine initial style based on representation
        // Note: Loading 3Dmol-min.js from CDN requires network access and may fail offline.
        // For production, consider bundling the JS library or implementing a caching strategy.
        let initialStyle: String
        let initialScript: String
        switch representation {
        case .surface:
            initialStyle = "surface"
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.addSurface($3Dmol.SurfaceType.VDW, {opacity: 0.7, color: 'white'}, {});
                viewer.zoomTo();
                viewer.render();
            """
        case .ballAndStick:
            initialStyle = "stick"
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {stick: {}});
                viewer.zoomTo();
                viewer.render();
            """
        case .spaceFilling:
            initialStyle = "sphere"
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {sphere: {}});
                viewer.zoomTo();
                viewer.render();
            """
        case .wireframe:
            initialStyle = "line"
            initialScript = """
                viewer.addModel(pdb, "pdb");
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {line: {}});
                viewer.zoomTo();
                viewer.render();
            """
        }
        
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.1.0/3Dmol-min.js"></script>
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
                
                var pdb = `\(escapedPDB)`;
                
                \(initialScript)
                
                // Handle mouse interactions
                viewer.zoom(0.8);
            </script>
        </body>
        </html>
        """
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
    
    private func updateRepresentation(webView: WKWebView, representation: Molecule3DView.RepresentationType) {
        let script: String
        switch representation {
        case .surface:
            // Surface representation requires addSurface API, not setStyle
            script = """
            if (typeof viewer !== 'undefined') {
                viewer.removeAllSurfaces();
                viewer.addSurface($3Dmol.SurfaceType.VDW, {opacity: 0.7, color: 'white'}, {});
                viewer.render();
            }
            """
        case .ballAndStick:
            script = """
            if (typeof viewer !== 'undefined') {
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {stick: {}});
                viewer.render();
            }
            """
        case .spaceFilling:
            script = """
            if (typeof viewer !== 'undefined') {
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {sphere: {}});
                viewer.render();
            }
            """
        case .wireframe:
            script = """
            if (typeof viewer !== 'undefined') {
                viewer.removeAllSurfaces();
                viewer.setStyle({}, {line: {}});
                viewer.render();
            }
            """
        }
        webView.evaluateJavaScript(script, completionHandler: nil)
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

