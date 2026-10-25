import Foundation

struct User: Codable, Equatable {
    let id: Int
    let email: String
    let name: String
    let avatarUrl: String?
}

struct UserEnvelope: Decodable { let user: User? }

struct LoginRequest: Encodable {
    let email: String
    let password: String
}

struct LoginResponse: Decodable { let user: User }
