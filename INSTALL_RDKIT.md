# Installing RDKit

RDKit installation can be tricky. **RDKit is NOT available via standard pip/PyPI**. Here are the recommended methods:

## Option 1: Using Conda (STRONGLY RECOMMENDED)

Conda is the most reliable and easiest way to install RDKit:

```bash
# Install miniconda if you don't have it
# Download from: https://docs.conda.io/en/latest/miniconda.html
# Or: brew install miniconda

# Create a new conda environment with Python 3.11
conda create -n bioneighbor python=3.11
conda activate bioneighbor

# Install RDKit from conda-forge
conda install -c conda-forge rdkit

# Install other dependencies
cd /path/to/bio-neighbor
pip install -r backend/requirements.txt
```

**Why conda?** RDKit has complex C++ dependencies that are pre-built in conda packages, making installation much easier.

## Option 2: Install from Pre-built Wheels (Alternative)

If you cannot use conda, you can try installing from pre-built wheels:

```bash
# For Python 3.11 on macOS (Intel)
pip install https://github.com/rdkit/rdkit/releases/download/Release_2023_09_1/rdkit-2023.9.1-cp311-cp311-macosx_10_9_x86_64.whl

# For Python 3.11 on macOS (Apple Silicon)
pip install https://github.com/rdkit/rdkit/releases/download/Release_2023_09_1/rdkit-2023.9.1-cp311-cp311-macosx_11_0_arm64.whl

# Check available releases: https://github.com/rdkit/rdkit/releases
```

**Note:** You need to match your Python version and architecture. Check your Python version:
```bash
python --version
python -c "import platform; print(platform.machine())"
```

## Option 3: Install from Source

If the above methods don't work, you can build RDKit from source:

```bash
# See official instructions:
# https://www.rdkit.org/docs/Install.html
```

## Verify Installation

After installing RDKit, verify it works:

```bash
python -c "from rdkit import Chem; print('RDKit version:', Chem.__version__)"
```

If this command succeeds, RDKit is installed correctly!

