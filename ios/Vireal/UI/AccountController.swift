import UIKit

@MainActor final class AccountController: StackController {
    private let state: AppState
    private weak var coordinator: AppCoordinator?
    init(state: AppState, coordinator: AppCoordinator) { self.state = state; self.coordinator = coordinator; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "我的"
        NotificationCenter.default.addObserver(self, selector: #selector(render), name: AppState.didChange, object: state)
    }
    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated); render()
        guard state.user != nil else { return }
        work = Task { [weak self] in
            guard let self else { return }; do { try await state.refreshAccount() } catch { showError(error, state: state) }
        }
    }
    @objc private func render() {
        clear(); add("VIREAL ✦", style: .largeTitle, color: Theme.accent)
        if let user = state.user {
            add(user.nickname ?? "灵感创作者", style: .title1); add(user.identity?.email ?? "已登录账户", color: Theme.muted)
            add("我的金币 · ✦ \(state.wallet?.balance.description ?? "—")", style: .title2)
            stack.addArrangedSubview(Theme.button("金币明细", primary: false, id: "account.wallet") { [weak self] in
                guard let self else { return }; navigationController?.pushViewController(WalletController(state: state), animated: true)
            })
            stack.addArrangedSubview(Theme.button("修改昵称", primary: false, id: "account.rename") { [weak self] in self?.rename() })
            stack.addArrangedSubview(Theme.button("退出当前账户", primary: false, id: "account.logout") { [weak self] in self?.logout() })
        } else {
            add("每一面，都属于你。", style: .title1)
            stack.addArrangedSubview(Theme.button("登录 Vireal", id: "account.login") { [weak self] in
                guard let self else { return }; coordinator?.login(from: self) { [weak self] in self?.render() }
            })
        }
        stack.addArrangedSubview(Theme.button("使用与隐私说明", primary: false) { [weak self] in
            let info = StackController(); info.title = "使用与隐私说明"; info.loadViewIfNeeded()
            info.add("照片与生成", style: .title2); info.add("请仅使用你有权使用的照片。选择的照片先在本机处理，确认生成后会上传到服务端并交给配置的模型处理。照片和视频由服务器按其保留策略管理。")
            info.add("账户与金币", style: .title2); info.add("作品与金币属于登录账户。充值暂未开放；失败退款状态以服务端流水为准。")
            info.add("内测说明", style: .title2); info.add("当前是内部测试客户端。正式上线前需补齐适用的隐私政策、模型处理披露、注销与联系渠道。", color: Theme.muted)
            self?.navigationController?.pushViewController(info, animated: true)
        })
        add("内测版本 · 充值暂未开放", style: .footnote, color: Theme.muted)
    }
    private func rename() {
        let alert = UIAlertController(title: "修改昵称", message: nil, preferredStyle: .alert)
        alert.addTextField { [weak self] field in field.text = self?.state.user?.nickname; field.placeholder = "昵称（最多 50 字）" }
        alert.addAction(UIAlertAction(title: "取消", style: .cancel))
        alert.addAction(UIAlertAction(title: "保存", style: .default) { [weak self, weak alert] _ in
            guard let self, let name = alert?.textFields?.first?.text?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty, name.count <= 50 else { return }
            work = Task { [weak self] in
                guard let self else { return }; do { try await state.rename(name) } catch { showError(error, state: state) }
            }
        }); present(alert, animated: true)
    }
    private func logout() {
        confirm(title: "退出当前 App 会话？", message: "网页或其他设备的会话不受影响。临时照片和下载会在本机清理。") { [weak self] in
            guard let self else { return }
            work = Task { [weak self] in
                guard let self else { return }
                if let warning = await state.signOut() { showError(ClientError.backend(503, warning)) }
            }
        }
    }
}

@MainActor final class WalletController: StackController {
    private let state: AppState
    init(state: AppState) { self.state = state; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "我的金币"; busy(true)
        work = Task { [weak self] in
            guard let self else { return }; defer { busy(false) }
            do {
                try await state.refreshAccount(); try Task.checkCancellation()
                guard let wallet = state.wallet else { return }
                add("✦ \(wallet.balance)", style: .largeTitle, color: Theme.accent)
                add("充值暂未开放", style: .headline)
                add("今日个人剩余 \(wallet.dailyRemaining) 次 · 全站剩余 \(wallet.globalRealRemaining) 次", style: .footnote, color: Theme.muted)
                add("额度重置：\(wallet.resetsAt.formatted(date: .abbreviated, time: .shortened))", style: .footnote, color: Theme.muted)
                add("金币明细", style: .title2)
                if wallet.ledger.isEmpty { add("暂无金币变动", color: Theme.muted) }
                for entry in wallet.ledger { add("\(entry.delta > 0 ? "+" : "")\(entry.delta) · \(entry.reason)"); if let date = entry.createdAt { add(date.formatted(), style: .caption1, color: Theme.muted) } }
            } catch { showError(error, state: state) }
        }
    }
}
