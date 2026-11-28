import UIKit
import PhotosUI
import UniformTypeIdentifiers

@MainActor final class CreateController: StackController, PHPickerViewControllerDelegate {
    private let effect: Effect
    private let state: AppState
    private weak var coordinator: AppCoordinator?
    private var variant: Variant
    private var photos: [Data?]
    private var uploads: [UploadedImage?]
    private var photoIndex = 0
    private var imageVersion = UUID()
    private var consent = false
    private var submitting = false
    private var refreshing = false
    private var photoWork: Task<Void, Never>?
    private let owner: String?

    init(effect: Effect, state: AppState, coordinator: AppCoordinator) {
        self.effect = effect; self.state = state; self.coordinator = coordinator; owner = state.user?.id
        variant = effect.variants.first(where: \.isDefault) ?? effect.variants[0]
        photos = Array(repeating: nil, count: effect.inputImageCount)
        uploads = Array(repeating: nil, count: effect.inputImageCount)
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() { super.viewDidLoad(); title = "创建视频"; navigationItem.largeTitleDisplayMode = .never; render(); refresh() }
    private func refresh() {
        guard !refreshing, !submitting else { return }; refreshing = true; busy(true)
        work = Task { [weak self] in
            guard let self else { return }
            defer { refreshing = false; busy(false); render() }
            do { try await state.refreshAccount() }
            catch { showError(error, state: state) }
        }
    }
    private func render() {
        let offset = scroll.contentOffset
        clear(); add(effect.titleZh, style: .title1)
        if let balance = state.wallet?.balance { add("可用金币 ✦ \(balance)", style: .subheadline, color: Theme.accent) }
        add("添加 \(effect.inputImageCount) 张照片", style: .headline)
        for index in photos.indices {
            if let data = photos[index], let image = UIImage(data: data) {
                let preview = UIImageView(image: image); preview.contentMode = .scaleAspectFill; preview.clipsToBounds = true
                preview.layer.cornerRadius = 14; preview.heightAnchor.constraint(equalToConstant: 180).isActive = true
                preview.accessibilityLabel = "第 \(index + 1) 张已选照片"; stack.addArrangedSubview(preview)
            }
            let choose = Theme.button(photos[index] == nil ? "选择照片 \(index + 1)" : "替换照片 \(index + 1)", primary: false, id: "photo.\(index)") { [weak self] in self?.choose(index: index) }
            choose.isEnabled = !submitting; stack.addArrangedSubview(choose)
            if photos[index] != nil {
                let remove = Theme.button("移除照片 \(index + 1)", primary: false) { [weak self] in
                    guard let self, !submitting else { return }; imageVersion = UUID(); photos[index] = nil; uploads[index] = nil; render()
                }
                remove.isEnabled = !submitting; stack.addArrangedSubview(remove)
            }
        }
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-testing") {
            stack.addArrangedSubview(Theme.button("添加本地测试图片", primary: false, id: "photo.fixture") { [weak self] in
                guard let self else { return }
                let image = UIGraphicsImageRenderer(size: CGSize(width: 200, height: 200)).image { context in
                    Theme.accent.setFill(); context.fill(CGRect(x: 0, y: 0, width: 200, height: 200))
                }
                photos = photos.map { _ in image.jpegData(compressionQuality: 0.8) }; render()
            })
        }
        #endif
        add("所选照片先在本机预览，确认生成后才上传。请只使用你有权使用的照片。", style: .footnote, color: Theme.muted)
        add("视频时长", style: .headline)
        for choice in effect.variants {
            let button = Theme.button("\(choice.id == variant.id ? "✓ " : "")\(choice.durationSeconds) 秒 · ✦ \(choice.coinCost)", primary: choice.id == variant.id) { [weak self] in
                guard let self, !submitting else { return }; variant = choice; render()
            }
            button.isEnabled = !submitting; stack.addArrangedSubview(button)
        }
        let consentRow = UIStackView(); consentRow.spacing = 12; consentRow.alignment = .center
        let toggle = UISwitch(); toggle.isOn = consent; toggle.isEnabled = !submitting; toggle.accessibilityIdentifier = "photo.consent"
        toggle.addAction(UIAction { [weak self, weak toggle] _ in self?.consent = toggle?.isOn == true; self?.render() }, for: .valueChanged)
        consentRow.addArrangedSubview(toggle); consentRow.addArrangedSubview(Theme.label("我有权使用照片，并已获得照片中人物的同意。", style: .footnote)); stack.addArrangedSubview(consentRow)
        let pending: PendingSubmission?
        do { pending = try state.pending() } catch { add(error.localizedDescription, color: .systemRed); return }
        if pending != nil { add("上一笔提交结果待确认，请先在作品中核对原任务。", color: .systemOrange) }
        let block = state.creationBlock(cost: variant.coinCost)
        if let block { add(block, style: .subheadline, color: .systemOrange) }
        let generate = Theme.button(submitting ? "正在提交，请稍候…" : "生成视频 · ✦ \(variant.coinCost)", id: "generation.submit") { [weak self] in self?.requestConfirmation() }
        generate.isEnabled = !submitting && !refreshing && block == nil && pending == nil && consent && photos.allSatisfy { $0 != nil }
        stack.addArrangedSubview(generate)
        stack.addArrangedSubview(Theme.button("刷新服务与金币", primary: false) { [weak self] in self?.refresh() })
        scroll.setContentOffset(offset, animated: false)
    }
    private func choose(index: Int) {
        guard !submitting else { return }; photoIndex = index; imageVersion = UUID()
        var config = PHPickerConfiguration(photoLibrary: .shared()); config.filter = .images; config.selectionLimit = 1
        let picker = PHPickerViewController(configuration: config); picker.delegate = self; present(picker, animated: true)
    }
    func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
        picker.dismiss(animated: true)
        guard let result = results.first else { return }
        let version = imageVersion, index = photoIndex, epoch = state.generation
        result.itemProvider.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { [weak self] data, _ in
            Task { @MainActor [weak self] in
                guard let self, let data, version == imageVersion, epoch == state.generation, owner == state.user?.id else { return }
                photoWork?.cancel()
                photoWork = Task { [weak self] in
                    guard let self else { return }
                    do {
                        let jpeg = try await PhotoProcessor.jpeg(from: data)
                        guard version == imageVersion, epoch == state.generation, owner == state.user?.id else { return }
                        photos[index] = jpeg; uploads[index] = nil; render()
                    } catch { showError(error, state: state) }
                }
            }
        }
    }
    private func requestConfirmation() {
        guard !submitting else { return }
        confirm(title: "确认生成视频", message: "\(effect.titleZh) · \(variant.durationSeconds) 秒\n将上传所选照片并消耗 \(variant.coinCost) 金币。") { [weak self] in self?.submit() }
    }
    private func submit() {
        guard !submitting, consent, photos.allSatisfy({ $0 != nil }), owner == state.user?.id else { return }
        submitting = true; render(); busy(true)
        let epoch = state.generation
        work = Task { [weak self] in
            guard let self else { return }
            defer { submitting = false; busy(false); render() }
            do {
                if try state.pending() != nil { throw ClientError.pendingSubmission }
                try await state.refreshAccount()
                if let block = state.creationBlock(cost: variant.coinCost) { throw ClientError.backend(403, block) }
                for index in photos.indices {
                    guard epoch == state.generation, owner == state.user?.id else { throw ClientError.sessionChanged }
                    if uploads[index]?.expiresAt ?? .distantPast <= Date() {
                        guard let jpeg = photos[index] else { throw ClientError.invalidMedia }
                        uploads[index] = try await state.api.upload(jpeg)
                    }
                }
                guard let owner, owner == state.user?.id, epoch == state.generation,
                      uploads.allSatisfy({ ($0?.expiresAt ?? .distantPast) > Date() }) else { throw ClientError.sessionChanged }
                let request = GenerationRequest(effectId: effect.id, variantId: variant.id, uploadIds: uploads.compactMap { $0?.id })
                let pending = PendingSubmission(owner: owner, key: UUID().uuidString, request: request, createdAt: Date())
                let task = try await state.submit(pending)
                guard epoch == state.generation else { return }
                photos = photos.map { _ in nil }; uploads = uploads.map { _ in nil }
                if let navigationController {
                    var controllers = navigationController.viewControllers; controllers.removeLast()
                    controllers.append(TaskController(task: task, state: state))
                    navigationController.setViewControllers(controllers, animated: true)
                }
            } catch { showError(error, state: state) }
        }
    }
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isMovingFromParent { photoWork?.cancel(); imageVersion = UUID(); photos = photos.map { _ in nil } }
    }
}
