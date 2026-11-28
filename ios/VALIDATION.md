# Vireal UIKit 本地验证结果

2026 年 11 月 21 日，在 Xcode 26.6 上完成以下检查。当时基于候选提交 `1bcff9975f7b9ae6a32a186a4a6db10995e36104` 验证。2026-11-28 已归并到固定开发分支 `codex/pilot-five-global-one-20261101` 并接入 `f40ddbc` 的限定预发布认证兼容；本轮复验结果另记。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 后端登录回归 | 95 项通过 | `test-results/backend/tests.log` 和 `results.xml` |
| Swift 原生逻辑与 HTTP 契约 | 12 项通过 | `test-results/NativeUnitFinal.xcresult` |
| UIKit 完整操作流程 | 1 项通过 | `test-results/NativeFinal.xcresult`，包含完成页截图附件 |
| iPhone Simulator Debug 构建 | 通过 | 测试构建及运行成功 |
| iPhoneOS Release 构建 | 通过，未签名 | `build/DerivedData/Build/Products/Release-iphoneos/Vireal.app` |
| 正式二进制隔离测试实现 | 通过 | 正式二进制不含本地测试令牌和测试服务类 |
| Python 变更静态检查 | 通过 | 修改的后端及本地测试脚本 Ruff 检查通过 |
| 工程及隐私配置 | 通过语法检查 | `Info.plist`、`PrivacyInfo.xcprivacy` |
| 预发布 API 登录适配发布 | SUCCESS，发布后健康检查通过 | 部署 `51b578db-c6ca-41ee-8085-bf4ccec8ddba`，详见 `STAGING.md` |
| 真实 Clerk SDK 与预发布只读连接 | 通过，未进行用户登录 | `test-results/StagingBootstrapSigned.xcresult` |

后端测试使用临时 PostgreSQL 18、本机 Unix socket、合成账户和网络阻断器，完成后已删除测试库。覆盖原生无 `azp`、错误及畸形来源、必要安全字段、pending 会话、网页与原生共用身份、当前会话注销以及网页专用验收边界。

12 项原生检查覆盖日期与可空字段、配置校验、业务 403 与身份错误区分、公共请求不携带 Bearer、multipart 上传、令牌重取时保持请求标识、超时恢复后沿用原提交、账户间待确认记录隔离、退出数据清理、特殊模式关闭、照片方向归一、缩略限制与 GPS 元数据移除。

UIKit 测试在 iOS 26.2 的 iPhone 17 Pro 模拟器中执行邮箱登录、选择本地测试图、照片授权确认、提交生成、等待完成、删除作品、退出与游客状态检查。测试服务只在 Debug 且显式指定 `--ui-testing` 时启用。

## 尚未验证

真实邮箱验证码、业务初始化与鉴权只读请求已于 2026-11-28 通过；真实照片上传、模型生成、实际视频下载、真机 PhotoKit 权限和系统分享尚未联调。预发布地址、公钥、Native API 和邮箱第一因素已核对，API 适配已发布，真实 SDK 初始化及目录读取也已通过。此前 Mac 锁定的阻碍已解除，2026-11-28 已可操作模拟器；真实登录已于本轮通过。

Release 构建是未签名产物，不是可直接安装到实体 iPhone 的 IPA。真机安装需要 Apple 开发者 Team、匹配的 Bundle ID 和签名设置。

本地通过不代表生产发布、公开注册、收款、上架审核或真实生成验收通过。

## 2026-11-28 固定分支复验

接入 `f40ddbc` 的限定预发布 Clerk 校验后，后端登录回归 **98 项通过**，临时测试库已删除；Swift 单元及 HTTP 契约 **12 项通过**；真实 Clerk SDK 与预发布目录、关闭态配置只读连接 **1 项通过**。本轮使用 iOS 26.3 的 iPhone 17 Pro 模拟器和本地签名。

网页 Node 离线测试 **144 项通过**，公开配置与来源离线检查 **20 项通过**；归档交互原型在 Chromium、WebKit 共 **10 组检查通过**。Ruff、资源 plist 和新增大文件检查通过。原生图标经无损压缩满足仓库大小检查。

通过模拟器手动打开普通 Debug 客户端，真实目录成功展示，并进入原生邮箱验证码登录页。随后经本人确认并提供验证码，已在真实 Clerk SDK 完成登录与业务会话初始化，并读取金币与作品。没有上传照片或调用付费模型。

本轮结果保留在本机 `ios/test-results/FixedBranchUnit20261128.xcresult`、`FixedBranchStaging20261128.xcresult`、`ios/test-results/backend/` 与原型 `checks/results/`，这些运行输出不提交。

## 真实账号联调结果

2026-11-28，使用本人确认的既有内测邮箱完成一次真实 Clerk 邮箱验证码登录，App 自动完成业务会话初始化并显示当前账户。真实金币接口返回余额 **0**，个人当天剩余 **5** 次、全站剩余 **30** 次；金币流水为空。真实私人作品列表成功读取，显示暂无作品。

进入真实目录的 `dance-1` 创作页，读取到 5 秒 / 28 金币与 10 秒 / 47 金币规格。页面明确显示当前账户或地区未开放上传和生成，生成按钮禁用；此时未发送上传或生成请求，不能视作实际生成验收。

客户端代码提交 `a58ad68` 的远端六组检查均通过：后端、Docker Compose、Playwright、H5 Chromium/WebKit、代码规范与工作流安全检查。完整生成还需解决账号测试额度、预发布单账号生成准入和地区限制，并准备可用于上传的测试照片；会话冷启动恢复与网页账户 ID 直接比对仍待复验。

验证码与身份令牌不写入验证记录或版本库。
