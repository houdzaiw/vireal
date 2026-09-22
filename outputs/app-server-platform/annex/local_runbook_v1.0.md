# 本地联调 Runbook v1.0

## 适用范围

本 runbook 用于本地或内网跑通 v1.0 首版能力：

- App 设备号登录
- App 用户资料修改
- 本地图片上传
- 文字/图片动态发布和动态流
- 后台 App 用户、内容、订单、运营配置管理
- Apple IAP、Google Play 本地模拟支付回调
- 支付回调 shared-secret 防护模式

## 本地服务

```text
Frontend: http://localhost:5173
Backend API: http://localhost:8000
Swagger Docs: http://localhost:8000/docs
Mailpit: http://localhost:8025
PostgreSQL: localhost:5432
```

开发期前端建议使用 `http://localhost:5173`，不要混用 `http://127.0.0.1:5173`，否则可能触发 CORS 限制。

## 启动顺序

### 1. 启动数据库和 Mailpit

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
docker compose up -d db mailpit
docker compose ps db mailpit
```

期望结果：`db` 和 `mailpit` 都是 `healthy`。

### 2. 初始化数据库

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server/backend
uv run alembic upgrade head
uv run python app/initial_data.py
```

管理员账号以 `server/.env` 为准：

```text
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=changethis
APP_IMAGE_STORAGE_BACKEND=local
LOCAL_UPLOAD_DIR=uploads
MAX_UPLOAD_IMAGE_BYTES=5242880
PAYMENT_WEBHOOK_VERIFICATION_MODE=local
```

### 3. 启动后端

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

检查：

```bash
curl -I http://localhost:8000/docs
```

### 4. 启动前端

另开终端：

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
bun run dev --host 0.0.0.0
```

打开：

```text
http://localhost:5173/login
```

## 基础变量

以下 curl 示例默认在 `server/` 目录执行：

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server
API=http://localhost:8000
set -a
source .env
set +a
```

获取后台管理员 token：

```bash
ADMIN_TOKEN=$(curl -s -X POST "$API/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=$FIRST_SUPERUSER" \
  --data-urlencode "password=$FIRST_SUPERUSER_PASSWORD" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

获取 App token：

```bash
DEVICE_UUID="ios-local-device-$(date +%s)"
APP_LOGIN_JSON=$(curl -s -X POST "$API/api/v1/app/auth/device-login" \
  -H "Content-Type: application/json" \
  -d "{\"device_uuid\":\"$DEVICE_UUID\",\"platform\":\"ios\"}")

APP_TOKEN=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' <<< "$APP_LOGIN_JSON")
APP_USER_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["app_user"]["id"])' <<< "$APP_LOGIN_JSON")
```

复用同一个 `DEVICE_UUID` 再登录，会返回同一个 App 用户；换一个设备号会生成新用户。

## App 资料和动态联调

### 1. 修改昵称

```bash
curl -s -X PATCH "$API/api/v1/app/users/me" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nickname":"Local Tester"}'
```

### 2. 准备一张本地测试图片

```bash
python3 - <<'PY'
import base64
from pathlib import Path

png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
Path("/tmp/app-test.png").write_bytes(base64.b64decode(png))
PY
```

### 3. 上传图片

```bash
UPLOAD_JSON=$(curl -s -X POST "$API/api/v1/app/uploads/images" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -F "file=@/tmp/app-test.png;type=image/png")

IMAGE_URL=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["url"])' <<< "$UPLOAD_JSON")
```

### 4. 发布动态

```bash
CONTENT_JSON=$(curl -s -X POST "$API/api/v1/app/contents/" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"first local post\",\"image_urls\":[\"$IMAGE_URL\"]}")

CONTENT_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "$CONTENT_JSON")
```

### 5. 拉取动态流

```bash
curl -s "$API/api/v1/app/contents/feed" \
  -H "Authorization: Bearer $APP_TOKEN"
```

期望结果：刚发布的动态立即出现在列表中。

## 运营配置联调

### 1. 后台新增配置

```bash
CONFIG_KEY="home_banner_$(date +%s)"
CONFIG_JSON=$(curl -s -X POST "$API/api/v1/admin/app/configs" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"$CONFIG_KEY\",\"value\":\"enabled\",\"description\":\"Local banner switch\",\"is_enabled\":true}")

CONFIG_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "$CONFIG_JSON")
```

### 2. App 启动拉取配置

```bash
curl -s "$API/api/v1/app/configs" \
  -H "Authorization: Bearer $APP_TOKEN"
```

期望结果：返回 `$CONFIG_KEY`。

### 3. 后台禁用配置

```bash
curl -s -X PATCH "$API/api/v1/admin/app/configs/$CONFIG_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled":false}'
```

再次拉取 App 配置时，`$CONFIG_KEY` 不应返回。

## 支付回调联调

默认 `.env` 使用 `PAYMENT_WEBHOOK_VERIFICATION_MODE=local`，本地模拟支付回调不需要额外请求头。

### 1. 创建 Apple 订单

```bash
APPLE_ORDER_JSON=$(curl -s -X POST "$API/api/v1/app/orders" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"apple","product_id":"pro.monthly","amount":990,"currency":"USD"}')

APPLE_ORDER_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "$APPLE_ORDER_JSON")
APPLE_EVENT_ID="apple-local-event-$(date +%s)"
APPLE_TRANSACTION_ID="apple-tx-$(date +%s)"
```

### 2. 模拟 Apple IAP 成功通知

```bash
curl -s -X POST "$API/api/v1/webhooks/payments/apple-iap" \
  -H "Content-Type: application/json" \
  -d "{\"order_id\":\"$APPLE_ORDER_ID\",\"event_id\":\"$APPLE_EVENT_ID\",\"event_type\":\"DID_RENEW\",\"status\":\"paid\",\"transaction_id\":\"$APPLE_TRANSACTION_ID\",\"raw_data\":{\"environment\":\"local\"}}"
```

### 3. 验证幂等

重复发送同一个 `event_id`：

```bash
curl -s -X POST "$API/api/v1/webhooks/payments/apple-iap" \
  -H "Content-Type: application/json" \
  -d "{\"order_id\":\"$APPLE_ORDER_ID\",\"event_id\":\"$APPLE_EVENT_ID\",\"event_type\":\"DID_RENEW\",\"status\":\"paid\",\"transaction_id\":\"$APPLE_TRANSACTION_ID\",\"raw_data\":{\"environment\":\"local\",\"duplicate\":true}}"
```

期望结果：`is_duplicate` 为 `true`。

### 4. 创建并模拟 Google Play 订单

```bash
GOOGLE_ORDER_JSON=$(curl -s -X POST "$API/api/v1/app/orders" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"google","product_id":"pro.monthly","amount":990,"currency":"USD"}')

GOOGLE_ORDER_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "$GOOGLE_ORDER_JSON")
GOOGLE_EVENT_ID="google-local-event-$(date +%s)"
GOOGLE_TRANSACTION_ID="google-tx-$(date +%s)"

curl -s -X POST "$API/api/v1/webhooks/payments/google-play" \
  -H "Content-Type: application/json" \
  -d "{\"order_id\":\"$GOOGLE_ORDER_ID\",\"event_id\":\"$GOOGLE_EVENT_ID\",\"event_type\":\"SUBSCRIPTION_RENEWED\",\"status\":\"paid\",\"transaction_id\":\"$GOOGLE_TRANSACTION_ID\",\"raw_data\":{\"environment\":\"local\"}}"
```

### 5. 可选：验证 shared-secret 模式

如需在内网代理或非本地模拟环境中加一层共享密钥防护，修改 `server/.env` 后重启后端：

```text
PAYMENT_WEBHOOK_VERIFICATION_MODE=shared_secret
PAYMENT_WEBHOOK_SHARED_SECRET=replace-with-a-long-random-secret
```

启用后，支付回调必须带请求头：

```bash
curl -s -X POST "$API/api/v1/webhooks/payments/apple-iap" \
  -H "Content-Type: application/json" \
  -H "X-App-Payment-Webhook-Secret: $PAYMENT_WEBHOOK_SHARED_SECRET" \
  -d "{\"order_id\":\"$APPLE_ORDER_ID\",\"event_id\":\"apple-secret-event-$(date +%s)\",\"event_type\":\"DID_RENEW\",\"status\":\"paid\",\"transaction_id\":\"apple-secret-tx-$(date +%s)\",\"raw_data\":{\"environment\":\"shared_secret\"}}"
```

缺失或错误的 `X-App-Payment-Webhook-Secret` 会返回 403，订单状态不会更新。

### 6. 后台查看订单和事件

```bash
curl -s "$API/api/v1/admin/app/orders?status=paid" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

curl -s "$API/api/v1/admin/app/orders/$APPLE_ORDER_ID/events" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## 后台治理联调

### 1. 查看 App 用户

```bash
curl -s "$API/api/v1/admin/app/users" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 2. 禁用 App 用户

```bash
curl -s -X PATCH "$API/api/v1/admin/app/users/$APP_USER_ID/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"disabled"}'
```

禁用后再发布动态应失败：

```bash
curl -i -X POST "$API/api/v1/app/contents/" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"should fail after disabled","image_urls":[]}'
```

恢复启用：

```bash
curl -s -X PATCH "$API/api/v1/admin/app/users/$APP_USER_ID/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"active"}'
```

### 3. 删除动态

```bash
curl -s -X DELETE "$API/api/v1/admin/app/contents/$CONTENT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

删除后 App 动态详情应返回 404：

```bash
curl -i "$API/api/v1/app/contents/$CONTENT_ID" \
  -H "Authorization: Bearer $APP_TOKEN"
```

## React 后台页面验收

打开 `http://localhost:5173/login`，使用 `server/.env` 中的管理员账号登录。

需要检查的菜单：

- `App Users`：可看到设备登录生成的 App 用户，可禁用、恢复和删除。
- `App Contents`：可看到发布的动态和图片，可删除动态。
- `App Orders`：可看到 Apple/Google 订单，可查看支付事件。
- `App Configs`：可新增、编辑、启用和禁用 key-value 配置。

## 自动验证命令

后端：

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server/backend
uv run ruff check app tests
uv run mypy app
uv run python -m compileall app tests
uv run pytest
```

前端：

```bash
cd /Users/liqihui/Documents/Codex/2026-08-22/new-chat/server/frontend
curl -s http://127.0.0.1:8000/api/v1/openapi.json -o openapi.json
bun run generate-client
bunx @tanstack/router-cli generate
bun run lint
bun run build
bunx playwright test tests/app-admin.spec.ts --project=chromium
```

`app-admin.spec.ts` 覆盖：

- 后台配置新增、编辑、禁用。
- App 用户禁用和恢复。
- App 动态删除。
- 订单支付事件查看。
- App 操作日志查看和详情弹窗。
- 普通后台用户无法访问 App 管理页面。

## 手工验收清单

- [ ] 数据库和 Mailpit 启动后均为 healthy。
- [ ] 后端 `/docs` 返回 200。
- [ ] 前端 `http://localhost:5173/login` 可打开并登录后台。
- [ ] 新设备号首次登录会创建新 App 用户。
- [ ] 同一设备号重复登录返回同一 App 用户。
- [ ] 更换设备号会创建另一个新 App 用户。
- [ ] App 用户可修改昵称和头像。
- [ ] 图片上传返回 `/uploads/...` URL。
- [ ] 本地上传文件写入 `backend/uploads/images/{app_user_id}/`。
- [ ] 文字/图片动态发布后立即在动态流展示。
- [ ] 后台可看到 App 用户和动态。
- [ ] 后台禁用 App 用户后，该用户不能继续发布动态。
- [ ] 后台删除动态后，App 动态流和详情不再返回该动态。
- [ ] 后台新增启用配置后，App 启动配置接口可拉取。
- [ ] 后台禁用配置后，App 启动配置接口不再返回。
- [ ] App 可创建 Apple 和 Google 订单。
- [ ] Apple IAP 模拟回调可将订单更新为 `paid`。
- [ ] Google Play 模拟回调可将订单更新为 `paid`。
- [ ] 重复支付事件不会重复处理，返回 `is_duplicate=true`。
- [ ] 启用 `shared_secret` 后，缺失或错误密钥的支付回调返回 403，正确密钥可正常更新订单。
- [ ] 后台订单页可查看订单和事件。
- [ ] 后台 App Logs 页可查看配置、用户和内容管理操作日志。

## 已知限制

- 支付回调已支持本地模拟 JSON 和 shared-secret 基础防护，尚未实现 Apple/Google 官方生产级 JWS、Pub/Sub 或票据校验。
- 图片当前默认只存本地文件；已抽象 storage service，生产环境仍需补 S3、OSS 或 R2 等对象存储适配器和凭证配置。
- App token 当前按第一版需求长期有效，尚未实现服务端主动踢出或刷新 token 流程。
- 开发期 React 深链接请走 Vite 前端服务 `http://localhost:5173`。如要让 FastAPI 直接承载所有 React 深链接，需要额外增加 SPA fallback。
