# pipeline — 知识库自动化（在常开 Mac 上跑）

完整可运行脚本，对应 [`docs/setup-ios-mac.md`](../docs/setup-ios-mac.md) §5 与
[`docs/notebooklm-to-obsidian.md`](../docs/notebooklm-to-obsidian.md) 的后处理。
脚本读写的是你 Mac 上的 vault（由 `VAULT_PATH` 指定），与本仓库分离。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 填 VAULT_PATH 与各 API key（.env 不会提交）
```

## 用法

```bash
python triage.py            # 三分 00_Inbox 与 20_Sources/NotebookLM：打标/归位/摘要
python triage.py --dry-run  # 只预览，不写盘
python triage.py --review   # 生成近 7 天复盘到 70_Output/
```

- 便宜批量活（分类/打标）走 **DeepSeek**；周复盘走 **Claude**（`CLAUDE_MODEL` 填最新 Opus）。
- 容错：单条失败只跳过该条；不会删除文件，移动时自动避免重名。
- 语义 `related` 连接建议交给 Obsidian 的 **Smart Connections** 插件（embedding），此脚本不做。

## 定时（macOS，二选一）

crontab 示例（每 30 分钟三分；周一 08:00 复盘）：

```cron
*/30 * * * * cd ~/turbo-barnacle/pipeline && .venv/bin/python triage.py >> /tmp/triage.log 2>&1
0 8 * * 1   cd ~/turbo-barnacle/pipeline && .venv/bin/python triage.py --review >> /tmp/review.log 2>&1
```

更稳的方式用 `launchd`（key 放 `.env` 或 plist 的 `EnvironmentVariables`）。
