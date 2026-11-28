import UIKit

@MainActor final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private var coordinator: AppCoordinator?
    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        let window = UIWindow(windowScene: scene)
        window.overrideUserInterfaceStyle = .dark
        window.tintColor = Theme.accent; self.window = window
        do {
            let store: SubmissionStore
            let auth: any Authentication
            let api: any VirealAPI
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--ui-testing") || ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil {
                store = try SubmissionStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("UITests-" + UUID().uuidString))
                auth = FixtureAuthentication(); api = FixtureAPI()
            } else {
                store = try SubmissionStore()
                let configuration = try AppConfiguration.load()
                let clerk = ClerkAuthentication(configuration: configuration)
                auth = clerk; api = HTTPAPI(origin: configuration.origin, auth: clerk)
            }
            #else
            store = try SubmissionStore()
            let configuration = try AppConfiguration.load()
            let clerk = ClerkAuthentication(configuration: configuration)
            auth = clerk; api = HTTPAPI(origin: configuration.origin, auth: clerk)
            #endif
            let state = AppState(auth: auth, api: api, submissions: store)
            let coordinator = AppCoordinator(window: window, state: state)
            self.coordinator = coordinator; coordinator.start()
        } catch {
            let controller = StackController(); controller.title = "Vireal"
            controller.loadViewIfNeeded(); controller.add("VIREAL ✦", style: .largeTitle, color: Theme.accent)
            controller.add("测试版本尚未配置", style: .title2); controller.add(error.localizedDescription, color: Theme.muted)
            window.rootViewController = UINavigationController(rootViewController: controller)
        }
        window.makeKeyAndVisible()
    }
    func sceneDidBecomeActive(_ scene: UIScene) { coordinator?.becameActive() }
    func sceneWillResignActive(_ scene: UIScene) { coordinator?.resignedActive() }
}
