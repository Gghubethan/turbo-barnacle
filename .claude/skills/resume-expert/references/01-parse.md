# ① 读取并结构化简历

目标：把任意格式的简历变成**两份可引用的东西**——结构化的 `resume.json`（后续所有操作的事实来源）和逐行原文 `resume.raw.txt`（诊断时"原文"字段必须逐字来自这里）。

## 支持的输入

| 格式 | 提取方式 | 注意 |
| --- | --- | --- |
| `.docx` | python-docx，含表格单元格 | 最可靠，优先要这个 |
| `.pdf` | pdfminer.six → pypdf → `pdftotext` 逐级降级 | 扫描件提不出文本，见下 |
| `.md` / `.txt` | 直读 | 结构靠标题符号 |
| `.doc`（老格式） | 不支持 | 请用户另存为 `.docx` |

## 用法

```bash
python3 .claude/skills/resume-expert/scripts/parse_resume.py resume-work/原简历.docx --out-dir resume-work
```

输出 `resume.json` + `resume.raw.txt`，并在终端打印一份**解析自检摘要**（识别到几个模块、几段经历、几条 bullet、联系方式是否抓到）。

## 关键前提：解析器是保守启发式，必须人工校验

`parse_resume.py` 用关键词表识别模块标题、用日期区间正则识别经历条目、用符号/缩进识别 bullet。它会错。**在诊断之前，必读一遍 `resume.raw.txt` 并核对 JSON**，重点核对：

- [ ] 姓名、电话、邮箱、链接抓对了吗（没抓到不代表原文没有）
- [ ] 模块数量和顺序与原文一致吗，有没有把正文误判成标题
- [ ] 每段经历的公司 / 职位 / 起止时间是否对应正确，有没有串行
- [ ] bullet 条数对得上吗（被合并或被拆开都很常见）
- [ ] 表格排版的简历，内容顺序是否被打乱（`meta.warnings` 会提示 `table_layout`）

发现错误就**直接改 `resume.json`**（它是普通 JSON，手改即可），不要在错误结构上继续往下做——诊断结论会跟着错。

## 解析失败怎么办

- **PDF 提不出文本**（输出几乎为空 / 全是乱码）：这是扫描件或图片版。不要猜内容。告诉用户：
  > 这份 PDF 提取不出文字，意味着 ATS 系统同样读不到 —— 这本身就是一条 🔴 必改项。请提供 DOCX，或可复制文字的 PDF。
- **双栏 PDF 文字交错**：`meta.warnings` 会给 `multi_column_suspected`。让用户提供 DOCX；若只有 PDF，按 `raw.txt` 人工重排后再改 JSON。
- **缺少依赖**：脚本会明确报缺哪个包，`pip install -r .claude/skills/resume-expert/requirements.txt`。

## resume.json 结构

见 `assets/resume-schema.json`（带注释说明的样例）。要点：

- `basics`：姓名、求职意向、电话、邮箱、城市、链接。
- `sections[]`：按原文顺序排列，每个有 `id` / `title` / `type`。
  - `type: "entries"` —— 工作经历、项目经历、教育背景（有公司/时间/bullet）
  - `type: "paragraph"` —— 个人简介、自我评价
  - `type: "list"` —— 技能、证书、奖项
- **每个可引用单元都有稳定 `id` 和 `line`**（`line` 指向 `resume.raw.txt` 的行号）。`id` 用于定位，例如 `exp-1-b2` = 第 1 段工作经历的第 2 条 bullet，正是诊断里"工作经历 → XX公司 → 第2条"的机器表示。
- 改写阶段**只改 `text` 字段，不动 `id`**——`diff_report.py` 靠 `id` 做前后对应。

## 引用原文的纪律

诊断报告里的"原文："必须是 `resume.raw.txt` 里的**原句逐字复制**，不许顺手润色、不许省略成"……"（长句可截断但要标 `[…]`）。用户看到自己写的原话才能判断你的意见对不对。
