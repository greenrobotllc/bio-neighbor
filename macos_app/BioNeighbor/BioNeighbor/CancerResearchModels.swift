//
//  CancerResearchModels.swift
//  BioNeighbor
//
//  Data models for Cancer Mechanism Research Workspace
//

import Foundation

// MARK: - Mechanism

struct Mechanism: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let description: String?
    let biologicalSummary: String?
    let tumorMicroenvironmentRole: String?
    let immuneEffects: String?
    let dataSources: [String]?
    let createdAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case biologicalSummary = "biological_summary"
        case tumorMicroenvironmentRole = "tumor_microenvironment_role"
        case immuneEffects = "immune_effects"
        case dataSources = "data_sources"
        case createdAt = "created_at"
    }
}

// MARK: - Target

struct Target: Codable, Identifiable, Hashable {
    let id: Int
    let uniprotId: String?
    let geneSymbol: String?
    let proteinName: String?
    let function: String?
    let cellularLocation: String?
    let cancerRole: String?
    let ligandTypes: [String]?
    let roleInMechanism: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case uniprotId = "uniprot_id"
        case geneSymbol = "gene_symbol"
        case proteinName = "protein_name"
        case function
        case cellularLocation = "cellular_location"
        case cancerRole = "cancer_role"
        case ligandTypes = "ligand_types"
        case roleInMechanism = "role_in_mechanism"
    }
}

// MARK: - Ligand

struct Ligand: Codable, Identifiable, Hashable {
    let id: Int
    let name: String?
    let smiles: String?
    let chemblId: String?
    let pubchemCid: String?
    let interactionType: String?
    let targetId: Int?
    let moleculeIndex: Int?
    let geneSymbol: String?
    let proteinName: String?
    let similarity: Double?
    let similarityScore: Double?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case smiles
        case chemblId = "chembl_id"
        case pubchemCid = "pubchem_cid"
        case interactionType = "interaction_type"
        case targetId = "target_id"
        case moleculeIndex = "molecule_index"
        case geneSymbol = "gene_symbol"
        case proteinName = "protein_name"
        case similarity
        case similarityScore = "similarity_score"
    }
}

// MARK: - Assay

struct Assay: Codable, Identifiable, Hashable {
    let id: Int
    let assayType: String?
    let targetId: Int?
    let readout: String?
    let limitations: String?
    let dataSource: String?
    let pubchemAssayId: String?
    let chemblAssayId: String?
    let createdAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case assayType = "assay_type"
        case targetId = "target_id"
        case readout
        case limitations
        case dataSource = "data_source"
        case pubchemAssayId = "pubchem_assay_id"
        case chemblAssayId = "chembl_assay_id"
        case createdAt = "created_at"
    }
}

// MARK: - Drug Outcome

struct DrugOutcome: Codable, Identifiable, Hashable {
    let id: Int
    let drugId: Int?
    let moleculeIndex: Int?
    let outcomeType: String  // partial_success/failure/mixed
    let context: String?
    let evidenceLevel: String?
    let notes: String?
    let createdAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case drugId = "drug_id"
        case moleculeIndex = "molecule_index"
        case outcomeType = "outcome_type"
        case context
        case evidenceLevel = "evidence_level"
        case notes
        case createdAt = "created_at"
    }
}

// MARK: - Cancer Mechanism Mapping

struct CancerMechanismMapping: Codable, Identifiable, Hashable {
    let id: Int
    let cancerType: String
    let mechanismId: Int
    let activityLevel: String?  // High/Moderate/Low
    let evidenceSource: String?
    let mechanismName: String?
    let createdAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case cancerType = "cancer_type"
        case mechanismId = "mechanism_id"
        case activityLevel = "activity_level"
        case evidenceSource = "evidence_source"
        case mechanismName = "mechanism_name"
        case createdAt = "created_at"
    }
}

// MARK: - Workspace

struct Workspace: Codable, Identifiable, Hashable {
    let id: Int
    let mechanismId: Int?
    let userId: String?
    let filters: [String: AnyCodable]?
    let selections: [String: AnyCodable]?
    let notes: String?
    let createdAt: String?
    let updatedAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case mechanismId = "mechanism_id"
        case userId = "user_id"
        case filters
        case selections
        case notes
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        mechanismId = try container.decodeIfPresent(Int.self, forKey: .mechanismId)
        userId = try container.decodeIfPresent(String.self, forKey: .userId)
        notes = try container.decodeIfPresent(String.self, forKey: .notes)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        
        // Decode filters and selections as dictionaries
        filters = try? container.decodeIfPresent([String: AnyCodable].self, forKey: .filters)
        selections = try? container.decodeIfPresent([String: AnyCodable].self, forKey: .selections)
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encodeIfPresent(mechanismId, forKey: .mechanismId)
        try container.encodeIfPresent(userId, forKey: .userId)
        try container.encodeIfPresent(notes, forKey: .notes)
        try container.encodeIfPresent(createdAt, forKey: .createdAt)
        try container.encodeIfPresent(updatedAt, forKey: .updatedAt)
        try container.encodeIfPresent(filters, forKey: .filters)
        try container.encodeIfPresent(selections, forKey: .selections)
    }
    
    static func == (lhs: Workspace, rhs: Workspace) -> Bool {
        return lhs.id == rhs.id &&
               lhs.mechanismId == rhs.mechanismId &&
               lhs.userId == rhs.userId &&
               lhs.notes == rhs.notes &&
               lhs.createdAt == rhs.createdAt &&
               lhs.updatedAt == rhs.updatedAt
    }
    
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
        hasher.combine(mechanismId)
        hasher.combine(userId)
        hasher.combine(notes)
        hasher.combine(createdAt)
        hasher.combine(updatedAt)
    }
}

// Helper for decoding Any type
struct AnyCodable: Codable, Hashable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode AnyCodable")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch value {
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        default:
            throw EncodingError.invalidValue(value, EncodingError.Context(codingPath: container.codingPath, debugDescription: "Cannot encode AnyCodable"))
        }
    }
    
    static func == (lhs: AnyCodable, rhs: AnyCodable) -> Bool {
        if let lhsString = lhs.value as? String, let rhsString = rhs.value as? String {
            return lhsString == rhsString
        }
        if let lhsInt = lhs.value as? Int, let rhsInt = rhs.value as? Int {
            return lhsInt == rhsInt
        }
        if let lhsDouble = lhs.value as? Double, let rhsDouble = rhs.value as? Double {
            return lhsDouble == rhsDouble
        }
        if let lhsBool = lhs.value as? Bool, let rhsBool = rhs.value as? Bool {
            return lhsBool == rhsBool
        }
        if let lhsArray = lhs.value as? [Any], let rhsArray = rhs.value as? [Any] {
            guard lhsArray.count == rhsArray.count else { return false }
            return zip(lhsArray.map { AnyCodable($0) }, rhsArray.map { AnyCodable($0) })
                .allSatisfy { $0 == $1 }
        }
        if let lhsDict = lhs.value as? [String: Any], let rhsDict = rhs.value as? [String: Any] {
            guard lhsDict.count == rhsDict.count else { return false }
            return lhsDict.keys.allSatisfy { key in
                guard let lhsVal = lhsDict[key], let rhsVal = rhsDict[key] else { return false }
                return AnyCodable(lhsVal) == AnyCodable(rhsVal)
            }
        }
        return false
    }
    
    func hash(into hasher: inout Hasher) {
        if let string = value as? String {
            hasher.combine(string)
        } else if let int = value as? Int {
            hasher.combine(int)
        } else if let double = value as? Double {
            hasher.combine(double)
        } else if let bool = value as? Bool {
            hasher.combine(bool)
        } else if let array = value as? [Any] {
            hasher.combine(array.count)
            for item in array {
                AnyCodable(item).hash(into: &hasher)
            }
        } else if let dict = value as? [String: Any] {
            hasher.combine(dict.count)
            for key in dict.keys.sorted() {
                hasher.combine(key)
                if let val = dict[key] {
                    AnyCodable(val).hash(into: &hasher)
                }
            }
        }
    }
}

// MARK: - Hypothesis

struct Hypothesis: Codable, Identifiable, Hashable {
    let id: String
    let label: String
    let description: String
    let supportingNeighbors: [String]
    let mechanismId: Int?
    let confidence: Double?  // 0.0 to 1.0
    
    enum CodingKeys: String, CodingKey {
        case id
        case label
        case description
        case supportingNeighbors = "supporting_neighbors"
        case mechanismId = "mechanism_id"
        case confidence
    }
}

// MARK: - API Response Models

struct MechanismsResponse: Codable {
    let success: Bool
    let mechanisms: [Mechanism]?
    let disclaimer: String?
    let error: String?
}

struct MechanismResponse: Codable {
    let success: Bool
    let mechanism: Mechanism?
    let disclaimer: String?
    let error: String?
}

struct TargetsResponse: Codable {
    let success: Bool
    let targets: [Target]?
    let disclaimer: String?
    let error: String?
}

struct TargetResponse: Codable {
    let success: Bool
    let target: Target?
    let disclaimer: String?
    let error: String?
}

struct LigandsResponse: Codable {
    let success: Bool
    let ligands: [Ligand]?
    let count: Int?
    let disclaimer: String?
    let error: String?
}

struct AssaysResponse: Codable {
    let success: Bool
    let assays: [Assay]?
    let count: Int?
    let disclaimer: String?
    let error: String?
}

struct DrugOutcomesResponse: Codable {
    let success: Bool
    let outcomes: [DrugOutcome]?
    let count: Int?
    let disclaimer: String?
    let error: String?
}

struct CancersResponse: Codable {
    let success: Bool
    let cancers: [String]?
    let disclaimer: String?
    let error: String?
}

struct CancerMechanismsResponse: Codable {
    let success: Bool
    let cancerType: String?
    let mechanisms: [CancerMechanismMapping]?
    let disclaimer: String?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case cancerType = "cancer_type"
        case mechanisms
        case disclaimer
        case error
    }
}

struct WorkspacesResponse: Codable {
    let success: Bool
    let workspaces: [Workspace]?
    let error: String?
}

struct WorkspaceResponse: Codable {
    let success: Bool
    let workspace: Workspace?
    let error: String?
}

struct WorkspaceCreateResponse: Codable {
    let success: Bool
    let workspaceId: Int?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case workspaceId = "workspace_id"
        case error
    }
}

struct SimilarLigandsResponse: Codable {
    let success: Bool
    let similarLigands: [Ligand]?
    let disclaimer: String?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case similarLigands = "similar_ligands"
        case disclaimer
        case error
    }
}
