"""报表中心模块测试：只读聚合现有数据。"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.reports as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)  # SCHEMA 为空字符串，executescript("") 安全
    return s


_seq = [0]


def _make_wo(store, planned=100, workshop=""):
    _seq[0] += 1
    p = store.create_product({"code": f"P-{_seq[0]}", "name": "件A"})
    w = store.create_work_order({
        "product_id": p["id"], "planned_qty": planned, "workshop": workshop,
    })
    store.transition(w["id"], "dispatch", {"assignee": "张三"})
    return store.transition(w["id"], "start")


# ── output_trend ────────────────────────────────────────────────────────────
def test_output_trend_length_and_ascending(store):
    rows = mod.output_trend(store, days=14)
    assert len(rows) == 14
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)            # 升序
    assert dates[-1] == date.today().isoformat()  # 以今天结尾
    # 无数据时全为 0
    assert all(r["qty_ok"] == 0 and r["qty_defect"] == 0 for r in rows)


def test_output_trend_reflects_reports(store):
    wo = _make_wo(store, planned=1000)
    store.report_production(wo["id"], {"reporter": "李", "qty_ok": 40, "qty_defect": 3})
    store.report_production(wo["id"], {"reporter": "李", "qty_ok": 10, "qty_defect": 1})
    rows = mod.output_trend(store, days=7)
    assert len(rows) == 7
    today = next(r for r in rows if r["date"] == date.today().isoformat())
    assert today["qty_ok"] == 50
    assert today["qty_defect"] == 4


def test_output_trend_custom_days(store):
    assert len(mod.output_trend(store, days=3)) == 3
    assert len(mod.output_trend(store, days="bad")) == 14  # 非法回退默认


# ── quality_trend ───────────────────────────────────────────────────────────
def test_quality_trend_pass_rate(store):
    wo = _make_wo(store)
    store.create_inspection(wo["id"], {
        "inspector": "陈", "qty_inspected": 80, "qty_qualified": 76, "qty_defective": 4})
    rows = mod.quality_trend(store, days=14)
    assert len(rows) == 14
    today = next(r for r in rows if r["date"] == date.today().isoformat())
    assert today["inspected"] == 80
    assert today["qualified"] == 76
    assert today["pass_rate"] == 95.0


def test_quality_trend_zero_inspected_is_zero_rate(store):
    rows = mod.quality_trend(store, days=5)
    assert len(rows) == 5
    assert all(r["pass_rate"] == 0 for r in rows)
    assert all(r["inspected"] == 0 for r in rows)


# ── status_distribution ─────────────────────────────────────────────────────
def test_status_distribution_covers_all_six(store):
    rows = mod.status_distribution(store)
    statuses = {r["status"] for r in rows}
    assert statuses == {"pending", "dispatched", "producing", "paused", "completed", "closed"}
    assert all(r["count"] == 0 for r in rows)
    # 含中文 label
    labels = {r["status"]: r["status_label"] for r in rows}
    assert labels["producing"] == "生产中"


def test_status_distribution_counts(store):
    _make_wo(store)                          # producing
    _make_wo(store)                          # producing
    p = store.create_product({"code": "P-pending", "name": "x"})
    store.create_work_order({"product_id": p["id"], "planned_qty": 10})  # pending
    rows = mod.status_distribution(store)
    by = {r["status"]: r["count"] for r in rows}
    assert by["producing"] == 2
    assert by["pending"] == 1
    assert by["closed"] == 0


# ── workshop_output ─────────────────────────────────────────────────────────
def test_workshop_output_rate_and_unassigned(store):
    a = _make_wo(store, planned=200, workshop="一号车间")
    store.report_production(a["id"], {"reporter": "李", "qty_ok": 100})
    # 两张空 workshop 的工单 -> 归并到“未分配”
    b = _make_wo(store, planned=50, workshop="")
    store.report_production(b["id"], {"reporter": "李", "qty_ok": 25})
    _make_wo(store, planned=50, workshop="")  # 未报工
    rows = mod.workshop_output(store)
    by = {r["workshop"]: r for r in rows}
    assert "未分配" in by
    assert by["一号车间"]["planned"] == 200
    assert by["一号车间"]["completed"] == 100
    assert by["一号车间"]["rate"] == 50.0
    # 未分配两张合并：planned 100, completed 25
    assert by["未分配"]["planned"] == 100
    assert by["未分配"]["completed"] == 25
    assert by["未分配"]["rate"] == 25.0


# ── material_flow ───────────────────────────────────────────────────────────
def test_material_flow_in_out(store):
    m = store.create_material({"code": "M-1", "name": "钢板", "stock": 100})  # 期初入库 100
    store.stock_move(m["id"], "purchase", 30)   # in 30
    store.stock_move(m["id"], "issue", 40)      # out 40
    rows = mod.material_flow(store)
    by = {r["material_name"]: r for r in rows}
    assert by["钢板"]["in_qty"] == 130          # 100 + 30
    assert by["钢板"]["out_qty"] == 40


def test_material_flow_empty(store):
    assert mod.material_flow(store) == []


# ── summary ─────────────────────────────────────────────────────────────────
def test_summary_fields(store):
    wo = _make_wo(store, planned=10)
    store.report_production(wo["id"], {"reporter": "李", "qty_ok": 8, "qty_defect": 2})
    # 自动完工（8 < 10，不会），再补一笔到达计划数完工
    store.report_production(wo["id"], {"reporter": "李", "qty_ok": 5})
    store.create_inspection(wo["id"], {
        "inspector": "陈", "qty_inspected": 100, "qty_qualified": 90, "qty_defective": 10})
    store.create_material({"code": "M-1", "name": "钢板", "stock": 5})
    s = mod.summary(store)
    assert s["total_orders"] == 1
    assert s["completed_orders"] == 1          # 报到计划数自动完工
    assert s["total_output"] == 13             # 8 + 5
    assert s["total_defect"] == 2
    assert s["avg_pass_rate"] == 90.0
    assert s["materials"] == 1


def test_summary_empty_store(store):
    s = mod.summary(store)
    assert s == {
        "total_orders": 0, "completed_orders": 0, "total_output": 0,
        "total_defect": 0, "avg_pass_rate": 0.0, "materials": 0,
    }


# ── 路由清单 ────────────────────────────────────────────────────────────────
def test_routes_registered(store):
    paths = {p for _, p, _ in mod.routes(store)}
    assert r"/api/reports/summary" in paths
    assert r"/api/reports/output-trend" in paths
    assert r"/api/reports/quality-trend" in paths
    assert r"/api/reports/status-distribution" in paths
    assert r"/api/reports/workshop-output" in paths
    assert r"/api/reports/material-flow" in paths
