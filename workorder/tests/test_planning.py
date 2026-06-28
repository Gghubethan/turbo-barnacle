"""计划排产模块测试。"""

import sys
from pathlib import Path
from datetime import date, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.planning as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


@pytest.fixture
def wo(store):
    p = store.create_product({"code": "P-1", "name": "件A"})
    return store.create_work_order({
        "product_id": p["id"], "planned_qty": 100, "workshop": "一号车间",
        "planned_start": "2026-06-25", "planned_end": "2026-06-30",
    })


# ── board ────────────────────────────────────────────────────────────────
def test_board_empty_structure(store):
    b = mod.board(store)
    assert set(b) == {"start", "days", "dates", "orders"}
    assert b["days"] == 14
    assert b["orders"] == []
    # 缺省起始 = 今天减 3 天
    assert b["start"] == (date.today() - timedelta(days=3)).isoformat()


def test_board_dates_length_equals_days(store):
    b = mod.board(store, start="2026-06-01", days=7)
    assert b["days"] == 7
    assert len(b["dates"]) == 7
    assert b["dates"][0] == "2026-06-01"
    assert b["dates"][-1] == "2026-06-07"


def test_board_order_fields_and_progress(store, wo):
    store.transition(wo["id"], "dispatch", {"assignee": "张三"})
    store.transition(wo["id"], "start")
    store.report_production(wo["id"], {"reporter": "李", "qty_ok": 25})
    b = mod.board(store, start="2026-06-24", days=14)
    assert len(b["orders"]) == 1
    o = b["orders"][0]
    for f in ("order_no", "work_order_id", "product_name", "status",
              "status_label", "priority", "priority_label", "assignee",
              "workshop", "planned_start", "planned_end", "planned_qty",
              "completed_qty", "progress"):
        assert f in o
    assert o["work_order_id"] == wo["id"]
    assert o["status_label"] == "生产中"
    assert o["progress"] == 25.0
    assert o["planned_start"] == "2026-06-25"


def test_board_excludes_closed(store, wo):
    # 走完整生命周期到 closed
    store.transition(wo["id"], "dispatch", {"assignee": "张三"})
    store.transition(wo["id"], "start")
    store.report_production(wo["id"], {"reporter": "李", "qty_ok": 100})  # 自动完工
    store.transition(wo["id"], "close")
    b = mod.board(store)
    assert b["orders"] == []


# ── create_entry ──────────────────────────────────────────────────────────
def test_create_entry_ok(store, wo):
    e = mod.create_entry(store, {
        "work_order_id": wo["id"], "line": "一号产线",
        "plan_date": "2026-06-26", "seq": 2, "remark": "加急"})
    assert e["line"] == "一号产线"
    assert e["plan_date"] == "2026-06-26"
    assert e["seq"] == 2
    assert e["order_no"] == wo["order_no"]
    assert e["product_name"] == wo["product_name"]


def test_create_entry_defaults_seq_and_optional_date(store, wo):
    e = mod.create_entry(store, {"work_order_id": wo["id"], "line": "二号产线"})
    assert e["seq"] == 0
    assert e["plan_date"] == ""


def test_create_entry_requires_work_order_id(store):
    with pytest.raises(ValidationError):
        mod.create_entry(store, {"line": "一号产线"})


def test_create_entry_requires_line(store, wo):
    with pytest.raises(ValidationError):
        mod.create_entry(store, {"work_order_id": wo["id"]})


def test_create_entry_unknown_work_order(store):
    with pytest.raises(ValidationError):
        mod.create_entry(store, {"work_order_id": 999, "line": "一号产线"})


# ── delete_entry ──────────────────────────────────────────────────────────
def test_delete_entry_ok(store, wo):
    e = mod.create_entry(store, {"work_order_id": wo["id"], "line": "一号产线"})
    mod.delete_entry(store, e["id"])
    assert mod.list_entries(store) == []


def test_delete_entry_not_found(store):
    with pytest.raises(NotFound):
        mod.delete_entry(store, 999)


# ── list_entries ──────────────────────────────────────────────────────────
def test_list_entries_brings_order_no(store, wo):
    mod.create_entry(store, {"work_order_id": wo["id"], "line": "一号产线"})
    rows = mod.list_entries(store)
    assert len(rows) == 1
    assert rows[0]["order_no"] == wo["order_no"]
    assert rows[0]["product_name"] == wo["product_name"]


# ── seed ──────────────────────────────────────────────────────────────────
def test_seed_idempotent(store, wo):
    mod.seed(store)
    n1 = len(mod.list_entries(store))
    mod.seed(store)
    n2 = len(mod.list_entries(store))
    assert n1 == 1  # 只有一张工单
    assert n1 == n2
