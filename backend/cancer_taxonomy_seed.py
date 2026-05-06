"""
Curated cancer-type and subtype taxonomy seed for the v2 Cancer Research browse.

Each cancer type carries a MeSH ID for ChEMBL drug_indication lookups, and each
subtype carries a JSON `markers` array (rendered as filter chips in the UI) plus
optional EFO and ChEMBL indication search terms used by cancer_drug_aggregator.
"""

import json
import sqlite3
from typing import Dict, List


CANCER_TAXONOMY: List[Dict] = [
    {
        "name": "Breast cancer",
        "display_name": "Breast",
        "category": "Solid tumor",
        "mesh_id": "D001943",
        "icon": "figure.dress",
        "sort_order": 10,
        "description": "Malignant neoplasms originating in the breast tissue, classified by hormone-receptor and HER2 status.",
        "subtypes": [
            {
                "name": "Triple-Negative Breast Cancer",
                "short_name": "TNBC",
                "description": "ER-, PR-, HER2- breast cancer; aggressive, fewer targeted therapies.",
                "markers": ["ER-", "PR-", "HER2-", "BRCA1/2"],
                "chembl_indication_terms": ["triple-negative breast", "triple negative breast cancer"],
            },
            {
                "name": "HER2-Positive Breast Cancer",
                "short_name": "HER2+",
                "description": "HER2/neu over-expressing breast cancer; trastuzumab-targetable.",
                "markers": ["HER2+", "ERBB2"],
                "chembl_indication_terms": ["HER2-positive breast cancer", "ERBB2 positive breast"],
            },
            {
                "name": "Hormone Receptor-Positive Breast Cancer",
                "short_name": "HR+",
                "description": "ER+ and/or PR+ breast cancer; endocrine-therapy responsive.",
                "markers": ["ER+", "PR+", "HER2-"],
                "chembl_indication_terms": ["hormone receptor positive breast", "ER positive breast cancer"],
            },
            {
                "name": "Luminal A",
                "short_name": "Luminal A",
                "description": "ER+/PR+, HER2-, low Ki-67; best prognosis among breast subtypes.",
                "markers": ["ER+", "PR+", "HER2-", "Ki-67 low"],
                "chembl_indication_terms": ["luminal A breast cancer"],
            },
            {
                "name": "Luminal B",
                "short_name": "Luminal B",
                "description": "ER+, HER2+/-, high Ki-67; more proliferative than Luminal A.",
                "markers": ["ER+", "Ki-67 high"],
                "chembl_indication_terms": ["luminal B breast cancer"],
            },
        ],
    },
    {
        "name": "Lung cancer",
        "display_name": "Lung",
        "category": "Solid tumor",
        "mesh_id": "D008175",
        "icon": "lungs.fill",
        "sort_order": 20,
        "description": "Malignancies of the lung, primarily NSCLC and SCLC subtypes.",
        "subtypes": [
            {
                "name": "NSCLC Adenocarcinoma",
                "short_name": "LUAD",
                "description": "Most common NSCLC subtype; frequently EGFR/KRAS/ALK driven.",
                "markers": ["EGFR", "KRAS", "ALK", "ROS1"],
                "chembl_indication_terms": ["non-small cell lung adenocarcinoma", "lung adenocarcinoma"],
            },
            {
                "name": "NSCLC Squamous Cell",
                "short_name": "LUSC",
                "description": "Squamous-histology NSCLC; tobacco-associated, FGFR1-amplified.",
                "markers": ["FGFR1", "PIK3CA"],
                "chembl_indication_terms": ["squamous non-small cell lung cancer", "lung squamous cell carcinoma"],
            },
            {
                "name": "Small Cell Lung Cancer",
                "short_name": "SCLC",
                "description": "Aggressive neuroendocrine lung cancer; rapid growth, early metastasis.",
                "markers": ["TP53", "RB1"],
                "chembl_indication_terms": ["small cell lung cancer"],
            },
        ],
    },
    {
        "name": "Melanoma",
        "display_name": "Melanoma",
        "category": "Solid tumor",
        "mesh_id": "D008545",
        "icon": "circle.hexagongrid.fill",
        "sort_order": 30,
        "description": "Malignant tumors of melanocytes; checkpoint-inhibitor responsive.",
        "subtypes": [
            {
                "name": "Cutaneous Melanoma",
                "short_name": "Cutaneous",
                "description": "Skin melanoma; BRAF V600E common, immunotherapy responsive.",
                "markers": ["BRAF V600E", "NRAS"],
                "chembl_indication_terms": ["cutaneous melanoma", "skin melanoma"],
            },
            {
                "name": "Uveal Melanoma",
                "short_name": "Uveal",
                "description": "Eye melanoma; GNAQ/GNA11 mutations, immunotherapy-resistant.",
                "markers": ["GNAQ", "GNA11", "BAP1"],
                "chembl_indication_terms": ["uveal melanoma", "ocular melanoma"],
            },
            {
                "name": "Mucosal Melanoma",
                "short_name": "Mucosal",
                "description": "Rare melanoma of mucous membranes; KIT mutations.",
                "markers": ["KIT", "NF1"],
                "chembl_indication_terms": ["mucosal melanoma"],
            },
        ],
    },
    {
        "name": "Colorectal cancer",
        "display_name": "Colorectal",
        "category": "Solid tumor",
        "mesh_id": "D015179",
        "icon": "circle.grid.cross.fill",
        "sort_order": 40,
        "description": "Cancers of the colon and rectum; molecular subtypes guide therapy.",
        "subtypes": [
            {
                "name": "MSI-High Colorectal Cancer",
                "short_name": "MSI-H",
                "description": "Microsatellite-unstable CRC; checkpoint-inhibitor responsive.",
                "markers": ["MSI-H", "MMR-deficient"],
                "chembl_indication_terms": ["microsatellite instability colorectal", "MSI-H colorectal"],
            },
            {
                "name": "MSS Colorectal Cancer",
                "short_name": "MSS",
                "description": "Microsatellite-stable CRC; standard chemotherapy backbone.",
                "markers": ["MSS", "MMR-proficient"],
                "chembl_indication_terms": ["microsatellite stable colorectal"],
            },
            {
                "name": "KRAS-Mutant Colorectal Cancer",
                "short_name": "KRAS-mut",
                "description": "KRAS-driven CRC; G12C-targeted therapies emerging.",
                "markers": ["KRAS G12C", "KRAS G12D"],
                "chembl_indication_terms": ["KRAS mutant colorectal"],
            },
        ],
    },
    {
        "name": "Pancreatic cancer",
        "display_name": "Pancreatic",
        "category": "Solid tumor",
        "mesh_id": "D010190",
        "icon": "drop.triangle",
        "sort_order": 50,
        "description": "Cancers of the pancreas, predominantly ductal adenocarcinoma.",
        "subtypes": [
            {
                "name": "Pancreatic Ductal Adenocarcinoma",
                "short_name": "PDAC",
                "description": "Most common pancreatic cancer; KRAS-mutant in >90%.",
                "markers": ["KRAS", "TP53", "CDKN2A", "SMAD4"],
                "chembl_indication_terms": ["pancreatic ductal adenocarcinoma", "pancreatic adenocarcinoma"],
            },
            {
                "name": "Pancreatic Neuroendocrine Tumor",
                "short_name": "PNET",
                "description": "Slower-growing islet-cell tumors; mTOR/SSTR-targetable.",
                "markers": ["MEN1", "SSTR2"],
                "chembl_indication_terms": ["pancreatic neuroendocrine tumor"],
            },
        ],
    },
    {
        "name": "Renal cell carcinoma",
        "display_name": "Kidney",
        "category": "Solid tumor",
        "mesh_id": "D002292",
        "icon": "circle.dotted",
        "sort_order": 60,
        "description": "Cancers arising in the kidney's renal tubules.",
        "subtypes": [
            {
                "name": "Clear Cell Renal Cell Carcinoma",
                "short_name": "ccRCC",
                "description": "Most common RCC; VHL-loss driven, VEGF/HIF dependent.",
                "markers": ["VHL", "HIF-2α"],
                "chembl_indication_terms": ["clear cell renal cell carcinoma", "ccRCC"],
            },
            {
                "name": "Papillary Renal Cell Carcinoma",
                "short_name": "pRCC",
                "description": "MET-driven papillary RCC; less common than ccRCC.",
                "markers": ["MET", "FH"],
                "chembl_indication_terms": ["papillary renal cell carcinoma"],
            },
        ],
    },
    {
        "name": "Prostate cancer",
        "display_name": "Prostate",
        "category": "Solid tumor",
        "mesh_id": "D011471",
        "icon": "circle.circle.fill",
        "sort_order": 70,
        "description": "Malignancies of the prostate gland; AR-axis driven.",
        "subtypes": [
            {
                "name": "Castration-Sensitive Prostate Cancer",
                "short_name": "CSPC",
                "description": "Hormone-sensitive prostate cancer; ADT-responsive.",
                "markers": ["AR", "PSA"],
                "chembl_indication_terms": ["hormone sensitive prostate cancer", "castration sensitive prostate"],
            },
            {
                "name": "Castration-Resistant Prostate Cancer",
                "short_name": "CRPC",
                "description": "Progressed despite ADT; AR-pathway and PARP inhibitors used.",
                "markers": ["AR-V7", "BRCA2"],
                "chembl_indication_terms": ["castration resistant prostate cancer", "metastatic CRPC"],
            },
        ],
    },
    {
        "name": "Ovarian cancer",
        "display_name": "Ovarian",
        "category": "Solid tumor",
        "mesh_id": "D010051",
        "icon": "circle.grid.2x2.fill",
        "sort_order": 80,
        "description": "Malignancies of the ovary; high-grade serous most common.",
        "subtypes": [
            {
                "name": "High-Grade Serous Ovarian Carcinoma",
                "short_name": "HGSOC",
                "description": "Most common ovarian cancer; TP53-mutant, often BRCA-deficient.",
                "markers": ["TP53", "BRCA1/2", "HRD"],
                "chembl_indication_terms": ["high grade serous ovarian", "serous ovarian carcinoma"],
            },
            {
                "name": "BRCA-Mutant Ovarian Cancer",
                "short_name": "BRCA-mut",
                "description": "BRCA1/2-mutant ovarian cancer; PARP-inhibitor sensitive.",
                "markers": ["BRCA1", "BRCA2"],
                "chembl_indication_terms": ["BRCA mutant ovarian cancer"],
            },
        ],
    },
    {
        "name": "Bladder cancer",
        "display_name": "Bladder",
        "category": "Solid tumor",
        "mesh_id": "D001749",
        "icon": "drop.fill",
        "sort_order": 90,
        "description": "Urothelial malignancies of the bladder.",
        "subtypes": [
            {
                "name": "Urothelial Carcinoma",
                "short_name": "Urothelial",
                "description": "Most common bladder cancer; FGFR3-mutant subset targetable.",
                "markers": ["FGFR3", "PD-L1"],
                "chembl_indication_terms": ["urothelial carcinoma", "transitional cell bladder"],
            },
            {
                "name": "Muscle-Invasive Bladder Cancer",
                "short_name": "MIBC",
                "description": "Bladder cancer invading muscularis propria; cisplatin-based therapy.",
                "markers": ["TP53", "RB1"],
                "chembl_indication_terms": ["muscle invasive bladder cancer"],
            },
        ],
    },
    {
        "name": "Gastric cancer",
        "display_name": "Stomach",
        "category": "Solid tumor",
        "mesh_id": "D013274",
        "icon": "oval.fill",
        "sort_order": 100,
        "description": "Malignancies of the stomach; HER2/CLDN18.2 subtypes targetable.",
        "subtypes": [
            {
                "name": "HER2-Positive Gastric Cancer",
                "short_name": "HER2+ Gastric",
                "description": "HER2-overexpressing gastric cancer; trastuzumab-eligible.",
                "markers": ["HER2+"],
                "chembl_indication_terms": ["HER2 positive gastric"],
            },
            {
                "name": "Gastric Adenocarcinoma",
                "short_name": "Adeno",
                "description": "Most common gastric cancer histology.",
                "markers": ["CDH1", "CLDN18.2"],
                "chembl_indication_terms": ["gastric adenocarcinoma", "stomach adenocarcinoma"],
            },
        ],
    },
    {
        "name": "Hepatocellular carcinoma",
        "display_name": "Liver",
        "category": "Solid tumor",
        "mesh_id": "D006528",
        "icon": "leaf.fill",
        "sort_order": 110,
        "description": "Primary liver cancer arising from hepatocytes.",
        "subtypes": [
            {
                "name": "Hepatocellular Carcinoma",
                "short_name": "HCC",
                "description": "Primary liver cancer; multikinase and checkpoint therapies used.",
                "markers": ["AFP", "CTNNB1"],
                "chembl_indication_terms": ["hepatocellular carcinoma", "liver cell carcinoma"],
            },
        ],
    },
    {
        "name": "Glioma",
        "display_name": "Brain (Glioma)",
        "category": "Solid tumor",
        "mesh_id": "D005910",
        "icon": "brain.head.profile",
        "sort_order": 120,
        "description": "Primary CNS tumors arising from glial cells.",
        "subtypes": [
            {
                "name": "Glioblastoma",
                "short_name": "GBM",
                "description": "Most aggressive primary brain tumor; IDH-wildtype.",
                "markers": ["IDH-WT", "MGMT", "EGFR"],
                "chembl_indication_terms": ["glioblastoma", "glioblastoma multiforme"],
            },
            {
                "name": "Lower-Grade Glioma",
                "short_name": "LGG",
                "description": "WHO grade 2-3 gliomas; IDH-mutant subset has better prognosis.",
                "markers": ["IDH1/2", "1p/19q codel"],
                "chembl_indication_terms": ["lower grade glioma", "anaplastic glioma"],
            },
        ],
    },
    {
        "name": "Acute myeloid leukemia",
        "display_name": "AML",
        "category": "Hematologic",
        "mesh_id": "D015470",
        "icon": "drop.degreesign.fill",
        "sort_order": 200,
        "description": "Aggressive blood cancer of myeloid lineage.",
        "subtypes": [
            {
                "name": "FLT3-Mutant AML",
                "short_name": "FLT3+",
                "description": "FLT3-ITD/TKD AML; midostaurin/gilteritinib targetable.",
                "markers": ["FLT3-ITD", "FLT3-TKD"],
                "chembl_indication_terms": ["FLT3 mutant acute myeloid leukemia"],
            },
            {
                "name": "IDH-Mutant AML",
                "short_name": "IDH+",
                "description": "IDH1/2-mutant AML; ivosidenib/enasidenib targetable.",
                "markers": ["IDH1", "IDH2"],
                "chembl_indication_terms": ["IDH mutant acute myeloid leukemia"],
            },
        ],
    },
    {
        "name": "Chronic lymphocytic leukemia",
        "display_name": "CLL",
        "category": "Hematologic",
        "mesh_id": "D015451",
        "icon": "drop.halffull",
        "sort_order": 210,
        "description": "Indolent B-cell leukemia; BTK/BCL2 inhibitor responsive.",
        "subtypes": [
            {
                "name": "CLL (Treatment-Naive)",
                "short_name": "CLL-TN",
                "description": "Newly diagnosed CLL; BTK inhibitors first-line.",
                "markers": ["IGHV", "del(13q)"],
                "chembl_indication_terms": ["chronic lymphocytic leukemia"],
            },
            {
                "name": "Relapsed/Refractory CLL",
                "short_name": "R/R CLL",
                "description": "Relapsed CLL; venetoclax + obinutuzumab combinations used.",
                "markers": ["TP53", "del(17p)"],
                "chembl_indication_terms": ["relapsed chronic lymphocytic leukemia"],
            },
        ],
    },
    {
        "name": "Hodgkin lymphoma",
        "display_name": "Hodgkin",
        "category": "Hematologic",
        "mesh_id": "D006689",
        "icon": "circle.hexagonpath.fill",
        "sort_order": 220,
        "description": "B-cell lymphoma with Reed-Sternberg cells; highly curable.",
        "subtypes": [
            {
                "name": "Classical Hodgkin Lymphoma",
                "short_name": "cHL",
                "description": "Most common Hodgkin subtype; CD30+, brentuximab vedotin targetable.",
                "markers": ["CD30", "PD-L1"],
                "chembl_indication_terms": ["classical Hodgkin lymphoma", "Hodgkin disease"],
            },
        ],
    },
    {
        "name": "Non-Hodgkin lymphoma",
        "display_name": "NHL",
        "category": "Hematologic",
        "mesh_id": "D008228",
        "icon": "rectangle.stack.fill",
        "sort_order": 230,
        "description": "Diverse B/T-cell lymphomas excluding Hodgkin.",
        "subtypes": [
            {
                "name": "Diffuse Large B-Cell Lymphoma",
                "short_name": "DLBCL",
                "description": "Aggressive B-cell NHL; R-CHOP standard, CAR-T for R/R.",
                "markers": ["CD20", "MYC", "BCL2"],
                "chembl_indication_terms": ["diffuse large B-cell lymphoma"],
            },
            {
                "name": "Follicular Lymphoma",
                "short_name": "FL",
                "description": "Indolent B-cell NHL; t(14;18)/BCL2-driven.",
                "markers": ["CD20", "BCL2", "t(14;18)"],
                "chembl_indication_terms": ["follicular lymphoma"],
            },
        ],
    },
]


def seed_cancer_taxonomy(conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Idempotently upsert the curated cancer taxonomy into cancer_types and
    cancer_subtypes. Safe to re-run: existing rows are updated with the latest
    curated metadata; new rows are inserted.

    Returns a dict with the count of types and subtypes seeded.
    """
    cursor = conn.cursor()
    types_upserted = 0
    subtypes_upserted = 0

    for type_def in CANCER_TAXONOMY:
        cursor.execute(
            """
            INSERT INTO cancer_types (name, display_name, category, description, mesh_id, icon, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                description = excluded.description,
                mesh_id = excluded.mesh_id,
                icon = excluded.icon,
                sort_order = excluded.sort_order
            """,
            (
                type_def["name"],
                type_def.get("display_name"),
                type_def.get("category"),
                type_def.get("description"),
                type_def.get("mesh_id"),
                type_def.get("icon"),
                type_def.get("sort_order", 100),
            ),
        )
        types_upserted += 1

        cursor.execute("SELECT id FROM cancer_types WHERE name = ?", (type_def["name"],))
        type_row = cursor.fetchone()
        if not type_row:
            continue
        type_id = type_row[0]

        for subtype in type_def.get("subtypes", []):
            markers_json = json.dumps(subtype.get("markers", []))
            terms_json = json.dumps(subtype.get("chembl_indication_terms", []))
            cursor.execute(
                """
                INSERT INTO cancer_subtypes (
                    cancer_type_id, name, short_name, description, mesh_id,
                    efo_id, chembl_indication_terms, markers, prevalence_note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cancer_type_id, name) DO UPDATE SET
                    short_name = excluded.short_name,
                    description = excluded.description,
                    mesh_id = excluded.mesh_id,
                    efo_id = excluded.efo_id,
                    chembl_indication_terms = excluded.chembl_indication_terms,
                    markers = excluded.markers,
                    prevalence_note = excluded.prevalence_note
                """,
                (
                    type_id,
                    subtype["name"],
                    subtype.get("short_name"),
                    subtype.get("description"),
                    subtype.get("mesh_id"),
                    subtype.get("efo_id"),
                    terms_json,
                    markers_json,
                    subtype.get("prevalence_note"),
                ),
            )
            subtypes_upserted += 1

    conn.commit()
    return {"types": types_upserted, "subtypes": subtypes_upserted}


if __name__ == "__main__":
    from data_loader import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    result = seed_cancer_taxonomy(conn)
    conn.close()
    print(f"Seeded {result['types']} cancer types, {result['subtypes']} subtypes")
