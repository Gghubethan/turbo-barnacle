"""报表中心模块：对现有生产 / 质量 / 库存数据做统计分析。

本模块**不新建任何表**（``SCHEMA`` 为空字符串），只读聚合现有核心表：
``reports`` / ``inspections`` / ``work_orders`` / ``inventory_txns`` / ``materials``。

所有服务函数写成普通函数，便于 pytest 直接调用；只用 ``store._conn()`` 做只读查询。
"""

from __future__ import annotations

from datetime import date, timedelta

from server.store import STATUS


# 本模块无需建表
SCHEMA = ""


# ── 工具 ──────────────────────────────────────────────────────────────────
def _coerce_days(days, default: int = 14) -> int:
    """把外部传入的 days 归一为正整数，非法回退到默认值。"""
    try:
        days = int(days)
    except (TypeError, ValueError):
        return default
    return days if days > 0 else default


def _recent_dates(days: int) -> list[str]:
    """返回最近 days 天的日期字符串（升序），含今天。"""
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


# ── 趋势 ──────────────────────────────────────────────────────────────────
def output_trend(store, days: int = 14) -> list[dict]:
    """近 days 天每日产量（基于 reports.report_time 前 10 位分组）。

    输出 ``[{"date","qty_ok","qty_defect"}]``，缺数据的日期补 0，按日期升序，长度 == days。
    """
    days = _coerce_days(days)
    dates = _recent_dates(days)
    start = dates[0]
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT substr(report_time,1,10) AS d, "
            "COALESCE(SUM(qty_ok),0) AS qty_ok, "
            "COALESCE(SUM(qty_defect),0) AS qty_defect "
            "FROM reports WHERE substr(report_time,1,10) >= ? "
            "GROUP BY substr(report_time,1,10)",
            (start,),
        ).fetchall()
    by_date = {r["d"]: r for r in rows}
    out = []
    for d in dates:
        r = by_date.get(d)
        out.append({
            "date": d,
            "qty_ok": r["qty_ok"] if r else 0,
            "qty_defect": r["qty_defect"] if r else 0,
        })
    return out


def quality_trend(store, days: int = 14) -> list[dict]:
    """近 days 天每日质检（基于 inspections.created_at 前 10 位分组）。

    输出 ``[{"date","inspected","qualified","pass_rate"}]``，补全日期，升序。
    pass_rate = qualified/inspected*100（1 位小数）；inspected 为 0 时 pass_rate=0。
    """
    days = _coerce_days(days)
    dates = _recent_dates(days)
    start = dates[0]
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT substr(created_at,1,10) AS d, "
            "COALESCE(SUM(qty_inspected),0) AS inspected, "
            "COALESCE(SUM(qty_qualified),0) AS qualified "
            "FROM inspections WHERE substr(created_at,1,10) >= ? "
            "GROUP BY substr(created_at,1,10)",
            (start,),
        ).fetchall()
    by_date = {r["d"]: r for r in rows}
    out = []
    for d in dates:
        r = by_date.get(d)
        inspected = r["inspected"] if r else 0
        qualified = r["qualified"] if r else 0
        rate = round((qualified / inspected) * 100, 1) if inspected else 0.0
        out.append({
            "date": d,
            "inspected": inspected,
            "qualified": qualified,
            "pass_rate": rate,
        })
    return out


# ── 分布 / 汇总 ─────────────────────────────────────────────────────────────
def status_distribution(store) -> list[dict]:
    """work_orders 按 status 分组计数，覆盖全部 6 个状态，含中文 label，缺省 0。"""
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM work_orders GROUP BY status"
        ).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    return [
        {"status": s, "status_label": label, "count": counts.get(s, 0)}
        for s, label in STATUS.items()
    ]


def workshop_output(store) -> list[dict]:
    """按 workshop 汇总 work_orders 的 planned_qty 与 completed_qty。

    输出 ``[{"workshop","planned","completed","rate"}]``；rate=completed/planned*100（1 位）；
    workshop 为空显示“未分配”。
    """
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT COALESCE(NULLIF(TRIM(workshop),''),'未分配') AS workshop, "
            "COALESCE(SUM(planned_qty),0) AS planned, "
            "COALESCE(SUM(completed_qty),0) AS completed "
            "FROM work_orders GROUP BY workshop ORDER BY workshop"
        ).fetchall()
    out = []
    for r in rows:
        planned = r["planned"] or 0
        completed = r["completed"] or 0
        rate = round((completed / planned) * 100, 1) if planned else 0.0
        out.append({
            "workshop": r["workshop"],
            "planned": planned,
            "completed": completed,
            "rate": rate,
        })
    return out


def material_flow(store) -> list[dict]:
    """按物料汇总 inventory_txns 出入库。

    输出 ``[{"material_name","in_qty","out_qty"}]``；
    in_qty = kind='in' 之和，out_qty = kind='out' 之和。
    """
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT material_name, "
            "COALESCE(SUM(CASE WHEN kind='in'  THEN qty ELSE 0 END),0) AS in_qty, "
            "COALESCE(SUM(CASE WHEN kind='out' THEN qty ELSE 0 END),0) AS out_qty "
            "FROM inventory_txns GROUP BY material_name ORDER BY material_name"
        ).fetchall()
    return [
        {
            "material_name": r["material_name"],
            "in_qty": r["in_qty"] or 0,
            "out_qty": r["out_qty"] or 0,
        }
        for r in rows
    ]


def summary(store) -> dict:
    """一组头条数字。"""
    with store._conn() as conn:
        wo = conn.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0) AS completed "
            "FROM work_orders"
        ).fetchone()
        rep = conn.execute(
            "SELECT COALESCE(SUM(qty_ok),0) AS ok, COALESCE(SUM(qty_defect),0) AS defect "
            "FROM reports"
        ).fetchone()
        insp = conn.execute(
            "SELECT COALESCE(SUM(qty_inspected),0) AS i, COALESCE(SUM(qty_qualified),0) AS q "
            "FROM inspections"
        ).fetchone()
        materials = conn.execute("SELECT COUNT(*) AS c FROM materials").fetchone()["c"]

    inspected = insp["i"] or 0
    return {
        "total_orders": wo["total"],
        "completed_orders": wo["completed"],
        "total_output": rep["ok"] or 0,
        "total_defect": rep["defect"] or 0,
        "avg_pass_rate": round((insp["q"] / inspected) * 100, 1) if inspected else 0.0,
        "materials": materials,
    }


# ── 路由 ──────────────────────────────────────────────────────────────────
def routes(store):
    def _days(req):
        return req["query"].get("days", [14])[0] or 14

    return [
        ("GET", r"/api/reports/summary",
         lambda req, p: (200, summary(store))),
        ("GET", r"/api/reports/output-trend",
         lambda req, p: (200, output_trend(store, _days(req)))),
        ("GET", r"/api/reports/quality-trend",
         lambda req, p: (200, quality_trend(store, _days(req)))),
        ("GET", r"/api/reports/status-distribution",
         lambda req, p: (200, status_distribution(store))),
        ("GET", r"/api/reports/workshop-output",
         lambda req, p: (200, workshop_output(store))),
        ("GET", r"/api/reports/material-flow",
         lambda req, p: (200, material_flow(store))),
    ]
