import UIKit

@MainActor final class LoginController: StackController {
    private let state: AppState
    private let completed: @MainActor () -> Void
    private let field = UITextField()
    private let errorLabel = Theme.label("", style: .subheadline, color: .systemRed)
    private var verification = false
    private var verified = false
    private var submitting = false
    private var email = ""

    init(state: AppState, completed: @escaping @MainActor () -> Void) {
        self.state = state; self.completed = completed; super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError("Programmatic UI") }
    override func viewDidLoad() {
        super.viewDidLoad(); title = "登录 Vireal"
        navigationItem.leftBarButtonItem = UIBarButtonItem(systemItem: .cancel, primaryAction: UIAction { [weak self] _ in self?.dismiss(animated: true) })
        render()
    }
    private func render() {
        clear(); add("VIREAL ✦", style: .largeTitle, color: Theme.accent)
        add(verification ? "查看你的邮箱" : "让每一次灵感，都有迹可循。", style: .title1)
        add(verification ? "请输入发送到 \(email) 的验证码。" : "使用与网页相同的邮箱，查看已有作品与金币。内测版暂不开放新用户注册。", color: Theme.muted)
        field.text = ""; field.borderStyle = .roundedRect
        field.autocapitalizationType = .none; field.autocorrectionType = .no
        field.keyboardType = verification ? .numberPad : .emailAddress
        field.textContentType = verification ? .oneTimeCode : .emailAddress
        field.placeholder = verification ? "邮箱验证码" : "邮箱地址"
        field.accessibilityIdentifier = verification ? "login.code" : "login.email"
        field.heightAnchor.constraint(greaterThanOrEqualToConstant: 52).isActive = true
        stack.addArrangedSubview(field); stack.addArrangedSubview(errorLabel)
        stack.addArrangedSubview(Theme.button(verified ? "重试同步账户" : verification ? "验证并继续" : "发送验证码", id: "login.continue") { [weak self] in self?.proceed() })
        if verification {
            stack.addArrangedSubview(Theme.button("重新输入邮箱", primary: false) { [weak self] in
                guard let self, !submitting else { return }
                verification = false; verified = false; errorLabel.text = ""; render()
            })
        }
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-testing") { add("本地界面测试 · 使用验证码 123456", style: .caption1, color: Theme.accent) }
        #endif
    }
    private func proceed() {
        guard !submitting else { return }
        let input = field.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !verification && (!input.contains("@") || input.contains(" ")) { errorLabel.text = "请输入有效的邮箱地址。"; return }
        if verification && !verified && (input.count < 4 || input.count > 10 || !input.allSatisfy(\.isNumber)) { errorLabel.text = "请输入有效的邮箱验证码。"; return }
        submitting = true; errorLabel.text = ""; busy(true); field.resignFirstResponder()
        work = Task { [weak self] in
            guard let self else { return }
            defer { submitting = false; busy(false) }
            do {
                if !verification {
                    try await state.auth.sendCode(email: input)
                    try Task.checkCancellation(); email = input; verification = true; render(); field.becomeFirstResponder()
                } else {
                    if !verified { try await state.auth.verifyCode(input); verified = true }
                    try await state.initializeSession()
                    try Task.checkCancellation(); completed()
                }
            } catch {
                if error is CancellationError { return }
                errorLabel.text = error.localizedDescription
                if verified { render() } // Retry only the business sync, never send a second OTP.
            }
        }
    }
}
