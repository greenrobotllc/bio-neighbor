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

