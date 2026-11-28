import XCTest
@testable import Vireal

@MainActor final class LiveServiceTests: XCTestCase {
    func testStagingReadOnlyBootstrap() async throws {
        guard ProcessInfo.processInfo.environment["VIREAL_LIVE_READ_ONLY"] == "1" else {
            throw XCTSkip("Run explicitly with the VirealLive scheme; ordinary tests stay offline.")
        }
        let configuration = try AppConfiguration.load()
        XCTAssertEqual(configuration.origin.host, "staging-api.usevireal.com")
        let authentication = ClerkAuthentication(configuration: configuration)
        try await authentication.restore()
        let api = HTTPAPI(origin: configuration.origin, auth: authentication)
        let catalog = try await api.catalog()
        let availability = try await api.availability()
        XCTAssertFalse(catalog.categories.isEmpty)
        XCTAssertFalse(availability.generationEnabled, "This bootstrap must not open generation")
        // No sign-in OTP, upload, paid generation or business registration is triggered.
    }
}
