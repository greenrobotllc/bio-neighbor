"""
Molecule structure rendering using RDKit.
Generates 2D structure images from SMILES strings.
"""

import io
from pathlib import Path
from typing import Optional, Dict
from rdkit import Chem
from rdkit.Chem import Draw, AllChem
from rdkit.Chem.Draw import rdMolDraw2D
from PIL import Image
import base64


def render_molecule_2d(smiles: str, width: int = 400, height: int = 400) -> Optional[Image.Image]:
    """
    Render a 2D structure image from a SMILES string.
    
    Args:
        smiles: SMILES string
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        PIL Image object, or None if SMILES is invalid
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # Generate 2D coordinates
        AllChem.Compute2DCoords(mol)
        
        # Draw molecule
        img = Draw.MolToImage(mol, size=(width, height))
        return img
    
    except Exception as e:
        print(f"Error rendering molecule: {e}")
        return None


def render_molecule_2d_enhanced(smiles: str, width: int = 400, height: int = 400) -> Optional[Image.Image]:
    """
    Render a 2D structure image with enhanced styling (better colors, fonts, resolution).
    
    Args:
        smiles: SMILES string
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        PIL Image object, or None if SMILES is invalid
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # Generate 2D coordinates with better algorithm
        AllChem.Compute2DCoords(mol)
        
        # Try to use enhanced drawer if available, otherwise fall back to basic
        try:
            # Try Cairo-based drawer for better quality
            drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
            drawer.SetDrawOptions()
            
            # Enhanced drawing options
            opts = drawer.drawOptions()
            opts.useBWAtomPalette = False  # Use colored atoms
            opts.atomLabelFontSize = max(12, width // 30)  # Larger font for larger images
            opts.bondLineWidth = max(2, width // 200)  # Thicker bonds
            opts.highlightAtomColors = {}
            opts.highlightBondColors = {}
            
            # Draw molecule
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()
            
            # Get image
            img_data = drawer.GetDrawingText()
            img = Image.open(io.BytesIO(img_data))
            return img
        except Exception:
            # Fallback to basic rendering with larger size for better quality
            # Cap dimensions to prevent memory spikes (max 2000px)
            max_dimension = 2000
            fallback_width = min(width * 2, max_dimension)
            fallback_height = min(height * 2, max_dimension)
            return render_molecule_2d(smiles, fallback_width, fallback_height)
    
    except Exception as e:
        print(f"Error rendering enhanced molecule: {e}")
        # Fallback to basic rendering
        return render_molecule_2d(smiles, width, height)


def render_molecule_to_base64(smiles: str, width: int = 400, height: int = 400, format: str = "PNG", enhanced: bool = False) -> Optional[str]:
    """
    Render a molecule to a base64-encoded image string.
    
    Args:
        smiles: SMILES string
        width: Image width in pixels
        height: Image height in pixels
        format: Image format (PNG, JPEG, etc.)
        enhanced: If True, use enhanced rendering with better styling
        
    Returns:
        Base64-encoded image string, or None if SMILES is invalid
    """
    if enhanced:
        img = render_molecule_2d_enhanced(smiles, width=width, height=height)
    else:
        img = render_molecule_2d(smiles, width=width, height=height)
    
    if img is None:
        return None
    
    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    img_bytes = buffer.getvalue()
    
    # Encode to base64
    base64_str = base64.b64encode(img_bytes).decode('utf-8')
    return f"data:image/{format.lower()};base64,{base64_str}"


def generate_3d_coordinates(smiles: str) -> Optional[Dict]:
    """
    Generate 3D coordinates for a molecule from SMILES string.
    
    Args:
        smiles: SMILES string
        
    Returns:
        Dictionary with:
        - atoms: List of dicts with 'symbol', 'x', 'y', 'z'
        - bonds: List of dicts with 'atom1', 'atom2', 'order'
        - smiles: Original SMILES string
        Or None if SMILES is invalid
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # Add hydrogens for better 3D structure
        mol = Chem.AddHs(mol)
        
        # Generate 3D coordinates
        result = AllChem.EmbedMolecule(mol, randomSeed=42)
        if result != 0:
            # Try alternative method if embedding fails
            AllChem.EmbedMolecule(mol, useRandomCoords=True)
        
        # Optimize geometry using MMFF
        try:
            AllChem.MMFFOptimizeMolecule(mol)
        except Exception:
            # If MMFF fails, try UFF
            AllChem.UFFOptimizeMolecule(mol)
        
        # Extract atom coordinates and types
        conf = mol.GetConformer()
        atoms = []
        for i, atom in enumerate(mol.GetAtoms()):
            pos = conf.GetAtomPosition(i)
            atoms.append({
                'symbol': atom.GetSymbol(),
                'x': float(pos.x),
                'y': float(pos.y),
                'z': float(pos.z),
                'index': i
            })
        
        # Extract bonds
        bonds = []
        for bond in mol.GetBonds():
            bonds.append({
                'atom1': int(bond.GetBeginAtomIdx()),
                'atom2': int(bond.GetEndAtomIdx()),
                'order': int(bond.GetBondTypeAsDouble())
            })
        
        return {
            'atoms': atoms,
            'bonds': bonds,
            'smiles': smiles
        }
    
    except Exception as e:
        print(f"Error generating 3D coordinates: {e}")
        return None


def render_molecule_to_file(smiles: str, output_path: Path, width: int = 400, height: int = 400, format: str = "PNG"):
    """
    Render a molecule to a file.
    
    Args:
        smiles: SMILES string
        output_path: Path to save the image
        width: Image width in pixels
        height: Image height in pixels
        format: Image format (PNG, JPEG, etc.)
    """
    img = render_molecule_2d(smiles, width=width, height=height)
    if img is None:
        raise ValueError(f"Invalid SMILES string: {smiles}")
    
    img.save(output_path, format=format)


if __name__ == "__main__":
    # Test rendering
    test_smiles = [
        ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
        ("Caffeine", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"),
    ]
    
    for name, smiles in test_smiles:
        print(f"Rendering {name}...")
        img = render_molecule_2d(smiles)
        if img:
            output_path = Path(f"test_{name.lower()}.png")
            img.save(output_path)
            print(f"  ✓ Saved to {output_path}")
        else:
            print(f"  ✗ Failed to render")

