#if DEBUG
import Foundation

@MainActor final class FixtureAuthentication: Authentication {
    private(set) var sessionID: String?
    func restore() async throws { }
    func sendCode(email: String) async throws { }
    func verifyCode(_ code: String) async throws {
        guard code == "123456" else { throw ClientError.backend(422, "测试验证码不正确。") }
        sessionID = UUID().uuidString
    }
    func token(forceRefresh: Bool) async throws -> String { guard sessionID != nil else { throw ClientError.signedOut }; return "LOCAL-UI-TEST-ONLY" }
    func signOut() async throws { sessionID = nil }
}

@MainActor final class FixtureAPI: VirealAPI {
    static let owner = "11111111-1111-4111-8111-111111111111"
    private var nickname = "本地测试账户"
    private var credits = 128
    private var records: [VideoTask] = []
    private var requests: [String: VideoTask] = [:]
    var submissionFailure: Error?
    private(set) var submittedKeys: [String] = []
    private let effect = Effect(id: "22222222-2222-4222-8222-222222222222", slug: "dance-1", titleZh: "随光起舞", description: "本地界面测试效果，不连接服务器。", inputImageCount: 1, posterUrl: nil, previewVideoUrl: nil, variants: [Variant(id: "33333333-3333-4333-8333-333333333333", durationSeconds: 5, coinCost: 28, isDefault: true)])
    private func currentUser() -> AppUser { .init(id: Self.owner, nickname: nickname, identity: .init(email: "test@vireal.example", emailVerified: true)) }
    func catalog() async throws -> Catalog { .init(categories: [.init(id: "dance", slug: "dance", nameZh: "舞蹈", effects: [effect])]) }
    func availability() async throws -> Availability {
        .init(regionAllowed: true, uploadsEnabled: true, generationEnabled: true, pilotMode: false, pilotAccessAllowed: true, controlledAccountSetupMode: false, paymentOnlyAcceptanceMode: false, generationAcceptanceMode: false, generationAcceptanceAllowed: nil, generationAcceptanceTaskId: nil, internalSignInEnabled: false, country: "US")
    }
    func initializeSession() async throws -> AppSession { .init(appUser: currentUser(), isNewUser: false, internalGenerationAllowed: false, generationAcceptanceReadAllowed: false) }
    func wallet() async throws -> Wallet { .init(balance: credits, dailyRemaining: 5, concurrentRemaining: 1, globalRealRemaining: 30, resetsAt: Date().addingTimeInterval(86400), paymentHold: false, ledger: []) }
    func upload(_ jpeg: Data) async throws -> UploadedImage { .init(id: UUID().uuidString, expiresAt: Date().addingTimeInterval(86400)) }
    func createTask(_ request: GenerationRequest, key: String) async throws -> VideoTask {
        submittedKeys.append(key)
        if let submissionFailure { throw submissionFailure }
        if let existing = requests[key] { return existing }
        let item = VideoTask(id: UUID().uuidString, status: "pending", effectTitle: "随光起舞", duration: 5, coinCost: 28, error: nil, coinRefundedAt: nil, expiresAt: Date().addingTimeInterval(86400), createdAt: Date())
        records.insert(item, at: 0); requests[key] = item; credits -= 28; return item
    }
    func tasks(skip: Int) async throws -> TaskPage { .init(data: Array(records.dropFirst(skip).prefix(50)), count: records.count) }
    func task(id: String) async throws -> VideoTask {
        guard let previous = records.first(where: { $0.id == id }) else { throw ClientError.backend(404, "Task not found") }
        let status = Date().timeIntervalSince(previous.createdAt ?? Date()) > 2 ? "succeeded" : "running"
        let item = VideoTask(id: id, status: status, effectTitle: previous.effectTitle, duration: 5, coinCost: 28, error: nil, coinRefundedAt: nil, expiresAt: previous.expiresAt, createdAt: previous.createdAt)
        records = records.map { $0.id == id ? item : $0 }; return item
    }
    func download(id: String) async throws -> URL { throw ClientError.backend(503, "本地界面测试不提供真实视频，媒体需在预发布联调。") }
    func deleteTask(id: String) async throws { records.removeAll { $0.id == id } }
    func logout() async throws { }
    func rename(_ nickname: String) async throws -> AppUser { self.nickname = nickname; return currentUser() }
    func publicURL(_ path: String?) -> URL? { nil }
}
#endif
