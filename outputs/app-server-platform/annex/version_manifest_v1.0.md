# v1.0 版本清单

## 当前版本

- 当前正式 PRD：`prd/prd_final_v1.0.html`
- 初稿快照：`prd/prd_v1.0.html`
- 当前原型：`prototype/prototype_v1.0.html`
- 当前流程图汇总：`flowcharts/flowcharts_v1.0.html`
- 当前流程图 Markdown：`flowcharts/flowcharts_v1.0.md`
- 当前实现进度：`annex/implementation_progress_v1.0.md`
- 当前本地联调 Runbook：`annex/local_runbook_v1.0.md`

## 原型切片映射

| 功能 | PRD 模块 | 原型路径 |
| --- | --- | --- |
| App 设备号登录 | 功能 1 | `../prototype/prototype_v1.0.html?focus=app-login#app-login` |
| App 资料修改 | 功能 2 | `../prototype/prototype_v1.0.html?focus=app-profile#app-profile` |
| 动态发布 | 功能 3 | `../prototype/prototype_v1.0.html?focus=app-compose#app-compose` |
| 动态流展示 | 功能 3 | `../prototype/prototype_v1.0.html?focus=app-feed#app-feed` |
| 后台用户管理 | 功能 4 | `../prototype/prototype_v1.0.html?focus=admin-users#admin-users` |
| 后台内容管理 | 功能 4 | `../prototype/prototype_v1.0.html?focus=admin-content#admin-content` |
| 后台订单状态 | 功能 5 | `../prototype/prototype_v1.0.html?focus=admin-orders#admin-orders` |
| 后台运营配置 | 功能 6 | `../prototype/prototype_v1.0.html?focus=admin-configs#admin-configs` |

## Mermaid 源文件

- `flowcharts/app_device_login_v1.0.mmd`
- `flowcharts/content_publish_feed_v1.0.mmd`
- `flowcharts/admin_governance_v1.0.mmd`
- `flowcharts/payment_callback_v1.0.mmd`
- `flowcharts/config_delivery_v1.0.mmd`

## v1.0 交付状态

- PRD：完成
- 原型：完成
- 流程图：完成
- 版本切换器：完成
- 后续迭代模板：完成
- 后端 M0-M6 API 切片：完成
- 后台前端 M7 页面切片：完成
- 本地联调 M8 文档：完成
- v1.1 后台操作日志：完成
- v1.1 图片存储抽象：完成
- v1.1 支付回调 shared-secret 验证层：完成

## 下一版本建议

建议继续处理：

1. Apple IAP 与 Google Play 官方生产级 JWS、Pub/Sub 或票据校验。
2. 增加 S3、OSS 或 R2 对象存储适配器。
3. 删除原因、内容举报和恢复能力。
4. 管理后台更细的筛选、搜索和导出。
