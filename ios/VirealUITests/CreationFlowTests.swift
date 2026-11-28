import XCTest

@MainActor final class CreationFlowTests: XCTestCase {
    private func tap(_ element: XCUIElement, app: XCUIApplication) {
        for _ in 0..<8 { if element.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(element.waitForExistence(timeout: 5)); element.tap()
    }
    func testLoginCreateWorksAndLogout() {
        let app = XCUIApplication(); app.launchArguments = ["--ui-testing"]; app.launch()
        XCTAssertTrue(app.staticTexts["本地界面测试 · 非真实服务"].waitForExistence(timeout: 8))
        tap(app.buttons["effect.dance-1"], app: app)
        tap(app.buttons["effect.use"], app: app)
        let email = app.textFields["login.email"]
        XCTAssertTrue(email.waitForExistence(timeout: 5)); email.tap(); email.typeText("test@vireal.example")
        tap(app.buttons["login.continue"], app: app)
        let code = app.textFields["login.code"]
        XCTAssertTrue(code.waitForExistence(timeout: 5)); code.tap(); code.typeText("123456")
        tap(app.buttons["login.continue"], app: app)
        let photo = app.buttons["photo.fixture"]
        XCTAssertTrue(photo.waitForExistence(timeout: 8)); tap(photo, app: app)
        tap(app.switches["photo.consent"], app: app)
        let submit = app.buttons["generation.submit"]
        XCTAssertTrue(submit.isEnabled); tap(submit, app: app)
        app.alerts.buttons["确认"].tap()
        XCTAssertTrue(app.buttons["task.play"].waitForExistence(timeout: 12))
        let screenshot = XCTAttachment(screenshot: app.screenshot()); screenshot.name = "UIKit completed task"; screenshot.lifetime = .keepAlways; add(screenshot)
        tap(app.buttons["task.delete"], app: app); app.alerts.buttons["确认"].tap()
        app.tabBars.buttons["作品"].tap(); XCTAssertTrue(app.staticTexts["暂无作品"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap(); tap(app.buttons["account.logout"], app: app)
        app.alerts.buttons["确认"].tap(); XCTAssertTrue(app.buttons["account.login"].waitForExistence(timeout: 5))
        app.tabBars.buttons["作品"].tap(); XCTAssertTrue(app.buttons["works.login"].waitForExistence(timeout: 5))
    }
}
