import Foundation

struct Catalog: Decodable, Sendable { let categories: [EffectCategory] }
struct EffectCategory: Decodable, Sendable {
    let id: String
    let slug: String
    let nameZh: String
    let effects: [Effect]
}
struct Effect: Codable, Sendable {
    let id: String
    let slug: String
    let titleZh: String
    let description: String?
    let inputImageCount: Int
    let posterUrl: String?
    let previewVideoUrl: String?
    let variants: [Variant]
}
struct Variant: Codable, Equatable, Sendable {
    let id: String
    let durationSeconds: Int
    let coinCost: Int
    let isDefault: Bool
}
struct AppUser: Decodable, Sendable {
    let id: String
    let nickname: String?
    let identity: Identity?
    struct Identity: Decodable, Sendable { let email: String; let emailVerified: Bool }
}
struct AppSession: Decodable, Sendable {
    let appUser: AppUser
    let isNewUser: Bool
    let internalGenerationAllowed: Bool?
    let generationAcceptanceReadAllowed: Bool?
}
struct Wallet: Decodable, Sendable {
    let balance: Int
    let dailyRemaining: Int
    let concurrentRemaining: Int
    let globalRealRemaining: Int
    let resetsAt: Date
    let paymentHold: Bool
    let ledger: [LedgerEntry]
}
struct LedgerEntry: Decodable, Sendable {
    let id: String
    let delta: Int
    let reason: String
    let createdAt: Date?
}
struct Availability: Decodable, Sendable {
    let regionAllowed: Bool
    let uploadsEnabled: Bool
    let generationEnabled: Bool
    let pilotMode: Bool?
    let pilotAccessAllowed: Bool?
    let controlledAccountSetupMode: Bool?
    let paymentOnlyAcceptanceMode: Bool?
    let generationAcceptanceMode: Bool?
    let generationAcceptanceAllowed: Bool?
    let generationAcceptanceTaskId: String?
    let internalSignInEnabled: Bool?
    let country: String?

    func allowsCreation(session: AppSession?) -> Bool {
        guard controlledAccountSetupMode != true, paymentOnlyAcceptanceMode != true else { return false }
        guard pilotMode != true || pilotAccessAllowed == true else { return false }
        if generationAcceptanceMode == true {
            return generationAcceptanceAllowed == true && generationAcceptanceTaskId == nil
        }
        if session?.internalGenerationAllowed == true && country == "CN" && internalSignInEnabled == true { return true }
        return regionAllowed && uploadsEnabled && generationEnabled
    }
}
struct UploadedImage: Codable, Sendable { let id: String; let expiresAt: Date }
struct TaskPage: Decodable, Sendable { let data: [VideoTask]; let count: Int }
struct VideoTask: Decodable, Sendable {
    let id: String
    let status: String
    let effectTitle: String?
    let duration: Int
    let coinCost: Int?
    let error: String?
    let coinRefundedAt: Date?
    let expiresAt: Date
    let createdAt: Date?
    var isTerminal: Bool { ["succeeded", "failed", "canceled", "expired"].contains(status) }
    var isPlayable: Bool { status == "succeeded" && expiresAt > Date() }
    var statusTitle: String {
        switch status {
        case "submitting": "正在提交"
        case "pending": "排队等待"
        case "running": "AI 生成中"
        case "rendering_demo": "正在生成演示"
        case "saving": "正在保存作品"
        case "succeeded": "已完成"
        case "failed": "生成失败"
        case "canceled": "已取消"
        case "submission_unknown": "正在确认提交结果"
        case "expired": "作品已过期"
        default: "正在确认状态"
        }
    }
}
struct GenerationRequest: Codable, Equatable, Sendable {
    let effectId: String
    let variantId: String
    let uploadIds: [String]
}
struct PendingSubmission: Codable, Sendable {
    let owner: String
    let key: String
    let request: GenerationRequest
    let createdAt: Date
}
struct Message: Decodable { let message: String }

enum JSONCoding {
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: string) { return date }
            formatter.formatOptions = [.withInternetDateTime]
            guard let date = formatter.date(from: string) else {
                throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid ISO8601 date")
            }
            return date
        }
        return decoder
    }
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}
