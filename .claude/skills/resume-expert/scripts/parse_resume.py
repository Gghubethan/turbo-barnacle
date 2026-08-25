#!/usr/bin/env python3
"""
parse_resume.py — 简历读取与结构化（流程 ①）。

职责：
1) 从 .docx / .pdf / .md / .txt 提取逐行原文（DOCX 含表格单元格）；
2) 用保守启发式切分模块、经历条目、bullet，给每个可引用单元分配稳定 id；
3) 输出 resume.json（后续唯一事实来源）与 resume.raw.txt（带行号，用于逐字引用原文）；
4) 打印解析自检摘要，并把可疑之处写进 meta.warnings。

用法：
  python3 parse_resume.py 简历.docx --out-dir resume-work
  python3 parse_resume.py 简历.pdf --out-dir resume-work --quiet

启发式一定会出错：拿到结果必须对照 resume.raw.txt 人工校验，错了直接改 resume.json。
依赖：python-docx（docx）、pdfminer.six 或 pypdf 或 pdftotext（仅 PDF 需要）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---- 模块标题关键词 -------------------------------------------------------
SECTION_KEYWORDS: list[tuple[str, str, list[str]]] = [
    # (section_id, 默认类型, 关键词)
    ("summary", "paragraph", ["个人简介", "自我评价", "个人总结", "职业目标", "求职意向",
                              "个人优势", "summary", "profile", "objective", "about me"]),
    ("experience", "entries", ["工作经历", "工作经验", "实习经历", "实习经验", "职业经历",
                               "工作履历", "work experience", "experience", "employment"]),
    ("project", "entries", ["项目经历", "项目经验", "项目实践", "核心项目", "projects", "project experience"]),
    ("education", "entries", ["教育背景", "教育经历", "学历", "教育", "education"]),
    ("skills", "list", ["专业技能", "技能特长", "技能", "技术栈", "掌握技能", "skills",
                        "technical skills", "core competencies"]),
    ("awards", "list", ["荣誉奖项", "获奖经历", "奖项", "荣誉", "awards", "honors"]),
    ("certificates", "list", ["证书", "资格证书", "certifications", "licenses"]),
    ("campus", "entries", ["校园经历", "社团经历", "学生工作", "校内实践"]),
    ("publications", "list", ["论文", "发表", "专利", "publications", "patents"]),
    ("other", "list", ["其他", "兴趣爱好", "自我介绍", "additional", "interests"]),
]

BULLET_CHARS = "•▪●◆◇·‣◦∙-–—*＊❖✦➢➤>《"
RE_BULLET = re.compile(r"^\s*([" + re.escape(BULLET_CHARS) + r"]|\d{1,2}[.)、]|\(\d{1,2}\))\s+")
RE_DATE_RANGE = re.compile(
    r"((19|20)\d{2}\s*[./年\-]\s*\d{0,2}\s*月?)\s*[-–—~～至到]{1,2}\s*"
    r"((19|20)\d{2}\s*[./年\-]\s*\d{0,2}\s*月?|至今|今|现在|present|now|current)",
    re.IGNORECASE,
)
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[-\s]?)?1[3-9]\d{9}(?!\d)|(?<!\d)\d{3}[-\s]\d{3,4}[-\s]\d{4}(?!\d)")
RE_URL = re.compile(r"(https?://\S+|(?:www|github\.com|linkedin\.com)\S*)", re.IGNORECASE)
SEP = re.compile(r"\s*[｜|·•/\t]\s*|\s{3,}")


# ---- 提取：各格式 → 行 ----------------------------------------------------
def read_docx(path: Path) -> tuple[list[dict], list[str]]:
    try:
        import docx  # python-docx
    except ImportError:
        sys.exit("缺少依赖 python-docx：pip install -r .claude/skills/resume-expert/requirements.txt")

    doc = docx.Document(str(path))
    lines: list[dict] = []

    def push(text: str, style: str = "", from_table: bool = False) -> None:
        text = text.replace("\xa0", " ").rstrip()
        if text.strip():
            lines.append({"text": text.strip(), "style": style, "from_table": from_table})

    # 按文档顺序遍历 body（段落与表格交替出现）
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            push(para.text, para.style.name if para.style is not None else "")
        elif tag == "tbl":
            table = Table(child, doc)
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        push(para.text, para.style.name if para.style is not None else "", True)

    warnings: list[str] = []
    if lines and sum(1 for ln in lines if ln["from_table"]) / len(lines) > 0.3:
        warnings.append("table_layout：大量内容来自表格，阅读顺序可能被打乱，且对 ATS 不友好")
    return lines, warnings


def read_pdf(path: Path) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    text = ""
    xs: list[float] = []

    try:  # 首选 pdfminer.six：顺带拿到 x 坐标做双栏检测
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer

        chunks: list[str] = []
        for layout in extract_pages(str(path)):
            width = float(getattr(layout, "width", 0) or 0)
            for element in layout:
                if isinstance(element, LTTextContainer):
                    chunks.append(element.get_text())
                    if width:
                        xs.append(float(element.x0) / width)
        text = "\n".join(chunks)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — 换下一个提取器
        warnings.append(f"pdfminer 提取失败（{exc}），已降级")

    if not text.strip():
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"pypdf 提取失败（{exc}），已降级")

    if not text.strip() and shutil.which("pdftotext"):
        try:
            text = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=60, check=True,
            ).stdout
        except (subprocess.SubprocessError, OSError) as exc:
            warnings.append(f"pdftotext 提取失败（{exc}）")

    if not text.strip():
        warnings.append(
            "no_text_extracted：这份 PDF 提取不出文字（扫描件/图片版），ATS 同样读不到——"
            "属于 🔴 必改项，请让用户提供 DOCX 或可复制文字的 PDF"
        )
        if not any(m in " ".join(warnings) for m in ("pdfminer", "pypdf", "pdftotext")):
            warnings.append("未安装任何 PDF 提取库：pip install pdfminer.six")

    if len(xs) >= 12:  # 双栏检测：x0 明显分成左右两簇，且右簇占比可观
        right = [x for x in xs if x > 0.45]
        if 0.25 <= len(right) / len(xs) <= 0.75:
            warnings.append("multi_column_suspected：疑似双栏排版，文字顺序可能左右交错，请核对 raw.txt")

    lines = [{"text": ln.strip(), "style": "", "from_table": False}
             for ln in text.splitlines() if ln.strip()]
    return lines, warnings


def read_plain(path: Path) -> tuple[list[dict], list[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        style = "Heading" if stripped.startswith("#") else ""
        lines.append({"text": stripped.lstrip("# ").strip(), "style": style, "from_table": False})
    return lines, []


# ---- 切分：行 → 结构 ------------------------------------------------------
def match_section(text: str, style: str) -> tuple[str, str] | None:
    """判断某行是否是模块标题，返回 (section_id, 类型)。"""
    if (m := re.match(r"^([^:：]{2,10})[:：]\s*(\S.*)$", text)) and len(m.group(2)) > 1:
        return None  # "求职意向：数据分析师"是内容行，不是模块标题
    plain = re.sub(r"[\s:：|｜/\-—_·]+", "", text).lower()
    if len(plain) > 14:  # 标题不会很长
        return None
    for section_id, kind, keywords in SECTION_KEYWORDS:
        for kw in keywords:
            key = kw.replace(" ", "").lower()
            if plain == key or (len(plain) <= 12 and key in plain):
                return section_id, kind
    if style.startswith("Heading") and len(plain) <= 12:
        return "custom:" + text.strip(), "entries"
    return None


def is_bullet(text: str, style: str) -> bool:
    return bool(RE_BULLET.match(text)) or "List" in style


def strip_bullet(text: str) -> str:
    return RE_BULLET.sub("", text).strip()


def parse_entry_title(text: str) -> dict:
    """从"公司 | 职位 | 2021.03-2023.06"这类行里尽量拆出字段，拆不出就留空。"""
    date = ""
    match = RE_DATE_RANGE.search(text)
    if match:
        date = match.group(0).strip()
        text = text.replace(match.group(0), " ").strip()
    parts = [p.strip(" -—–|｜·、") for p in SEP.split(text) if p and p.strip(" -—–|｜·、")]
    entry = {"org": parts[0] if parts else text.strip(), "role": "", "location": "", "date": date}
    if len(parts) >= 2:
        entry["role"] = parts[1]
    if len(parts) >= 3:
        entry["location"] = parts[2]
    return entry


def extract_basics(lines: list[dict]) -> dict:
    """从第一个模块标题之前的行里抓基本信息。"""
    basics = {"name": "", "headline": "", "phone": "", "email": "", "location": "", "links": []}
    blob = "\n".join(ln["text"] for ln in lines)
    if (m := RE_EMAIL.search(blob)):
        basics["email"] = m.group(0)
    if (m := RE_PHONE.search(blob)):
        basics["phone"] = m.group(0)
    basics["links"] = list(dict.fromkeys(RE_URL.findall(blob)))[:5]
    for ln in lines:  # 姓名：靠前、短、无数字无邮箱
        text = ln["text"]
        if 2 <= len(text) <= 12 and not re.search(r"[\d@]", text):
            basics["name"] = text
            break
    for ln in lines:
        if (m := re.search(r"(求职意向|应聘岗位|目标岗位|意向岗位)[:：]?\s*(.+)", ln["text"])):
            basics["headline"] = m.group(2).strip()
            break
    if (m := re.search(r"([一-龥]{2,8}(?:省|市|区))", blob)):
        basics["location"] = m.group(1)
    return basics


def segment(lines: list[dict]) -> tuple[dict, list[dict]]:
    """把行切成模块/条目/bullet；返回 (basics, sections)。"""
    heads: list[dict] = []          # 第一个模块标题之前的行
    sections: list[dict] = []
    current: dict | None = None
    entry: dict | None = None
    counters: dict[str, int] = {}

    for idx, ln in enumerate(lines):
        text, style = ln["text"], ln["style"]
        hit = match_section(text, style)
        if hit:
            section_id, kind = hit
            counters[section_id] = counters.get(section_id, 0) + 1
            uid = section_id if counters[section_id] == 1 else f"{section_id}-{counters[section_id]}"
            current = {"id": uid.replace("custom:", ""), "title": text.strip(),
                       "type": kind, "line": idx + 1,
                       **({"entries": []} if kind == "entries" else {"items": []})}
            sections.append(current)
            entry = None
            continue

        if current is None:
            heads.append(ln)
            continue

        if current["type"] == "entries":
            bullet = is_bullet(text, style)
            has_date = bool(RE_DATE_RANGE.search(text))
            if not bullet and (has_date or entry is None):
                entry = {"id": f"{current['id']}-{len(current['entries']) + 1}",
                         "line": idx + 1, "bullets": [], **parse_entry_title(text)}
                current["entries"].append(entry)
            elif entry is not None and not bullet and not entry["bullets"] and not entry["role"] \
                    and len(text) <= 24:
                entry["role"] = text.strip()          # 职位单独占一行的写法
            else:
                if entry is None:                      # 没有标题行就先兜一个空条目
                    entry = {"id": f"{current['id']}-1", "line": idx + 1, "bullets": [],
                             "org": "", "role": "", "location": "", "date": ""}
                    current["entries"].append(entry)
                entry["bullets"].append({
                    "id": f"{entry['id']}-b{len(entry['bullets']) + 1}",
                    "line": idx + 1,
                    "text": strip_bullet(text),
                    "marker": bullet,
                })
        else:
            current["items"].append({
                "id": f"{current['id']}-{len(current['items']) + 1}",
                "line": idx + 1,
                "text": strip_bullet(text),
            })

    return extract_basics(heads if len(heads) >= 2 else lines[:8]), sections


# ---- 自检 ------------------------------------------------------------------
def self_check(resume: dict) -> list[str]:
    notes: list[str] = []
    basics = resume["basics"]
    if not basics["name"]:
        notes.append("未识别到姓名，请核对 raw.txt 后手动填入 basics.name")
    if not basics["phone"] and not basics["email"]:
        notes.append("未识别到电话和邮箱——若原文确实没有，这是 🔴 必改项")
    if not resume["sections"]:
        notes.append("未识别到任何模块标题：可能是无标题排版或模块名过于个性化，需人工切分")
    for section in resume["sections"]:
        if section["type"] == "entries":
            for entry in section["entries"]:
                if not entry["date"]:
                    notes.append(f"{section['title']} → {entry['org'] or entry['id']}：未识别到时间区间")
                if not entry["bullets"] and not section["id"].startswith("education"):
                    notes.append(f"{section['title']} → {entry['org'] or entry['id']}：没有正文条目")
    return notes


def build(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        lines, warnings = read_docx(path)
    elif suffix == ".pdf":
        lines, warnings = read_pdf(path)
    elif suffix in (".md", ".txt", ".markdown"):
        lines, warnings = read_plain(path)
    elif suffix == ".doc":
        sys.exit("不支持旧版 .doc，请在 Word 里另存为 .docx 后重试")
    else:
        sys.exit(f"不支持的格式：{suffix}（支持 .docx / .pdf / .md / .txt）")

    basics, sections = segment(lines)
    total_chars = sum(len(ln["text"]) for ln in lines)
    if total_chars < 80:
        warnings.append("提取到的文字极少，解析结果基本不可用，请换一份输入文件")

    return {
        "meta": {
            "source_file": path.name,
            "parsed_at": dt.datetime.now().isoformat(timespec="seconds"),
            "parser": f"parse_resume.py/{suffix.lstrip('.')}",
            "line_count": len(lines),
            "char_count": total_chars,
            "warnings": warnings,
        },
        "basics": basics,
        "sections": sections,
        "raw_lines": [ln["text"] for ln in lines],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="简历读取与结构化（流程 ①）")
    ap.add_argument("input", type=Path, help="简历文件：.docx / .pdf / .md / .txt")
    ap.add_argument("--out-dir", type=Path, default=None, help="输出目录，默认与输入同目录")
    ap.add_argument("--quiet", action="store_true", help="不打印自检摘要")
    args = ap.parse_args()

    if not args.input.exists():
        sys.exit(f"文件不存在：{args.input}")
    out_dir = args.out_dir or args.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    resume = build(args.input)
    json_path = out_dir / "resume.json"
    raw_path = out_dir / "resume.raw.txt"
    json_path.write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_path.write_text(
        "\n".join(f"{i + 1:>4} | {text}" for i, text in enumerate(resume["raw_lines"])),
        encoding="utf-8",
    )

    if not args.quiet:
        entries = sum(len(s.get("entries", [])) for s in resume["sections"])
        bullets = sum(len(e["bullets"]) for s in resume["sections"] for e in s.get("entries", []))
        items = sum(len(s.get("items", [])) for s in resume["sections"])
        print(f"✓ {json_path}\n✓ {raw_path}")
        print(f"\n解析自检：{len(resume['sections'])} 个模块 / {entries} 段经历 / "
              f"{bullets} 条 bullet / {items} 条列表项 / {resume['meta']['char_count']} 字")
        print(f"姓名={resume['basics']['name'] or '—'}  电话={resume['basics']['phone'] or '—'}  "
              f"邮箱={resume['basics']['email'] or '—'}")
        for section in resume["sections"]:
            count = len(section.get("entries", section.get("items", [])))
            print(f"  - {section['title']}（{section['type']}，{count} 项）")
        for note in resume["meta"]["warnings"] + self_check(resume):
            print(f"  ⚠ {note}")
        print("\n启发式解析必然有误差：请对照 resume.raw.txt 核对后再进入诊断，错了直接改 resume.json。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
