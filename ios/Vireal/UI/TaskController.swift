import UIKit
import AVKit
import Photos

@MainActor final class TaskController: StackController {
    private var task: VideoTask
    private let state: AppState
    private let owner: String?
    private var polling: Task<Void, Never>?
    private var media: URL?
    private var player: AVPlayer?
    private var working = false
    init(task: VideoTask, state: AppState) { self.task = task; self.state = state; owner = state.user?.id; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "生成任务"; navigationItem.largeTitleDisplayMode = .never; render()
        NotificationCenter.default.addObserver(self, selector: #selector(foreground), name: UIApplication.didBecomeActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(background), name: UIApplication.willResignActiveNotification, object: nil)
    }
    override func viewWillAppear(_ animated: Bool) { super.viewWillAppear(animated); startPolling() }
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated); polling?.cancel()
        if isMovingFromParent || navigationController?.isBeingDismissed == true {
            work?.cancel(); player?.pause()
            if let media { try? FileManager.default.removeItem(at: media) }; media = nil
        }
    }
    @objc private func foreground() { if isViewLoaded && view.window != nil { startPolling() } }
    @objc private func background() { polling?.cancel() }
    private func startPolling() {
        polling?.cancel()
        polling = Task { [weak self] in
            var delay = 3
            while !Task.isCancelled {
                guard let self, owner == state.user?.id else { return }
                do {
                    let result = try await state.api.task(id: task.id)
                    try Task.checkCancellation(); guard owner == state.user?.id else { return }
                    task = result; render(); delay = 3
                    if result.isTerminal { return }
                } catch {
                    if error is CancellationError { return }
                    state.invalidateIfNeeded(error)
                    if state.user == nil { return }
                    delay = min(30, delay * 2)
                    render(); add("暂时无法刷新进度，稍后会查询同一任务。", style: .footnote, color: .systemOrange)
                }
                do { try await Task.sleep(for: .seconds(delay)) } catch { return }
            }
        }
    }
    private func render() {
        clear(); title = task.isTerminal ? "作品详情" : "生成进度"
        let art = ArtworkView(number: 1); art.heightAnchor.constraint(equalToConstant: 210).isActive = true; stack.addArrangedSubview(art)
        add(task.effectTitle ?? "视频作品", style: .title1)
        add(task.statusTitle, style: .title2, color: task.status == "failed" ? .systemRed : Theme.accent)
        add("\(task.duration) 秒 · ✦ \(task.coinCost.map(String.init) ?? "—")", style: .subheadline, color: Theme.muted)
        if let error = task.error, !error.isEmpty { add(error, color: .systemOrange) }
        if task.status == "failed" { add(task.coinRefundedAt == nil ? "退币状态请以金币明细为准。" : "本次金币已退回，可在金币明细核对。", color: Theme.muted) }
        if task.status == "submission_unknown" { add("结果尚待确认，请查询原任务，不要重复创建。", color: .systemOrange) }
        if !task.isTerminal { add("你可以离开页面，稍后在作品中查看。", color: Theme.muted) }
        if task.isPlayable {
            stack.addArrangedSubview(Theme.button("播放作品", id: "task.play") { [weak self] in self?.useMedia(.play) })
            stack.addArrangedSubview(Theme.button("保存到相册", primary: false, id: "task.save") { [weak self] in self?.useMedia(.save) })
            stack.addArrangedSubview(Theme.button("分享作品", primary: false, id: "task.share") { [weak self] in self?.useMedia(.share) })
            add("有效期至 \(task.expiresAt.formatted(date: .abbreviated, time: .shortened))，请及时保存。", style: .footnote, color: Theme.muted)
        } else if task.status == "expired" || (task.status == "succeeded" && !task.isPlayable) { add("媒体保存期限已结束，无法播放、保存或分享。", color: .systemOrange) }
        stack.addArrangedSubview(Theme.button("刷新原任务", primary: false, id: "task.refresh") { [weak self] in self?.startPolling() })
        if task.isTerminal {
            stack.addArrangedSubview(Theme.button("删除作品记录", primary: false, id: "task.delete") { [weak self] in self?.delete() })
        }
        add("任务编号 \(task.id)", style: .caption1, color: Theme.muted)
    }
    private enum MediaAction { case play, save, share }
    private func useMedia(_ action: MediaAction) {
        guard !working, owner == state.user?.id else { return }
        guard task.isPlayable else { render(); showError(ClientError.invalidMedia); return }
        working = true; busy(true)
        let epoch = state.generation
        work = Task { [weak self] in
            guard let self else { return }; defer { working = false; busy(false) }
            do {
                if media == nil { media = try await state.api.download(id: task.id) }
                guard let media, epoch == state.generation, owner == state.user?.id, task.isPlayable else { throw ClientError.sessionChanged }
                try Task.checkCancellation()
                switch action {
                case .play:
                    let controller = AVPlayerViewController(); let player = AVPlayer(url: media); self.player = player
                    controller.player = player; present(controller, animated: true) { player.play() }
                case .share:
                    let controller = UIActivityViewController(activityItems: [media], applicationActivities: nil)
                    controller.popoverPresentationController?.sourceView = view
                    present(controller, animated: true)
                case .save:
                    let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
                    guard epoch == state.generation else { throw ClientError.sessionChanged }
                    guard status == .authorized || status == .limited else {
                        throw ClientError.backend(403, "相册添加权限未开启。你仍可使用系统分享保存作品。")
                    }
                    try await PHPhotoLibrary.shared().performChanges { PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: media) }
                    guard epoch == state.generation else { return }
                    confirm(title: "已保存到相册", message: "你可以在照片 App 中查看作品。") { }
                }
            } catch { showError(error, state: state) }
        }
    }
    private func delete() {
        guard task.isTerminal, !working else { return }
        confirm(title: "删除这件作品？", message: "删除记录与可删除的输出媒体，已消耗金币不会因此返还。", destructive: true) { [weak self] in
            guard let self else { return }; working = true; busy(true)
            work = Task { [weak self] in
                guard let self else { return }; defer { working = false; busy(false) }
                do { try await state.api.deleteTask(id: task.id); navigationController?.popViewController(animated: true) }
                catch { showError(error, state: state) }
            }
        }
    }
}
