import XCTest
import UIKit
import ImageIO
import UniformTypeIdentifiers
@testable import Vireal

@MainActor final class CoreTests: XCTestCase {
    func testNativeDatesAndNullFieldsDecode() throws {
        let data = Data(#"{"id":"t","status":"submission_unknown","effect_title":null,"duration":5,"coin_cost":null,"error":null,"coin_refunded_at":null,"expires_at":"2027-01-01T09:00:00.123456Z","created_at":null}"#.utf8)
        let task = try JSONCoding.decoder().decode(VideoTask.self, from: data)
        XCTAssertEqual(task.statusTitle, "正在确认提交结果")
        XCTAssertFalse(task.isTerminal)
        XCTAssertFalse(task.isPlayable)
    }
    func testBusiness403DoesNotBecomeLoginFailure() {
        XCTAssertFalse(ClientError.backend(403, "Registration is not yet open / 注册尚未开放").isAuthenticationFailure)
        XCTAssertFalse(ClientError.backend(403, "Region unavailable").canRefreshToken)
        XCTAssertTrue(ClientError.backend(403, "App session is no longer active").isAuthenticationFailure)
        XCTAssertFalse(ClientError.backend(403, "App session is no longer active").canRefreshToken)
        XCTAssertTrue(ClientError.backend(403, "Could not validate Clerk credentials").canRefreshToken)
    }
    func testTimeoutRetainsOriginalSubmissionAcrossRelaunch() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let auth = FixtureAuthentication(); try await auth.verifyCode("123456")
        let api = FixtureAPI(); let store = try SubmissionStore(directory: directory)
        let state = AppState(auth: auth, api: api, submissions: store)
        try await state.initializeSession()
        let request = GenerationRequest(effectId: "e", variantId: "v", uploadIds: ["u"])
        let original = PendingSubmission(owner: FixtureAPI.owner, key: UUID().uuidString, request: request, createdAt: Date())
        api.submissionFailure = URLError(.timedOut)
        do { _ = try await state.submit(original); XCTFail("Expected timeout") } catch { }
        let restoredStore = try SubmissionStore(directory: directory)
        let restored = try XCTUnwrap(restoredStore.load(owner: FixtureAPI.owner))
        XCTAssertEqual(restored.key, original.key)
        XCTAssertEqual(restored.request, original.request)
        api.submissionFailure = nil
        _ = try await state.submit(restored)
        XCTAssertEqual(api.submittedKeys, [original.key, original.key])
        XCTAssertNil(try store.load(owner: FixtureAPI.owner))
        let wallet = try await api.wallet(); XCTAssertEqual(wallet.balance, 100)
    }
    func testPersistedSubmissionCannotCrossAccounts() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try SubmissionStore(directory: directory)
        let pending = PendingSubmission(owner: FixtureAPI.owner, key: "one", request: .init(effectId: "e", variantId: "v", uploadIds: ["u"]), createdAt: Date())
        try store.save(pending)
        XCTAssertNil(try store.load(owner: "99999999-9999-4999-8999-999999999999"))
        XCTAssertThrowsError(try store.load(owner: "../escape"))
    }
    func testSignOutClearsPrivateState() async throws {
        let auth = FixtureAuthentication(); try await auth.verifyCode("123456")
        let state = AppState(auth: auth, api: FixtureAPI(), submissions: try SubmissionStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)))
        try await state.initializeSession(); try await state.refreshAccount()
        let epoch = state.generation
        XCTAssertNotNil(state.user); XCTAssertNotNil(state.wallet)
        let warning = await state.signOut()
        XCTAssertNil(warning); XCTAssertNil(state.user); XCTAssertNil(state.wallet)
        XCTAssertNotEqual(epoch, state.generation); XCTAssertNil(auth.sessionID)
    }
    func testFailClosedAvailabilityIgnoresOrdinaryFlagsInPrivateMode() throws {
        let json = #"{"region_allowed":true,"uploads_enabled":true,"generation_enabled":true,"controlled_account_setup_mode":true}"#
        let mode = try JSONCoding.decoder().decode(Availability.self, from: Data(json.utf8))
        XCTAssertFalse(mode.allowsCreation(session: nil))
    }
    func testConfigurationRequiresMatchingHTTPSOriginAndPublicKey() {
        let key = "pk_test_" + Data("clerk.example.test$".utf8).base64EncodedString()
        XCTAssertNoThrow(try AppConfiguration.validate(originText: "https://api.example.test", key: key))
        XCTAssertThrowsError(try AppConfiguration.validate(originText: "http://api.example.test", key: key))
        XCTAssertThrowsError(try AppConfiguration.validate(originText: "https://api.example.test/api", key: key))
        XCTAssertThrowsError(try AppConfiguration.validate(originText: "https://api.example.test", key: "sk_test_not-a-public-key"))
        XCTAssertThrowsError(try AppConfiguration.validate(originText: "https://api.example.test", key: "pk_test_invalid"))
    }
    func testPhotoProcessingBakesOrientationAndRemovesLocation() async throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 3000, height: 2000), format: {
            let format = UIGraphicsImageRendererFormat(); format.scale = 1; return format
        }()).image { context in
            UIColor.cyan.setFill(); context.fill(CGRect(x: 0, y: 0, width: 3000, height: 2000))
        }
        let sourceData = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(sourceData, UTType.jpeg.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, try XCTUnwrap(image.cgImage), [
            kCGImagePropertyOrientation: 6,
            kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 31.0, kCGImagePropertyGPSLatitudeRef: "N", kCGImagePropertyGPSLongitude: 121.0, kCGImagePropertyGPSLongitudeRef: "E"],
        ] as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let processed = try await PhotoProcessor.jpeg(from: sourceData as Data)
        XCTAssertLessThanOrEqual(processed.count, 5 * 1024 * 1024)
        let source = try XCTUnwrap(CGImageSourceCreateWithData(processed as CFData, nil))
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
        XCTAssertNil(properties[kCGImagePropertyGPSDictionary])
        let width = try XCTUnwrap(properties[kCGImagePropertyPixelWidth] as? Int)
        let height = try XCTUnwrap(properties[kCGImagePropertyPixelHeight] as? Int)
        XCTAssertLessThan(width, height)
        XCTAssertLessThanOrEqual(max(width, height), 2048)
    }
}
