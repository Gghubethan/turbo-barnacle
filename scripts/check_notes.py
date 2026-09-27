#!/usr/bin/env python3
"""
check_notes.py — 校验 knowledge/ 下笔记是否符合 vault 的 frontmatter 契约，并检查双链能否解析。

用法：python3 scripts/check_notes.py [knowledge_dir]
退出码：0 全部通过；1 有问题（逐条打印）。
依赖：python-frontmatter（pipeline/requirements.txt 已含）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import frontmatter

REQUIRED = ["title", "created", "modified", "type", "status", "tags", "source",
            "related", "ai_processed", "ai_model"]
TYPES = {"fleeting", "literature", "permanent", "moc", "source", "output"}
STATUSES = {"inbox", "processing", "done", "review"}
SOURCES = {"捷径", "飞书", "微信", "web", "pdf", "notebooklm", "手动"}
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


def main(root: Path) -> int:
    notes = sorted(root.rglob("*.md"))
    notes = [n for n in notes if n.name != "README.md"]
    stems = {n.stem for n in notes}
    problems: list[str] = []
    for path in notes:
        rel = path.relative_to(root)
        try:
            post = frontmatter.load(path)
        except Exception as e:  # noqa: BLE001 — 坏 YAML 也要报出来
            problems.append(f"{rel}: frontmatter 解析失败: {e}")
            continue
        meta = post.metadata
        for key in REQUIRED:
            if key not in meta:
                problems.append(f"{rel}: 缺少字段 {key}")
        if meta.get("type") not in TYPES:
            problems.append(f"{rel}: type={meta.get('type')!r} 不在 {sorted(TYPES)}")
        if meta.get("status") not in STATUSES:
            problems.append(f"{rel}: status={meta.get('status')!r} 不在 {sorted(STATUSES)}")
        if meta.get("source") not in SOURCES:
            problems.append(f"{rel}: source={meta.get('source')!r} 不在受控词表")
        if meta.get("title") != path.stem:
            problems.append(f"{rel}: title={meta.get('title')!r} 与文件名不一致")
        if not isinstance(meta.get("tags"), list) or not meta.get("tags"):
            problems.append(f"{rel}: tags 应为非空列表")
        related = meta.get("related") or []
        if not isinstance(related, list):
            problems.append(f"{rel}: related 应为列表")
            related = []
        links = [m.group(1).strip() for m in WIKILINK.finditer(post.content)]
        for item in related:
            m = WIKILINK.fullmatch(str(item).strip())
            if not m:
                problems.append(f"{rel}: related 项不是双链: {item!r}")
            else:
                links.append(m.group(1).strip())
        for target in links:
            if target not in stems:
                problems.append(f"{rel}: 双链 [[{target}]] 找不到目标笔记")
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} 个问题，共检查 {len(notes)} 篇笔记")
        return 1
    print(f"OK：{len(notes)} 篇笔记，frontmatter 与双链均通过")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "knowledge"
    sys.exit(main(target))
