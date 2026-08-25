---
name: resume-expert
description: 中文简历的一站式处理：读取结构化、分级诊断（必改/建议改/不建议动）、逐条说明理由、零编造精准改写、结构与信息密度复查、JD 匹配、ATS 兼容检查、DOCX/PDF 自动排版，最后输出修改前后对比。当用户上传或指向简历文件（.docx/.pdf/.md/.txt），或说"帮我看看简历/改简历/优化简历/简历排版/投这个岗位合不合适/ATS 过不过"时使用。
---

# resume-expert · 简历诊断 → 修改 → 排版 全流程

一句话职责：**先当审稿人，再当编辑，最后当排版。** 不是一上来就把用户的简历重写一遍。

## 铁律（任何阶段都不许破）

1. **零编造**：不新增经历、公司、职位、时间、技能、数字。原文里没有的数据一律写成 `【待补充：具体数字】`，回头问用户，绝不替他填一个"看起来合理"的值。
2. **先诊断，后修改**：没有拿到用户对诊断结果的确认，不进入改写阶段。诊断阶段只给结论和理由，不交付改写全文（示例句可以给，且必须标"示例"）。
3. **每条建议必须带四要素**：原文 / 问题 / 修改价值 / 优先级。给不出"改了有什么用"的建议，就不要给。
4. **保留原事实**：改写只允许换表达、换结构、换顺序、补上下文（上下文也必须来自原文其他位置）。
5. **敢说"不建议改"**：个人风格、行业惯例、已经足够好的表述，明确列进 ⚪ 不动区，并说明为什么不动。用户需要的是判断，不是全量重写。
6. **一次只改确认过的条目**：用户确认哪几条就改哪几条，不顺手改别的。
7. **隐私**：简历含真实姓名/电话/邮箱。工作产物默认放 `resume-work/`（已在 `.gitignore`），**永远不要提交到 git，不要上传到任何外部服务**。

## 目录约定

```
resume-work/                     # 工作目录，不提交
├── 原简历.docx                  # 用户输入（拷贝一份，永不原地覆盖）
├── resume.json                  # ① 结构化中间态（唯一事实来源）
├── resume.raw.txt               # ① 逐行原文，带行号，用来"逐字引用原文"
├── audit.md                     # ②③ 诊断报告
├── resume.edited.json           # ④ 改写后（在 resume.json 上改）
├── 姓名-岗位-简历.docx           # ⑥ 排版产物
├── 姓名-岗位-简历.pdf            # ⑧ 交付
└── diff.md                      # ⑧ 修改前后对比
```

## 流水线（按阶段推进，两个必停点）

| 阶段 | 做什么 | 读 | 跑 | 产出 |
| --- | --- | --- | --- | --- |
| ① 读取 | PDF/DOCX → 结构化 + 逐行原文，人工校验解析结果 | `references/01-parse.md` | `scripts/parse_resume.py` | `resume.json` `resume.raw.txt` |
| ② 诊断 | 按 10 个维度扫问题，只记录不修改 | `references/02-audit.md` | — | 问题清单（内部） |
| ③ 分级 | 三分 🔴必改 / 🟡值得改 / ⚪不建议改，排序，写理由 | `references/03-priority.md` | — | `audit.md` **← 必停点 1** |
| ④ 改写 | 只改用户确认的条目，零编造 | `references/04-rewrite.md` | — | `resume.edited.json` **← 必停点 2** |
| ⑤ JD 匹配 | 有目标 JD 时：拆要求、算匹配、找 gap（可选，可提前到 ②之前） | `references/05-jd-match.md` | — | 匹配报告 |
| ⑥ 结构复查 | 模块顺序、内容重复、信息密度、总长度 | `references/06-layout-review.md` | — | 结构结论 |
| ⑦ ATS | 机器可检项自动扫 + 人工判断项 | `references/07-ats-check.md` | `scripts/ats_check.py` | ATS 报告 |
| ⑧ 排版 | 字体/字号/行距/页边距/对齐/分页/bullet | `references/08-docx-format.md` | `scripts/build_docx.py` 或 `scripts/format_docx.py` | `.docx` + `.pdf` |
| ⑨ 终检 | 事实回溯、占位符清零、交付说明 | `references/09-final-qa.md` | `scripts/diff_report.py` | `diff.md` + 交付 |

**必停点 1（③ 之后）**：把诊断报告给用户，问"这些要改哪些"，等回复。
**必停点 2（④ 之后）**：把改写逐条对照给用户确认，再进排版。
用户明确说"你直接一路做到底"时，两个必停点可以合并成一次确认，但诊断报告仍然要先完整给出。

## 阶段③ 输出格式（用户看到的就是这个）

先给总览：

```
🔴 必改 3 条 ｜ 🟡 值得改 5 条 ｜ ⚪ 不建议动 4 处

| # | 位置 | 一句话问题 | 优先级 |
| - | ---- | -------- | ----- |
| 1 | 工作经历 → 字节跳动 → 第2条 | 写的是职责不是成果 | 🔴 |
```

再逐条展开，**固定六段式**：

```
位置：工作经历 → XX公司 → 第2条

原文：负责用户增长相关的数据分析工作。

结论：🔴 必改

原因：这是职责描述，不是成果。HR 无法从中判断你做到了什么程度；
      同岗位竞争者写同一句话的概率极高，读完记不住你。

建议：改成「动作 + 方法 + 结果」结构。原文里没有任何量化，
      我不会替你编数字，需要你补一个真实数据（留占位）。

修改后（待你确认）：搭建用户增长数据看板，覆盖 XX 个核心指标，
      支撑增长团队周会决策，使 XX 类分析的响应时间从【待补充】降至【待补充】。
```

⚪ 不建议动的部分同样要写清楚"为什么不动"——这是这套流程比"一键重写"更值钱的地方。

## 脚本速查

```bash
S=.claude/skills/resume-expert/scripts
pip install -r .claude/skills/resume-expert/requirements.txt   # 首次

python3 $S/parse_resume.py resume-work/原简历.docx --out-dir resume-work
python3 $S/ats_check.py resume-work/原简历.docx                # 也吃 .pdf / resume.json
python3 $S/build_docx.py resume-work/resume.edited.json -o "resume-work/张三-数据分析-简历.docx" --pdf
python3 $S/format_docx.py resume-work/原简历.docx -o resume-work/排版修正版.docx   # 保留原内容只修排版
python3 $S/diff_report.py resume-work/resume.json resume-work/resume.edited.json -o resume-work/diff.md
```

- `build_docx.py`：从结构化 JSON **重建**一份干净的单栏 ATS 友好简历（推荐，改写后走这条）。
- `format_docx.py`：**不重建**，只把用户原 DOCX 的字体/字号/行距/页边距/对齐/项目符号规范化（用户想保留原设计时走这条）。
- 两个脚本都不覆盖输入文件；`--pdf` 依赖本机 LibreOffice（`soffice`），没有就只出 DOCX 并提示用户自己导出。

## 常见坑

- **PDF 解析出乱码/空白**：多半是扫描件或双栏。别硬猜内容——直接告诉用户"这份 PDF 提取不出文本，ATS 也读不出来（这本身就是 🔴 问题），请给我 DOCX 或原始可编辑版本"。
- **解析器分段错了**：`parse_resume.py` 是保守启发式，一定要对照 `resume.raw.txt` 人工校验，错了就改 JSON，别在错误结构上继续诊断。
- **用户只说"帮我改简历"没给目标岗位**：先问一句目标岗位/行业，没有目标的诊断只能做通用项，价值打对折。用户不想说就按通用项做，并说明这个取舍。
- **想加关键词**：只允许把**已有事实**换成 JD 用的说法（如"用户画像"↔"用户分层"），不允许堆砌没做过的技能词。
- **中英文混排**：`references/08-docx-format.md` 里中文简历和英文简历是两套排版 profile，别混用。
