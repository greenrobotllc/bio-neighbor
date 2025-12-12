"""
Molecule structure rendering using RDKit.
Generates 2D structure images from SMILES strings.
"""

import io
from pathlib import Path
from typing import Optional
from rdkit import Chem
from rdkit.Chem import Draw, AllChem
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


def render_molecule_to_base64(smiles: str, width: int = 400, height: int = 400, format: str = "PNG") -> Optional[str]:
    """
    Render a molecule to a base64-encoded image string.
    
    Args:
        smiles: SMILES string
        width: Image width in pixels
        height: Image height in pixels
        format: Image format (PNG, JPEG, etc.)
        
    Returns:
        Base64-encoded image string, or None if SMILES is invalid
    """
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

