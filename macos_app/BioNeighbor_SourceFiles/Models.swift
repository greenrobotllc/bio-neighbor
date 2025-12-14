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
    
    enum CodingKeys: String, CodingKey {
        case id = "index"
        case chemblId = "chembl_id"
        case name
        case smiles
        case similarity
        case similarityScore = "similarity_score"
        case molecularWeight = "molecular_weight"
        case isApproved = "is_approved"
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

