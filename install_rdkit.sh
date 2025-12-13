#!/bin/bash

# Helper script to install RDKit
# This script helps install RDKit using the best available method

set -e

echo "🔬 RDKit Installation Helper"
echo "=============================="
echo ""

# Check if conda is available
if command -v conda &> /dev/null; then
    echo "✅ Conda is available - this is the recommended method"
    echo ""
    read -p "Do you want to use conda to install RDKit? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Creating conda environment 'bioneighbor' with Python 3.11..."
        conda create -n bioneighbor python=3.11 -y
        echo ""
        echo "Installing RDKit..."
        conda activate bioneighbor
        conda install -c conda-forge rdkit -y
        echo ""
        echo "✅ RDKit installed successfully via conda!"
        echo ""
        echo "To activate this environment in the future:"
        echo "  conda activate bioneighbor"
        exit 0
    fi
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

echo "Detected Python version: $PYTHON_VERSION"
echo ""

# Check architecture
ARCH=$(python3 -c "import platform; print(platform.machine())" 2>/dev/null || echo "unknown")
echo "Detected architecture: $ARCH"
echo ""

# Try to install from GitHub releases
if [ "$PYTHON_MAJOR" = "3" ] && [ "$PYTHON_MINOR" -ge "9" ] && [ "$PYTHON_MINOR" -le "11" ]; then
    echo "Attempting to install RDKit from pre-built wheels..."
    echo ""
    
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
        # Apple Silicon
        WHEEL_URL="https://github.com/rdkit/rdkit/releases/download/Release_2023_09_1/rdkit-2023.9.1-cp${PYTHON_MINOR}-cp${PYTHON_MINOR}-macosx_11_0_arm64.whl"
    else
        # Intel
        WHEEL_URL="https://github.com/rdkit/rdkit/releases/download/Release_2023_09_1/rdkit-2023.9.1-cp${PYTHON_MINOR}-cp${PYTHON_MINOR}-macosx_10_9_x86_64.whl"
    fi
    
    echo "Trying to install from: $WHEEL_URL"
    if pip install "$WHEEL_URL"; then
        echo ""
        echo "✅ RDKit installed successfully from pre-built wheel!"
        exit 0
    else
        echo ""
        echo "❌ Failed to install from pre-built wheel"
    fi
else
    echo "⚠️  Python $PYTHON_VERSION detected"
    echo "   Pre-built wheels are available for Python 3.9-3.11"
fi

echo ""
echo "❌ Automatic installation failed"
echo ""
echo "Please use one of these methods:"
echo ""
echo "1. Install conda and use it (RECOMMENDED):"
echo "   brew install miniconda"
echo "   conda create -n bioneighbor python=3.11"
echo "   conda activate bioneighbor"
echo "   conda install -c conda-forge rdkit"
echo ""
echo "2. Use Python 3.11 with pre-built wheels:"
echo "   brew install python@3.11"
echo "   python3.11 -m venv venv"
echo "   source venv/bin/activate"
echo "   # Then run this script again"
echo ""
echo "3. Build from source (advanced):"
echo "   See: https://www.rdkit.org/docs/Install.html"
echo ""
exit 1

