"""
Shared molecule lookup utilities.
Used by ligand_loader and curated_ligand_loader.
"""

import sqlite3
from typing import Optional


def find_molecule_by_chembl_id(chembl_id: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index by ChEMBL ID.

    Args:
        chembl_id: ChEMBL ID
        conn: Database connection

    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE chembl_id = ?", (chembl_id,))
    result = cursor.fetchone()
    return result[0] if result else None


def find_molecule_by_pubchem_cid(pubchem_cid: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index by PubChem CID.

    Args:
        pubchem_cid: PubChem Compound ID
        conn: Database connection

    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE pubchem_cid = ?", (pubchem_cid,))
    result = cursor.fetchone()
    return result[0] if result else None


def find_molecule_by_smiles(smiles: str, conn: sqlite3.Connection) -> Optional[int]:
    """
    Find molecule index by SMILES.

    Args:
        smiles: SMILES string
        conn: Database connection

    Returns:
        Molecule index (rowid) or None
    """
    cursor = conn.cursor()
    cursor.execute("SELECT rowid FROM molecules WHERE smiles = ?", (smiles,))
    result = cursor.fetchone()
    return result[0] if result else None
