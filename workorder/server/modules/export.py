"""数据导出模块：把各业务数据集导出为 CSV（Excel 友好，UTF-8 BOM）。

只读现有核心表，按数据集注册「中文表头 + 取值」，统一经 :class:`FileResponse` 下载。
枚举值导出为中文标签，与界面一致。
"""

from __future__ import annotations

import csv
import io

from server.store import (
    FileResponse, ValidationError,
    STATUS, PRIORITY, TXN_BIZ, INSPECT_RESULT, EXCEPTION_CATEGORY,
    STAFF_ROLE, MATERIAL_CATEGORY,
)

SCHEMA = ""  # 本模块不建表，只读现有数据


def _rows(store, sql, params=()):
    with store._conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _ds_work_orders(store):
    headers = ["工单号", "产品", "计划数", "完成数", "不良数", "状态", "优先级",
               "负责人", "车间", "计划开工", "计划完工", "创建时间"]
    out = []
    for r in _rows(store, "SELECT * FROM work_orders ORDER BY id"):
        out.append([r["order_no"], r["product_name"], r["planned_qty"], r["completed_qty"],
                    r["defect_qty"], STATUS.get(r["status"], r["status"]),
                    PRIORITY.get(r["priority"], r["priority"]), r["assignee"], r["workshop"],
                    r["planned_start"], r["planned_end"], r["created_at"]])
    return headers, out


def _ds_reports(store):
    headers = ["工单号", "报工人", "合格数", "不良数", "备注", "报工时间"]
    sql = ("SELECT r.*, w.order_no FROM reports r "
           "JOIN work_orders w ON w.id = r.work_order_id ORDER BY r.id")
    out = [[r["order_no"], r["reporter"], r["qty_ok"], r["qty_defect"], r["remark"],
            r["report_time"]] for r in _rows(store, sql)]
    return headers, out


def _ds_inspections(store):
    headers = ["工单号", "质检员", "送检数", "合格数", "不良数", "结论", "不良原因", "时间"]
    sql = ("SELECT i.*, w.order_no FROM inspections i "
           "JOIN work_orders w ON w.id = i.work_order_id ORDER BY i.id")
    out = [[r["order_no"], r["inspector"], r["qty_inspected"], r["qty_qualified"],
            r["qty_defective"], INSPECT_RESULT.get(r["result"], r["result"]),
            r["defect_reason"], r["created_at"]] for r in _rows(store, sql)]
    return headers, out


def _ds_inventory(store):
    headers = ["时间", "物料", "方向", "业务类型", "数量", "结余", "关联工单", "操作人", "备注"]
    out = []
    for r in _rows(store, "SELECT * FROM inventory_txns ORDER BY id"):
        out.append([r["created_at"], r["material_name"], "入库" if r["kind"] == "in" else "出库",
                    TXN_BIZ.get(r["biz_type"], r["biz_type"]), r["qty"], r["balance_after"],
                    r["work_order_id"] or "", r["operator"], r["remark"]])
    return headers, out


def _ds_materials(store):
    headers = ["编码", "名称", "规格", "单位", "类别", "当前库存", "安全库存"]
    out = [[r["code"], r["name"], r["spec"], r["unit"],
            MATERIAL_CATEGORY.get(r["category"], r["category"]), r["stock"], r["safety_stock"]]
           for r in _rows(store, "SELECT * FROM materials ORDER BY id")]
    return headers, out


def _ds_products(store):
    headers = ["编码", "名称", "规格", "单位", "创建时间"]
    out = [[r["code"], r["name"], r["spec"], r["unit"], r["created_at"]]
           for r in _rows(store, "SELECT * FROM products ORDER BY id")]
    return headers, out


def _ds_staff(store):
    headers = ["姓名", "角色", "班组", "状态", "创建时间"]
    out = [[r["name"], STAFF_ROLE.get(r["role"], r["role"]), r["team"],
            "在职" if r["active"] else "停用", r["created_at"]]
           for r in _rows(store, "SELECT * FROM staff ORDER BY id")]
    return headers, out


def _ds_exceptions(store):
    headers = ["工单号", "类型", "描述", "上报人", "状态", "处理结果", "创建时间", "处理时间"]
    sql = ("SELECT e.*, w.order_no FROM exceptions e "
           "JOIN work_orders w ON w.id = e.work_order_id ORDER BY e.id")
    out = [[r["order_no"], EXCEPTION_CATEGORY.get(r["category"], r["category"]), r["description"],
            r["reporter"], "已处理" if r["status"] == "resolved" else "待处理",
            r["resolution"], r["created_at"], r["resolved_at"]] for r in _rows(store, sql)]
    return headers, out


# 数据集注册表：key -> (中文名, 构建函数, 导出文件名)
DATASETS = {
    "work_orders": ("工单", _ds_work_orders, "工单.csv"),
    "reports": ("报工记录", _ds_reports, "报工记录.csv"),
    "inspections": ("质检记录", _ds_inspections, "质检记录.csv"),
    "inventory": ("库存流水", _ds_inventory, "库存流水.csv"),
    "materials": ("物料档案", _ds_materials, "物料档案.csv"),
    "products": ("产品档案", _ds_products, "产品档案.csv"),
    "staff": ("员工", _ds_staff, "员工.csv"),
    "exceptions": ("异常", _ds_exceptions, "异常.csv"),
}


def list_datasets():
    return [{"key": k, "label": v[0]} for k, v in DATASETS.items()]


def build_csv(store, key):
    if key not in DATASETS:
        raise ValidationError(f"未知数据集：{key}")
    label, builder, filename = DATASETS[key]
    headers, rows = builder(store)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return FileResponse(buf.getvalue(), filename)


def routes(store):
    return [
        ("GET", r"/api/export", lambda req, p: (200, list_datasets())),
        ("GET", r"/api/export/(?P<key>[a-z_]+)\.csv",
         lambda req, p: (200, build_csv(store, p["key"]))),
    ]
