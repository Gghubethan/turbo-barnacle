# 落地路径：iOS 捕获 + Mac 处理中枢 + Obsidian Sync

> 基于已确定的选择：**手机 iOS（捷径）/ 常开 Mac / Obsidian Sync**。
> 本文把[专项方案](obsidian-ai-integration.md)里的并列选项收敛成一条可照做的路径。

## 收敛后的技术栈

| 模块 | 确定方案 |
| --- | --- |
| 输入端 | iOS 捷径 + Advanced URI（文字/语音转写直写 Inbox）；图片/PDF/录音 → iCloud 投放文件夹 → Mac 归档 |
| 存储端 | Obsidian + Obsidian Sync（Mac ⇄ iPhone，端到端加密） |
| 处理中枢 | 常开 Mac：交互用插件，批处理/定时复盘用脚本 |
| 分析端 | Copilot（交互）+ Mac pipeline（自动）；Claude 质量活 / DeepSeek 批量活 |
| 输出端 | Dataview 看板 + 定时 Claude 复盘 → `70_Output/` |

---

## 第 1 步：Obsidian + Sync + 文件夹

1. Mac 与 iPhone 都装 Obsidian。
2. 开通 **Obsidian Sync**，建远程 vault，两端连同一个 vault。
3. 建文件夹结构（同专项方案 4.1 节）：`00_Inbox` … `90_Archive` + `_attachments` + `_templates`。

## 第 2 步：核心插件 + frontmatter 模板

社区插件安装：`Copilot`、`Templater`、`QuickAdd`、`Dataview`、`Advanced URI`。
（移动端这几个都能用；Templater 的 user script 仅在 Mac 跑 —— 正好放处理中枢。）

`_templates/permanent.md`（Templater 模板）：
```markdown
---
title: <% tp.file.title %>
created: <% tp.date.now("YYYY-MM-DD") %>
modified: <% tp.date.now("YYYY-MM-DD") %>
type: permanent
status: processing
tags: []
source: 手动
aliases: []
related: []
ai_processed: false
ai_model:
---

```

## 第 3 步：iOS 捷径捕获到 Inbox

核心机制：捷径用「打开 URL」触发 **Advanced URI**，往 Inbox 当天的笔记**追加**内容。

```
obsidian://advanced-uri?vault=你的vault名&filepath=00_Inbox/{当天日期}.md&mode=append&data={URL编码后的内容}
```

**捷径搭建（"快速记录"）**：
1. 接收输入：文本（或来自共享表单的内容）。
2. 文本动作：拼接 `- {时间} {正文}`。
3. 用「URL 编码」动作编码该文本。
4. 「打开 URL」：上面的 advanced-uri，`filepath` 指到 `00_Inbox/{当天日期}.md`，`mode=append`。
5. 加到主屏/锁屏/分享表单，随手可记。

- **语音**：捷径加「听写文本」动作 → 转成文字后同上 append。
- **图片 / PDF / 录音（二进制）**：捷径「存储文件」到 iCloud 的 `KB-Drop/` 文件夹 → 由第 5 步 Mac 脚本自动归档进 vault 的 `_attachments/` 并建一条索引笔记。
  > 为什么二进制不直接写 vault：Obsidian Sync 的 vault 在 iOS App 沙盒里，捷径无法直接写入二进制文件。走「iCloud 投放 + Mac 中转」最稳，正好用上常开 Mac。

## 第 4 步：Copilot 接 Claude + DeepSeek

Copilot 设置里配两个供应商：
- **Anthropic（Claude）**：填 Claude API key，模型选最新 Claude Opus（质量活）/ Sonnet（日常）。
- **自定义 OpenAI 兼容供应商（DeepSeek）**：Base URL `https://api.deepseek.com`，填 DeepSeek key，模型 `deepseek-chat`(V3) / `deepseek-reasoner`(R1)。
- **语义问答（QA/RAG）需要 embedding**：DeepSeek 无 embedding 接口 —— 用 OpenAI `text-embedding-3-small`，或装 `Smart Connections` 单独做语义层。
- ⚠️ **Key 安全**：key 存在 vault 配置里会随 Sync 同步（Sync 是端到端加密，可接受），但**不要把 vault 推到公开 git 仓库**。

## 第 5 步（V2）：Mac 上的 pipeline 脚本

放常开 Mac 上，用 `launchd`/`cron` 定时跑。职责：**自动三分 + 定时复盘**。

依赖：`pip install anthropic openai watchdog python-frontmatter`

骨架（`pipeline/triage.py`）：
```python
import os, glob, frontmatter
from openai import OpenAI            # 指到 DeepSeek（兼容 OpenAI）
from anthropic import Anthropic

VAULT = os.path.expanduser("~/路径/你的vault")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "")   # 设为最新 Claude Opus 模型ID
deepseek = OpenAI(base_url="https://api.deepseek.com", api_key=os.environ["DEEPSEEK_API_KEY"])
claude   = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def triage_inbox():
    """便宜批量活 → DeepSeek：分类 + 打标 + 判定目标文件夹"""
    for path in glob.glob(f"{VAULT}/00_Inbox/*.md"):
        post = frontmatter.load(path)
        if post.get("ai_processed"):
            continue
        resp = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "给笔记打标签、判定 type 与目标文件夹，输出 JSON"},
                {"role": "user", "content": post.content},
            ],
        )
        meta = parse_json(resp.choices[0].message.content)   # {tags, type, folder}
        post["tags"], post["type"] = meta["tags"], meta["type"]
        post["ai_processed"], post["ai_model"], post["status"] = True, "deepseek", "processing"
        save_and_move(path, post, meta["folder"])            # 写回 + 移到目标目录

def weekly_review():
    """质量敏感的最终产出 → Claude：复盘 + 预测方向"""
    notes = recent_notes(days=7)
    msg = claude.messages.create(
        model=CLAUDE_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": build_review_prompt(notes)}],
    )
    write_output("70_Output", msg.content[0].text)
```
- **Key 放 Mac 环境变量**（`~/.zshrc` 或 launchd plist），不要写进笔记或提交 git。
- **二进制归档**：另写一个监听 `~/iCloud/KB-Drop/` 的小脚本，把图片/PDF 移进 `_attachments/`，录音跑 Whisper 转写后建 Inbox 笔记。

---

## 建议节奏

- **本周**：第 1–4 步（纯插件 MVP）—— 手机能随手收集，Mac 用 Copilot 整理。
- **下周**：第 5 步 pipeline —— 自动三分 + 周复盘落到 `70_Output/`。
