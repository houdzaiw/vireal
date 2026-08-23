# Vireal

Vireal 是一个基于 FastAPI full-stack template 二次开发的 App 后端和后台管理系统。

## 当前能力

- App 设备号登录，App 用户与后台管理员独立账号体系。
- App 用户资料修改，支持昵称和头像。
- 本地图片上传，已抽象存储服务，默认使用本地文件。
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

当前支付回调已支持 shared-secret 基础防护，但尚未实现 Apple/Google 官方生产级 JWS、Pub/Sub 或票据校验。生产环境还需要补充对象存储适配器、正式密钥管理和部署配置。
