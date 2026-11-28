import UIKit

@MainActor final class AppCoordinator {
    let state: AppState
    private let window: UIWindow
    private let tabs = UITabBarController()
    private var previousUser: String?
    private var restoration: Task<Void, Never>?

    init(window: UIWindow, state: AppState) { self.window = window; self.state = state }
    func start() {
        let discover = CatalogController(state: state, coordinator: self)
        let works = WorksController(state: state, coordinator: self)
        let account = AccountController(state: state, coordinator: self)
        tabs.viewControllers = [discover, works, account].enumerated().map { index, controller in
            let nav = UINavigationController(rootViewController: controller)
            nav.navigationBar.prefersLargeTitles = true
            nav.tabBarItem = UITabBarItem(title: ["发现", "作品", "我的"][index], image: UIImage(systemName: ["sparkles", "play.rectangle", "person.crop.circle"][index]), tag: index)
            return nav
        }
        window.rootViewController = tabs
        NotificationCenter.default.addObserver(self, selector: #selector(identityChanged), name: AppState.didChange, object: state)
        restoration = Task { [weak self] in
            guard let self else { return }
            do { try await state.restore() }
            catch { discover.showError(error, state: state) }
        }
    }
    @objc private func identityChanged() {
        let current = state.user?.id
        if previousUser != nil && previousUser != current {
            tabs.dismiss(animated: false)
            for case let navigation as UINavigationController in tabs.viewControllers ?? [] { navigation.popToRootViewController(animated: false) }
        }
        previousUser = current
    }
    func login(from controller: UIViewController, then action: @escaping @MainActor () -> Void) {
        if state.user != nil { action(); return }
        let login = LoginController(state: state) { [weak controller] in
            controller?.dismiss(animated: true, completion: action)
        }
        controller.present(UINavigationController(rootViewController: login), animated: true)
    }
    func create(effect: Effect, from controller: UIViewController) {
        login(from: controller) { [weak self, weak controller] in
            guard let self else { return }
            controller?.navigationController?.pushViewController(CreateController(effect: effect, state: state, coordinator: self), animated: true)
        }
    }
    func openTask(_ task: VideoTask, from controller: UIViewController) {
        controller.navigationController?.pushViewController(TaskController(task: task, state: state), animated: true)
    }
    func showWorks() { tabs.selectedIndex = 1 }
    func becameActive() {
        guard state.user != nil else { return }
        Task { [weak self] in
            guard let self else { return }
            do { try await state.refreshAccount() } catch { state.invalidateIfNeeded(error) }
        }
    }
    func resignedActive() { }
}
