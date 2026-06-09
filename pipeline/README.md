# pipeline — 知识库自动化（在常开 Windows PC 上跑）

完整可运行脚本，对应 [`docs/setup-ios-windows.md`](../docs/setup-ios-windows.md) §5 与
[`docs/notebooklm-to-obsidian.md`](../docs/notebooklm-to-obsidian.md) 的后处理。
脚本读写的是你电脑上的 vault（由 `VAULT_PATH` 指定），与本仓库分离。脚本跨平台，下面以 Windows 为例。

## 安装（Windows PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # 填 VAULT_PATH 与各 API key（.env 不会提交）
```

## 用法

```powershell
python triage.py            # 三分 00_Inbox 与 20_Sources/NotebookLM：打标/归位/摘要
python triage.py --dry-run  # 只预览，不写盘
python triage.py --review   # 生成近 7 天复盘到 70_Output/
```

- 便宜批量活（分类/打标）走 **DeepSeek**；周复盘走 **Claude**（`CLAUDE_MODEL` 填最新 Opus）。
- 容错：单条失败只跳过该条；不会删除文件，移动时自动避免重名。
- 语义 `related` 连接建议交给 Obsidian 的 **Smart Connections** 插件（embedding），此脚本不做。
- `VAULT_PATH` 在 Windows 用正斜杠最省事，如 `C:/Users/你/Documents/vault`。

## 测试

```powershell
python -m pytest tests/ -v
```

测试不碰网络（模型调用全部 mock），用临时目录模拟 vault，验证打标、归位、重名、坏 YAML 容错与 dry-run 语义。改动 `triage.py` 后先跑这个。

## 定时（Windows 任务计划程序）

用「任务计划程序」(Task Scheduler) 建两个任务，或用 `schtasks`（每 30 分钟三分；周一 08:00 复盘）：

```bat
schtasks /Create /TN "KB Triage" /SC MINUTE /MO 30 ^
  /TR "C:\path\to\pipeline\.venv\Scripts\python.exe C:\path\to\pipeline\triage.py"

schtasks /Create /TN "KB Review" /SC WEEKLY /D MON /ST 08:00 ^
  /TR "C:\path\to\pipeline\.venv\Scripts\python.exe C:\path\to\pipeline\triage.py --review"
```

API key 放 `pipeline\.env`（脚本会自动加载），或设为系统环境变量。
