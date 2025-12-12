# BioNeighbor macOS App

SwiftUI macOS application for BioNeighbor molecular similarity search.

## Setup Instructions

### 1. Create Xcode Project

1. Open Xcode
2. Create a new project:
   - Choose "macOS" → "App"
   - Product Name: `BioNeighbor`
   - Interface: `SwiftUI`
   - Language: `Swift`
   - Save location: Choose the `macos_app` directory

### 2. Add Source Files

Copy all Swift files from this directory into the Xcode project:
- `BioNeighborApp.swift` → Replace the default App file
- `Models.swift`
- `BackendService.swift`
- `SearchView.swift`
- `ResultsView.swift`
- `MoleculeDetailView.swift`

### 3. Configure Project

1. Set minimum macOS version to 13.0 (for NavigationStack)
2. Enable "App Sandbox" if needed (may need to disable for subprocess execution)
3. Add network access permissions if using sandbox

### 4. Build and Run

1. Build the project (⌘B)
2. Run the app (⌘R)
3. Make sure the Python backend is running (the app can start it automatically)

## Notes

- The app communicates with the Python backend via HTTP (localhost:5000)
- The backend must be set up first (run `python backend/main.py setup`)
- The app will attempt to start the backend automatically if it's not running

