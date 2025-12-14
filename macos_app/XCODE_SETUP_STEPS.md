# Xcode Project Setup - Step by Step

## Current Status
✅ Swift source files temporarily renamed to `BioNeighbor_SourceFiles` to avoid conflict

## Steps to Create Xcode Project

### 1. In Xcode (Now that folder is renamed):

1. **File → New → Project** (⌘⇧N)
2. **Choose Template:**
   - Platform: **macOS**
   - Template: **App**
   - Click **Next**

3. **Configure Project:**
   - **Product Name:** `BioNeighbor`
   - **Team:** (Your team or leave blank)
   - **Organization Identifier:** `com.yourname` (or your domain)
   - **Interface:** **SwiftUI**
   - **Language:** **Swift**
   - **Storage:** None (uncheck Core Data)
   - **Include Tests:** (optional)
   - Click **Next**

4. **Choose Location:**
   - Navigate to: `/Users/andytriboletti/Documents/GitHub/bio-neighbor/macos_app/`
   - **IMPORTANT:** Uncheck "Create Git repository" (we already have one)
   - Click **Create**

### 2. After Xcode Creates the Project:

Xcode will create:
- `BioNeighbor.xcodeproj` (project file)
- `BioNeighbor/` folder (with default ContentView.swift)

### 3. Replace Default Files:

1. **Delete default files:**
   - In Xcode, right-click `ContentView.swift` → Delete → Move to Trash
   - Delete `BioNeighborApp.swift` if Xcode created one (we have our own)

2. **Add our Swift files:**
   - Right-click the `BioNeighbor` folder in Xcode navigator
   - Select **"Add Files to BioNeighbor..."**
   - Navigate to `macos_app/BioNeighbor_SourceFiles/`
   - Select **ALL** Swift files:
     - `BioNeighborApp.swift`
     - `Models.swift`
     - `BackendService.swift`
     - `SearchView.swift`
     - `ResultsView.swift`
     - `MoleculeDetailView.swift`
   - **IMPORTANT:** 
     - ✅ Check "Copy items if needed" (this copies files into Xcode's BioNeighbor folder)
     - ✅ Check "Add to targets: BioNeighbor"
   - Click **Add**

3. **Clean up:**
   - After files are added, you can delete the `BioNeighbor_SourceFiles` folder:
     ```bash
     rm -rf macos_app/BioNeighbor_SourceFiles
     ```

### 4. Configure Project Settings:

1. **Select project** (top item in navigator)
2. **Select "BioNeighbor" target**
3. **General Tab:**
   - **Minimum Deployments:** macOS 13.0
   - **App Category:** Utilities

4. **Signing & Capabilities Tab:**
   - **App Sandbox:** **DISABLE** ✅
     - (Needed for subprocess execution and localhost network)

### 5. Build and Test:

1. **Build:** ⌘B
2. **Run:** ⌘R

The app should launch and try to connect to the backend!

## Troubleshooting

If you see errors about missing files or imports, make sure all Swift files were added to the target.

