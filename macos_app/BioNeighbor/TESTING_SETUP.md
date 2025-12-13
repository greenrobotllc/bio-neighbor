# Testing Setup Guide

## Overview

This project includes comprehensive testing:
- **Unit Tests**: RxSwift reactive code, ViewModels
- **UI Tests**: Actual app interaction, button clicks, navigation
- **Integration Tests**: Backend API workflows
- **Snapshot Tests**: Visual regression testing
- **End-to-End Tests**: Complete user workflows

## Required Dependencies

### 1. RxTest and RxBlocking (for RxSwift testing)

**In Xcode:**
1. File → Add Package Dependencies...
2. URL: `https://github.com/ReactiveX/RxSwift.git`
3. Version: 6.7.0 or latest
4. Add to **BioNeighborTests** target:
   - ✅ RxTest
   - ✅ RxBlocking

### 2. SnapshotTesting (for visual regression tests)

**In Xcode:**
1. File → Add Package Dependencies...
2. URL: `https://github.com/pointfreeco/swift-snapshot-testing`
3. Version: Latest
4. Add to **BioNeighborSnapshotTests** target

### 3. Optional: Quick and Nimble (BDD testing)

**In Xcode:**
1. Quick: `https://github.com/Quick/Quick`
2. Nimble: `https://github.com/Quick/Nimble`
3. RxNimble: `https://github.com/RxSwiftCommunity/RxNimble`

## Test Targets

The project includes three test targets:

1. **BioNeighborTests** - Unit tests
   - ReactiveDownloadServiceTests
   - ViewModelTests
   - BackendServiceTests

2. **BioNeighborUITests** - UI integration tests
   - DownloadDataUITests
   - MoleculesDownloadUITests
   - DrugsDownloadUITests
   - DiseasesDownloadUITests
   - SearchAutocompleteUITests
   - E2EDownloadTests

3. **BioNeighborSnapshotTests** - Snapshot tests
   - DownloadViewsSnapshotTests
   - StatisticsViewSnapshotTests

## Running Tests

### In Xcode:
1. **Run All Tests**: ⌘U
2. **Run Specific Test**: Click diamond icon next to test
3. **Run Test Target**: Product → Test (⌘U)

### From Command Line:
```bash
# Run all tests
xcodebuild test -scheme BioNeighbor -destination 'platform=macOS'

# Run specific test target
xcodebuild test -scheme BioNeighbor -only-testing:BioNeighborTests

# Run UI tests
xcodebuild test -scheme BioNeighbor -only-testing:BioNeighborUITests
```

### Backend Tests:
```bash
cd /Users/andytriboletti/Documents/GitHub/bio-neighbor
source venv/bin/activate
python backend/test_downloads.py
python backend/test_api_integration.py
```

## Test Coverage

To enable code coverage:
1. Edit Scheme → Test
2. Check "Gather coverage data"
3. Run tests
4. View coverage: Report Navigator → Coverage

## UI Test Requirements

UI tests require:
- Backend to be running (or use mocks)
- Accessibility identifiers (already added)
- Reasonable timeouts for network operations

## Snapshot Test Setup

1. Add SnapshotTesting package
2. Run tests once to generate reference images
3. Reference images stored in `__Snapshots__/` directory
4. Commit reference images to git

## Continuous Integration

For CI/CD:
```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    xcodebuild test -scheme BioNeighbor -destination 'platform=macOS'
    
- name: Run Backend Tests
  run: |
    python backend/test_downloads.py
    python backend/test_api_integration.py
```

## Test Data

- Use `TestDataFactory` for creating test data
- Use `MockBackendService` for unit tests
- Backend tests use actual database (test data)

## Troubleshooting

### UI Tests Fail:
- Ensure backend is running
- Check accessibility identifiers
- Increase timeouts if needed
- Use `XCTSkip` for tests requiring backend

### Snapshot Tests Fail:
- Run `swift test` to generate reference images
- Update snapshots: `swift test --update-snapshots`

### RxTest Issues:
- Ensure RxTest is added to test target
- Check import statements
- Verify TestScheduler usage

