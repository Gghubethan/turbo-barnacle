# Obsidian 接入 AI API 方案（Phase 2 技术核心专项）

本文是第二阶段「分析端」的落地方案，覆盖四件事：**插件选型、工作流设计、笔记结构规范、AI 任务路由**，
并在末尾列出需要你拍板的**关键决策点**与**待确认问题**。

---

## 0. 设计原则

1. **捕获零摩擦**：手机端只管「扔进收件箱」，不在捕获时分类。分类是 AI/事后的事。
2. **单一收件箱（Inbox）**：所有来源先落到一个文件夹，避免「该存哪」的决策瘫痪。
3. **元数据结构化**：每条笔记有统一 YAML frontmatter —— 这是 AI 能稳定处理的前提（结构化输入→结构化输出）。
4. **桌面/服务器是处理中枢**：手机插件能力受限，重活（批处理、定时复盘）放在常开的电脑或服务器跑。
5. **成本分级**：便宜批量活交给 DeepSeek，质量敏感/多模态/最终产出交给 Claude。

---

## 1. 整体架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐
│  输入端      │     │  收件箱       │     │  Obsidian Vault     │     │  输出端       │
│ 手机多模态   │ ──▶ │ 00_Inbox/    │ ──▶ │ 结构化存储 + 元数据  │ ──▶ │ 70_Output/   │
│ 捷径/飞书    │     │ (原始、带时间)│     │ (PARA + Zettel + MOC)│     │ 复盘/预测/整合│
└─────────────┘     └──────────────┘     └─────────────────────┘     └──────────────┘
                            │                       ▲   │                     ▲
                            │                       │   │                     │
                            ▼                       │   ▼                     │
                    ┌───────────────────────────────────────────────────────────┐
                    │  分析端：AI API（Claude / DeepSeek，按任务路由）            │
                    │  插件内调用（交互） + 外部脚本 pipeline（批处理/定时）       │
                    └───────────────────────────────────────────────────────────┘
```

关键认知：**Obsidian vault 本质就是一堆磁盘上的 Markdown 文件**。
所以既能用插件在 App 内调用 AI，也能用任意脚本（Python/Node）在 App 外读写笔记。最佳实践是两者混合。

---

## 2. 插件选型

| 用途 | 推荐插件 | 说明 | 移动端 |
| --- | --- | --- | --- |
| AI 对话 / 库内问答 | **Copilot** (logancyang) | 多供应商（OpenAI / Anthropic / 兼容 OpenAI 的 DeepSeek）、对全库做 RAG 问答、自定义 prompt | ✅ |
| 语义检索 / 连接发现 | **Smart Connections** | 基于 embedding 找相关笔记、语义搜索 —— 服务「知识预测/连接」目标 | 🟡 部分 |
| 自定义文本生成 | **Text Generator** | 模板化调用、可配自定义 endpoint，灵活 | ✅ |
| 移动端捕获写入 | **Advanced URI** | 让捷径/外部 App 通过 URI 往「指定笔记」追加内容 | ✅（作为写入目标） |
| 笔记模板标准化 | **Templater** | 统一 frontmatter 与结构；user script 仅桌面 | 🟡 模板可用、脚本仅桌面 |
| 捕获宏 / 快速记录 | **QuickAdd** | 一键捕获、宏、调用模板 | ✅ |
| 查询 / 复盘仪表盘 | **Dataview** | 按 frontmatter 查询，驱动复盘报告与看板 | ✅ |
| 语音转写 | **Whisper** (Nik Danilov) | 录音 → 调 Whisper API 转写入库 | 🟡 |

**推荐核心组合（MVP）**：`Copilot` + `Templater` + `QuickAdd` + `Dataview` + `Advanced URI`
**进阶补充**：`Smart Connections`（连接/预测）+ `Whisper`（语音）+ 外部 pipeline 脚本（自动化）

> 关于 DeepSeek：它提供**兼容 OpenAI 的 endpoint**，所以在 Copilot / Text Generator 里把
> base URL 指到 DeepSeek、填上 key、选对模型即可，无需专门插件。

---

## 3. 工作流设计

四步循环：**捕获 → 三分（triage）→ 归位 → 输出**。

### 3.1 捕获（Capture）
手机端把任意内容追加进 `00_Inbox/`，自动带时间戳和来源标记。**不分类、不纠结**。
- iOS：捷径(Shortcuts) + Advanced URI，或共享到同步文件夹。
- 跨平台：飞书机器人 / 多维表格 webhook → 中转脚本写入 Inbox。
- 语音：Whisper 转写；图片/PDF：先存附件，处理阶段再由多模态模型理解。

### 3.2 三分（Triage，AI 介入）
对 Inbox 条目：分类打标 → 抽取原子笔记 → 补全 frontmatter → 链接到已有笔记。
- 轻量：在桌面用 Copilot 自定义 prompt 逐条处理。
- 自动：外部脚本批量处理（见 3.4）。

### 3.3 归位（Organize）
从 Inbox 移入结构化目录（见第 4 节），原子笔记通过 MOC 串联。

### 3.4 输出（Output）
定期生成复盘 / 知识缺口 / 预测方向 / 内容整合，落到 `70_Output/`。
由 Dataview 查询出时间窗内的笔记 → 喂给 AI → 生成报告。

### 插件直连 vs. 外部 pipeline（重要选择）
| 维度 | 纯插件 | 外部脚本 pipeline |
| --- | --- | --- |
| 上手成本 | 低（低代码） | 高（要写脚本） |
| 移动端友好 | 好 | 不适用（跑在桌面/服务器） |
| 自动化/定时 | 弱 | 强（cron 定时、批处理、任务路由） |
| 控制力 | 受插件功能限制 | 完全可控 |

> **建议**：先用纯插件跑通 MVP；等复盘/批量打标成为日常，再上「混合」——
> 交互用插件，批处理与定时复盘用脚本，脚本直接读写 vault 的 `.md` 文件。

---

## 4. 笔记结构规范

### 4.1 文件夹结构（PARA + Zettelkasten + MOC 混合）
```
00_Inbox/        # 手机端原始输入先落这里，不分类
10_Notes/        # 永久笔记（原子化，Zettelkasten）
20_Sources/      # 文献/PDF/网页摘录（literature notes）
30_Projects/     # 进行中的项目（PARA: Projects）
40_Areas/        # 长期负责的领域（PARA: Areas）
50_Resources/    # 资源/参考资料（PARA: Resources）
60_MOC/          # Maps of Content 知识地图（服务「预测/连接」）
70_Output/       # AI 生成的复盘报告、预测、整合内容
90_Archive/      # 归档
_attachments/    # 图片/音频/PDF 等附件
_templates/      # Templater 模板
```

### 4.2 统一 Frontmatter 规范
```yaml
---
title:
created: 2026-06-02
modified: 2026-06-02
type: fleeting        # fleeting | literature | permanent | moc | source | output
status: inbox         # inbox | processing | done | review
tags: []
source: 捷径          # 捷径 | 飞书 | 微信 | web | pdf | 手动
aliases: []
related: []           # [[双链]]，连接发现的落点
ai_processed: false   # 是否已被 AI 处理
ai_model:             # claude | deepseek
---
```
> frontmatter 是 AI 流水线的「接口契约」：`status` 驱动流转，`type`/`tags` 驱动分类，
> `related` 承载连接，`ai_processed` 防止重复处理，`source` 便于追溯。

### 4.3 其他约定
- **命名**：永久笔记用稳定标题（或 `时间戳ID + 描述`），便于双链不易断。
- **标签**：维护一份**受控词表**（避免 `#AI` / `#ai` / `#人工智能` 混用），AI 分类才稳定。
- **原子化**：一条笔记一个想法；用 MOC（`60_MOC/`）而非深层文件夹来组织，利于发现跨主题连接。

---

## 5. AI 任务路由（Claude / DeepSeek 按任务分配）

| 任务 | 推荐模型 | 理由 |
| --- | --- | --- |
| 批量分类 / 打标签 | **DeepSeek-V3** | 量大、简单、便宜 |
| OCR 后清洗、转写后整理 | **DeepSeek** | 便宜、够用 |
| 简单摘要 | **DeepSeek** | 成本敏感 |
| 图片 / PDF 多模态理解 | **Claude** | 视觉与文档理解能力强 |
| 跨笔记长上下文综合 / 整合 | **Claude** | 长上下文 + 推理 |
| 复盘报告 / 预测方向 | **Claude** | 质量敏感的「最终产出」 |
| 复杂推理 | **Claude**（或 DeepSeek-R1 省钱） | 看预算 |

路由原则：**便宜的批量活 → DeepSeek；质量敏感 / 多模态 / 最终输出 → Claude。**

---

## 6. 关键决策点（需要你拍板，附推荐默认）

1. **同步方案**
   - Obsidian Sync（付费、E2E、官方移动端最省心）✅ *推荐*
   - iCloud（免费，偏 iOS）
   - Syncthing / Git（免费，但要折腾，移动端后台同步弱）
   - **默认建议**：手机为主的多模态工作流 → Obsidian Sync；纯 iOS 且想省钱 → iCloud。

2. **输入中转**（你表里的「留白」项）
   - iOS → 捷径 + Advanced URI ✅ *推荐（若 iOS）*
   - 跨平台 → 飞书机器人 / 多维表格 webhook → 中转脚本写入 Inbox
   - Android → Tasker/MacroDroid + Advanced URI，或「分享到同步文件夹」

3. **插件直连 vs. 混合 pipeline**
   - **默认建议**：MVP 先纯插件；复盘/批处理上混合脚本。需要一台常开机器才能发挥 pipeline。

4. **API Key 安全**
   - 插件里的 key 存在 vault 配置中，**会随 vault 同步** —— 切勿把含 key 的配置同步到公开仓库/不安全位置。
   - pipeline 的 key 放服务器环境变量，不要写进笔记或提交进 git。

---

## 7. 分阶段落地

- **MVP（约 1 周）**：建 vault + 文件夹规范 + frontmatter 模板（Templater）+ Copilot 接 Claude/DeepSeek
  + 单一 Inbox + 手机捕获到 Inbox。→ *能做到：手机随手收集，桌面用 Copilot 整理。*
- **V1**：+ Dataview 复盘仪表盘 + Smart Connections 连接发现 + Whisper 语音 + Claude/DeepSeek 任务路由。
- **V2**：+ 外部 pipeline 脚本（监听 Inbox 自动分类/打标/写回，定时生成复盘报告到 `70_Output/`）。

---

## 8. 待确认问题

1. **手机生态**：iOS / Android / 两者都用？→ 决定「输入中转」走捷径还是飞书/Tasker。
2. **有没有常开的电脑或服务器（含 NAS）？** → 决定外部 pipeline 是否可行。
3. **同步方案偏好**：Obsidian Sync / iCloud / Syncthing / 让我推荐？

> 回答这三点后，就能把上面的「并列选项」收敛成一条确定的落地路径，并补上对应的捷径/脚本细节。
