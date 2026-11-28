import UIKit

@MainActor enum Theme {
    static let background = UIColor(red: 9/255, green: 11/255, blue: 13/255, alpha: 1)
    static let panel = UIColor(red: 21/255, green: 26/255, blue: 29/255, alpha: 1)
    static let accent = UIColor(red: 183/255, green: 242/255, blue: 1, alpha: 1)
    static let muted = UIColor.secondaryLabel
    static func label(_ text: String = "", style: UIFont.TextStyle = .body, color: UIColor = .label) -> UILabel {
        let label = UILabel(); label.text = text; label.font = .preferredFont(forTextStyle: style)
        label.adjustsFontForContentSizeCategory = true; label.textColor = color; label.numberOfLines = 0
        return label
    }
    static func button(_ title: String, primary: Bool = true, id: String? = nil, action: @escaping @MainActor () -> Void) -> UIButton {
        var config = primary ? UIButton.Configuration.filled() : .tinted()
        config.title = title; config.cornerStyle = .large
        config.baseBackgroundColor = primary ? accent : panel
        config.baseForegroundColor = primary ? background : accent
        config.contentInsets = .init(top: 15, leading: 16, bottom: 15, trailing: 16)
        let button = UIButton(configuration: config, primaryAction: UIAction { _ in action() })
        button.accessibilityIdentifier = id
        button.heightAnchor.constraint(greaterThanOrEqualToConstant: 52).isActive = true
        return button
    }
}

@MainActor class StackController: UIViewController {
    let stack = UIStackView()
    let scroll = UIScrollView()
    var work: Task<Void, Never>?
    private let spinner = UIActivityIndicatorView(style: .medium)

    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = Theme.background
        stack.axis = .vertical; stack.spacing = 18; stack.translatesAutoresizingMaskIntoConstraints = false
        scroll.translatesAutoresizingMaskIntoConstraints = false; scroll.keyboardDismissMode = .interactive
        view.addSubview(scroll); scroll.addSubview(stack)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: view.leadingAnchor),scroll.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 16),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -28),
            stack.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor, constant: -20),
            stack.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor, constant: -40),
        ])
    }
    func clear() { stack.arrangedSubviews.forEach { $0.removeFromSuperview() } }
    func add(_ text: String, style: UIFont.TextStyle = .body, color: UIColor = .label) { stack.addArrangedSubview(Theme.label(text, style: style, color: color)) }
    func busy(_ busy: Bool) {
        if busy { spinner.startAnimating(); navigationItem.rightBarButtonItem = UIBarButtonItem(customView: spinner) }
        else { spinner.stopAnimating(); navigationItem.rightBarButtonItem = nil }
    }
    func showError(_ error: Error, state: AppState? = nil) {
        if error is CancellationError { return }
        state?.invalidateIfNeeded(error)
        let alert = UIAlertController(title: "暂时无法完成", message: error.localizedDescription, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "知道了", style: .default))
        if presentedViewController == nil { present(alert, animated: true) }
    }
    func confirm(title: String, message: String, destructive: Bool = false, action: @escaping @MainActor () -> Void) {
        let alert = UIAlertController(title: title, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "取消", style: .cancel))
        alert.addAction(UIAlertAction(title: "确认", style: destructive ? .destructive : .default) { _ in action() })
        present(alert, animated: true)
    }
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isMovingFromParent || navigationController?.isBeingDismissed == true { work?.cancel() }
    }
}

@MainActor final class ArtworkView: UIView {
    private let gradient = CAGradientLayer()
    private let number = Theme.label("01", style: .largeTitle, color: .white.withAlphaComponent(0.7))
    private var imageWork: Task<Void, Never>?
    init(number: Int) {
        super.init(frame: .zero); layer.cornerRadius = 20; clipsToBounds = true
        gradient.colors = [UIColor(red: 0.18, green: 0.36, blue: 0.42, alpha: 1).cgColor, Theme.background.cgColor]
        gradient.startPoint = .zero; gradient.endPoint = CGPoint(x: 1, y: 1); layer.addSublayer(gradient)
        self.number.text = String(format: "%02d", number); self.number.font = .systemFont(ofSize: 70, weight: .ultraLight)
        self.number.translatesAutoresizingMaskIntoConstraints = false; addSubview(self.number)
        NSLayoutConstraint.activate([self.number.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 20),self.number.centerYAnchor.constraint(equalTo: centerYAnchor)])
        isAccessibilityElement = false
    }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func layoutSubviews() { super.layoutSubviews(); gradient.frame = bounds }
    deinit { imageWork?.cancel() }
    func loadCover(_ url: URL?) {
        guard let url else { return }
        imageWork?.cancel()
        imageWork = Task { [weak self] in
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
                guard let response = response as? HTTPURLResponse, response.statusCode == 200,
                      response.mimeType?.hasPrefix("image/") == true, data.count < 10 * 1024 * 1024 else { return }
                let thumbnail = try await PhotoProcessor.jpeg(from: data)
                try Task.checkCancellation()
                guard let self, let image = UIImage(data: thumbnail) else { return }
                let view = UIImageView(image: image); view.contentMode = .scaleAspectFill; view.clipsToBounds = true
                view.translatesAutoresizingMaskIntoConstraints = false; addSubview(view)
                NSLayoutConstraint.activate([view.topAnchor.constraint(equalTo: topAnchor),view.bottomAnchor.constraint(equalTo: bottomAnchor),view.leadingAnchor.constraint(equalTo: leadingAnchor),view.trailingAnchor.constraint(equalTo: trailingAnchor)])
            } catch { /* Keep the numbered brand fallback when media is unavailable. */ }
        }
    }
}
