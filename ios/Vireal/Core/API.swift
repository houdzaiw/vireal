import Foundation

@MainActor protocol VirealAPI: AnyObject, Sendable {
    func catalog() async throws -> Catalog
    func availability() async throws -> Availability
    func initializeSession() async throws -> AppSession
    func wallet() async throws -> Wallet
    func upload(_ jpeg: Data) async throws -> UploadedImage
    func createTask(_ request: GenerationRequest, key: String) async throws -> VideoTask
    func tasks(skip: Int) async throws -> TaskPage
    func task(id: String) async throws -> VideoTask
    func download(id: String) async throws -> URL
    func deleteTask(id: String) async throws
    func logout() async throws
    func rename(_ nickname: String) async throws -> AppUser
    func publicURL(_ path: String?) -> URL?
}

final class APIRedirectPolicy: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        let original = task.originalRequest?.url
        let next = request.url
        let safe = original?.scheme == "https" && next?.scheme == "https" && original?.host == next?.host && original?.port == next?.port
        completionHandler(safe ? request : nil)
    }
}

@MainActor final class HTTPAPI: VirealAPI {
    let origin: URL
    private let auth: any Authentication
    private let session: URLSession

    init(origin: URL, auth: any Authentication, session: URLSession? = nil) {
        self.origin = origin; self.auth = auth
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 180
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        self.session = session ?? URLSession(configuration: configuration, delegate: APIRedirectPolicy(), delegateQueue: nil)
    }
    func publicURL(_ path: String?) -> URL? {
        guard let path, let url = URL(string: path, relativeTo: origin)?.absoluteURL,
              url.scheme == "https", url.user == nil, url.password == nil else { return nil }
        return url
    }
    private func endpoint(_ path: String) -> URL {
        // All path components here are server UUIDs or fixed literals, never media URLs.
        URL(string: "/api/v1/app/" + path, relativeTo: origin)!.absoluteURL
    }
    private func error(data: Data, response: HTTPURLResponse) -> ClientError {
        let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        let detail = payload?["detail"] as? String
        return .backend(response.statusCode, detail ?? "服务暂不可用（\(response.statusCode)），请稍后重试。")
    }
    private func data(_ path: String, method: String = "GET", body: Data? = nil,
                      contentType: String = "application/json", authenticated: Bool = true, key: String? = nil) async throws -> Data {
        let owner = authenticated ? auth.sessionID : nil
        if authenticated && owner == nil { throw ClientError.signedOut }
        for attempt in 0...1 {
            var request = URLRequest(url: endpoint(path))
            request.httpMethod = method
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue("Vireal-iOS/0.1", forHTTPHeaderField: "User-Agent")
            if body != nil { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
            if let key { request.setValue(key, forHTTPHeaderField: "Idempotency-Key") }
            if authenticated {
                request.setValue("Bearer \(try await auth.token(forceRefresh: attempt > 0))", forHTTPHeaderField: "Authorization")
                guard owner == auth.sessionID else { throw ClientError.sessionChanged }
            }
            let (data, rawResponse) = try await session.data(for: request)
            try Task.checkCancellation()
            guard !authenticated || owner == auth.sessionID else { throw ClientError.sessionChanged }
            guard let response = rawResponse as? HTTPURLResponse else { throw ClientError.invalidMedia }
            if (200..<300).contains(response.statusCode) { return data }
            let failure = error(data: data, response: response)
            if authenticated && attempt == 0 && failure.canRefreshToken { continue }
            throw failure
        }
        throw ClientError.signedOut
    }
    private func get<T: Decodable>(_ path: String, authenticated: Bool = true) async throws -> T {
        try JSONCoding.decoder().decode(T.self, from: await data(path, authenticated: authenticated))
    }
    func catalog() async throws -> Catalog { try await get("effect-catalog", authenticated: false) }
    func availability() async throws -> Availability { try await get("paypal/config", authenticated: auth.sessionID != nil) }
    func initializeSession() async throws -> AppSession {
        try JSONCoding.decoder().decode(AppSession.self, from: await data("auth/session", method: "POST"))
    }
    func wallet() async throws -> Wallet { try await get("wallet") }
    func upload(_ jpeg: Data) async throws -> UploadedImage {
        guard jpeg.count <= 5 * 1024 * 1024 else { throw ClientError.photoTooLarge }
        let boundary = "Vireal-" + UUID().uuidString
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
        body.append(jpeg); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return try JSONCoding.decoder().decode(UploadedImage.self, from: await data("uploads/images", method: "POST", body: body, contentType: "multipart/form-data; boundary=\(boundary)"))
    }
    func createTask(_ request: GenerationRequest, key: String) async throws -> VideoTask {
        let body = try JSONCoding.encoder().encode(request)
        return try JSONCoding.decoder().decode(VideoTask.self, from: await data("video-tasks", method: "POST", body: body, key: key))
    }
    func tasks(skip: Int) async throws -> TaskPage { try await get("video-tasks?skip=\(max(0, skip))&limit=50") }
    func task(id: String) async throws -> VideoTask { try await get("video-tasks/\(id)") }
    func deleteTask(id: String) async throws { _ = try await data("video-tasks/\(id)", method: "DELETE") }
    func logout() async throws { _ = try await data("auth/logout", method: "POST") }
    func rename(_ nickname: String) async throws -> AppUser {
        struct Body: Encodable { let nickname: String }
        return try JSONCoding.decoder().decode(AppUser.self, from: await data("users/me", method: "PATCH", body: JSONCoding.encoder().encode(Body(nickname: nickname))))
    }
    func download(id: String) async throws -> URL {
        let owner = auth.sessionID
        guard owner != nil else { throw ClientError.signedOut }
        var request = URLRequest(url: endpoint("video-tasks/\(id)/download"))
        request.setValue("Vireal-iOS/0.1", forHTTPHeaderField: "User-Agent")
        request.setValue("Bearer \(try await auth.token(forceRefresh: false))", forHTTPHeaderField: "Authorization")
        guard owner == auth.sessionID else { throw ClientError.sessionChanged }
        let (temporary, raw) = try await session.download(for: request)
        defer { try? FileManager.default.removeItem(at: temporary) }
        guard owner == auth.sessionID else { throw ClientError.sessionChanged }
        try Task.checkCancellation()
        guard let response = raw as? HTTPURLResponse else { throw ClientError.invalidMedia }
        guard (200..<300).contains(response.statusCode) else {
            throw error(data: (try? Data(contentsOf: temporary)) ?? Data(), response: response)
        }
        guard response.mimeType == "video/mp4" else { throw ClientError.invalidMedia }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("VirealMedia", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let destination = directory.appendingPathComponent(UUID().uuidString + ".mp4")
        try FileManager.default.moveItem(at: temporary, to: destination)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: destination.path)
        return destination
    }
}
