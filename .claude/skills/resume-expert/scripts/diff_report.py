#!/usr/bin/env python3
"""
diff_report.py — 生成修改前后对比报告（流程 ⑨）。

职责：
1) 按 id 对应两份 resume.json，逐条列出改动 / 新增 / 删除，并统计规模；
2) 自动跑两道零编造检查：
   - 新文本里出现、但原简历全文找不到的数字 → 疑似编造的数据；
   - "参与/协助/参加"被改成"主导/负责/牵头" → 疑似抬高职级；
3) 检查残留的【待补充】占位符（交付前必须清零）。

用法：
  python3 diff_report.py resume.json resume.edited.json -o diff.md
  python3 diff_report.py resume.json resume.edited.json        # 打到终端

脚本只做机器可判定的比对；"改得好不好"仍要人看。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"【待补充[^】]*】")
NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
WEAK = ("参与", "协助", "参加", "配合", "跟进")
STRONG = ("主导", "负责", "牵头", "带领", "统筹")


def collect(resume: dict) -> dict[str, tuple[str, str]]:
    """把所有可引用单元拍平成 {id: (定位路径, 文本)}。"""
    flat: dict[str, tuple[str, str]] = {}
    for key, value in (resume.get("basics") or {}).items():
        if isinstance(value, str) and value:
            flat[f"basics.{key}"] = (f"基本信息 → {key}", value)
    for sec in resume.get("sections", []):
        title = sec.get("title", sec.get("id", ""))
        for item in sec.get("items", []):
            flat[item["id"]] = (f"{title} → 第{item['id'].rsplit('-', 1)[-1]}项", item["text"])
        for entry in sec.get("entries", []):
            label = entry.get("org") or entry["id"]
            head = "  ｜  ".join(x for x in (entry.get("org"), entry.get("role"),
                                            entry.get("date")) if x)
            flat[entry["id"]] = (f"{title} → {label}（标题行）", head)
            for i, bullet in enumerate(entry.get("bullets", []), 1):
                flat[bullet["id"]] = (f"{title} → {label} → 第{i}条", bullet["text"])
    return flat


def all_text(resume: dict) -> str:
    return json.dumps(resume, ensure_ascii=False) + "\n" + "\n".join(resume.get("raw_lines", []))


def fabrication_checks(before: str, after: str, original_blob: str) -> list[str]:
    alerts: list[str] = []
    new_numbers = [n for n in NUMBER.findall(after)
                   if n not in NUMBER.findall(before) and n not in original_blob]
    if new_numbers:
        alerts.append(f"🔴 出现原简历中找不到的数字：{'、'.join(dict.fromkeys(new_numbers))}"
                      "——请确认是用户提供的真实数据，不是被编造出来的")
    if any(w in before for w in WEAK) and any(s in after for s in STRONG) \
            and not any(w in after for w in WEAK):
        alerts.append("🔴 职级/参与度被抬高（参与/协助 → 主导/负责）——职级是事实不是修辞，面试会被追问")
    return alerts


def render(old: dict, new: dict) -> tuple[str, int]:
    before, after = collect(old), collect(new)
    original_blob = all_text(old)
    changed, added, removed = [], [], []

    for uid, (path, text) in after.items():
        if uid not in before:
            added.append((path, text))
        elif before[uid][1] != text:
            changed.append((path, before[uid][1], text))
    for uid, (path, text) in before.items():
        if uid not in after:
            removed.append((path, text))

    lines = ["# 简历修改前后对比", ""]
    old_chars = len(re.sub(r"\s", "", " ".join(t for _, t in before.values())))
    new_chars = len(re.sub(r"\s", "", " ".join(t for _, t in after.values())))
    lines.append(f"改动 **{len(changed)}** 条 ｜ 新增 **{len(added)}** 条 ｜ 删除 **{len(removed)}** 条 ｜ "
                 f"正文字数 {old_chars} → {new_chars}（{new_chars - old_chars:+d}）")
    lines.append("")

    alerts: list[str] = []
    if changed:
        lines += ["## 改动明细", ""]
        for path, old_text, new_text in changed:
            lines += [f"### {path}", "",
                      f"- **改前**：{old_text}",
                      f"- **改后**：{new_text}"]
            for alert in fabrication_checks(old_text, new_text, original_blob):
                lines.append(f"- {alert}")
                alerts.append(f"{path}：{alert}")
            lines.append("")

    if added:
        lines += ["## 新增", ""]
        for path, text in added:
            lines.append(f"- **{path}**：{text}")
            for alert in fabrication_checks("", text, original_blob):
                lines.append(f"  - {alert}")
                alerts.append(f"{path}：{alert}")
        lines.append("")

    if removed:
        lines += ["## 删除", ""] + [f"- **{path}**：{text}" for path, text in removed] + [""]

    placeholders = PLACEHOLDER.findall(json.dumps(new, ensure_ascii=False))
    lines += ["## 交付前检查", ""]
    if placeholders:
        lines.append(f"- 🔴 仍有 {len(placeholders)} 处占位符未填："
                     f"{'、'.join(dict.fromkeys(placeholders))}")
    else:
        lines.append("- ✅ 占位符已清零")
    if alerts:
        lines.append(f"- 🔴 {len(alerts)} 处零编造告警，见上文标红条目")
    else:
        lines.append("- ✅ 未发现新增数字或职级抬高")
    lines += ["- ⬜ 抽 3 条改动回 `resume.raw.txt` 核对出处（人工）",
              "- ⬜ 确认只改了用户点名要改的条目（人工）", ""]

    return "\n".join(lines), len(alerts) + len(placeholders)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成修改前后对比报告（流程 ⑨）")
    ap.add_argument("before", type=Path, help="修改前 resume.json")
    ap.add_argument("after", type=Path, help="修改后 resume.edited.json")
    ap.add_argument("-o", "--output", type=Path, help="输出 .md，省略则打到终端")
    args = ap.parse_args()

    for path in (args.before, args.after):
        if not path.exists():
            sys.exit(f"文件不存在：{path}")

    report, issues = render(json.loads(args.before.read_text(encoding="utf-8")),
                            json.loads(args.after.read_text(encoding="utf-8")))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"✓ {args.output}")
        if issues:
            print(f"⚠ {issues} 处需要处理（占位符 / 零编造告警），见报告末尾")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
