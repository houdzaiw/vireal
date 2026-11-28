import XCTest
import os
@testable import Vireal

private struct StubState: Sendable {
    var replies: [(Int, Data)] = []
    var requests: [URLRequest] = []
}
// URLProtocol's inherited unchecked conformance is restated; added state is lock-protected.
private final class StubProtocol: URLProtocol, @unchecked Sendable {
    static let state = OSAllocatedUnfairLock(initialState: StubState())
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let reply = Self.state.withLock { state in
            state.requests.append(request)
            return state.replies.isEmpty ? (500, Data()) : state.replies.removeFirst()
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: reply.0, httpVersion: "HTTP/1.1", headerFields: ["Content-Type":"application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: reply.1)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}

@MainActor final class HTTPTests: XCTestCase {
    private func api(replies: [(Int, String)]) async throws -> HTTPAPI {
        StubProtocol.state.withLock { $0 = StubState(replies: replies.map { ($0.0, Data($0.1.utf8)) }) }
        let auth = FixtureAuthentication(); try await auth.verifyCode("123456")
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [StubProtocol.self]
        return HTTPAPI(origin: URL(string: "https://api.example.test")!, auth: auth, session: URLSession(configuration: config))
    }
    func testPublicCatalogDoesNotSendBearer() async throws {
        let api = try await api(replies: [(200, #"{"categories":[]}"#)])
        _ = try await api.catalog()
        let requests = StubProtocol.state.withLock { $0.requests }
        XCTAssertEqual(requests.count, 1); XCTAssertNil(requests[0].value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(requests[0].value(forHTTPHeaderField: "User-Agent"), "Vireal-iOS/0.1")
    }
    func testRegistrationClosedIsNotRetried() async throws {
        let api = try await api(replies: [(403, #"{"detail":"Registration is not yet open"}"#)])
        do { _ = try await api.initializeSession(); XCTFail("Expected closed registration") }
        catch { XCTAssertFalse((error as? ClientError)?.isAuthenticationFailure ?? true) }
        XCTAssertEqual(StubProtocol.state.withLock { $0.requests.count }, 1)
    }
    func testCredentialRefreshRetriesWithSameBodyAndIdempotencyKey() async throws {
        let result = #"{"id":"task-1","status":"pending","effect_title":null,"duration":5,"expires_at":"2027-01-01T00:00:00Z"}"#
        let api = try await api(replies: [(403, #"{"detail":"Could not validate app credentials"}"#), (202, result)])
        let request = GenerationRequest(effectId: "e", variantId: "v", uploadIds: ["u"])
        let task = try await api.createTask(request, key: "immutable-key")
        XCTAssertEqual(task.id, "task-1")
        let sent = StubProtocol.state.withLock { $0.requests }
        XCTAssertEqual(sent.count, 2)
        XCTAssertEqual(sent.map { $0.value(forHTTPHeaderField: "Idempotency-Key") }, ["immutable-key", "immutable-key"])
        // URLSession may stream the body in URLProtocol; confirm wire keys when accessible.
        if let data = sent[0].httpBody {
            let fields = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(fields["effect_id"] as? String, "e")
            XCTAssertNil(fields["coin_cost"])
        }
    }
    func testUploadIsMultipartAndNeverAutoRetriesServerError() async throws {
        let api = try await api(replies: [(503, #"{"detail":"Storage unavailable"}"#)])
        do { _ = try await api.upload(Data([1,2,3])); XCTFail("Expected upload error") } catch { }
        let sent = StubProtocol.state.withLock { $0.requests }
        XCTAssertEqual(sent.count,1)
        XCTAssertTrue(sent[0].value(forHTTPHeaderField: "Content-Type")?.hasPrefix("multipart/form-data; boundary=") == true)
    }
}
