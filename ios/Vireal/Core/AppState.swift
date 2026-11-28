import Foundation

@MainActor final class SubmissionStore {
    private let directory: URL
    init(directory: URL? = nil) throws {
        self.directory = try directory ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("VirealPending", isDirectory: true)
        try FileManager.default.createDirectory(at: self.directory, withIntermediateDirectories: true,
                                              attributes: [.protectionKey: FileProtectionType.complete])
        var protected = self.directory
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try protected.setResourceValues(values)
    }
    private func file(owner: String) throws -> URL {
        guard UUID(uuidString: owner) != nil else { throw ClientError.sessionChanged }
        return directory.appendingPathComponent(owner + ".json")
    }
    func load(owner: String) throws -> PendingSubmission? {
        let url = try file(owner: owner)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let item = try JSONCoding.decoder().decode(PendingSubmission.self, from: Data(contentsOf: url))
        guard item.owner == owner else { throw ClientError.sessionChanged }
        return item
    }
    func save(_ pending: PendingSubmission) throws {
        try JSONCoding.encoder().encode(pending).write(to: file(owner: pending.owner), options: [.atomic, .completeFileProtection])
    }
    func clear(owner: String) throws {
        let url = try file(owner: owner)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }
}

@MainActor final class AppState {
    static let didChange = Notification.Name("VirealAppStateDidChange")
    let auth: any Authentication
    let api: any VirealAPI
    let submissions: SubmissionStore
    private(set) var session: AppSession?
    private(set) var wallet: Wallet?
    private(set) var availability: Availability?
    private(set) var generation = UUID()
    private var blockedSessionID: String?
    var user: AppUser? { session?.appUser }

    init(auth: any Authentication, api: any VirealAPI, submissions: SubmissionStore) {
        self.auth = auth; self.api = api; self.submissions = submissions
    }
    func restore() async throws {
        try await auth.restore()
        if auth.sessionID != nil && auth.sessionID != blockedSessionID { try await initializeSession() }
    }
    func initializeSession() async throws {
        let epoch = generation
        let result = try await api.initializeSession()
        guard epoch == generation else { throw ClientError.sessionChanged }
        if session?.appUser.id != result.appUser.id {
            generation = UUID(); wallet = nil; availability = nil
        }
        session = result; blockedSessionID = nil
        notify()
    }
    func refreshAccount() async throws {
        guard user != nil else { throw ClientError.signedOut }
        let epoch = generation
        async let funds = api.wallet()
        async let status = api.availability()
        let (newWallet, newStatus) = try await (funds, status)
        guard generation == epoch else { throw ClientError.sessionChanged }
        wallet = newWallet; availability = newStatus; notify()
    }
    func creationBlock(cost: Int) -> String? {
        guard user != nil else { return "请先登录。" }
        guard let wallet, let availability else { return "正在确认金币和服务状态，请稍后重试。" }
        guard availability.allowsCreation(session: session) else { return "当前账户或地区暂未开放照片上传和视频生成。" }
        if wallet.paymentHold { return "账户需要人工核对，暂不能生成。" }
        if wallet.dailyRemaining <= 0 || wallet.globalRealRemaining <= 0 { return "今日生成额度已用完，请在额度重置后再试。" }
        if wallet.concurrentRemaining <= 0 { return "已有生成任务占用当前额度，请稍后再试。" }
        if wallet.balance < cost { return "金币不足，内测版暂未开放充值。" }
        return nil
    }
    func pending() throws -> PendingSubmission? {
        guard let owner = user?.id else { throw ClientError.signedOut }
        return try submissions.load(owner: owner)
    }
    func submit(_ pending: PendingSubmission) async throws -> VideoTask {
        guard pending.owner == user?.id else { throw ClientError.sessionChanged }
        let epoch = generation
        // Persist before the network side effect; never manufacture a fresh key on retry.
        try submissions.save(pending)
        let result = try await api.createTask(pending.request, key: pending.key)
        guard generation == epoch, user?.id == pending.owner else { throw ClientError.sessionChanged }
        try submissions.clear(owner: pending.owner)
        return result
    }
    func signOut() async -> String? {
        blockedSessionID = auth.sessionID
        generation = UUID(); session = nil; wallet = nil; availability = nil
        notify() // Clear private views before awaiting the network.
        var warning: String?
        do { try await api.logout() } catch { warning = "本机已退出，但服务器会话撤销尚未确认。请联网后重试。" }
        do { try await auth.signOut() } catch { warning = "本机已退出，远端退出尚未确认，请联网后重试。" }
        try? FileManager.default.removeItem(at: FileManager.default.temporaryDirectory.appendingPathComponent("VirealMedia"))
        return warning
    }
    func rename(_ nickname: String) async throws {
        guard let previous = session else { throw ClientError.signedOut }
        let epoch = generation
        let result = try await api.rename(nickname)
        guard epoch == generation else { throw ClientError.sessionChanged }
        session = AppSession(appUser: result, isNewUser: previous.isNewUser,
                             internalGenerationAllowed: previous.internalGenerationAllowed,
                             generationAcceptanceReadAllowed: previous.generationAcceptanceReadAllowed)
        notify()
    }
    func invalidateIfNeeded(_ error: Error) {
        guard let error = error as? ClientError, error.isAuthenticationFailure else { return }
        blockedSessionID = auth.sessionID
        generation = UUID(); session = nil; wallet = nil; availability = nil
        notify()
    }
    private func notify() { NotificationCenter.default.post(name: Self.didChange, object: self) }
}
