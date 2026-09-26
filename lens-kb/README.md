# lens-kb · 镜片产品标准化知识库

把分散、品牌化的镜片内部资料，沉淀为可进入 **产品数据库 / 商品标签系统 / 门店 iPad 推荐 / 自动推荐规则 / 消费者话术** 的结构化知识。

目标链路：

```
验光结果 → 用户问题 → 主观症状 → 使用场景 → 功能需求 → 标准功能 → 商品标签 → SKU → 推荐理由
EXAM_     PROBLEM_   SYMPTOM_   SCENE_     NEED_      FUNC_      (PRODUCT)   SKU_   COPY_
```

当前版本：**v0.1.0**（batch-001，2026-09-26）。每批新资料在此基础上**增量更新**，不重建。

---

## 1. 目录与 16 项长期资产

| # | 资产 | 文件 |
| --- | --- | --- |
| 1 | 标准功能字典 | `dictionaries/functions.yaml`（FUNC_） |
| 2 | 技术机制字典 | `dictionaries/mechanisms.yaml`（MECH_） |
| 3 | 光学效果字典 | `dictionaries/effects.yaml`（EFFECT_） |
| 4 | 用户价值字典 | `dictionaries/values.yaml`（VALUE_） |
| 5 | 用户问题标签库 | `dictionaries/problems.yaml`（PROBLEM_） |
| 5b | 功能需求标签库 | `dictionaries/needs.yaml`（NEED_，见 §4.3） |
| 6 | 主观症状标签库 | `dictionaries/symptoms.yaml`（SYMPTOM_） |
| 7 | 使用场景标签库 | `dictionaries/scenes.yaml`（SCENE_） |
| 8 | 验光指标标签库 | `dictionaries/exams.yaml`（EXAM_） |
| 9 | 品牌术语映射表 | `dictionaries/brand_terms.yaml`（TERM_） |
| 10 | 镜片产品标准库 | `products/products.yaml`（PRODUCT_） |
| 11 | SKU 数据库 | `products/skus.csv`（SKU_） |
| 12 | 商品关系表 | `relations/product_relations.csv`（PREL_） |
| — | 标签关系表 | `relations/tag_relations.csv`（REL_） |
| 13 | 自动推荐规则库 | `rules/rules.yaml`（RULE_） |
| 14 | 消费者解释话术库 | `copy/consumer_copy.yaml`（COPY_） |
| 15 | 待确认问题库 | `open_questions.yaml`（Q_） |
| 16 | 版本变更日志 | `changelog.csv`（CHG_） |
| — | 资料来源登记 | `sources.yaml`（SRC_） |
| — | 参考数据（专家共识图表） | `reference/*.csv` |
| — | 每批处理报告（A–G） | `batches/batch-NNN.md` |
| — | 校验与导出脚本 | `tools/validate.py` |

## 2. 五层知识结构

| 层 | 回答 | 字典 |
| --- | --- | --- |
| L1 技术机制 | 怎么实现的 | MECH_ |
| L2 光学效果 | 改变了什么光学表现（禁止写营销价值） | EFFECT_ |
| L3 用户价值 | 用户能感受到什么（普通人语言） | VALUE_ |
| L4 使用场景 | 什么时候才有价值（按真实距离） | SCENE_ |
| L5 适用人群/判断条件 | 什么样的人需要（验光/年龄/症状/场景） | EXAM_ / SYMPTOM_ / PROBLEM_ |

**标准功能（FUNC_）** 是跨品牌统一的"能力"标签，由一个或多个光学效果实现，是商品匹配的主键。品牌名称一律进入 `brand_terms.yaml`，**不得直接作为 FUNC**。

## 3. 证据等级

| 等级 | 含义 | 能否进入正式自动推荐规则 |
| --- | --- | --- |
| **A** 明确事实 | 内部/品牌资料直接写明（含资料引用的研究、专家共识、检测报告） | 可以 |
| **B** 合理归纳 | 资料未直接写，但可由已有事实稳定推导 | 需业务确认后可以 |
| **C** 待确认 | 资料不足、多解释、说法冲突、医学关系不明、无明确阈值 | **不得** |

A 级内部再用 `claim_type` 区分来源性质，供话术合规使用：
`产品参数` / `品牌宣称` / `引用临床研究` / `引用专家共识` / `检测报告` / `品牌内部数据`。
"A 级"只代表"资料确实这么写"，不代表医学结论已被独立验证。

## 4. ID 与建模约定

### 4.1 ID 规则

| 前缀 | 实体 | 例 |
| --- | --- | --- |
| MECH_nnn | 技术机制 | MECH_001 微透镜阵列近视离焦 |
| EFFECT_nnn | 光学效果 | EFFECT_001 周边视网膜近视性离焦 |
| FUNC_nnn | 标准功能 | FUNC_011 中近距离视觉优化 |
| VALUE_nnn | 用户价值 | |
| PROBLEM_nnn | 用户问题 | |
| NEED_nnn | 功能需求 | |
| SYMPTOM_nnn | 主观症状 | |
| SCENE_nnn | 使用场景 | |
| EXAM_nnn | 验光/检查/档案指标 | |
| TERM_nnn | 品牌术语 | |
| PRODUCT_<BRAND>_nnn | 产品（系列级设计） | PRODUCT_ZEISS_001 |
| SKU_<BRAND>_nnn_nn | SKU（折射率×膜层×版本×通道） | SKU_ZEISS_001_03 |
| RULE_nnn / COPY_nnn / Q_nnn / REL_nnnn / PREL_nnn / CHG_nnnn / SRC_nnn | | |

- ID 一经分配**永不复用、永不改义**；废弃用 `DEPRECATE`，合并用 `MERGE`（保留旧 ID 指向新 ID）。
- 编号段预留：FUNC_001–009 近视/儿童视功能；FUNC_010–029 视觉设计；FUNC_030–049 膜层/材料。MECH_001–019 儿童近视管理；MECH_020–049 渐进/单光设计；MECH_050–069 膜层/材料。
- 新建标签前必须检查：同义词、近义词、上下位、重复（字典内 `aliases` / `parent` 字段）。

### 4.2 产品 vs SKU

- **PRODUCT** = 品牌资料中一个独立设计/系列（有独立价格页或独立技术说明）。
- **SKU** = 同一设计下的 折射率 × 膜层/变色/蓝光 × 版本（如依视路 A360/F360/豪华版）× 通道 组合，带价格与光度范围。
- 设计层功能写在 PRODUCT；**膜层/材料/变色/蓝光等随 SKU 变化的功能**写在 SKU 的 `extra_functions`；随版本变化的功能等级写在 SKU 的 `function_levels`。

### 4.3 为什么增加 NEED_（功能需求）层

目标链路中"用户问题"与"功能需求"是两个环节：问题（如 PROBLEM_008 老视）描述状态，需求（如 NEED_004 一副兼顾远中近 vs NEED_005 长时间中近舒适）描述用户想要的结果，同一问题可导出不同需求、对应不同功能。规则 `THEN` 生成 NEED，`REQUIRE/BOOST` 指向 FUNC。

### 4.4 关系类型（`predicate`）

`directly_supports` 直接支持 · `may_support` 可能支持 · `requires` 必须 · `improves` 改善 · `conflicts_with` 冲突 · `excludes` 排除 · `equivalent_to` 高度等价 · `overlaps_with` 部分重合 · `upgrade_of` 升级（A upgrade_of B = A 是 B 的升级）。

标签关系中同一主体的多个 `requires` 若为"任一满足"，用 `group` 列标同组（如 `G1`）。

产品关系另有 `comparison` 列，取值：`高度等价` / `部分重合` / `解决同一问题但机制不同` / `升级关系` / `无法直接比较`。

### 4.5 功能等级（L0–L4）

只在资料能回答"比低一级**多了什么实际能力**"时使用，**不按价格分级**。当前仅 `FUNC_016 配戴参数个性化` 有资料支撑的分级（见 functions.yaml）。儿童近视管理（FUNC_001）**不分级**：各品牌疗效数据来自不同研究设计，不可横向比较。

### 4.6 价格层级（与功能等级无关）

以该产品**最低价 SKU** 的建议零售价划分（口径待业务确认，见 Q_016）：
P1 <¥1,500 · P2 ¥1,500–2,999 · P3 ¥3,000–5,999 · P4 ¥6,000–14,999 · P5 ≥¥15,000。

### 4.7 场景距离框架

30–40cm 手机/阅读/书报 · 40–100cm 电脑/平板/办公/棋牌 · 1–3m 电视/家务/室内交流 · 3m+ 会议/讲课/驾驶/户外/看远。

### 4.8 缺失值

资料没有提供的信息统一写 `资料未提供`；没有明确阈值统一写 `阈值待业务确认`。**禁止用常识补全**。

## 5. 每批资料处理流程

1. 登记来源 → `sources.yaml`（新 SRC_ID、页码、版本日期、已知问题）
2. 事实提取 → 产品识别 → 五层拆解
3. 标签匹配：先查字典与 `brand_terms.yaml`，复用 / 新建 / 合并 / 拆分
4. 跨品牌比较 → `product_relations.csv`
5. 验光/症状/场景关联 → `tag_relations.csv`、`exams.yaml`
6. 规则影响 → `rules.yaml`（状态：`可上线候选` / `草案(阈值待业务确认)` / `阻塞(C类)`）
7. 每一处新增/修改写入 `changelog.csv`（ADD / UPDATE / MERGE / SPLIT / DEPRECATE / CONFLICT），**不允许静默修改**
8. 待确认 → `open_questions.yaml`
9. 运行校验：`python lens-kb/tools/validate.py`
10. 输出 `batches/batch-NNN.md`（A–G 报告）

## 6. 校验与导出

```bash
python lens-kb/tools/validate.py            # 校验 ID 唯一、前缀、引用完整、关系类型、证据等级、变更日志覆盖
python lens-kb/tools/validate.py --export   # 额外导出 lens-kb/build/kb.json（供数据库/前端导入）
```

依赖：Python 3.9+、PyYAML。
