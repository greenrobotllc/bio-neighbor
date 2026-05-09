//
//  Models.swift
//  BioNeighbor
//
//  Data models for BioNeighbor app
//

import Foundation

struct Molecule: Codable, Identifiable, Hashable {
    let id: Int
    let chemblId: String
    let name: String
    let smiles: String
    let similarity: Double
    let similarityScore: Double
    let molecularWeight: Double
    let isApproved: Bool
    let formula: String?
    
    enum CodingKeys: String, CodingKey {
        case id = "index"
        case chemblId = "chembl_id"
        case name
        case smiles
        case similarity
        case similarityScore = "similarity_score"
        case molecularWeight = "molecular_weight"
        case isApproved = "is_approved"
        case formula
    }
}

struct SearchResponse: Codable {
    let success: Bool
    let results: [Molecule]?
    let querySmiles: String?
    let topK: Int?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case results
        case querySmiles = "query_smiles"
        case topK = "top_k"
        case error
    }
}

struct SearchRequest: Codable {
    let querySmiles: String
    let topK: Int
    
    enum CodingKeys: String, CodingKey {
        case querySmiles = "query_smiles"
        case topK = "top_k"
    }
}

struct MoleculeDetail: Codable {
    let index: Int
    let chemblId: String
    let name: String
    let smiles: String
    let molecularWeight: Double
    let isApproved: Bool
    
    enum CodingKeys: String, CodingKey {
        case index
        case chemblId = "chembl_id"
        case name
        case smiles
        case molecularWeight = "molecular_weight"
        case isApproved = "is_approved"
    }
}

struct Pagination: Codable {
    let page: Int
    let perPage: Int
    let total: Int
    let totalPages: Int
    
    enum CodingKeys: String, CodingKey {
        case page
        case perPage = "per_page"
        case total
        case totalPages = "total_pages"
    }
}

struct MoleculeListResponse: Codable {
    let success: Bool?
    let molecules: [MoleculeBasic]?
    let pagination: Pagination?
    let error: String?
    
    var isSuccess: Bool {
        success ?? (molecules != nil)
    }
}

struct MoleculeBasic: Codable, Identifiable, Hashable {
    let id: Int
    let chemblId: String
    let name: String
    let smiles: String
    let molecularWeight: Double
    let isApproved: Bool
    let formula: String?
    
    enum CodingKeys: String, CodingKey {
        case id = "index"
        case chemblId = "chembl_id"
        case name
        case smiles
        case molecularWeight = "molecular_weight"
        case isApproved = "is_approved"
        case formula
    }
}

struct MoleculeWithSimilar: Codable {
    let molecule: MoleculeBasic
    let similar: [Molecule]
}

struct MoleculeWithSimilarResponse: Codable {
    let success: Bool?
    let molecule: MoleculeBasic?
    let similar: [Molecule]?
    let error: String?
    
    var isSuccess: Bool {
        success ?? (molecule != nil)
    }
}

struct Atom3D: Codable {
    let symbol: String
    let x: Double
    let y: Double
    let z: Double
    let index: Int
}

struct Bond3D: Codable {
    let atom1: Int
    let atom2: Int
    let order: Int
}

struct Molecule3DCoordinates: Codable {
    let atoms: [Atom3D]
    let bonds: [Bond3D]
    let smiles: String
}

struct Molecule3DResponse: Codable {
    let success: Bool
    let atoms: [Atom3D]?
    let bonds: [Bond3D]?
    let smiles: String?
    let error: String?
}

struct Disease: Codable, Identifiable {
    let id: Int
    let name: String
    let meshId: String?
    let description: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case meshId = "mesh_id"
        case description
    }
}

struct DiseasesResponse: Codable {
    let success: Bool
    let diseases: [Disease]?
    let error: String?
}

struct DiseaseMoleculesResponse: Codable {
    let success: Bool
    let disease: String
    let molecules: [MoleculeBasic]?
    let count: Int?
    let error: String?
}

struct DiseaseSearchResponse: Codable {
    let success: Bool
    let disease: String
    let results: [Molecule]?
    let count: Int?
    let error: String?
}

/// One row in /search/drugs response — supports the live ChEMBL fallback
/// where the same payload may carry locally-cached and ChEMBL-fetched rows
/// distinguished by `source`.
struct DrugSearchResult: Codable, Identifiable, Hashable {
    /// DB primary key when available (local rows), nil for ChEMBL-only rows
    /// that haven't been cached yet. Use this when you specifically need the
    /// numeric drug id for navigation.
    let localId: Int?
    let name: String
    let genericName: String?
    let brandNames: [String]?
    let chemblId: String?
    let maxPhase: Int?
    let source: String  // "local" | "chembl"

    /// Stable, non-optional Identifiable id — chembl id when present, else a
    /// composite that's deterministic across renders. Do NOT use this for
    /// navigation; use `localId` or `chemblId` directly.
    var id: String {
        if let chemblId, !chemblId.isEmpty { return "chembl:\(chemblId)" }
        if let localId { return "local:\(localId)" }
        return "result:\(source)|\(name)"
    }

    enum CodingKeys: String, CodingKey {
        case localId = "id"
        case name
        case genericName = "generic_name"
        case brandNames = "brand_names"
        case chemblId = "chembl_id"
        case maxPhase = "max_phase"
        case source
    }
}

struct DrugSearchEnvelope: Codable {
    let success: Bool
    let query: String?
    let results: [DrugSearchResult]?
    let chemblUsed: Bool?
    let chemblInserted: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case query
        case results
        case chemblUsed = "chembl_used"
        case chemblInserted = "chembl_inserted"
        case error
    }
}

struct Drug: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let genericName: String?
    let brandNames: [String]?
    let pubchemCid: String?
    let drugbankId: String?
    let chemblId: String?
    let description: String?
    let indication: String?
    let activeIngredientMoleculeIndices: [Int]?
    let inactiveIngredients: [String]?
    let dosageForm: String?
    let route: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case genericName = "generic_name"
        case brandNames = "brand_names"
        case pubchemCid = "pubchem_cid"
        case drugbankId = "drugbank_id"
        case chemblId = "chembl_id"
        case description
        case indication
        case activeIngredientMoleculeIndices = "active_ingredient_molecule_indices"
        case inactiveIngredients = "inactive_ingredients"
        case dosageForm = "dosage_form"
        case route
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        genericName = try container.decodeIfPresent(String.self, forKey: .genericName)
        brandNames = try container.decodeIfPresent([String].self, forKey: .brandNames)
        pubchemCid = try container.decodeIfPresent(String.self, forKey: .pubchemCid)
        drugbankId = try container.decodeIfPresent(String.self, forKey: .drugbankId)
        chemblId = try container.decodeIfPresent(String.self, forKey: .chemblId)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        indication = try container.decodeIfPresent(String.self, forKey: .indication)
        inactiveIngredients = try container.decodeIfPresent([String].self, forKey: .inactiveIngredients)
        dosageForm = try container.decodeIfPresent(String.self, forKey: .dosageForm)
        route = try container.decodeIfPresent(String.self, forKey: .route)
        
        // Handle active_ingredient_molecule_indices which may contain null values
        if let indicesArray = try? container.decodeIfPresent([Int?].self, forKey: .activeIngredientMoleculeIndices) {
            // Filter out nil values and convert to [Int]
            activeIngredientMoleculeIndices = indicesArray.compactMap { $0 }
        } else if let indicesArray = try? container.decodeIfPresent([Int].self, forKey: .activeIngredientMoleculeIndices) {
            // If it's already [Int], use it directly
            activeIngredientMoleculeIndices = indicesArray
        } else {
            // If decoding fails or field is missing, set to nil
            activeIngredientMoleculeIndices = nil
        }
    }
    
    // Explicit initializer for manual creation (e.g., in previews)
    init(
        id: Int,
        name: String,
        genericName: String? = nil,
        brandNames: [String]? = nil,
        pubchemCid: String? = nil,
        drugbankId: String? = nil,
        chemblId: String? = nil,
        description: String? = nil,
        indication: String? = nil,
        activeIngredientMoleculeIndices: [Int]? = nil,
        inactiveIngredients: [String]? = nil,
        dosageForm: String? = nil,
        route: String? = nil
    ) {
        self.id = id
        self.name = name
        self.genericName = genericName
        self.brandNames = brandNames
        self.pubchemCid = pubchemCid
        self.drugbankId = drugbankId
        self.chemblId = chemblId
        self.description = description
        self.indication = indication
        self.activeIngredientMoleculeIndices = activeIngredientMoleculeIndices
        self.inactiveIngredients = inactiveIngredients
        self.dosageForm = dosageForm
        self.route = route
    }
}

struct DrugsResponse: Codable {
    let success: Bool?
    let drugs: [Drug]?
    let error: String?
    
    var isSuccess: Bool {
        success ?? (drugs != nil)
    }
}

struct DrugResponse: Codable {
    let success: Bool
    let drug: Drug?
    let error: String?
}

struct DiseaseDrugsResponse: Codable {
    let success: Bool
    let disease: String
    let drugs: [Drug]?
    let molecules: [MoleculeBasic]?
    let count: Int?
    let error: String?
}

struct DrugMoleculesResponse: Codable {
    let success: Bool
    let drug: Drug?
    let molecules: [MoleculeBasic]?
    let error: String?
}

struct DatabaseStats: Codable {
    let molecules: Int
    let drugs: Int
    let diseases: Int
    let relationships: Int
}

struct StatsResponse: Codable {
    let success: Bool
    let stats: DatabaseStats?
    let error: String?
}

struct DownloadMoleculesRequest: Codable {
    let count: Int?
    let source: String?
    let names: [String]?
    let fullFile: Bool?
    
    enum CodingKeys: String, CodingKey {
        case count
        case source
        case names
        case fullFile = "full_file"
    }
}

struct DownloadDrugsRequest: Codable {
    let names: [String]?
    let disease: String?
    let count: Int?
    let bulk: Bool?
}

struct DownloadDiseasesRequest: Codable {
    let names: [String]?
    let count: Int?
}

struct DownloadResponse: Codable {
    let success: Bool
    let message: String?
    let taskId: String?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case message
        case taskId = "task_id"
        case error
    }
}

struct SearchResult: Codable, Identifiable, Equatable {
    let id: Int
    let name: String
    let chemblId: String?
    let smiles: String?
    let genericName: String?
    let brandNames: [String]?
    let meshId: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case chemblId = "chembl_id"
        case smiles
        case genericName = "generic_name"
        case brandNames = "brand_names"
        case meshId = "mesh_id"
    }
}

struct AutocompleteResponse: Codable {
    let success: Bool
    let results: [SearchResult]?
    let error: String?
}

struct APIProgressInfo: Codable {
    let taskId: String?
    let status: String?
    let message: String?
    let timestamp: Double?
    let details: ProgressDetails?
    
    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case message
        case timestamp
        case details
    }
}

struct ProgressDetails: Codable {
    let currentDisease: String?
    let diseaseIndex: Int?
    let totalDiseases: Int?
    let progressPercent: Double?
    let drugsFound: Int?
    let drugsLoaded: Int?
    let totalDrugs: Int?
    let loadProgressPercent: Double?
    let drugsSaved: Int?
    let relationshipsCreated: Int?
    let stage: String?
    let totalTime: Double?
    
    enum CodingKeys: String, CodingKey {
        case currentDisease = "current_disease"
        case diseaseIndex = "disease_index"
        case totalDiseases = "total_diseases"
        case progressPercent = "progress_percent"
        case drugsFound = "drugs_found"
        case drugsLoaded = "drugs_loaded"
        case totalDrugs = "total_drugs"
        case loadProgressPercent = "load_progress_percent"
        case drugsSaved = "drugs_saved"
        case relationshipsCreated = "relationships_created"
        case stage
        case totalTime = "total_time"
    }
}

struct DownloadStatusResponse: Codable {
    let success: Bool
    let running: Bool?
    let exitCode: Int?
    let message: String?
    let error: String?
    let progress: APIProgressInfo?
    
    enum CodingKeys: String, CodingKey {
        case success
        case running
        case exitCode = "exit_code"
        case message
        case error
        case progress
    }
}

// MARK: - Bond Analysis Models

struct AtomDetail: Codable {
    let index: Int
    let symbol: String
    let atomicNum: Int
    let formalCharge: Int
    let hybridization: String
    let isAromatic: Bool
    let degree: Int
    let totalValence: Int
    let numHydrogens: Int
    let isInRing: Bool
    let chiralTag: String
    
    enum CodingKeys: String, CodingKey {
        case index
        case symbol
        case atomicNum = "atomic_num"
        case formalCharge = "formal_charge"
        case hybridization
        case isAromatic = "is_aromatic"
        case degree
        case totalValence = "total_valence"
        case numHydrogens = "num_hydrogens"
        case isInRing = "is_in_ring"
        case chiralTag = "chiral_tag"
    }
}

struct BondDetail: Codable {
    let atom1: Int
    let atom2: Int
    let order: Int
    let isAromatic: Bool
    let isInRing: Bool
    let bondType: String
    let stereo: String
    
    enum CodingKeys: String, CodingKey {
        case atom1
        case atom2
        case order
        case isAromatic = "is_aromatic"
        case isInRing = "is_in_ring"
        case bondType = "bond_type"
        case stereo
    }
}

struct MoleculeBondData: Codable {
    let atoms: [AtomDetail]
    let bonds: [BondDetail]
    let smiles: String
}

struct MoleculeBondDataResponse: Codable {
    let success: Bool
    let atoms: [AtomDetail]?
    let bonds: [BondDetail]?
    let smiles: String?
    let error: String?
}

struct FunctionalGroup: Codable, Identifiable, Equatable {
    let id: UUID
    let type: String
    let atoms: [Int]
    let description: String
    
    init(type: String, atoms: [Int], description: String) {
        self.id = UUID()
        self.type = type
        self.atoms = atoms
        self.description = description
    }
    
    enum CodingKeys: String, CodingKey {
        case type
        case atoms
        case description
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.type = try container.decode(String.self, forKey: .type)
        self.atoms = try container.decode([Int].self, forKey: .atoms)
        self.description = try container.decode(String.self, forKey: .description)
    }
}

struct FunctionalGroupsResponse: Codable {
    let success: Bool
    let functionalGroups: [FunctionalGroup]?
    let smiles: String?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case functionalGroups = "functional_groups"
        case smiles
        case error
    }
}

struct ScaffoldComparison: Codable {
    let mcsSmiles: String
    let mcsSmarts: String
    let numAtoms: Int
    let numBonds: Int
    let atomMapping1: [String: Int]
    let atomMapping2: [String: Int]
    let bondMapping1: [String: Int]
    let bondMapping2: [String: Int]
    let sharedAtoms1: [Int]
    let sharedAtoms2: [Int]
    let sharedBonds1: [Int]
    let sharedBonds2: [Int]
    
    enum CodingKeys: String, CodingKey {
        case mcsSmiles = "mcs_smiles"
        case mcsSmarts = "mcs_smarts"
        case numAtoms = "num_atoms"
        case numBonds = "num_bonds"
        case atomMapping1 = "atom_mapping_1"
        case atomMapping2 = "atom_mapping_2"
        case bondMapping1 = "bond_mapping_1"
        case bondMapping2 = "bond_mapping_2"
        case sharedAtoms1 = "shared_atoms_1"
        case sharedAtoms2 = "shared_atoms_2"
        case sharedBonds1 = "shared_bonds_1"
        case sharedBonds2 = "shared_bonds_2"
    }
}

struct MoleculeComparisonResponse: Codable {
    let success: Bool
    let molecule1: MoleculeBondData?
    let molecule2: MoleculeBondData?
    let mcs: ScaffoldComparison?
    let functionalGroups1: [FunctionalGroup]?
    let functionalGroups2: [FunctionalGroup]?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case molecule1
        case molecule2
        case mcs
        case functionalGroups1 = "functional_groups_1"
        case functionalGroups2 = "functional_groups_2"
        case error
    }
}

struct CompareMoleculesRequest: Codable {
    let smiles1: String?
    let smiles2: String?
    let index1: Int?
    let index2: Int?
}

// MARK: - Treatment Auditor RxNorm normalization (issue #55)

/// One row of RxNorm-normalized output from
/// `/cancer-research/v2/treatment-auditor/normalize-drugs`. The Treatment
/// Auditor uses `groupKey` to dedupe brand-vs-generic entries before
/// fanning out per-drug fetches; `ingredientName` drives the "merged"
/// callout in the UI.
struct DrugNormalization: Codable, Hashable {
    let inputName: String
    let inputChemblId: String?
    let rxcui: String?
    let normalizedName: String?
    let ingredientRxcui: String?
    let ingredientName: String?
    let matched: Bool
    /// Stable dedupe key: `rxcui:<ingredientRxcui>` when matched, else
    /// `name:<lowercased input>` so unmatched names still render as their
    /// own row instead of all collapsing together.
    let groupKey: String

    enum CodingKeys: String, CodingKey {
        case inputName = "input_name"
        case inputChemblId = "input_chembl_id"
        case rxcui
        case normalizedName = "normalized_name"
        case ingredientRxcui = "ingredient_rxcui"
        case ingredientName = "ingredient_name"
        case matched
        case groupKey = "group_key"
    }
}

struct DrugNormalizationRequestEntry: Codable {
    let name: String
    let chemblId: String?

    enum CodingKeys: String, CodingKey {
        case name
        case chemblId = "chembl_id"
    }
}

struct DrugNormalizationRequest: Codable {
    let drugs: [DrugNormalizationRequestEntry]
}

struct DrugNormalizationResponse: Codable {
    let success: Bool
    let normalizations: [DrugNormalization]?
    let error: String?
}

// MARK: - Treatment Auditor DDInter pairwise interactions (issue #47)

/// One pairwise drug-drug interaction returned from
/// `/cancer-research/v2/treatment-auditor/drug-interactions`. Severity is
/// `"major" | "moderate" | "minor" | nil` (curated by DDInter). The drug
/// IDs are DDInter IDs (e.g. "DDInter576"). `description` is currently
/// unused — DDInter v1 has no per-pair free text — but is kept for the
/// wire-format shape.
struct DrugInteraction: Codable, Hashable, Identifiable {
    let drugAId: String
    let drugAName: String
    let drugBId: String
    let drugBName: String
    let description: String?
    let severity: String?

    /// Stable id for SwiftUI list rendering. The pair (a_id, b_id) is
    /// unique across the table by virtue of the UNIQUE constraint.
    var id: String { "\(drugAId)::\(drugBId)" }

    enum CodingKeys: String, CodingKey {
        case drugAId = "drug_a_id"
        case drugAName = "drug_a_name"
        case drugBId = "drug_b_id"
        case drugBName = "drug_b_name"
        case description
        case severity
    }
}

struct DrugInteractionMatch: Codable, Hashable {
    let inputName: String
    let ddinterId: String
    let ddinterName: String

    enum CodingKeys: String, CodingKey {
        case inputName = "input_name"
        case ddinterId = "ddinter_id"
        case ddinterName = "ddinter_name"
    }
}

struct DrugInteractionsResponse: Codable {
    let success: Bool
    /// Legacy field name preserved across the DrugBank → DDInter swap so
    /// older clients can still parse the response. Means "DDI data is
    /// loaded server-side."
    let drugbankLoaded: Bool?
    let matched: [DrugInteractionMatch]?
    let unmatched: [String]?
    let interactions: [DrugInteraction]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case drugbankLoaded = "drugbank_loaded"
        case matched
        case unmatched
        case interactions
        case error
    }
}

struct DrugInteractionsRequestEntry: Codable {
    let name: String
    let chemblId: String?

    enum CodingKeys: String, CodingKey {
        case name
        case chemblId = "chembl_id"
    }
}

struct DrugInteractionsRequest: Codable {
    let drugs: [DrugInteractionsRequestEntry]
}

// MARK: - Treatment Auditor target overlap (issue #53)

/// One mechanism-of-action target row for a drug. Returned per-drug in
/// the target-overlap response.
struct DrugTargetEntry: Codable, Hashable {
    let targetChemblId: String?
    let geneSymbol: String?
    let proteinName: String?
    let actionType: String?
    let mechanismOfAction: String?

    enum CodingKeys: String, CodingKey {
        case targetChemblId = "target_chembl_id"
        case geneSymbol = "gene_symbol"
        case proteinName = "protein_name"
        case actionType = "action_type"
        case mechanismOfAction = "mechanism_of_action"
    }
}

struct DrugTargetsByDrug: Codable, Hashable, Identifiable {
    let name: String
    let chemblId: String?
    let targets: [DrugTargetEntry]

    var id: String { chemblId ?? name }

    enum CodingKeys: String, CodingKey {
        case name
        case chemblId = "chembl_id"
        case targets
    }
}

/// One pair of drugs sharing one or more mechanism-of-action targets.
struct DrugTargetOverlap: Codable, Hashable, Identifiable {
    let drugA: String
    let drugB: String
    let sharedTargets: [SharedTarget]

    var id: String { "\(drugA)::\(drugB)" }

    struct SharedTarget: Codable, Hashable {
        let targetChemblId: String?
        let geneSymbol: String?
        let proteinName: String?
        let mechanismOfAction: String?
        let actionTypeA: String?
        let actionTypeB: String?

        enum CodingKeys: String, CodingKey {
            case targetChemblId = "target_chembl_id"
            case geneSymbol = "gene_symbol"
            case proteinName = "protein_name"
            case mechanismOfAction = "mechanism_of_action"
            case actionTypeA = "action_type_a"
            case actionTypeB = "action_type_b"
        }
    }

    enum CodingKeys: String, CodingKey {
        case drugA = "drug_a"
        case drugB = "drug_b"
        case sharedTargets = "shared_targets"
    }
}

struct TargetOverlapResponse: Codable {
    let success: Bool
    let targetsByDrug: [DrugTargetsByDrug]?
    let unmatched: [String]?
    let overlaps: [DrugTargetOverlap]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case targetsByDrug = "targets_by_drug"
        case unmatched
        case overlaps
        case error
    }
}

struct TargetOverlapRequestEntry: Codable {
    let name: String
    let chemblId: String?

    enum CodingKeys: String, CodingKey {
        case name
        case chemblId = "chembl_id"
    }
}

struct TargetOverlapRequest: Codable {
    let drugs: [TargetOverlapRequestEntry]
}

// MARK: - Treatment Auditor FAERS adverse events (issue #46)

struct FAERSEvent: Codable, Hashable {
    let term: String
    let count: Int
}

struct FAERSDrugPanel: Codable, Hashable, Identifiable {
    let drugName: String
    let totalReports: Int
    let topEvents: [FAERSEvent]

    var id: String { drugName }

    enum CodingKeys: String, CodingKey {
        case drugName = "drug_name"
        case totalReports = "total_reports"
        case topEvents = "top_events"
    }
}

struct FAERSSymptomMatch: Codable, Hashable, Identifiable {
    let drugName: String
    let symptom: String
    let matchedTerm: String
    let count: Int
    let rankInTop: Int?
    let totalReports: Int

    var id: String { "\(drugName)::\(symptom)::\(matchedTerm)" }

    enum CodingKeys: String, CodingKey {
        case drugName = "drug_name"
        case symptom
        case matchedTerm = "matched_term"
        case count
        case rankInTop = "rank_in_top"
        case totalReports = "total_reports"
    }
}

struct FAERSResponse: Codable {
    let success: Bool
    let perDrug: [FAERSDrugPanel]?
    let symptomMatches: [FAERSSymptomMatch]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case perDrug = "per_drug"
        case symptomMatches = "symptom_matches"
        case error
    }
}

struct FAERSRequestDrug: Codable {
    let name: String
    let chemblId: String?

    enum CodingKeys: String, CodingKey {
        case name
        case chemblId = "chembl_id"
    }
}

struct FAERSRequest: Codable {
    let drugs: [FAERSRequestDrug]
    let symptoms: [String]
}

