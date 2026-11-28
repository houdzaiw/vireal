import UIKit
import AVKit

@MainActor final class CatalogController: StackController {
    private let state: AppState
    private weak var coordinator: AppCoordinator?
    private var catalog: Catalog?
    private var selected = "all"
    init(state: AppState, coordinator: AppCoordinator) { self.state = state; self.coordinator = coordinator; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "发现"
        let refresh = UIRefreshControl(); refresh.addTarget(self, action: #selector(load), for: .valueChanged); scroll.refreshControl = refresh
        load()
    }
    @objc private func load() {
        work?.cancel(); busy(true)
        work = Task { [weak self] in
            guard let self else { return }
            defer { busy(false); scroll.refreshControl?.endRefreshing() }
            do { catalog = try await state.api.catalog(); try Task.checkCancellation(); render() }
            catch { clear(); add("灵感暂时无法载入", style: .title2); add(error.localizedDescription, color: Theme.muted); stack.addArrangedSubview(Theme.button("重试") { [weak self] in self?.load() }) }
        }
    }
    private func render() {
        clear(); add("VIREAL ✦", style: .title1, color: Theme.accent)
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-testing") { add("本地界面测试 · 非真实服务", style: .caption1, color: Theme.accent) }
        #endif
        let categories = catalog?.categories ?? []
        let bar = UIScrollView(); bar.showsHorizontalScrollIndicator = false
        let row = UIStackView(); row.axis = .horizontal; row.spacing = 8
        row.translatesAutoresizingMaskIntoConstraints = false; bar.addSubview(row)
        NSLayoutConstraint.activate([row.leadingAnchor.constraint(equalTo: bar.contentLayoutGuide.leadingAnchor),row.trailingAnchor.constraint(equalTo: bar.contentLayoutGuide.trailingAnchor),row.topAnchor.constraint(equalTo: bar.contentLayoutGuide.topAnchor),row.bottomAnchor.constraint(equalTo: bar.contentLayoutGuide.bottomAnchor),row.heightAnchor.constraint(equalTo: bar.frameLayoutGuide.heightAnchor)])
        for (id, title) in [("all", "精选")] + categories.map({ ($0.slug, $0.nameZh) }) {
            row.addArrangedSubview(Theme.button(title, primary: selected == id) { [weak self] in self?.selected = id; self?.render() })
        }
        stack.addArrangedSubview(bar); add("找到你的下一种\n可能性。", style: .largeTitle)
        let effects = categories.filter { selected == "all" || $0.slug == selected }.flatMap(\.effects)
        if effects.isEmpty { add("该分类暂无可用效果，试试其他分类。", color: Theme.muted) }
        var cards: [UIView] = []
        for (index, effect) in effects.enumerated() {
            let card = UIControl(); card.accessibilityIdentifier = "effect.\(effect.slug)"
            card.isAccessibilityElement = true
            card.accessibilityLabel = "\(effect.titleZh)，\(effect.inputImageCount) 张照片，\(effect.variants.first?.coinCost ?? 0) 金币起"
            card.accessibilityTraits = .button
            let content = UIStackView(); content.axis = .vertical; content.spacing = 10; content.isUserInteractionEnabled = false
            let art = ArtworkView(number: index + 1); art.heightAnchor.constraint(equalToConstant: index == 0 ? 250 : 180).isActive = true
            art.loadCover(state.api.publicURL(effect.posterUrl))
            content.addArrangedSubview(art); content.addArrangedSubview(Theme.label(effect.titleZh, style: .title2))
            content.addArrangedSubview(Theme.label("\(effect.inputImageCount) 张照片 · ✦ \(effect.variants.map(\.coinCost).min() ?? 0) 起", style: .subheadline, color: Theme.muted))
            content.translatesAutoresizingMaskIntoConstraints = false; card.addSubview(content)
            NSLayoutConstraint.activate([content.topAnchor.constraint(equalTo: card.topAnchor),content.bottomAnchor.constraint(equalTo: card.bottomAnchor),content.leadingAnchor.constraint(equalTo: card.leadingAnchor),content.trailingAnchor.constraint(equalTo: card.trailingAnchor)])
            card.addAction(UIAction { [weak self] _ in
                guard let self, let coordinator else { return }
                navigationController?.pushViewController(EffectController(effect: effect, state: state, coordinator: coordinator), animated: true)
            }, for: .touchUpInside)
            cards.append(card)
        }
        if let first = cards.first { stack.addArrangedSubview(first) }
        for index in stride(from: 1, to: cards.count, by: traitCollection.preferredContentSizeCategory.isAccessibilityCategory ? 1 : 2) {
            if traitCollection.preferredContentSizeCategory.isAccessibilityCategory {
                stack.addArrangedSubview(cards[index])
            } else {
                let row = UIStackView(); row.axis = .horizontal; row.spacing = 12; row.alignment = .top; row.distribution = .fillEqually
                row.addArrangedSubview(cards[index]); row.addArrangedSubview(index + 1 < cards.count ? cards[index + 1] : UIView())
                stack.addArrangedSubview(row)
            }
        }
    }
}

@MainActor final class EffectController: StackController {
    private let effect: Effect
    private let state: AppState
    private weak var coordinator: AppCoordinator?
    init(effect: Effect, state: AppState, coordinator: AppCoordinator) { self.effect = effect; self.state = state; self.coordinator = coordinator; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "效果详情"; navigationItem.largeTitleDisplayMode = .never
        let art = ArtworkView(number: 1); art.heightAnchor.constraint(equalToConstant: 280).isActive = true; stack.addArrangedSubview(art)
        art.loadCover(state.api.publicURL(effect.posterUrl))
        if let preview = state.api.publicURL(effect.previewVideoUrl) {
            stack.addArrangedSubview(Theme.button("播放效果预览", primary: false) { [weak self] in
                let player = AVPlayerViewController(); player.player = AVPlayer(url: preview)
                self?.present(player, animated: true) { player.player?.play() }
            })
        } else { add("效果媒体暂未配置，显示品牌占位图。", style: .caption1, color: Theme.muted) }
        add(effect.titleZh, style: .largeTitle); add(effect.description ?? "选择照片，让静止瞬间成为动态影像。", color: Theme.muted)
        add("\(effect.inputImageCount) 张照片 · \(effect.variants.map { String($0.durationSeconds) }.joined(separator: " / ")) 秒")
        add("请使用清晰、无遮挡的人物照片，并确保获得照片中人物的同意。", style: .subheadline, color: Theme.muted)
        let button = Theme.button("使用此效果", id: "effect.use") { [weak self] in
            guard let self else { return }; coordinator?.create(effect: effect, from: self)
        }
        button.isEnabled = !effect.variants.isEmpty; stack.addArrangedSubview(button)
    }
}
