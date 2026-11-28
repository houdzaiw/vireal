# Vireal iPhone UIKit 客户端

原生 Swift 6 + UIKit 应用，最低 iOS 17，使用 ClerkKit 1.7.3 和现有 Vireal App API。客户端包含邮箱验证码登录、业务会话恢复、效果目录、单图或双图上传、视频生成、任务查询、作品下载播放、相册保存、系统分享、删除、金币明细与昵称管理。充值与公开注册保持关闭。

## 打开与运行

用 Xcode 26.6 或更新版本打开 `Vireal.xcodeproj`，选择 Vireal scheme 和 iPhone 模拟器。工程已经生成，普通使用不需要安装 XcodeGen。

1. Debug 已默认载入 `Config/Staging.xcconfig`，地址和公钥已与当前预发布网页核对。若需要覆盖配置，再复制 `Config/Local.example.xcconfig` 为忽略的 `Config/Local.xcconfig`。
2. API 为 `https://staging-api.usevireal.com`，Clerk 实例为 `infinite-shark-285.clerk.accounts.dev`。公钥在 `Staging.xcconfig` 中，不包含任何 Secret Key、密码或 JWT。URL 使用 `https:/$()/...` 写法，避免 xcconfig 将双斜线当注释。Release 需单独指定目标环境，不能默认当作生产包。
3. 在 Clerk 对应实例核对 Native API 和原生应用注册。默认 Bundle ID 是 `com.usevireal.ios`，真机安装前按你的 Apple 账户设置 Team、Bundle ID 和所需关联域名能力。修改标识后同步 Clerk 注册。
4. 默认会话令牌的 `aud` 必须与服务端 `CLERK_AUDIENCE` 一致。不要用缺失 `sid` 的普通 JWT 模板代替会话令牌。只有已验证模板保留全部必要会话字段时才设置可选模板名。
5. 使用已获准的内测账户登录。没有自动注册、管理员密钥或设备 UUID 登录后门。

未配置时 App 会明确显示配置缺失。Debug 仅在 `--ui-testing` 或 XCTest 宿主环境下启用内存测试服务；Release 不包含这些测试实现。普通 Debug 启动连接预发布服务。

`project.yml` 是工程结构来源，新增文件或调整工程设置后可以运行 `xcodegen generate --spec project.yml`。Clerk SDK 及间接依赖已固定在 `Package.resolved`。

## 服务端变更

同分支的 `backend/app/services/clerk_auth.py` 仅在预发布环境、既有 Clerk issuer、JWKS 与网页来源配置均匹配时，允许已验证 Clerk 会话令牌缺少浏览器 `azp` 字段；其他环境仍要求该字段，保持签名、算法、issuer、audience、有效期、`sub/sid` 和 pending 状态验证。存在但为空、null、类型错误或不在白名单中的来源仍然拒绝。`authorized_party` 改为可空类型。

业务会话与 API 路径不变，无数据库迁移。原生端先通过 Clerk 验证邮箱，再调用 `/api/v1/app/auth/session`。同一个 Clerk issuer 与 subject 映射到网页已有 App 用户。每个会话独立登记，退出当前 App 不撤销网页的另一会话。网页专用预发布验收仍严格要求网页来源，原生令牌不能绕过。

预发布已于 2026 年 11 月 21 日部署此修改，部署 ID `51b578db-c6ca-41ee-8085-bf4ccec8ddba`。为避免引入其他候选中的七张新表，发布基于当时实际预发布提交 `b37df553933d883d0a11643b93d51bbe1d42e773`，只合入登录改动、回归测试及开发目录打包排除规则，固定发布提交为 `57b4d5e615edead38a08d41c440690311477f8d0`。生产 API、生产 Worker 和预发布 Worker 的部署 ID 均未变化。

## 上传与生成

- 系统照片选择器只读取用户选中的图片，不请求整个图库权限。图片在后台缩略、处理方向、去除原始 EXIF 后编码为 JPEG，最大 5 MB；照片仅在内存中预览，确认生成后才上传。
- 时长、图片数量和金币费用读取目录规格，提交只包含效果 ID、规格 ID 和上传 ID。金币、地区、服务开关、并发和额度由服务端再次验证。
- 确认生成时先保存每个业务账户独立的原参数与幂等 UUID，使用文件保护并排除备份，不保存 bearer 或照片。网络超时、退出、重启都不会自动生成新标识。
- 作品页存在待确认提交时提供核对入口；核对明确告知可能开始此前已确认、但服务器尚未接收的原生成。核对沿用同参数、同标识，不自动开启下一笔。服务端没有接受结果前保留该记录，不提供静默清空重新付费的操作。
- 当前任务前台每 3 秒查询，失败以 6/12/24/30 秒退避，终态停止；作品存在进行中任务时每 10 秒刷新，支持分页。进入后台停止轮询，返回前台重新查询。
- 视频通过本人鉴权的下载接口落到受保护的临时文件，再供 AVPlayer、PhotoKit 和系统分享使用。避免把 Bearer 附加到外部媒体地址。保存成功仅在 PhotoKit 完成后提示；相册权限拒绝仍可分享。
- 退出立即移除个人界面，清除下载，并通过 Clerk SDK 清理本机持久身份；远端撤销失败会明确提示。未确认的原生成按业务账户留存，方便下次登录核对，不会泄露给其他账户。

## 验证命令

原生构建与测试，设备 ID 改成 `xcrun simctl list devices available` 中的可用 iPhone：

```sh
xcodebuild -project Vireal.xcodeproj -scheme Vireal \
  -destination 'platform=iOS Simulator,id=YOUR_DEVICE_ID' \
  -derivedDataPath build/DerivedData \
  -clonedSourcePackagesDirPath build/SourcePackages \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- test
```

真实 Clerk 会使用 Keychain。模拟器也需要 Xcode 的本地签名与应用标识权限；关闭签名构建可用于编译，但会导致真实 SDK 的 Keychain `-34018`。以上命令使用模拟器本地签名，不创建 Apple 证书或配置文件。实体 iPhone 仍需自己的开发团队签名。

只读预发布连接检查可显式运行 `VirealLive` scheme，并使用 `-only-testing:VirealTests/LiveServiceTests`。它初始化真实 Clerk SDK、读取真实目录与关闭态配置，不发送邮箱验证码、不上传、不生成。默认测试不会运行此网络检查。

在仓库根目录用具备依赖的 Python 执行后端回归：

```sh
python ios/scripts/check-backend.py --pg-bin /path/to/postgresql-18/bin
```

脚本只创建一次性、本机 Unix socket 的 PostgreSQL 测试库，注入合成配置，启用仓库网络阻断器，不读取真实 `.env`，不会连接线上数据库、发送邮件、调用模型或付款。完成后关闭并删除测试库。

## 已验证与待联调

验证结果见 `VALIDATION.md` 和 `STAGING.md`。本地界面测试使用测试服务，不能替代真实登录与生成验收。目前已完成预发布发布、公开配置核对、Native API 与邮箱验证码能力核查，以及真实 SDK 的只读初始化和目录连接；2026-11-28 已完成既有内测邮箱真实验证码登录、业务初始化、金币及作品读取。

1. 已完成既有账户的真实验证码登录、业务初始化、金币与作品读取；与网页会话账户 ID 的直接比对仍待完成。
2. 在签名的实体 iPhone 上复验登录与会话恢复。
3. 满足既有服务恢复与账户、地区、费用准入后，再由获准测试者确认一次真实照片上传和生成。
4. 验证后台恢复、状态未知核对、播放与相册保存、系统分享、删除和两设备会话隔离。

预发布登录补丁已部署；生产未改动，Worker 未重启，注册、充值、上传和生成入口仍关闭。正式上架还需补齐账号注销、苹果内购、正式政策与适用的内容安全要求。

## 官方参考

[Clerk iOS](https://clerk.com/docs/ios/getting-started/quickstart)、[认证接口](https://clerk.com/docs/ios/reference/native-mobile/auth)、[令牌验证](https://clerk.com/docs/guides/sessions/manual-jwt-verification)。实现使用 UIKit，而非将网页嵌入 WKWebView。
