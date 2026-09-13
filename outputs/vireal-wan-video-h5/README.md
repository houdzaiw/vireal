# Vireal Wan Video H5 产品文档

当前确认版本：v1.0

## 交付物

- `prd/prd_v1.0.html`：最终产品需求文档，包含 Mermaid 流程图与 Focus 模式原型切片。
- `prototype/prototype_v1.0.html`：单文件 Tailwind Web/H5 高保真交互原型。
- `flowcharts/*.mmd`：核心用户路径、生成时序、失败返币、PayPal、媒体生命周期与系统架构。
- `annex/requirements_baseline_v1.0.md`：经确认的需求基线。
- `annex/technical_design_v1.0.md`：与现有 FastAPI 项目对齐的系统、数据、接口和异步任务设计。
- `annex/wan_poc_plan_v1.0.md`：Wan 双人/单人动作的分阶段付费 PoC 计划与验收口径。
- `annex/implementation_backlog_v1.0.md`：可进入迭代排期的 Epic、故事、依赖和完成定义。
- `annex/unit_economics_v1.0.md`：按 2026-09-09 官方价格测算的单次模型成本和金币风险。
- `templates/prd_template.md`：后续版本的 PRD 结构模板。

## 原型路由

- `#home`：落地页
- `#login`：登录
- `#create`：创作
- `#generation`：生成进度
- `#works`：作品记录
- `#wallet`：PayPal 与金币
- `#account`：账户设置
- `#region-locked`：地区限制

## Cloudflare Pages 部署

生产构建会把 API Origin 注入页面，并默认启用真实后端模式。本地原型文件仍可继续使用查询参数覆盖配置。

Cloudflare Pages 项目配置：

```text
Production branch: master
Root directory: /
Build command: bash scripts/build-vireal-pages.sh
Build output directory: dist/vireal-pages
Environment variable: VIREAL_API_BASE_URL=https://api.example.com
```

本地验证生产构建：

```bash
VIREAL_API_BASE_URL=https://api.example.com bash scripts/build-vireal-pages.sh
python3 -m http.server 5173 --directory dist/vireal-pages
```

打开 `http://localhost:5173` 时页面会使用构建时注入的 HTTPS API。Cloudflare Pages 绑定 `app.example.com` 后，需要把该完整 Origin 同时加入后端 `BACKEND_CORS_ORIGINS`。

使用 `?sandbox=true&focus=功能编号` 可进入专注模式，例如：

- `prototype_v1.0.html?sandbox=true&focus=upload#create`
- `prototype_v1.0.html?sandbox=true&focus=generation#generation`

## 版本规则

迭代 v1.1 时，先复制 v1.0 的 PRD 与原型并修改文件名。历史版本不得覆盖；PRD 内嵌原型、Mermaid 源文件和版本记录必须同步升级。
