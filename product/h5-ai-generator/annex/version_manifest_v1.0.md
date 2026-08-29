# Vireal H5 AI Generator Version Manifest v1.0

基线日期：2026-08-29

基线状态：v1.0 产品方案已完成需求采集、初步 PRD、高保真 H5 原型、Mermaid 流程图、最终 PRD 与版本管理规则。后续需求迭代必须新建版本文件，不直接覆盖本版本。

## 1. 当前版本范围

v1.0 覆盖普通手机浏览器 H5 创作端，主导航为 AI 视频、AI 图片、作品三个 Tab。

核心范围：

- 默认进入 AI 视频落地页，支持风格、尺寸、时长、参考图、人物一致性等配置。
- AI 视频由 Seedance 承担，AI 图片由 Seedream 承担。
- 用户可以先进入页面浏览和填写创意，点击生成时才触发 Apple 或 Google 登录。
- 视频和图片各自允许 2 次免费生成额度，额度分别计算。
- 生成结果统一进入作品 Tab，支持下载、分享提示、删除、再次生成。
- 登录、生成失败、额度不足、作品空状态、下载失败等异常流程已进入 PRD 和流程图。

## 2. v1.0 交付物清单

| 类型 | 文件 | 用途 | SHA-256 |
| --- | --- | --- | --- |
| 最终 PRD | `product/h5-ai-generator/prd/prd_final_v1.0.html` | v1.0 正式产品需求文档，内嵌流程图和原型切片 | `1580bac60db43e37341034c079940cc74ee50159835bd463882a25d3f1a2e311` |
| 初步 PRD | `product/h5-ai-generator/prd/prd_v1.0.html` | 步骤三输出的第一版详细 PRD | `6cfb94e9927b51afcd61a5cd8bb1c1177814e2581ff9e994fd6642a79eb9d6a9` |
| 高保真原型 | `product/h5-ai-generator/prototype/prototype_v1.0.html` | 单文件 H5 原型，支持 Focus Mode | `f5483530d50b3cbdc916b5fff2a38525593b65e44efd29c915de50d7a7690e33` |
| 流程图总览 HTML | `product/h5-ai-generator/flowcharts/flowcharts_v1.0.html` | Mermaid 流程图可浏览版本 | `bfbbb4bdaa5113079f1d3609e4b3d4a73b55ba3c6063bc1ce4b372cccbbf4b3d` |
| 流程图总览 Markdown | `product/h5-ai-generator/flowcharts/flowcharts_v1.0.md` | Mermaid 流程图源码汇总 | `9b62d589c10f2d74797bb578f95524659144ff29b8ce1049563927e55e967980` |
| 流程图源码 | `product/h5-ai-generator/flowcharts/h5_entry_tabs_v1.0.mmd` | H5 入口与三 Tab 流程 | `86da9076176025b3e65677a96e16e83f70facba3fd89904418e46f61881442d1` |
| 流程图源码 | `product/h5-ai-generator/flowcharts/login_gate_v1.0.mmd` | Apple/Google 登录门禁流程 | `9c62aa4386a14edc46f4bbc50acabbcb988f7ea58a6e0e5dfed2bbbedff65e31` |
| 流程图源码 | `product/h5-ai-generator/flowcharts/video_generation_seedance_v1.0.mmd` | Seedance 视频生成流程 | `5a0ce5b0e08d7ca82b9122ca7b1f8fa906791c44e8447d367646c3eb031e7628` |
| 流程图源码 | `product/h5-ai-generator/flowcharts/image_generation_seedream_v1.0.mmd` | Seedream 图片生成流程 | `9fd3e508f6814474496ae70cc6309fe08afc9a070ac37276f32f1f834808e1c5` |
| 流程图源码 | `product/h5-ai-generator/flowcharts/works_management_v1.0.mmd` | 作品管理流程 | `8f03b5079a2a525c08e6a1598b0524cf3012593bc2a0613c217a0f5288ac8c8c` |
| 流程图源码 | `product/h5-ai-generator/flowcharts/quota_failure_v1.0.mmd` | 额度扣减、失败返还与不足拦截流程 | `a18aded3579abcdf658743d9a1f78f47aaa97942da6220911ac06764caafff04` |

## 3. 版本命名规则

主版本文件：

- 最终 PRD：`prd/prd_final_v{version}.html`
- 初稿或过程 PRD：`prd/prd_v{version}.html`
- 原型：`prototype/prototype_v{version}.html`
- 流程图总览：`flowcharts/flowcharts_v{version}.html` 和 `flowcharts/flowcharts_v{version}.md`
- Mermaid 单图：`flowcharts/{flow_name}_v{version}.mmd`

后续版本示例：

- v1.1 最终 PRD：`prd/prd_final_v1.1.html`
- v1.1 原型：`prototype/prototype_v1.1.html`
- v1.1 流程图总览：`flowcharts/flowcharts_v1.1.html`

## 4. 版本升级规则

进入 v1.1 或后续版本前，必须先复制当前版本文件，再在新版本文件中修改。

必须遵守：

- 不直接覆盖 `v1.0` 文件。
- 新版本 PRD 的版本记录表必须写清新增、修改、下线、风险和验证结果。
- 新版本 PRD 内所有 iframe 原型切片必须指向同版本原型，例如 `../prototype/prototype_v1.1.html?focus=video#video`。
- 新版本 PRD 内流程图链接必须指向同版本流程图，例如 `../flowcharts/flowcharts_v1.1.html`。
- 新版本 PRD 的版本切换下拉菜单必须同时保留历史版本入口和当前版本入口。
- 如果 v1.0 成为历史版本，v1.0 PRD 顶部可以追加历史版本提示，但不改动业务正文。

## 5. v1.1 复制基准

创建 v1.1 时，以以下文件为复制源：

| 新版本目标 | 复制来源 |
| --- | --- |
| `prd/prd_final_v1.1.html` | `prd/prd_final_v1.0.html` |
| `prototype/prototype_v1.1.html` | `prototype/prototype_v1.0.html` |
| `flowcharts/flowcharts_v1.1.html` | `flowcharts/flowcharts_v1.0.html` |
| `flowcharts/flowcharts_v1.1.md` | `flowcharts/flowcharts_v1.0.md` |
| `flowcharts/*_v1.1.mmd` | `flowcharts/*_v1.0.mmd` |

复制完成后，先全局替换新版本文件内的版本号和链接，再开始需求修改。

## 6. 发布前检查

每次新版本交付前至少完成以下检查：

- HTML 能通过浏览器正常打开，无控制台错误。
- 最终 PRD 中 Mermaid 流程图全部渲染成功。
- 最终 PRD 中 iframe 原型切片数量与详细方案模块数量一致。
- 每个 iframe 都带 `focus` 参数，并且能展示对应模块。
- 原型内核心交互能跑通：点击生成触发登录、登录后进入作品、失败态能返还额度。
- 版本清单中的文件路径、版本号、SHA-256 与实际文件一致。
- `git status --short` 中只包含本次版本相关变更。
