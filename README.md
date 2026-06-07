# turbo-barnacle · 个人知识库系统

> 起这个名字是随机生成的，但确实挺喜欢，就用它当项目代号了。

**第二阶段目标**：把散落在手机里的多模态碎片（图片 / 语音 / 文字 / PDF / Markdown），
统一沉淀进 Obsidian，再用 AI API 做分析、归纳、复盘与预测。

## 核心数据流

```
手机多模态输入  ──▶  统一收件箱(Inbox)  ──▶  Obsidian 结构化存储  ──▶  AI 分析整理  ──▶  输出
 图片/语音/文字       捕获即落地、零分类        分类 + 元数据规范        Claude/DeepSeek      复盘/预测/整合
 PDF/Markdown         (捷径/飞书/中转)                                  (按任务分配)
```

设计取舍一句话：**捕获要无摩擦，存储要结构化，分析放在处理中枢，成本按任务分级。**

## 模块与状态

| 模块 | 说明 | 工具 | 状态 |
| --- | --- | --- | --- |
| 输入端 | 图片、语音、文字、PDF、Markdown，手机上传 | **iOS 捷径 + Advanced URI**（二进制经 iCloud→Mac 归档） | 🟢 方案已定 |
| 存储端 | 所有内容归入 Obsidian，分类管理 | **Obsidian + Obsidian Sync**（Mac ⇄ iPhone） | 🟢 方案已定·待搭建 |
| 分析端 | AI 调用 API 做整理、归纳、预测 | Copilot（交互）+ Mac pipeline（自动）；Claude/DeepSeek 按任务 | 🟢 方案已定·待接入 |
| 输出端 | 复盘报告、知识预测方向、内容整合 | Dataview 看板 + 定时 Claude 复盘 | 🟡 V2（Mac pipeline） |

> 处理中枢：一台**常开 Mac** —— 交互用插件，批处理与定时复盘用脚本。
> 额外来源：NotebookLM 的 AI 产出可经浏览器扩展一键存入 `20_Sources/NotebookLM/`（见文档索引）。

> Obsidian 本身是**静态知识库**，没有 AI 对话能力 —— 必须外接 API 才能激活分析端。
> 这是整个第二阶段的技术核心，单独立项推进。

## 文档索引

- **[Obsidian 接入 AI API 方案（专项）](docs/obsidian-ai-integration.md)** —— 插件选型、工作流设计、笔记结构规范、AI 任务路由、关键决策点、分阶段落地。
- **[落地路径：iOS + Mac + Obsidian Sync](docs/setup-ios-mac.md)** —— 收敛后的确定方案，含捷径捕获、Copilot 配置、Mac pipeline 脚本骨架，可直接照做。
- **[NotebookLM → Obsidian](docs/notebooklm-to-obsidian.md)** —— 把 NotebookLM 的 AI 产出一键抓进 vault（Chrome/Edge 扩展 + Local REST API，附兜底与安全注意）。

## 路线图

- [ ] **MVP**：建 vault + 文件夹规范 + frontmatter 模板 + Copilot 接 Claude/DeepSeek + 单一 Inbox + 手机捕获到 Inbox
- [ ] **V1**：Dataview 复盘仪表盘 + 语义连接发现 + 语音转写 + Claude/DeepSeek 任务路由
- [ ] **V2**：外部 pipeline 脚本（监听 Inbox 自动分类/打标/写回 + 定时生成复盘报告）
