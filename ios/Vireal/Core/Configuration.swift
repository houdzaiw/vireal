import Foundation

struct AppConfiguration: Sendable {
    let origin: URL
    let publishableKey: String
    let tokenTemplate: String?

    static func load(bundle: Bundle = .main) throws -> Self {
        let originText = bundle.object(forInfoDictionaryKey: "VirealAPIOrigin") as? String ?? ""
        let key = bundle.object(forInfoDictionaryKey: "VirealClerkPublishableKey") as? String ?? ""
        let template = bundle.object(forInfoDictionaryKey: "VirealClerkTokenTemplate") as? String ?? ""
        return try validate(originText: originText, key: key, template: template)
    }
    static func validate(originText: String, key: String, template: String = "") throws -> Self {
        let encodedHost = String(key.dropFirst(8)).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        let paddedHost = encodedHost + String(repeating: "=", count: (4 - encodedHost.count % 4) % 4)
        guard let url = URL(string: originText), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              ["", "/"].contains(url.path), !originText.contains("example.com"),
              key.hasPrefix("pk_test_") || key.hasPrefix("pk_live_"), !key.contains("REPLACE"),
              let bytes = Data(base64Encoded: paddedHost), let host = String(data: bytes, encoding: .utf8),
              host.hasSuffix("$"), !host.contains("/"), !host.contains(":"),
              URL(string: "https://" + String(host.dropLast()))?.host != nil else {
            throw ClientError.configuration
        }
        return .init(origin: url, publishableKey: key, tokenTemplate: template.isEmpty ? nil : template)
    }
}

enum ClientError: Error, LocalizedError {
    case configuration
    case signedOut
    case sessionChanged
    case incompleteSignIn
    case pendingSubmission
    case invalidMedia
    case photoTooLarge
    case backend(Int, String)

    var errorDescription: String? {
        switch self {
        case .configuration: "测试版本尚未配置服务。请在 Xcode 的 Local.xcconfig 中设置匹配的 API 地址和 Clerk 公钥。"
        case .signedOut: "请先登录。"
        case .sessionChanged: "账户状态已变化，请重新操作。"
        case .incompleteSignIn: "此账户还需额外验证。请先在网页完成验证后，再重新登录。"
        case .pendingSubmission: "还有一笔提交结果待确认，请先在作品中核对原任务。"
        case .invalidMedia: "媒体当前不可用，请刷新作品后重试。"
        case .photoTooLarge: "照片压缩后仍超过 5 MB，请换一张较小的照片。"
        case let .backend(_, detail): detail
        }
    }
    var isAuthenticationFailure: Bool {
        switch self {
        case .signedOut: true
        case let .backend(code, detail): code == 401 || (code == 403 && ["Could not validate", "App session has not been initialized", "App session is no longer active", "Inactive app user"].contains(where: detail.contains))
        default: false
        }
    }
    var canRefreshToken: Bool {
        if case let .backend(code, detail) = self {
            return code == 401 || (code == 403 && detail.contains("Could not validate"))
        }
        return false
    }
}
