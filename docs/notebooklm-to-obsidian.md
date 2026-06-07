# NotebookLM → Obsidian：把 NotebookLM 产出一键抓进知识库

> 适用：把 NotebookLM 里 AI 生成的内容（简报 Briefing Doc、学习指南、摘要、置顶对话答案等）导入 Obsidian。
> 已确认走 **Chrome/Edge 浏览器扩展一键** 路径；处理中枢为常开 Mac（见 [setup-ios-mac.md](setup-ios-mac.md)）。

## 可行性结论（2026-06 核实）

**可以，但没有面向个人的官方一键 API。** 三个事实：
- Google 只对**企业**开放 NotebookLM Enterprise API（Google Cloud），个人无自助 API；旧的 Podcast API 已弃用。
- NotebookLM 2025-12 加了**原生导出**，但只能逐条「导出到 Google Docs」（含表格的转 Sheets），**不能整本一键、不直出 Markdown**。
- 非官方库（`notebooklm-py` 等）能编程抓取，但用未公开接口、易失效、ToS 灰色，官方声明"不适合生产"。

所以最实用的个人方案 = **浏览器扩展**：把 NotebookLM 的内容一键存成 Markdown 进 vault。

## 推荐工作流（Chrome/Edge + Local REST API，一键直写）

最接近"直抓"的体验：在 NotebookLM 页面点一下，内容直接以 Markdown 落进 vault。

**Step 1 — Obsidian(Mac) 装 Local REST API 插件**
1. 社区插件搜 **Local REST API**，安装并启用。
2. 复制生成的 **API Key**；端点默认绑定本机 `127.0.0.1`（建议保持只连 localhost）。

**Step 2 — Chrome/Edge 装「Save to Obsidian」类扩展**
1. 应用商店装一个**能对接 Local REST API** 的 NotebookLM→Obsidian 扩展（认准"需要 Obsidian Local REST API 插件"这一条）。
2. 扩展设置里填 Local REST API 的地址 + Step 1 的 token，目标文件夹设为 `20_Sources/NotebookLM/`。

**Step 3 — 一键保存**
在 NotebookLM 打开某条笔记/简报/对话 → 点扩展的「Save to Obsidian」→ 内容以 Markdown 写入 vault，表格/公式/列表格式保留。

## 兜底方案

**A. 批量导出扩展（无需 Local REST API）**
装导出类扩展（**NotebookLM Export Pro / NotebookLM Ultra Exporter / NoteBookLM Exporter**），一键把 notes / 对话 / 来源导成 **Markdown / PDF / Word** 文件 → 移进 vault；或丢进 `~/iCloud/KB-Drop/` 让 Mac pipeline 自动归档（见 setup-ios-mac.md §3/§5）。适合一次性搬运整本。

**B. 官方原生导出（零扩展，最稳）**
- Studio 面板某条 Note/Report 的 **⋮ → Export to Google Docs**（含表格的转 Google Sheets）→ 再从 Google Docs 下载/复制为 Markdown 进 Obsidian。
- 或用 **「Convert all notes to source」** 把一个 notebook 的所有笔记合并成一个来源文档 → 复制粘贴进 Obsidian。

## 落库规范（复用现有结构，不新造）

| 项 | 约定 |
| --- | --- |
| 目标目录 | `20_Sources/NotebookLM/`（NotebookLM 产出是对来源的合成，归 source 类） |
| frontmatter | 沿用 [obsidian-ai-integration.md §4.2](obsidian-ai-integration.md)；`type: source`，`source: notebooklm`（已加入受控词表） |
| 后处理 | 导入后交给 Mac pipeline 的 `triage.py`（setup-ios-mac.md §5）自动打标、建 `related` 双链 |

建议 frontmatter（导入后补全）：
```yaml
---
title: <NotebookLM 笔记标题>
created: 2026-06-07
type: source
status: inbox
tags: []
source: notebooklm
related: []
ai_processed: false
---
```

## 注意事项 / 安全

- **扩展权限**：第三方扩展能读你的 NotebookLM 内容，「Save to Obsidian」类还持有 Local REST API token → 选**开源/口碑好**的、装前审权限、优先**只连 localhost** 的。
- **token 不入 git**：Local REST API 的 token 别提交进仓库或写进笔记。
- **会失效**：扩展靠抓 NotebookLM 页面 DOM，Google 改版时可能短期失效——保留兜底方案 B。
- **来源是静态快照**：NotebookLM 的来源不随原文更新；真正值得抓的是**它的 AI 产出**（简报/指南/对话），原始来源你本来就有。

## V2 备选（本次不做）

常开 Mac 上用 **`notebooklm-py`** / **`notebooklm-rest-api`** 定时把笔记拉进 vault，可纳入 setup-ios-mac.md §5 的 pipeline。但它用未公开接口、需存 Google 登录态、易失效、ToS 灰色——等扩展路径跑顺、确有批量自动化需求时再评估。

## 参考来源

- NotebookLM 是否有 API（企业版/非官方）: <https://autocontentapi.com/blog/does-notebooklm-have-an-api>
- NotebookLM Enterprise API 文档: <https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks>
- 原生导出与导出工作流（2025-12）: <https://exploreaitogether.com/export-download-notebooklm-guide/>
- NotebookLM → Obsidian（Markdown/扩展）: <https://www.xda-developers.com/notebooklm-to-obsidian-markdown/>
- 非官方 Python 库 notebooklm-py: <https://github.com/teng-lin/notebooklm-py>
