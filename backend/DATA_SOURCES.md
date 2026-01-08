# Data Sources for Cancer Research Workspace

This document catalogs all data sources used in the BioNeighbor Cancer Research workspace, including API endpoints, authentication requirements, rate limits, and best practices.

## Primary Data Sources

### 1. UniProt REST API

**Base URL**: `https://rest.uniprot.org`

**Purpose**: Target protein information (gene symbols, protein names, functions, cellular locations)

**Endpoints Used**:
- `GET /uniprotkb/{uniprot_id}.json` - Get protein information by UniProt ID

**Authentication**: None required (public API)

**Rate Limits**: 
- No official rate limit, but be respectful
- Recommended: 1 request per second
- Use retry logic with exponential backoff

**Data Retrieved**:
- Gene symbol
- Protein name
- Function description
- Cellular location
- Additional annotations

**Implementation**: `backend/target_loader.py::fetch_uniprot_target()`

**Fallback Strategy**: Use hardcoded target definitions if API fails

---

### 2. IUPHAR Guide to Pharmacology

**Base URL**: `https://www.guidetopharmacology.org/services`

**Purpose**: Pharmacology data for targets, ligand-target interactions

**Endpoints Used**:
- Target information by UniProt ID
- Ligand interaction data

**Authentication**: None required (public API)

**Rate Limits**: 
- No official rate limit
- Recommended: 1 request per second

**Data Retrieved**:
- Ligand types (agonist, antagonist, inhibitor)
- Pharmacology classifications
- Target-ligand relationships

**Implementation**: `backend/target_loader.py::fetch_iuphar_target()`

**Fallback Strategy**: Use UniProt data only if IUPHAR fails

---

### 3. ChEMBL Database

**API**: ChEMBL WebResource Client (`chembl_webresource_client`)

**Purpose**: Ligands, compounds, assays, and target-ligand activities

**Endpoints Used**:
- `activity.filter()` - Get activities (IC50, Ki, Kd, EC50) for targets
- `molecule.filter()` - Get molecule details by ChEMBL ID
- `target.filter()` - Find targets by UniProt ID or gene symbol
- `assay.filter()` - Get assays for targets

**Authentication**: None required (public API)

**Rate Limits**: 
- No strict rate limit, but API can be slow or unavailable
- Recommended: 2 second delay between requests
- Implement retry logic (3 attempts with exponential backoff)

**Data Retrieved**:
- Ligand structures (SMILES)
- Activity values (IC50, Ki, Kd, EC50)
- Assay descriptions and types
- Target-ligand relationships

**Implementation**: 
- `backend/ligand_loader.py::load_ligand_from_chembl()`
- `backend/assay_loader.py::load_assay_from_chembl()`

**Fallback Strategy**: Try PubChem if ChEMBL fails or is unavailable

**Known Issues**:
- ChEMBL API can be slow or temporarily unavailable
- Some targets may not have ChEMBL IDs directly mapped
- Requires `chembl_webresource_client` Python package

---

### 4. PubChem

**API**: PubChemPy library + REST API

**Base URLs**:
- REST API: `https://pubchem.ncbi.nlm.nih.gov/rest/pug`
- BioAssay API: `https://pubchem.ncbi.nlm.nih.gov/rest/pug/assay`

**Purpose**: Compound information, BioAssay data, SMILES structures

**Endpoints Used**:
- Compound information by CID
- BioAssay data by assay ID
- Structure data (SMILES)

**Authentication**: None required (public API)

**Rate Limits**: 
- 5 requests per second (official limit)
- Recommended: 200ms delay between requests
- Implement retry logic

**Data Retrieved**:
- Compound names and identifiers
- SMILES structures
- Molecular properties
- BioAssay results

**Implementation**: 
- `backend/ligand_loader.py::load_ligand_from_pubchem()`
- `backend/assay_loader.py::load_assay_from_pubchem()`

**Fallback Strategy**: Use ChEMBL as primary, PubChem as fallback

**Known Issues**:
- Rate limiting is enforced
- Some compounds may not have complete data
- Requires `pubchempy` Python package

---

### 5. Reactome

**Base URL**: `https://reactome.org/ContentService`

**Purpose**: Pathway data, cancer pathway associations

**Endpoints Used**:
- Pathway information for targets
- Cancer pathway mappings

**Authentication**: None required (public API)

**Rate Limits**: 
- No official rate limit
- Recommended: 1 request per second

**Data Retrieved**:
- Pathway associations
- Cancer-related pathway information

**Implementation**: `backend/cancer_mapping_loader.py::fetch_reactome_pathways_for_target()`

**Fallback Strategy**: Use curated cancer mappings if Reactome unavailable

**Status**: Partially integrated (curated mappings are primary source)

---

## Secondary/Curated Sources

### 6. Literature Curation

**Purpose**: Drug outcomes and cancer-mechanism mappings that require expert curation

**Data Types**:
- Drug outcomes (success, failure, mixed, partial_success)
- Cancer-mechanism activity levels (High, Moderate, Low)
- Evidence sources and notes

**Implementation**:
- `backend/drug_outcome_loader.py` - Curated drug outcomes
- `backend/cancer_mapping_loader.py` - Curated cancer-mechanism mappings

**Update Frequency**: Manual updates as new literature/evidence becomes available

**Expansion Strategy**: 
- Can be expanded with literature mining tools
- Clinical trial databases (ClinicalTrials.gov)
- FDA approval databases

---

## Data Loading Strategy

### Automatic Loading (On Initialization)

When a mechanism is initialized:
1. Mechanism definition loaded (hardcoded)
2. Target definitions loaded (hardcoded)
3. **ETL Triggered**: Fetches target details from UniProt/IUPHAR
4. **ETL Triggered**: Fetches ligands from ChEMBL/PubChem
5. **ETL Triggered**: Fetches assays from ChEMBL/PubChem
6. Curated drug outcomes loaded
7. Curated cancer mappings loaded
8. Reactome enrichment attempted (if available)

### Manual Refresh

Users can trigger data refresh via:
- API: `POST /cancer-research/mechanisms/<id>/load-data`
- Frontend: "Load Data" button (to be implemented)

### Incremental Updates

- Check if data exists before fetching (unless `force_refresh=True`)
- Update timestamps for tracking
- Skip existing records to minimize API calls

---

## Error Handling Best Practices

### API Failures

1. **Retry Logic**: 3 attempts with exponential backoff (1s, 2s, 4s)
2. **Graceful Degradation**: Continue with available data if one source fails
3. **Fallback Chain**: 
   - Targets: UniProt → IUPHAR → Hardcoded
   - Ligands: ChEMBL → PubChem → Skip
   - Assays: ChEMBL → PubChem → Skip

### Rate Limiting

1. **Delays Between Calls**: 
   - UniProt/IUPHAR: 1 second
   - ChEMBL: 2 seconds
   - PubChem: 200ms (respect 5 req/sec limit)

2. **Batch Processing**: Process targets sequentially to avoid overwhelming APIs

3. **Caching**: Store API responses to minimize redundant calls

### Data Validation

1. **Required Fields**: Validate before database insertion
2. **Skip Invalid Records**: Log errors but continue processing
3. **Report Validation Errors**: Include in ETL response

---

## Data Update Frequencies

| Source | Update Frequency | Notes |
|--------|-----------------|-------|
| UniProt | Daily | Protein data is relatively stable |
| IUPHAR | Monthly | Pharmacology data updates less frequently |
| ChEMBL | Weekly | New compounds and assays added regularly |
| PubChem | Daily | Large database with frequent updates |
| Reactome | Monthly | Pathway data is relatively stable |
| Literature Curation | Manual | Updated as new evidence becomes available |

---

## API Dependencies

### Python Packages Required

```python
# Core dependencies
requests          # HTTP client for REST APIs
pubchempy         # PubChem API client
chembl_webresource_client  # ChEMBL API client
```

### Installation

```bash
pip install requests pubchempy chembl-webresource-client
```

### Optional Dependencies

- `pandas` - For data manipulation (already in requirements)
- `rdkit` - For molecular structure processing (already in requirements)

---

## Rate Limiting Implementation

### Current Implementation

The ETL pipeline includes:
- Retry logic with exponential backoff (`cancer_research_etl.py::retry_api_call()`)
- Delays between API calls (built into loaders)
- Graceful error handling (continues if one source fails)

### Recommended Improvements

1. **Request Queuing**: Queue API requests to respect rate limits
2. **Caching Layer**: Cache API responses to reduce redundant calls
3. **Batch API Calls**: Where possible, use batch endpoints
4. **Async Processing**: Use async/await for parallel API calls (where rate limits allow)

---

## Data Quality Considerations

### Validation

- **UniProt IDs**: Validate format (e.g., P12345)
- **SMILES**: Validate chemical structure syntax
- **ChEMBL IDs**: Validate format (e.g., CHEMBL123)
- **PubChem CIDs**: Validate as integers

### Data Completeness

- Some targets may not have ChEMBL mappings
- Some ligands may not have SMILES structures
- Some assays may have incomplete metadata
- Drug outcomes rely on curated data (limited coverage)

### Data Accuracy

- API data is generally reliable but may contain errors
- Curated data is manually verified but may be incomplete
- Users should verify critical information from primary sources

---

## Troubleshooting

### Common Issues

1. **ChEMBL API Unavailable**
   - Symptom: Ligands/assays not loading
   - Solution: Falls back to PubChem or uses curated data
   - Check: ChEMBL service status

2. **Rate Limiting**
   - Symptom: 429 errors or timeouts
   - Solution: Increase delays between requests
   - Check: Respect API rate limits

3. **Missing ChEMBL Target IDs**
   - Symptom: No ligands found for target
   - Solution: Try PubChem or manual curation
   - Check: Target may not be in ChEMBL database

4. **UniProt API Slow**
   - Symptom: Target loading takes long time
   - Solution: Implement caching, use retry logic
   - Check: Network connectivity

---

## Future Enhancements

### Additional Data Sources

1. **ClinicalTrials.gov API**
   - Clinical trial data
   - Drug outcomes from trials
   - Status: Not yet integrated

2. **FDA Drug Database**
   - Approved drug information
   - Indications and outcomes
   - Status: Not yet integrated

3. **PubMed/PMC APIs**
   - Literature mining
   - Automated evidence extraction
   - Status: Not yet integrated

4. **TCGA (The Cancer Genome Atlas)**
   - Cancer genomics data
   - Expression data
   - Status: Not yet integrated

### ETL Improvements

1. **Incremental Updates**: Only fetch new/changed data
2. **Parallel Processing**: Load multiple targets simultaneously
3. **Progress Webhooks**: Real-time progress updates via WebSocket
4. **Data Validation Pipeline**: Automated quality checks

---

## Contact and Support

For issues with data sources or ETL pipeline:
- Check API status pages
- Review error logs in backend console
- Verify network connectivity
- Check API rate limit compliance
