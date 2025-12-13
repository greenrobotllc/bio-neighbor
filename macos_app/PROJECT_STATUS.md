# Xcode Project Setup Status

## ✅ Completed

1. **All Swift files copied** to `BioNeighbor/BioNeighbor/`:
   - ✅ `BioNeighborApp.swift` - Main app entry (uses SearchView)
   - ✅ `Models.swift` - Data models
   - ✅ `BackendService.swift` - Python backend communication
   - ✅ `SearchView.swift` - Main search interface
   - ✅ `ResultsView.swift` - Results display
   - ✅ `MoleculeDetailView.swift` - Molecule detail view
   - ✅ `ContentView.swift` - **DELETED** (replaced by SearchView)

2. **Project settings updated**:
   - ✅ Minimum macOS version: **13.0** (changed from 26.1)
   - ✅ App Sandbox: **DISABLED** (needed for subprocess execution)

3. **Backend path detection** improved in `BackendService.swift`

## 📋 Next Steps in Xcode

### 1. Open the Project
```bash
open macos_app/BioNeighbor/BioNeighbor.xcodeproj
```

### 2. Verify Files are Visible
- In Xcode, check the Project Navigator (left sidebar)
- You should see all 6 Swift files under `BioNeighbor` folder
- If any are missing, right-click the folder → "Add Files to BioNeighbor..."

### 3. Build and Test
1. **Select scheme:** BioNeighbor → My Mac
2. **Build:** ⌘B (should succeed)
3. **Run:** ⌘R

### 4. If Build Fails
- Check that all Swift files are included in the target
- Select each file → File Inspector → Target Membership → ✅ BioNeighbor

### 5. Test Backend Connection
Before running the app, start the backend:
```bash
cd /Users/andytriboletti/Documents/GitHub/bio-neighbor
source venv/bin/activate
python backend/api.py --mode http --host 127.0.0.1 --port 5000
```

Then run the app - it should connect automatically!

## Project Structure

```
macos_app/BioNeighbor/
├── BioNeighbor.xcodeproj/     # Xcode project
├── BioNeighbor/               # Source files
│   ├── BioNeighborApp.swift  ✅
│   ├── Models.swift          ✅
│   ├── BackendService.swift  ✅
│   ├── SearchView.swift      ✅
│   ├── ResultsView.swift     ✅
│   ├── MoleculeDetailView.swift ✅
│   └── Assets.xcassets/      (default)
└── BioNeighborTests/         (test files)
```

## Troubleshooting

**"Cannot find 'SearchView' in scope"**
- Make sure `SearchView.swift` is in the project
- Check Target Membership for all files

**"Backend not available"**
- Start backend manually: `python backend/api.py --mode http`
- Check that `getProjectRoot()` finds the correct path
- Verify `venv/bin/python` and `backend/api.py` exist

**App Sandbox errors**
- Already disabled in project settings
- If still issues, check Signing & Capabilities tab

