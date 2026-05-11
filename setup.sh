#!/bin/bash

# BioNeighbor Setup Script for macOS

set -e

echo "🚀 Setting up BioNeighbor..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10+ first."
    exit 1
fi

# WeasyPrint (treatment-auditor PDF reports) needs Pango/cairo from Homebrew.
# This script is macOS-specific; bail out clearly rather than silently
# continuing without Pango (PDF rendering would later fail with an opaque
# library-load error otherwise).
if [[ "$OSTYPE" == darwin* ]]; then
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew is required on macOS for Pango/cairo (WeasyPrint PDF rendering)."
        echo "   Install Homebrew from https://brew.sh and re-run this script."
        exit 1
    fi
    if ! brew list pango &> /dev/null; then
        echo "📦 Installing Pango/cairo for PDF rendering (WeasyPrint)..."
        brew install pango
    fi
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo "📥 Installing Python dependencies..."
cd backend
pip install -r requirements.txt
cd ..

# Create data directory if it doesn't exist
mkdir -p data

# Verify RDKit installation
echo ""
echo "🔍 Verifying RDKit installation..."
if python -c "from rdkit import Chem; print('✅ RDKit version:', Chem.__version__)" 2>/dev/null; then
    echo "✅ RDKit is installed and working!"
else
    echo "⚠️  RDKit is not installed or not working"
    echo "   Please install RDKit using one of the methods in INSTALL_RDKIT.md"
    echo "   Then verify with: python -c 'from rdkit import Chem; print(Chem.__version__)'"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment: source venv/bin/activate"
if ! python -c "from rdkit import Chem" 2>/dev/null; then
    echo "2. Install RDKit (see INSTALL_RDKIT.md)"
fi
echo "2. Run the data loader: python backend/main.py setup --max-molecules 10000"
echo "3. Build the FAISS index (included in step 2)"
echo ""

