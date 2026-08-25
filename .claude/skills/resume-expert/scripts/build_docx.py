#!/usr/bin/env python3
"""
build_docx.py — 从结构化 JSON 重建一份排版规范、ATS 友好的简历（流程 ⑧）。

职责：
1) 读 resume.json / resume.edited.json + assets/format-profiles.json；
2) 生成单栏 DOCX：无表格布局、无文本框、联系方式在正文首行、标准项目符号；
3) 统一字体（中西文分设）、字号、行距、段间距、页边距、左对齐、悬挂缩进；
4) 控制分页：条目整体不跨页、标题跟随下段；
5) 可选转 PDF（需本机 LibreOffice），并回报实际页数。

用法：
  python3 build_docx.py resume-work/resume.edited.json -o "resume-work/张三-数据分析-简历.docx" --pdf
  python3 build_docx.py resume-work/resume.json -o out.docx --profile en

不覆盖输入文件；输出路径已存在时需加 --force。
依赖：python-docx；--pdf 需要 soffice（LibreOffice）。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
except ImportError as exc:
    sys.exit(f"依赖导入失败（{exc}）：pip install -r .claude/skills/resume-expert/requirements.txt")

PROFILES = Path(__file__).resolve().parent.parent / "assets" / "format-profiles.json"
PLACEHOLDER = re.compile(r"【待补充[^】]*】")


def load_profile(name: str | None, resume: dict) -> dict:
    data = json.loads(PROFILES.read_text(encoding="utf-8"))
    if name:
        if name not in data:
            sys.exit(f"未知 profile：{name}（可选：{[k for k in data if not k.startswith('_')]}）")
        return data[name]
    blob = json.dumps(resume, ensure_ascii=False)
    cjk = len(re.findall(r"[一-龥]", blob))
    return data["zh"] if cjk > len(blob) * 0.1 else data["en"]


def set_font(run, profile: dict, size: float, bold: bool = False) -> None:
    """中西文字体必须分别设定，否则数字会被中文字体渲染得很难看。"""
    run.font.name = profile["fonts"]["ascii"]
    run.font.size = Pt(size)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), profile["fonts"]["ascii"])
    rfonts.set(qn("w:hAnsi"), profile["fonts"]["ascii"])
    rfonts.set(qn("w:eastAsia"), profile["fonts"]["east_asia"])


def add_para(doc, profile: dict, text: str = "", *, size: float, bold: bool = False,
             before: float = 0, after: float = 0, keep_with_next: bool = False,
             keep_together: bool = False, indent: float = 0, hanging: float = 0):
    para = doc.add_paragraph()
    fmt = para.paragraph_format
    fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
    fmt.line_spacing = profile["spacing"]["line_spacing"]
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.keep_with_next = keep_with_next
    fmt.keep_together = keep_together
    if indent:
        fmt.left_indent = Cm(indent)
    if hanging:
        fmt.first_line_indent = Cm(-hanging)
    if text:
        set_font(para.add_run(text), profile, size, bold)
    return para


# w:pBdr 在 CT_PPr 里的后继元素，插入位置错了 Word 会直接报文件损坏
PBDR_SUCCESSORS = (
    "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
    "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
    "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
    "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
    "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)


def add_bottom_border(para) -> None:
    """模块标题下的横线：用段落边框，不用下划线也不用画图。"""
    ppr = para._element.get_or_add_pPr()
    pbdr = ppr.makeelement(qn("w:pBdr"), {})
    bottom = pbdr.makeelement(qn("w:bottom"), {
        qn("w:val"): "single", qn("w:sz"): "6", qn("w:space"): "1", qn("w:color"): "999999",
    })
    pbdr.append(bottom)
    ppr.insert_element_before(pbdr, *PBDR_SUCCESSORS)


def usable_width_cm(profile: dict) -> float:
    page = profile["page"]
    return 21.0 - page["margin_left_cm"] - page["margin_right_cm"]  # A4 宽 21cm


def render(resume: dict, profile: dict):
    doc = docx.Document()
    page, sizes, spacing, bullet = profile["page"], profile["sizes"], profile["spacing"], profile["bullet"]

    section = doc.sections[0]
    section.top_margin, section.bottom_margin = Cm(page["margin_top_cm"]), Cm(page["margin_bottom_cm"])
    section.left_margin, section.right_margin = Cm(page["margin_left_cm"]), Cm(page["margin_right_cm"])

    normal = doc.styles["Normal"]
    normal.font.name = profile["fonts"]["ascii"]
    normal.font.size = Pt(sizes["body"])
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), profile["fonts"]["east_asia"])

    basics = resume.get("basics", {})
    if basics.get("name"):
        add_para(doc, profile, basics["name"], size=sizes["name"], bold=True,
                 after=spacing["name_after_pt"], keep_with_next=True)
    if basics.get("headline"):
        add_para(doc, profile, f"求职意向：{basics['headline']}", size=sizes["entry_title"],
                 bold=True, after=2, keep_with_next=True)
    contact = [basics.get(k, "") for k in ("phone", "email", "location")]
    contact += list(basics.get("links", []))
    contact = [c for c in contact if c]
    if contact:  # 联系方式放正文首行，绝不放页眉页脚（ATS 多数不读页眉）
        add_para(doc, profile, "  |  ".join(contact), size=sizes["contact"],
                 after=spacing["contact_after_pt"])

    tab_cm = usable_width_cm(profile)
    for sec in resume.get("sections", []):
        heading = add_para(doc, profile, sec.get("title", ""), size=sizes["section_heading"],
                           bold=True, before=spacing["section_before_pt"],
                           after=spacing["section_after_pt"], keep_with_next=True)
        if profile["rules"].get("section_rule_line"):
            add_bottom_border(heading)

        if sec.get("type") == "entries":
            for entry in sec.get("entries", []):
                title = "  ｜  ".join(x for x in (entry.get("org"), entry.get("role"),
                                                 entry.get("location")) if x)
                para = add_para(doc, profile, size=sizes["entry_title"],
                                before=spacing["entry_before_pt"], after=spacing["entry_after_pt"],
                                keep_with_next=True, keep_together=profile["rules"]["keep_entry_together"])
                para.paragraph_format.tab_stops.add_tab_stop(Cm(tab_cm), WD_TAB_ALIGNMENT.RIGHT)
                set_font(para.add_run(title), profile, sizes["entry_title"], bold=True)
                if entry.get("date"):  # 时间靠右：用右对齐制表位，不用表格
                    set_font(para.add_run("\t" + entry["date"]), profile, sizes["entry_title"])
                for item in entry.get("bullets", []):
                    add_para(doc, profile, f"{bullet['char']} {item['text']}", size=sizes["bullet"],
                             after=spacing["bullet_after_pt"],
                             keep_together=profile["rules"]["keep_entry_together"],
                             indent=bullet["indent_left_cm"], hanging=bullet["hanging_cm"])
        else:
            for item in sec.get("items", []):
                add_para(doc, profile, item["text"], size=sizes["body"],
                         after=spacing["bullet_after_pt"])
    return doc


def to_pdf(docx_path: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("⚠ 未找到 LibreOffice（soffice），只生成了 DOCX。\n"
              "  请在 Word 里「另存为 PDF」（不要用“打印成图片”，那样文字无法被提取）。")
        return None
    try:
        proc = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir",
                               str(docx_path.parent), str(docx_path)],
                              capture_output=True, text=True, timeout=180)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"⚠ 调用 LibreOffice 失败（{exc}），请在 Word 里手动导出 PDF")
        return None

    pdf = docx_path.with_suffix(".pdf")
    if pdf.exists():
        return pdf
    # soffice 转换失败时也可能返回 0（例如只装了 core 没装 writer 模块），必须按产物判断
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    print("⚠ LibreOffice 没有生成 PDF" + (f"：{detail[-1]}" if detail else ""))
    print("  DOCX 已生成，可在 Word 里「另存为 PDF」；"
          "或安装完整版 LibreOffice（Debian 需 libreoffice-writer，只装 core 转不了 docx）。")
    return None


def page_count(pdf: Path) -> int | None:
    try:
        import pypdf

        return len(pypdf.PdfReader(str(pdf)).pages)
    except Exception:  # noqa: BLE001 — 数不出页数不影响交付
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="从结构化 JSON 重建规范排版的简历 DOCX（流程 ⑧）")
    ap.add_argument("input", type=Path, help="resume.json / resume.edited.json")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 .docx 路径")
    ap.add_argument("--profile", choices=["zh", "en"], default=None, help="排版规格，默认按中文占比自动判断")
    ap.add_argument("--pdf", action="store_true", help="同时转 PDF（需要本机 LibreOffice）")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    args = ap.parse_args()

    if not args.input.exists():
        sys.exit(f"文件不存在：{args.input}")
    if args.output.suffix.lower() != ".docx":
        sys.exit("输出必须是 .docx")
    if args.output.exists() and not args.force:
        sys.exit(f"输出文件已存在：{args.output}（加 --force 覆盖）")

    resume = json.loads(args.input.read_text(encoding="utf-8"))
    profile = load_profile(args.profile, resume)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(resume, profile).save(str(args.output))
    print(f"✓ {args.output}（profile={profile['label']}）")

    left = PLACEHOLDER.findall(json.dumps(resume, ensure_ascii=False))
    if left:  # 交付前必须清零，见 references/09-final-qa.md
        print(f"⚠ 仍有 {len(left)} 处待补充占位符未填：{'、'.join(dict.fromkeys(left))}")

    if args.pdf:
        pdf = to_pdf(args.output)
        if pdf:
            pages = page_count(pdf)
            print(f"✓ {pdf}" + (f"（{pages} 页）" if pages else ""))
            limit = profile["rules"].get("max_pages")
            if pages and limit and pages > limit:
                print(f"⚠ 超过 {limit} 页：按 references/06-layout-review.md 压缩内容")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
