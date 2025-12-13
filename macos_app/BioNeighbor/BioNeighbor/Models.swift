//
//  Models.swift
//  BioNeighbor
//
//  Data models for BioNeighbor app
//

import Foundation

struct Molecule: Codable, Identifiable {
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
    let success: Bool
    let molecules: [MoleculeBasic]?
    let pagination: Pagination?
    let error: String?
}

struct MoleculeBasic: Codable, Identifiable {
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
    let success: Bool
    let molecule: MoleculeBasic
    let similar: [Molecule]?
    let error: String?
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
    let diseases: [Disease]
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

struct Drug: Codable, Identifiable {
    let id: Int
    let name: String
    let genericName: String?
    let brandNames: [String]?
    let pubchemCid: String?
    let drugbankId: String?
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
        case description
        case indication
        case activeIngredientMoleculeIndices = "active_ingredient_molecule_indices"
        case inactiveIngredients = "inactive_ingredients"
        case dosageForm = "dosage_form"
        case route
    }
}

struct DrugsResponse: Codable {
    let success: Bool
    let drugs: [Drug]?
    let error: String?
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

