#!/bin/bash
# Script to help create Xcode project for BioNeighbor macOS app
# This creates a basic project structure that you can open in Xcode

set -e

PROJECT_DIR="macos_app"
XCODE_PROJECT_NAME="BioNeighbor"

echo "🚀 BioNeighbor Xcode Project Setup"
echo "=================================="
echo ""
echo "This script will help you create an Xcode project."
echo "You'll need to complete the setup in Xcode."
echo ""

# Check if Xcode is installed
if ! command -v xcodebuild &> /dev/null; then
    echo "⚠️  Xcode command line tools not found."
    echo "   Please install Xcode from the App Store first."
    exit 1
fi

echo "✅ Xcode found"
echo ""
echo "📝 Manual Steps Required:"
echo ""
echo "1. Open Xcode"
echo "2. File → New → Project"
echo "3. Choose 'macOS' → 'App'"
echo "4. Configure:"
echo "   - Product Name: BioNeighbor"
echo "   - Team: (your team)"
echo "   - Organization Identifier: com.yourname (or your domain)"
echo "   - Interface: SwiftUI"
echo "   - Language: Swift"
echo "   - ✅ Use Core Data (unchecked)"
echo "   - ✅ Include Tests (optional)"
echo ""
echo "5. Save location:"
echo "   Navigate to: $(pwd)/${PROJECT_DIR}"
echo "   Save the project there"
echo ""
echo "6. After creating the project:"
echo "   - Delete the default ContentView.swift"
echo "   - Add all Swift files from ${PROJECT_DIR}/BioNeighbor/ to the project"
echo "   - Set minimum macOS version to 13.0 in project settings"
echo "   - Disable App Sandbox (or configure network permissions)"
echo ""
echo "📁 Swift files to add:"
for file in ${PROJECT_DIR}/BioNeighbor/*.swift; do
    if [ -f "$file" ]; then
        echo "   - $(basename $file)"
    fi
done
echo ""
echo "See ${PROJECT_DIR}/README.md for detailed instructions"
echo ""

