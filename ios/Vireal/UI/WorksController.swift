import UIKit

@MainActor final class WorksController: StackController {
    private let state: AppState
    private weak var coordinator: AppCoordinator?
    private var items: [VideoTask] = []
    private var total = 0
    private var filter = 0
    private var loading = false
    private var polling: Task<Void, Never>?
    private var itemsOwner: String?
    init(state: AppState, coordinator: AppCoordinator) { self.state = state; self.coordinator = coordinator; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "我的作品"
        let refresh = UIRefreshControl(); refresh.addTarget(self, action: #selector(reload), for: .valueChanged); scroll.refreshControl = refresh
        NotificationCenter.default.addObserver(self, selector: #selector(identityChanged), name: AppState.didChange, object: state)
        NotificationCenter.default.addObserver(self, selector: #selector(foreground), name: UIApplication.didBecomeActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(background), name: UIApplication.willResignActiveNotification, object: nil)
    }
    override func viewWillAppear(_ animated: Bool) { super.viewWillAppear(animated); reload(); startPolling() }
    override func viewDidDisappear(_ animated: Bool) { super.viewDidDisappear(animated); polling?.cancel(); work?.cancel() }
    @objc private func identityChanged() {
        if itemsOwner != state.user?.id {
            work?.cancel(); polling?.cancel(); items = []; total = 0
            itemsOwner = state.user?.id; render()
        }
    }
    @objc private func foreground() { if isViewLoaded && view.window != nil { reload(); startPolling() } }
    @objc private func background() { polling?.cancel() }
    @objc private func reload() { load(more: false) }
    private func load(more: Bool) {
        guard state.user != nil else { render(); scroll.refreshControl?.endRefreshing(); return }
        guard !loading else { return }; loading = true; busy(true)
        let epoch = state.generation
        work = Task { [weak self] in
            guard let self else { return }
            defer { loading = false; busy(false); scroll.refreshControl?.endRefreshing() }
            do {
                let page = try await state.api.tasks(skip: more ? items.count : 0)
                guard state.generation == epoch else { return }; try Task.checkCancellation()
                items = more ? items + page.data.filter { next in !items.contains { $0.id == next.id } } : page.data
                itemsOwner = state.user?.id
                total = page.count; render()
            } catch { showError(error, state: state); render() }
        }
    }
    private func startPolling() {
        polling?.cancel()
        polling = Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(10)) } catch { return }
                guard let self, state.user != nil else { return }
                if items.contains(where: { !$0.isTerminal }) { reload() }
            }
        }
    }
    private func render() {
        clear()
        guard state.user != nil else {
            add("让灵感有迹可循", style: .title1); add("登录后查看你的生成任务与作品。", color: Theme.muted)
            stack.addArrangedSubview(Theme.button("登录查看作品", id: "works.login") { [weak self] in
                guard let self else { return }; coordinator?.login(from: self) { [weak self] in self?.reload() }
            }); return
        }
        do {
            if let pending = try state.pending() {
                add("有一笔提交结果待确认", style: .headline)
                add("\(pending.createdAt.formatted(date: .abbreviated, time: .shortened)) 提交。核对将使用原参数和原请求标识，不会另开一笔生成。", style: .footnote, color: Theme.muted)
                stack.addArrangedSubview(Theme.button("核对原任务", id: "works.recover") { [weak self] in self?.recover(pending) })
            }
        } catch { add(error.localizedDescription, color: .systemRed) }
        let segment = UISegmentedControl(items: ["全部", "进行中", "已完成"]); segment.selectedSegmentIndex = filter
        segment.addAction(UIAction { [weak self, weak segment] _ in self?.filter = segment?.selectedSegmentIndex ?? 0; self?.render() }, for: .valueChanged)
        stack.addArrangedSubview(segment)
        let visible = items.filter { filter == 0 || (filter == 1 ? !$0.isTerminal : $0.status == "succeeded") }
        if visible.isEmpty { add("暂无\(filter == 1 ? "进行中的任务" : "作品")", style: .title2); add("选择喜欢的效果，开始你的下一次创作。", color: Theme.muted) }
        for item in visible {
            let title = "\(item.effectTitle ?? "视频作品")\n\(item.duration) 秒 · \(item.statusTitle)"
            let button = Theme.button(title, primary: false, id: "task.\(item.id)") { [weak self] in
                guard let self else { return }; coordinator?.openTask(item, from: self)
            }
            button.titleLabel?.numberOfLines = 0; stack.addArrangedSubview(button)
        }
        if items.count < total { stack.addArrangedSubview(Theme.button("加载更多", primary: false) { [weak self] in self?.load(more: true) }) }
        stack.addArrangedSubview(Theme.button("刷新作品", primary: false, id: "works.refresh") { [weak self] in self?.reload() })
        add("作品媒体有保存期限，请及时下载。", style: .footnote, color: Theme.muted)
    }
    private func recover(_ pending: PendingSubmission) {
        guard !loading else { return }
        confirm(title: "核对原提交", message: "将向服务器重发同参数、同标识的原请求。服务器若已经接收，会返回原任务；若尚未接收，可能开始你此前确认的那次生成。") { [weak self] in
            guard let self else { return }; loading = true; busy(true)
            work = Task { [weak self] in
                guard let self else { return }; defer { loading = false; busy(false) }
                do { let result = try await state.submit(pending); coordinator?.openTask(result, from: self) }
                catch { showError(error, state: state) }
            }
        }
    }
}
