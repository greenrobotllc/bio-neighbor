# Setting Up the Xcode Project for BioNeighbor

## Current Status ✅

Your backend is ready:
- ✅ **9,993 molecules** loaded and indexed
- ✅ **FAISS index** built (78MB)
- ✅ **Fingerprints** computed (79MB)
- ✅ **Python backend** ready to serve API requests
- ✅ **SwiftUI source files** ready in `macos_app/BioNeighbor/`

## Next Steps: Create Xcode Project

### Step 1: Create New Xcode Project

1. **Open Xcode**
2. **File → New → Project** (or ⌘⇧N)
3. **Select Template:**
   - Platform: **macOS**
   - Template: **App**
   - Click **Next**

4. **Configure Project:**
   - **Product Name:** `BioNeighbor`
   - **Team:** (Select your team or leave blank)
   - **Organization Identifier:** `com.yourname` (or your domain)
   - **Interface:** **SwiftUI**
   - **Language:** **Swift**
   - **Storage:** None (uncheck Core Data)
   - **Include Tests:** (optional)
   - Click **Next**

5. **Choose Location:**
   - Navigate to: `/Users/andytriboletti/Documents/GitHub/bio-neighbor/macos_app/`
   - **IMPORTANT:** Check "Create Git repository" is **unchecked** (we already have a repo)
   - Click **Create**

### Step 2: Add Swift Source Files

1. **Delete default files:**
   - Right-click `ContentView.swift` → Delete → Move to Trash

2. **Add existing files:**
   - Right-click the `BioNeighbor` folder in Xcode
   - Select **"Add Files to BioNeighbor..."**
   - Navigate to `macos_app/BioNeighbor/`
   - Select **ALL** Swift files:
     - `BioNeighborApp.swift`
     - `Models.swift`
     - `BackendService.swift`
     - `SearchView.swift`
     - `ResultsView.swift`
     - `MoleculeDetailView.swift`
   - Make sure **"Copy items if needed"** is **UNCHECKED** (files are already in the right place)
   - **"Add to targets"** → Check `BioNeighbor`
   - Click **Add**

### Step 3: Configure Project Settings

1. **Select the project** (top item in navigator)
2. **Select the "BioNeighbor" target**
3. **General Tab:**
   - **Minimum Deployments:** macOS 13.0 or later
   - **App Category:** Utilities (or Science)

4. **Signing & Capabilities Tab:**
   - **App Sandbox:** Keep enabled for security (recommended)
     - Add minimal entitlements:
       - **Outgoing Connections (Client)** - for HTTP requests to localhost:5000
       - **User Selected File** - if you need file access
     - If you must disable sandbox (not recommended):
       - Only for development/testing
       - Production apps should use proper entitlements

5. **Build Settings:**
   - Search for "Swift Language Version"
   - Set to **Swift 5** (or latest)

### Step 4: Verify Backend is Ready

Before running the app, make sure the backend is set up:

```bash
cd /Users/andytriboletti/Documents/GitHub/bio-neighbor
source venv/bin/activate

# Verify data exists
ls -lh data/molecules.db data/faiss_index.bin

# Test the API (optional)
python backend/api.py --mode http --host 127.0.0.1 --port 5000
# (Leave this running, then test in another terminal or browser)
```

### Step 5: Build and Run

1. **In Xcode:**
   - Select scheme: **BioNeighbor** → **My Mac**
   - Build: **⌘B**
   - Run: **⌘R**

2. **First Run:**
   - The app will try to start the Python backend automatically
   - If it fails, you'll see an error message
   - You can manually start the backend:
     ```bash
     cd /Users/andytriboletti/Documents/GitHub/bio-neighbor
     source venv/bin/activate
     python backend/api.py --mode http --host 127.0.0.1 --port 5000
     ```

## Troubleshooting

### "Backend not available" error
- Make sure Python backend is running: `python backend/api.py --mode http`
- Check that port 5000 is not in use: `lsof -i :5000`
- Verify venv is activated and dependencies are installed

### App Sandbox issues
- Keep App Sandbox enabled and add minimal entitlements:
  - "Outgoing Connections (Client)" for network access
  - "User Selected File" if file access is needed
- Only disable sandbox for development/testing (not recommended for production)

### Python backend path issues
- The app looks for backend at: `../backend/api.py` relative to the app bundle
- Or modify `BackendService.swift` to use absolute paths

## Project Structure

```
bio-neighbor/
├── backend/              # Python backend (✅ Ready)
│   ├── api.py           # HTTP API server
│   ├── search_engine.py # FAISS search
│   └── ...
├── data/                 # Molecules and indexes (✅ Ready)
│   ├── molecules.db      # 9,993 molecules
│   ├── faiss_index.bin  # Search index
│   └── ...
└── macos_app/           # SwiftUI app
    ├── BioNeighbor/     # Swift source files (✅ Ready)
    │   ├── BioNeighborApp.swift
    │   ├── BackendService.swift
    │   └── ...
    └── BioNeighbor.xcodeproj  # (You'll create this)
```

## Quick Test

Once the Xcode project is set up:

1. **Start backend manually:**
   ```bash
   cd /Users/andytriboletti/Documents/GitHub/bio-neighbor
   source venv/bin/activate
   python backend/api.py --mode http
   ```

2. **Run the app in Xcode** (⌘R)

3. **Test search:**
   - Enter a SMILES string (e.g., `CC(=O)O` for acetic acid)
   - Click "Search"
   - Should see similar molecules

## Next Development Steps

After the Xcode project is working:

1. **UI Polish:**
   - Improve molecule visualization
   - Add loading states
   - Better error messages

2. **Features:**
   - Molecule structure rendering
   - Export results
   - Save favorite molecules

3. **Performance:**
   - Optimize search speed
   - Add caching
   - Background processing

