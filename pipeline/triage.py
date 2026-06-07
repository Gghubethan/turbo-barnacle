#!/usr/bin/env python3
"""
triage.py — 个人知识库 Inbox / NotebookLM 自动三分 + 定时复盘。

职责：
1) 扫描 00_Inbox 与 20_Sources/NotebookLM 下未处理的 .md（frontmatter ai_processed 为假）；
2) 便宜批量活 → DeepSeek：分类、打标签、判定目标文件夹、抽取一句话摘要；
3) 写回 frontmatter 并移动到目标目录；为 NotebookLM 来源补默认 type/source；
4) 可选：质量敏感的最终产出 → Claude：生成近 7 天复盘到 70_Output/。

用法：
  python triage.py            # 处理 00_Inbox + 20_Sources/NotebookLM
  python triage.py --dry-run  # 只打印将要做的改动，不落盘
  python triage.py --review   # 生成本周复盘（需 ANTHROPIC_API_KEY + CLAUDE_MODEL）

环境变量见 .env.example（会自动加载同目录 .env）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

import frontmatter  # python-frontmatter

try:  # 自动加载同目录 .env（可选依赖）
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

# ---- 配置 ----------------------------------------------------------------
VAULT = Path(os.environ.get("VAULT_PATH", "")).expanduser()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "")          # 填最新 Claude Opus 模型ID
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

SCAN_DIRS = ["00_Inbox", "20_Sources/NotebookLM"]          # 扫描哪些目录
ALLOWED_FOLDERS = [                                         # 受控目标目录，避免乱建
    "10_Notes", "20_Sources", "20_Sources/NotebookLM",
    "30_Projects", "40_Areas", "50_Resources", "60_MOC",
]


def today() -> str:
    return dt.date.today().isoformat()


# ---- DeepSeek 分类 -------------------------------------------------------
CLASSIFY_SYSTEM = (
    "你是个人知识库的整理助手。读用户给的笔记正文，输出严格 JSON："
    '{"type":"fleeting|literature|permanent|source|moc",'
    '"tags":["标签",...],'
    '"folder":"从允许列表里选一个最合适的目标文件夹",'
    '"summary":"一句话摘要"}。'
    "只输出 JSON，不要多余文字。允许的 folder：" + ", ".join(ALLOWED_FOLDERS)
)


def classify(content: str) -> dict:
    from openai import OpenAI  # 兼容 OpenAI 的 DeepSeek
    client = OpenAI(base_url="https://api.deepseek.com", api_key=DEEPSEEK_KEY)
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": content[:8000]},
        ],
    )
    return _parse_json(resp.choices[0].message.content)


def _parse_json(text: str) -> dict:
    """容错解析：剥离 ``` 围栏、取第一个 {...}。"""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"无法解析模型输出为 JSON: {text[:200]}")
    return json.loads(m.group(0))


# ---- 三分主流程 ----------------------------------------------------------
def iter_unprocessed():
    for rel in SCAN_DIRS:
        base = VAULT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            post = frontmatter.load(path)
            if not post.get("ai_processed"):
                yield path, post


def ensure_defaults(path: Path, post: frontmatter.Post) -> None:
    """NotebookLM 来源补默认元数据。"""
    if "20_Sources/NotebookLM" in path.as_posix():  # as_posix 保证 Windows 反斜杠也匹配
        post.setdefault("type", "source")
        post.setdefault("source", "notebooklm")


def safe_target(folder: str, source) -> str:
    if folder not in ALLOWED_FOLDERS:
        folder = "10_Notes"
    # NotebookLM 来源默认留在来源区，除非分类明确归入 MOC/项目等
    if source == "notebooklm" and folder in ("10_Notes", "20_Sources"):
        folder = "20_Sources/NotebookLM"
    return folder


def unique_path(dest_dir: Path, name: str) -> Path:
    dest, i = dest_dir / name, 1
    while dest.exists():
        dest = dest_dir / f"{Path(name).stem}-{i}{Path(name).suffix}"
        i += 1
    return dest


def process_one(path: Path, post: frontmatter.Post, dry_run: bool) -> None:
    ensure_defaults(path, post)
    meta = classify(post.content)
    post["tags"] = sorted(set((post.get("tags") or []) + meta.get("tags", [])))
    post["type"] = post.get("type") or meta.get("type", "fleeting")
    post["status"] = "processing"
    post["modified"] = today()
    post["ai_processed"] = True
    post["ai_model"] = DEEPSEEK_MODEL
    if meta.get("summary"):
        post.setdefault("summary", meta["summary"])

    folder = safe_target(meta.get("folder", ""), post.get("source"))
    dest = unique_path(VAULT / folder, path.name)
    print(f"[triage] {path.relative_to(VAULT)} → {dest.relative_to(VAULT)}  tags={post['tags']}")
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")  # 先写回元数据
    if dest != path:
        shutil.move(str(path), str(dest))


def run_triage(dry_run: bool) -> int:
    if not VAULT.exists():
        sys.exit(f"VAULT_PATH 不存在: {VAULT}")
    if not DEEPSEEK_KEY:
        sys.exit("缺少 DEEPSEEK_API_KEY")
    n = 0
    for path, post in iter_unprocessed():
        try:
            process_one(path, post, dry_run)
            n += 1
        except Exception as e:  # 单条失败不影响整体
            print(f"[skip] {path.name}: {e}", file=sys.stderr)
    print(f"[triage] 处理 {n} 条" + ("（dry-run）" if dry_run else ""))
    return n


# ---- 周复盘（Claude） ----------------------------------------------------
def recent_notes(days: int = 7):
    cutoff = dt.date.today() - dt.timedelta(days=days)
    out = []
    for path in VAULT.rglob("*.md"):
        if any(seg.startswith(("70_Output", "_")) for seg in path.parts):
            continue
        post = frontmatter.load(path)
        stamp = str(post.get("modified") or post.get("created") or "")[:10]
        try:
            if dt.date.fromisoformat(stamp) >= cutoff:
                out.append((path, post))
        except ValueError:
            continue
    return out


def weekly_review() -> None:
    if not ANTHROPIC_KEY:
        sys.exit("缺少 ANTHROPIC_API_KEY")
    if not CLAUDE_MODEL:
        sys.exit("缺少 CLAUDE_MODEL（填最新 Claude Opus 模型ID）")
    from anthropic import Anthropic
    notes = recent_notes(7)
    if not notes:
        print("[review] 近 7 天没有笔记，跳过")
        return
    digest = "\n\n".join(
        f"## {p.get('title') or path.stem}\ntags: {p.get('tags')}\n{p.content[:1500]}"
        for path, p in notes
    )
    prompt = (
        "下面是我近 7 天的笔记。请输出一份中文复盘：\n"
        "1) 本周主题脉络；2) 值得深挖/容易遗漏的连接；3) 下周知识预测方向（3 条）。\n\n"
        + digest[:60000]
    )
    msg = Anthropic(api_key=ANTHROPIC_KEY).messages.create(
        model=CLAUDE_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    out_dir = VAULT / "70_Output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"复盘-{today()}.md"
    body = frontmatter.Post(
        text, title=f"周复盘 {today()}", created=today(), type="output",
        source="manual", status="review", ai_processed=True,
        ai_model=CLAUDE_MODEL, tags=["复盘"],
    )
    out.write_text(frontmatter.dumps(body), encoding="utf-8")
    print(f"[review] 写入 {out.relative_to(VAULT)}")


# ---- CLI -----------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="知识库自动三分 + 周复盘")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写盘")
    ap.add_argument("--review", action="store_true", help="生成本周复盘")
    args = ap.parse_args()
    weekly_review() if args.review else run_triage(args.dry_run)


if __name__ == "__main__":
    main()
