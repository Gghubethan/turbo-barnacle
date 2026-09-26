#!/usr/bin/env python3
"""lens-kb 校验与导出。

校验：ID 唯一与前缀、跨文件引用完整、关系类型与证据等级取值、产品必填字段、
来源页码合法、变更日志覆盖（每个实体都有 ADD 记录）。
用法：
    python lens-kb/tools/validate.py            # 只校验
    python lens-kb/tools/validate.py --export   # 校验通过后导出 lens-kb/build/kb.json
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import yaml

KB = Path(__file__).resolve().parent.parent

PREDICATES = {"directly_supports", "may_support", "requires", "improves", "conflicts_with",
              "excludes", "equivalent_to", "overlaps_with", "upgrade_of"}
COMPARISONS = {"高度等价", "部分重合", "解决同一问题但机制不同", "升级关系", "无法直接比较"}
EVIDENCE = {"A", "B", "C"}
RULE_STATUS = {"可上线候选", "草案", "阻塞"}
CHANGE_ACTIONS = {"ADD", "UPDATE", "MERGE", "SPLIT", "DEPRECATE", "CONFLICT"}
LEVELS = {"L0", "L1", "L2", "L3", "L4"}

# 用户要求的产品字段（PRODUCT_ID/SKU_ID/与其他产品关系 分别由 id、skus.csv、product_relations.csv 承载）
PRODUCT_FIELDS = ["id", "brand", "series", "name", "product_type", "official_tech_names", "official_claims",
                  "mechanisms", "effects", "functions", "values", "problems", "population", "age", "symptoms",
                  "scenes", "exams", "required_conditions", "suggested_conditions", "exclusion_conditions",
                  "function_levels", "price_tier", "evidence_notes", "sources", "version", "open_questions"]

ID_RE = re.compile(r"\b(?:PRODUCT_[A-Z]+_\d{3}|SKU_[A-Z]+_\d{3}_\d{2}|"
                   r"(?:MECH|EFFECT|FUNC|VALUE|PROBLEM|NEED|SYMPTOM|SCENE|EXAM|TERM|RULE|COPY|Q|REL|PREL|SRC|CHG)_\d{3,4})\b")
SRC_RE = re.compile(r"\b(SRC_\d{3})#p(\d+)\b")

DICTS = {  # file -> (top key, id prefix)
    "dictionaries/mechanisms.yaml": ("mechanisms", "MECH_"),
    "dictionaries/effects.yaml": ("effects", "EFFECT_"),
    "dictionaries/functions.yaml": ("functions", "FUNC_"),
    "dictionaries/values.yaml": ("values", "VALUE_"),
    "dictionaries/problems.yaml": ("problems", "PROBLEM_"),
    "dictionaries/needs.yaml": ("needs", "NEED_"),
    "dictionaries/symptoms.yaml": ("symptoms", "SYMPTOM_"),
    "dictionaries/scenes.yaml": ("scenes", "SCENE_"),
    "dictionaries/exams.yaml": ("exams", "EXAM_"),
    "dictionaries/brand_terms.yaml": ("terms", "TERM_"),
    "products/products.yaml": ("products", "PRODUCT_"),
    "rules/rules.yaml": ("rules", "RULE_"),
    "copy/consumer_copy.yaml": ("copy", "COPY_"),
    "open_questions.yaml": ("questions", "Q_"),
    "sources.yaml": ("sources", "SRC_"),
}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def load_yaml(rel):
    with open(KB / rel, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_csv(rel):
    with open(KB / rel, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(str(k))
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def tagged_ids(value):
    """Return IDs from a tag field: list, {A:[],B:[],C:[]}, or a '资料未提供' string."""
    if value is None or isinstance(value, str):
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            if k not in EVIDENCE:
                raise ValueError(f"证据分组键必须是 A/B/C，实际为 {k!r}")
            out += v or []
        return out
    return []


def main(argv):
    rep = Report()
    data, ids, src_pages = {}, {}, {}

    # ---- 1. 载入并登记 ID ----
    for rel, (key, prefix) in DICTS.items():
        doc = load_yaml(rel)
        items = doc.get(key) or []
        data[rel] = items
        for it in items:
            i = it.get("id")
            if not i or not str(i).startswith(prefix):
                rep.err(f"{rel}: ID {i!r} 前缀应为 {prefix}")
            if i in ids:
                rep.err(f"ID 重复：{i}（{ids[i]} 与 {rel}）")
            ids[i] = rel
    for s in data["sources.yaml"]:
        src_pages[s["id"]] = int(s["pages"])

    skus = load_csv("products/skus.csv")
    tag_rels = load_csv("relations/tag_relations.csv")
    prod_rels = load_csv("relations/product_relations.csv")
    changelog = load_csv("changelog.csv") if (KB / "changelog.csv").exists() else []
    for rel, rows, col, prefix in [("products/skus.csv", skus, "sku_id", "SKU_"),
                                   ("relations/tag_relations.csv", tag_rels, "rel_id", "REL_"),
                                   ("relations/product_relations.csv", prod_rels, "prel_id", "PREL_"),
                                   ("changelog.csv", changelog, "change_id", "CHG_")]:
        for r in rows:
            i = r[col]
            if not i.startswith(prefix):
                rep.err(f"{rel}: ID {i!r} 前缀应为 {prefix}")
            if i in ids:
                rep.err(f"ID 重复：{i}")
            ids[i] = rel

    def check_ref(where, i):
        if i not in ids:
            rep.err(f"{where}: 引用了不存在的 ID {i}")

    # ---- 2. 全文 ID / 来源页码引用扫描 ----
    scan = {rel: data[rel] for rel in DICTS} | {"products/skus.csv": skus, "relations/tag_relations.csv": tag_rels,
                                                 "relations/product_relations.csv": prod_rels}
    for rel, obj in scan.items():
        for s in walk_strings(obj):
            for m in ID_RE.finditer(s):
                if m.group(0).startswith("CHG_"):
                    continue
                check_ref(rel, m.group(0))
            for m in SRC_RE.finditer(s):
                src, page = m.group(1), int(m.group(2))
                if src not in src_pages:
                    rep.err(f"{rel}: 未登记的来源 {src}")
                elif not 1 <= page <= src_pages[src]:
                    rep.err(f"{rel}: {src} 页码 p{page} 超出范围 1–{src_pages[src]}")

    # ---- 3. 字典内部 ----
    for it in data["dictionaries/functions.yaml"]:
        for e in it.get("realized_by_effects") or []:
            if not e.startswith("EFFECT_"):
                rep.err(f"{it['id']}: realized_by_effects 只能是 EFFECT_，实际 {e}")
        if it.get("scope") not in ("design", "sku", "both"):
            rep.err(f"{it['id']}: scope 必须是 design/sku/both")
    for rel in DICTS:
        for it in data[rel]:
            ev = it.get("evidence")
            if ev is not None and rel not in ("rules/rules.yaml",) and str(ev) not in EVIDENCE:
                rep.err(f"{rel} {it['id']}: evidence 取值 {ev!r} 不在 A/B/C")

    # ---- 4. 产品 ----
    func_scope = {f["id"]: f["scope"] for f in data["dictionaries/functions.yaml"]}
    for p in data["products/products.yaml"]:
        pid = p["id"]
        for fld in PRODUCT_FIELDS:
            if fld not in p or p[fld] in (None, "", []) and fld not in ("open_questions",):
                if fld == "open_questions" and fld in p:
                    continue
                rep.err(f"{pid}: 缺少字段 {fld}（无资料请写'资料未提供'）")
        if "price_range_cny" not in p:
            rep.err(f"{pid}: 缺少 price_range_cny")
        expect = {"mechanisms": "MECH_", "effects": "EFFECT_", "functions": "FUNC_", "values": "VALUE_",
                  "problems": "PROBLEM_", "needs": "NEED_", "symptoms": "SYMPTOM_", "scenes": "SCENE_",
                  "exams": "EXAM_", "open_questions": "Q_"}
        for fld, prefix in expect.items():
            try:
                for i in tagged_ids(p.get(fld)):
                    if not i.startswith(prefix):
                        rep.err(f"{pid}.{fld}: {i} 前缀应为 {prefix}")
            except ValueError as e:
                rep.err(f"{pid}.{fld}: {e}")
        p_skus = [r for r in skus if r["product_id"] == pid]
        for f in tagged_ids(p.get("functions")):
            if func_scope.get(f) == "sku" and not all(f in r["extra_functions"].split(";") for r in p_skus):
                rep.warn(f"{pid}: {f} 为 SKU 层功能但并非所有 SKU 都具备，应只写在 skus.csv.extra_functions")
        for k in (p.get("function_levels") or {}):
            check_ref(f"{pid}.function_levels", k)
        if p.get("price_tier") not in {"P1", "P2", "P3", "P4", "P5"}:
            rep.err(f"{pid}: price_tier 非法 {p.get('price_tier')!r}")

    # ---- 5. SKU ----
    prod_ids = {p["id"] for p in data["products/products.yaml"]}
    seen_products = set()
    for r in skus:
        sid, pid = r["sku_id"], r["product_id"]
        if pid not in prod_ids:
            rep.err(f"{sid}: product_id {pid} 不存在")
        seen_products.add(pid)
        brand, num = pid.split("_")[1], pid.split("_")[2]
        if not sid.startswith(f"SKU_{brand}_{num}_"):
            rep.err(f"{sid}: 与产品 {pid} 编号不一致")
        for f in filter(None, r["extra_functions"].split(";")):
            check_ref(sid, f)
        for kv in filter(None, r["function_levels"].split(";")):
            fid, _, lvl = kv.partition(":")
            check_ref(sid, fid)
            if lvl not in LEVELS:
                rep.err(f"{sid}: 功能等级 {lvl!r} 非法")
        if r["evidence"] not in EVIDENCE:
            rep.err(f"{sid}: evidence 非法")
        if not r["price_cny"] and "CONFLICT" not in r["notes"]:
            rep.err(f"{sid}: 价格为空但未标注 CONFLICT")
        if r["price_cny"] and not r["price_cny"].isdigit():
            rep.err(f"{sid}: 价格非整数 {r['price_cny']!r}")
    for pid in prod_ids - seen_products:
        rep.err(f"{pid}: 没有任何 SKU")

    # ---- 6. 关系 ----
    for r in tag_rels:
        if r["predicate"] not in PREDICATES:
            rep.err(f"{r['rel_id']}: predicate {r['predicate']!r} 非法")
        if r["evidence"] not in EVIDENCE:
            rep.err(f"{r['rel_id']}: evidence 非法")
        check_ref(r["rel_id"], r["subject"])
        check_ref(r["rel_id"], r["object"])
    seen_pairs = set()
    for r in tag_rels:
        key = (r["subject"], r["predicate"], r["object"])
        if key in seen_pairs:
            rep.err(f"{r['rel_id']}: 重复关系 {key}")
        seen_pairs.add(key)
    for r in prod_rels:
        if r["predicate"] not in PREDICATES:
            rep.err(f"{r['prel_id']}: predicate 非法")
        if r["comparison"] not in COMPARISONS:
            rep.err(f"{r['prel_id']}: comparison {r['comparison']!r} 非法")
        if r["evidence"] not in EVIDENCE:
            rep.err(f"{r['prel_id']}: evidence 非法")
        for c in ("product_a", "product_b"):
            if r[c] not in prod_ids:
                rep.err(f"{r['prel_id']}: {r[c]} 不是产品")

    # ---- 7. 规则 ----
    for rule in data["rules/rules.yaml"]:
        if rule.get("status") not in RULE_STATUS:
            rep.err(f"{rule['id']}: status {rule.get('status')!r} 非法")
        if rule.get("status") == "可上线候选" and "待业务确认" in json.dumps(rule, ensure_ascii=False):
            rep.err(f"{rule['id']}: 含'待业务确认'阈值，不能标为可上线候选")

    # ---- 8. 变更日志覆盖 ----
    if changelog:
        added = set()
        for c in changelog:
            if c["action"] not in CHANGE_ACTIONS:
                rep.err(f"{c['change_id']}: action {c['action']!r} 非法")
            if c["action"] == "ADD":
                added.add(c["object_id"])
        must_log = [i for i, rel in ids.items()
                    if rel not in ("changelog.csv", "products/skus.csv", "sources.yaml")]
        for i in must_log:
            if i not in added:
                rep.err(f"变更日志缺少 ADD 记录：{i}")
        for pid in prod_ids:
            if f"SKU@{pid}" not in added:
                rep.err(f"变更日志缺少 SKU 批量 ADD 记录：SKU@{pid}")
    else:
        rep.err("缺少 changelog.csv")

    # ---- 输出 ----
    counts = {k.split("/")[-1].split(".")[0]: len(v) for k, v in data.items()}
    counts |= {"skus": len(skus), "tag_relations": len(tag_rels), "product_relations": len(prod_rels),
               "changelog": len(changelog)}
    print("lens-kb 统计：" + "，".join(f"{k} {v}" for k, v in counts.items()))
    for w in rep.warnings:
        print("WARN ", w)
    for e in rep.errors:
        print("ERROR", e)
    if rep.errors:
        print(f"校验失败：{len(rep.errors)} 个错误")
        return 1
    print("校验通过")
    if "--export" in argv:
        out = KB / "build" / "kb.json"
        out.parent.mkdir(exist_ok=True)
        payload = {k: v for k, v in data.items()} | {"products/skus.csv": skus,
                                                      "relations/tag_relations.csv": tag_rels,
                                                      "relations/product_relations.csv": prod_rels,
                                                      "changelog.csv": changelog}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"已导出 {out.relative_to(KB.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
