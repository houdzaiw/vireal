import Foundation
import ClerkKit

@MainActor protocol Authentication: AnyObject {
    var sessionID: String? { get }
    func restore() async throws
    func sendCode(email: String) async throws
    func verifyCode(_ code: String) async throws
    func token(forceRefresh: Bool) async throws -> String
    func signOut() async throws
}

@MainActor final class ClerkAuthentication: Authentication {
    private let clerk: Clerk
    private let template: String?
    private let publishableKey: String
    private var attempt: SignIn?

    init(configuration: AppConfiguration) {
        clerk = Clerk.configure(publishableKey: configuration.publishableKey)
        template = configuration.tokenTemplate
        publishableKey = configuration.publishableKey
    }

    var sessionID: String? { clerk.session?.id }

    func restore() async throws {
        // configure starts loading. Refresh explicitly to surface transport errors.
        _ = try await clerk.refreshClient()
    }
    func sendCode(email: String) async throws {
        attempt = try await clerk.auth.signInWithEmailCode(emailAddress: email)
    }
    func verifyCode(_ code: String) async throws {
        guard let attempt else { throw ClientError.signedOut }
        let verified = try await attempt.verifyCode(code)
        self.attempt = verified
        guard verified.status == .complete, let id = verified.createdSessionId else {
            throw ClientError.incompleteSignIn
        }
        try await clerk.auth.setActive(sessionId: id)
        self.attempt = nil
    }
    func token(forceRefresh: Bool = false) async throws -> String {
        guard let value = try await clerk.auth.getToken(.init(template: template, skipCache: forceRefresh)) else {
            throw ClientError.signedOut
        }
        return value
    }
    func signOut() async throws {
        attempt = nil
        var remoteFailure: Error?
        if let id = sessionID {
            // The SDK's no-argument signOut removes all client sessions; scope to this one.
            do { try await clerk.auth.signOut(sessionId: id) } catch { remoteFailure = error }
        }
        // Clear the SDK's persisted native identity even when the device is offline.
        // Reconfiguring the same instance clears local storage, not other devices.
        try await Clerk.reconfigure(publishableKey: publishableKey)
        if let remoteFailure { throw remoteFailure }
    }
}
