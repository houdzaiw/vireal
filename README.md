# Vireal

Vireal 是一个基于 FastAPI full-stack template 二次开发的 App 后端和后台管理系统。

## 当前能力

- H5 使用 Clerk 正式认证，支持邀请制邮箱验证码、Google 和 Apple；App 用户与后台管理员独立账号体系。
- App 用户资料修改，支持昵称和头像。
- 图片上传支持本地文件和私有 Cloudflare R2；R2 模式通过稳定应用 URL 加短期签名跳转提供访问，并可为 Replicate 生成独立签名 URL。
- 双模式视频闭环：MiniMax Video-01 普通模式、Wan 2.7 高级模式、签名 Webhook、每日额度、PostgreSQL Worker、本地动画降级、私有 R2 播放和 24 小时清理。
- 文字/图片动态发布、动态流和详情。
- Apple IAP、Google Play 订单与支付回调处理。
- 支付事件幂等处理，支持本地模式和 shared-secret 基础防护。
- 后台管理 App 用户、内容、订单、运营配置和操作日志。
- React 后台管理页面和 Playwright E2E 验收测试。

## 本地启动

```bash
cp .env.example .env
docker compose up -d db mailpit

cd backend
uv run alembic upgrade head
uv run python app/initial_data.py
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

生成结果转存和过期清理需要另开一个终端运行 Worker：

```bash
cd backend
uv run python -m app.workers.video_tasks
```

另开终端启动后台前端：

```bash
cd frontend
bun install
bun run dev --host 0.0.0.0
```

## 常用地址

```text
Backend API: http://localhost:8000
Swagger Docs: http://localhost:8000/docs
Frontend: http://localhost:5173
Mailpit: http://localhost:8025
PostgreSQL: localhost:5432
```

## H5 真实登录与 R2 实链路验证

统一 `main` 分支中的 H5 位于 `h5/outputs/vireal-wan-video-h5/prototype/prototype_v1.1.html`。不要直接使用 `file://` 打开进行真实 API 验证；通过构建脚本注入 Clerk Publishable Key 和 API 地址：

```bash
cd h5
VIREAL_API_BASE_URL=http://localhost:8000 \
VITE_CLERK_PUBLISHABLE_KEY=pk_test_replace-me \
bash scripts/build-vireal-pages.sh
python3 -m http.server 5173 --directory dist/vireal-pages
```

然后访问：

```text
http://localhost:5173/
```

H5 使用 Clerk Session Token 调用 `/app/auth/session` 初始化本地用户，然后进行真实上传和私有图片读取。每个 Clerk Session 在数据库中单独登记；H5 退出时先调用 `/app/auth/logout` 即时撤销本地会话，再完成 Clerk `signOut()`。生产必须设置 `APP_AUTH_MODE=clerk`，此时设备登录接口返回 410。后端通过同源代理读取图片，因此本地上传验证不依赖 R2 Bucket CORS。普通模式使用 MiniMax 首帧图并固定 5 秒，高级模式使用 Wan 并支持 5/10 秒；两者均固定单人跳舞、720P、9:16、静音。当 Replicate 关闭、真实额度耗尽或供应商明确不可用时，Worker 会从用户原图生成带“演示结果”标识的本地 MP4，不调用外部模型。

Clerk 的普通 Session Token 必须增加 `{"aud":"vireal-api"}` 自定义 claim。Railway 保存 `CLERK_SECRET_KEY`，Pages 只保存 `VITE_CLERK_PUBLISHABLE_KEY`，不得互换或下发服务端 Secret。管理台的登录、用户、Items 和 Vireal 管理接口在生产环境都要求 Cloudflare Access JWT；超级管理员密码是第二层验证。

H5 会每 3 秒查询任务状态，并在刷新页面后从 `sessionStorage` 恢复当前任务。成功后使用 5 分钟有效的 R2 签名地址播放视频；签名密钥和 Replicate Token 不会进入浏览器。

## Cloudflare R2

生产环境建议创建私有 Bucket `vireal-media-prod`，然后在 Cloudflare Dashboard 的 R2 API Tokens 中创建仅限该 Bucket 的 Object Read & Write 凭据。后端使用 S3 兼容 Endpoint：

```env
APP_IMAGE_STORAGE_BACKEND=r2
R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
R2_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
R2_BUCKET_NAME=vireal-media-prod
R2_OBJECT_PREFIX=vireal
R2_DOWNLOAD_URL_EXPIRE_SECONDS=300
R2_REPLICATE_URL_EXPIRE_SECONDS=3600
R2_VIDEO_PLAYBACK_URL_EXPIRE_SECONDS=300
APP_MEDIA_RETENTION_HOURS=24
```

R2 模式下，上传接口返回 `upload_id`、过期时间和稳定的应用内 URL。登录用户读取该 URL 时由后端鉴权；提交 Replicate 时生成 1 小时有效的独立签名地址。密钥只配置在 API 和 Worker 环境变量中。

在 Bucket 的 `Settings > Object Lifecycle Rules` 添加规则：Prefix 设为 `vireal/`，对象年龄达到 1 天后删除。生命周期删除可能在到期后继续延迟最多约 24 小时；若产品要求精确到 24 小时，应另外运行应用侧定时清理任务。

## 双模式 Replicate 与本地降级

保持 `REPLICATE_ENABLED=False` 完成无费用测试。公网 HTTPS API 和无重定向 Webhook 就绪后，再补齐并启用：

```env
REPLICATE_ENABLED=True
REPLICATE_API_TOKEN=<server-side-token>
REPLICATE_STANDARD_MODEL=minimax/video-01
REPLICATE_ADVANCED_MODEL=wan-video/wan-2.7-r2v
REPLICATE_R2V_MODEL=wan-video/wan-2.7-r2v
REPLICATE_WEBHOOK_URL=https://api.usevireal.com/api/v1/webhooks/replicate
REPLICATE_WEBHOOK_SIGNING_SECRET=whsec_<signing-secret>
REPLICATE_REQUEST_TIMEOUT_SECONDS=30
REPLICATE_WEBHOOK_TOLERANCE_SECONDS=300
APP_USER_DAILY_REAL_SUBMISSIONS=5
APP_WAN_DAILY_GLOBAL_SUBMISSIONS=3
LOCAL_DEMO_ENABLED=True
LOCAL_DEMO_FFMPEG_PATH=/usr/bin/ffmpeg
LOCAL_DEMO_TIMEOUT_SECONDS=180
REPLICATE_POC_MAX_SUBMISSIONS=0
```

`REPLICATE_POC_MAX_SUBMISSIONS=0` 表示关闭历史累计 PoC 上限；用户每日 5 次真实生成和 Wan 全站每日 3 次仍会生效。若需要一次性验收保护，可临时设为 `1`。任何 `submission_unknown` 都不得自动重提或直接降级。

部署前必须替换默认的 `SECRET_KEY`、PostgreSQL 密码和管理员密码。若 H5 与 API 不同源，把完整 H5 Origin 以 JSON 数组配置到 `BACKEND_CORS_ORIGINS`，例如 `["https://h5.example.com"]`。Webhook URL 不得发生 HTTP→HTTPS 或尾斜杠重定向。

Compose 已包含 `video-worker` 服务。部署时先运行 migration，再启动 API 和 Worker：

```bash
docker compose run --rm backend bash scripts/prestart.sh
docker compose up -d backend video-worker
```

## 国际版云部署

当前 FastAPI、PostgreSQL 队列 Worker 和私有 R2 实现推荐使用混合部署：H5 放 Cloudflare Pages，API 和 Worker 放 Railway，数据库放 Neon，Cloudflare 继续负责 DNS、代理和 R2。

完整资源创建、环境变量、域名、无重定向 Webhook 和双模式受控验收步骤见 [`deployment-cloudflare-railway.md`](deployment-cloudflare-railway.md)。Railway 变量模板位于 [`deploy/railway-variables.example`](deploy/railway-variables.example)，公网验收脚本位于 [`scripts/verify-production.sh`](scripts/verify-production.sh)。

## 验证

```bash
cd backend
uv run ruff check app tests
uv run mypy app
uv run python -m compileall app tests
uv run pytest

cd ../frontend
bun run lint
bun run build
bunx playwright test tests/app-admin.spec.ts --project=chromium
```

## 说明

当前支付回调已支持 shared-secret 基础防护，但尚未实现 Apple/Google 官方生产级 JWS、Pub/Sub 或票据校验。当前生成只开放单人跳舞；双人、15 秒、音频、服务端金币账本和 provider 轮询兜底均不在本轮范围内。`submission_unknown` 不会自动重新创建 prediction，以避免重复计费。
