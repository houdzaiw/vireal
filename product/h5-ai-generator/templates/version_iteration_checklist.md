# Version Iteration Checklist

适用范围：Vireal H5 AI 视频与图片创作端的 PRD、原型、流程图版本迭代。

使用方式：每次从一个稳定版本进入下一个版本前，复制本检查表到本次迭代记录中，并按顺序勾选。

## 1. 迭代准备

- [ ] 明确新版本号，例如 `v1.1`。
- [ ] 明确本次迭代目标、上线范围和不做范围。
- [ ] 确认上一版本已经提交 Git，并能通过 SHA-256 或 Git commit 追溯。
- [ ] 确认当前工作树没有无关改动。

## 2. 文件复制

- [ ] 从上一版本复制最终 PRD 到 `product/h5-ai-generator/prd/prd_final_v{new_version}.html`。
- [ ] 从上一版本复制原型到 `product/h5-ai-generator/prototype/prototype_v{new_version}.html`。
- [ ] 从上一版本复制流程图总览 HTML 到 `product/h5-ai-generator/flowcharts/flowcharts_v{new_version}.html`。
- [ ] 从上一版本复制流程图总览 Markdown 到 `product/h5-ai-generator/flowcharts/flowcharts_v{new_version}.md`。
- [ ] 从上一版本复制所有 Mermaid 单图，并把文件名中的版本号改为新版本。

建议复制命令示例：

```bash
cp product/h5-ai-generator/prd/prd_final_v1.0.html product/h5-ai-generator/prd/prd_final_v1.1.html
cp product/h5-ai-generator/prototype/prototype_v1.0.html product/h5-ai-generator/prototype/prototype_v1.1.html
cp product/h5-ai-generator/flowcharts/flowcharts_v1.0.html product/h5-ai-generator/flowcharts/flowcharts_v1.1.html
cp product/h5-ai-generator/flowcharts/flowcharts_v1.0.md product/h5-ai-generator/flowcharts/flowcharts_v1.1.md
```

## 3. PRD 联动更新

- [ ] 更新页面标题、项目信息、当前版本号和版本日期。
- [ ] 在版本记录表中新增本次迭代记录。
- [ ] 更新版本切换下拉菜单，包含历史版本和当前版本。
- [ ] 如果上一版本变成历史版本，在上一版本 PRD 顶部追加历史版本提示。
- [ ] 将新版本 PRD 中所有原型 iframe 链接改为 `../prototype/prototype_v{new_version}.html`。
- [ ] 将新版本 PRD 中所有流程图链接改为 `../flowcharts/flowcharts_v{new_version}.html` 或 `flowcharts_v{new_version}.md`。
- [ ] 更新附件区，列出新版本 PRD、原型、流程图和版本清单。

## 4. 原型更新

- [ ] 保留 Focus Mode 参数解析能力。
- [ ] 每个核心功能点都有可被 PRD iframe 调用的 hash 或 focus 入口。
- [ ] 新增或变更交互后，同步更新 PRD 的详细方案规则。
- [ ] 新增或变更异常态后，同步更新流程图和异常处理章节。
- [ ] 手机视口下检查文字不溢出、不遮挡、不被底部 Tabbar 覆盖。

## 5. 流程图更新

- [ ] 每张 Mermaid 单图文件名包含新版本号。
- [ ] Mermaid 源码使用 `flowchart TD` 或明确的 Mermaid 图类型。
- [ ] 节点文案避免未转义特殊字符，尤其是中文全角括号。
- [ ] `flowcharts_v{new_version}.md` 汇总所有新版本图。
- [ ] `flowcharts_v{new_version}.html` 能渲染所有新版本图。

## 6. 验收检查

- [ ] 最终 PRD 能打开。
- [ ] 最终 PRD 中 Mermaid 图全部渲染。
- [ ] 最终 PRD 中 iframe 数量与详细方案模块数量一致。
- [ ] 每个 iframe 切片都能展示对应原型状态。
- [ ] 原型核心链路能跑通：入口、生成、登录、作品、失败、删除、再次生成。
- [ ] 版本切换下拉菜单能跳转到历史版本和当前版本。
- [ ] 重新计算新版本交付物 SHA-256，并写入新的 `version_manifest_v{new_version}.md`。
- [ ] 提交 Git，commit message 包含版本号和主要变更。

## 7. 推荐验证命令

```bash
git status --short
rg -n "prototype_v1.0|flowcharts_v1.0" product/h5-ai-generator/prd/prd_final_v1.1.html
shasum -a 256 product/h5-ai-generator/prd/prd_final_v1.1.html product/h5-ai-generator/prototype/prototype_v1.1.html
```

如果第二条命令在新版本 PRD 中仍然命中旧版本链接，需要逐项确认是否属于历史版本记录；非历史说明文字里的命中一般都应改为新版本链接。
