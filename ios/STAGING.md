# Vireal 原生客户端预发布联调

2026 年 11 月 21 日，从当前预发布网页的公开 meta 配置、Railway 当前实例和 Clerk 公开环境信息核对了以下设置。

| 项目 | 已核对值 |
| --- | --- |
| 网页 | `https://staging-app.usevireal.com` |
| API | `https://staging-api.usevireal.com` |
| Clerk issuer | `https://infinite-shark-285.clerk.accounts.dev` |
| API audience | `vireal-api` |
| Clerk 公钥 | `pk_test_aW5maW5pdGUtc2hhcmstMjg1LmNsZXJrLmFjY291bnRzLmRldiQ` |
| Native API | 已启用 |
| 邮箱第一因素 | `email_code`；不强制第二因素 |
| 既有内测身份 | 已验证邮箱 `52***@qq.com`；等待本人确认可接收验证码 |

公钥是网页本来就公开提供的 SDK 配置。没有将 Clerk Secret Key、Railway 凭据、用户令牌或数据库连接串写入客户端。

## 已部署的服务端版本

本次仅发布预发布 API，部署 ID 为 `51b578db-c6ca-41ee-8085-bf4ccec8ddba`，Railway 已报告 `SUCCESS`，活动部署也已切换到该 ID。

当前预发布原版本是 `b37df553933d883d0a11643b93d51bbe1d42e773`。在此版本上加入原生 Clerk 无 `azp` 的兼容和对应测试，另加入 `.railwayignore` 排除无效的开发辅助链接；发布提交为 `57b4d5e615edead38a08d41c440690311477f8d0`。没有把另一个候选分支的新表或其他业务改动一起发布，也未新增迁移。

首次上传在扫描开发辅助链接时失败，发布平台确认当时没有生成新部署。补上排除规则后才完成上述唯一的新部署。原有预部署脚本保留，使用相同版本的迁移和初始化程序。

后端针对实际预发布基线重新运行的 95 项回归全部通过。发布后的健康检查和公开配置读取均为 HTTP 200。注册、充值、上传和生成仍关闭；生产 API、生产 Worker、预发布 Worker 均未部署或重启。

## 原生连接检查

使用官方 ClerkKit 1.7.3，在 iOS 模拟器上通过真实 SDK 初始化、真实预发布目录读取和关闭态配置读取。该只读检查已经通过，尚不代表用户登录成功。

未签名模拟器构建曾使 Keychain 返回 `-34018`。使用 Xcode 模拟器本地签名后，SDK 安全存储与初始化检查通过。没有更改 SDK 的安全存储实现，也没有申请新证书。

程序库默认请求标识曾被 Cloudflare 返回 `1010`。客户端现使用明确的 `Vireal-iOS/0.1` 应用标识，API 请求已成功。没有使用浏览器伪装标识，也没有关闭或绕过 Cloudflare 安全规则。Cloudflare 的[官方 1010 说明](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)建议非浏览器客户端使用描述性的应用标识。

## 下一步与边界

真实邮箱登录尚未执行：需要本人确认现有内测邮箱并接收验证码。2026-11-28 已能操作模拟器，真实目录已显示并进入邮箱登录页。不会通过管理 API 为用户铸造登录令牌代替验证码。

登录后先核对业务初始化、账户 ID、钱包、作品与会话恢复，再准备单次上传和生成验证。预发布当前的上传和生成仍关闭，登录成功不会自动打开这些入口。真实生成前要核对账户余额、可用规格、现有单次验收约束、模型费用和 Worker 状态，不能直接打开面向所有用户的生成开关。

目前没有发送真实验证码、上传照片、发起付费模型调用或创建收款订单。

发布及检查记录位于项目根目录 `output/ios-staging-integration-20261121/`；原生只读检查结果在 `ios/test-results/StagingBootstrapSigned.xcresult`。

## 2026-11-28 运行态复核

通过当前预发布 HTML 再次核对 API 地址与 Clerk 公钥，两者均与 `Config/Staging.xcconfig` 一致。预发布 API 的活动部署仍为 `51b578db-c6ca-41ee-8085-bf4ccec8ddba`，API 和预发布 Worker 的状态均为 `SUCCESS`；健康检查与公开配置均返回 200。四个业务提示仍关闭，本次请求的地区提示为不可用。没有重复发布相同适配，也未把包含其他迁移的开发候选覆盖到该服务。

使用签名模拟器再次通过真实 Clerk SDK 启动及只读目录检查。真实邮箱登录、鉴权上传、实际生成和私人作品管理仍未完成；需要本人确认内测邮箱并完成验证码登录后继续。当前运行版本的发布来源与合并后开发分支不同，不应将开发推送当作运行版本更新。
