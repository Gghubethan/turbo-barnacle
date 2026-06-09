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
  python triage.py --dry-run  # 只列出将处理的文件：不调用模型、不写盘
  python triage.py --review   # 生成本周复盘（需 ANTHROPIC_API_KEY + CLAUDE_MODEL）

环境变量见 .env.example（会自动加载同目录 .env）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
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

API_TIMEOUT = float(os.environ.get("API_TIMEOUT", "60"))         # 单次请求超时（秒）
REVIEW_TIMEOUT = float(os.environ.get("REVIEW_TIMEOUT", "120"))  # 复盘输入长，放宽
API_MAX_RETRIES = int(os.environ.get("API_MAX_RETRIES", "2"))    # SDK 自带指数退避

LOCK_PATH = Path(__file__).with_name(".triage.lock")
LOCK_STALE_SECONDS = 2 * 60 * 60  # 超过视为进程被强杀留下的死锁，可接管


# ---- 单实例锁 -------------------------------------------------------------
def acquire_lock() -> bool:
    """O_CREAT|O_EXCL 原子建锁；拿不到返回 False，陈旧锁接管后重试一次。"""
    for _ in range(2):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(f"pid={os.getpid()} started={dt.datetime.now().isoformat()}\n")
            return True
        except FileExistsError:
            try:
                age = time.time() - LOCK_PATH.stat().st_mtime
            except FileNotFoundError:
                continue  # 对方刚好释放了，重试创建
            if age < LOCK_STALE_SECONDS:
                return False
            print(f"[lock] 锁已存在 {age / 3600:.1f} 小时，视为陈旧锁接管", file=sys.stderr)
            LOCK_PATH.unlink(missing_ok=True)
    return False


def release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


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


_deepseek = None


def deepseek_client():
    """复用同一个 client；超时与有限重试交给 SDK（指数退避）。"""
    global _deepseek
    if _deepseek is None:
        from openai import OpenAI  # 兼容 OpenAI 的 DeepSeek
        _deepseek = OpenAI(
            base_url="https://api.deepseek.com", api_key=DEEPSEEK_KEY,
            timeout=API_TIMEOUT, max_retries=API_MAX_RETRIES,
        )
    return _deepseek


def classify(content: str) -> dict:
    resp = deepseek_client().chat.completions.create(
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
        # sorted() 先固化文件列表：处理过程中会移动文件，不能边 rglob 边改目录
        for path in sorted(base.rglob("*.md")):
            try:
                post = frontmatter.load(path)
            except Exception as e:  # 单个坏 YAML 不应放倒整次运行
                print(f"[skip] {path.name}: frontmatter 解析失败: {e}", file=sys.stderr)
                continue
            if not post.get("ai_processed"):
                yield path, post


def ensure_defaults(path: Path, post: frontmatter.Post) -> None:
    """NotebookLM 来源补默认元数据。"""
    if "20_Sources/NotebookLM" in path.as_posix():  # as_posix 保证 Windows 反斜杠也匹配
        # frontmatter.Post 没有 setdefault，要落到 .metadata 这个 dict 上
        post.metadata.setdefault("type", "source")
        post.metadata.setdefault("source", "notebooklm")


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


def write_note(dest: Path, post: frontmatter.Post) -> None:
    """临时文件 + os.replace 原子落盘：中途崩溃不会留下半截笔记。"""
    tmp = dest.with_name(dest.name + ".triage-tmp")
    tmp.write_text(frontmatter.dumps(post), encoding="utf-8")
    os.replace(tmp, dest)


def process_one(path: Path, post: frontmatter.Post, dry_run: bool) -> None:
    if dry_run:  # 不调模型、不写盘，只报告会扫到哪些文件
        print(f"[dry-run] 将处理 {path.relative_to(VAULT)}")
        return
    ensure_defaults(path, post)
    meta = classify(post.content)
    post["tags"] = sorted(set((post.get("tags") or []) + meta.get("tags", [])))
    post["type"] = post.get("type") or meta.get("type", "fleeting")
    post["status"] = "processing"
    post["modified"] = today()
    post["ai_processed"] = True
    post["ai_model"] = DEEPSEEK_MODEL
    if meta.get("summary"):
        post.metadata.setdefault("summary", meta["summary"])

    folder = safe_target(meta.get("folder", ""), post.get("source"))
    target_dir = VAULT / folder
    # 已在目标目录就原地更新，否则 unique_path 会把文件自身当冲突、改名成 -1
    dest = path if path.parent == target_dir else unique_path(target_dir, path.name)
    print(f"[triage] {path.relative_to(VAULT)} → {dest.relative_to(VAULT)}  tags={post['tags']}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_note(dest, post)  # 新内容先在目标位置落稳
    if dest != path:
        path.unlink()  # 目标写成功后才删源文件，最坏情况是留下重复而非丢数据


def run_triage(dry_run: bool) -> int:
    if not VAULT.exists():
        sys.exit(f"VAULT_PATH 不存在: {VAULT}")
    if dry_run:
        print("[dry-run] 未调用模型，分类/目标目录不可信，仅验证扫描范围与零写盘。")
    elif not DEEPSEEK_KEY:
        sys.exit("缺少 DEEPSEEK_API_KEY")
    n = 0
    for path, post in iter_unprocessed():
        try:
            process_one(path, post, dry_run)
            n += 1
        except Exception as e:  # 单条失败不影响整体
            print(f"[skip] {path.name}: {e}", file=sys.stderr)
    if dry_run:
        print(f"[dry-run] 共 {n} 条待处理（未调用模型、未写盘）")
    else:
        print(f"[triage] 处理 {n} 条")
    return n


# ---- 周复盘（Claude） ----------------------------------------------------
def anthropic_client():
    from anthropic import Anthropic
    return Anthropic(api_key=ANTHROPIC_KEY,
                     timeout=REVIEW_TIMEOUT, max_retries=API_MAX_RETRIES)


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
    msg = anthropic_client().messages.create(
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
    ap.add_argument("--dry-run", action="store_true",
                    help="只列出将处理的文件，不调用模型、不写盘")
    ap.add_argument("--review", action="store_true", help="生成本周复盘")
    args = ap.parse_args()
    if not acquire_lock():
        # 定时任务撞上未结束的上一轮属正常情况，按成功退出
        print("[lock] 已有实例在运行（.triage.lock 未过期），本次跳过", file=sys.stderr)
        return
    try:
        weekly_review() if args.review else run_triage(args.dry_run)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
