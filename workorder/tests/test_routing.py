import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.routing as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


@pytest.fixture
def wo(store):
    store.create_product({"code": "P-1", "name": "测试件"})
    order = store.create_work_order({"product_id": 1, "planned_qty": 100})
    return order["id"]


# ── add_operation ─────────────────────────────────────────────────────────
def test_add_operation_ok(store, wo):
    op = mod.add_operation(store, wo, {"name": "下料", "planned_qty": 50, "workstation": "锯床"})
    assert op["name"] == "下料"
    assert op["seq"] == 1
    assert op["status"] == "pending"
    assert op["status_label"] == "待开工"
    assert op["workstation"] == "锯床"
    assert op["completed_qty"] == 0


def test_add_operation_auto_seq(store, wo):
    mod.add_operation(store, wo, {"name": "下料", "planned_qty": 50})
    op2 = mod.add_operation(store, wo, {"name": "加工", "planned_qty": 50})
    assert op2["seq"] == 2


def test_add_operation_missing_name(store, wo):
    with pytest.raises(ValidationError):
        mod.add_operation(store, wo, {"planned_qty": 50})


def test_add_operation_zero_qty(store, wo):
    with pytest.raises(ValidationError):
        mod.add_operation(store, wo, {"name": "下料", "planned_qty": 0})


def test_add_operation_wo_not_found(store):
    with pytest.raises(NotFound):
        mod.add_operation(store, 999, {"name": "下料", "planned_qty": 10})


# ── list_operations ───────────────────────────────────────────────────────
def test_list_operations_sorted_and_derived(store, wo):
    mod.add_operation(store, wo, {"name": "质检", "planned_qty": 40, "seq": 3})
    mod.add_operation(store, wo, {"name": "下料", "planned_qty": 40, "seq": 1})
    mod.add_operation(store, wo, {"name": "加工", "planned_qty": 40, "seq": 2})
    ops = mod.list_operations(store, wo)
    assert [o["seq"] for o in ops] == [1, 2, 3]
    assert [o["name"] for o in ops] == ["下料", "加工", "质检"]
    # progress + status_label 附带
    mod.report_operation(store, ops[0]["id"], {"qty": 10})
    again = mod.list_operations(store, wo)
    assert again[0]["progress"] == 25.0
    assert again[0]["status_label"] == "进行中"


# ── report_operation ──────────────────────────────────────────────────────
def test_report_operation_status_flow(store, wo):
    op = mod.add_operation(store, wo, {"name": "下料", "planned_qty": 100})
    assert op["status"] == "pending"
    r1 = mod.report_operation(store, op["id"], {"qty": 30})
    assert r1["status"] == "doing"
    assert r1["completed_qty"] == 30
    r2 = mod.report_operation(store, op["id"], {"qty": 70})
    assert r2["status"] == "done"
    assert r2["completed_qty"] == 100
    assert r2["progress"] == 100.0


def test_report_operation_worker_override(store, wo):
    op = mod.add_operation(store, wo, {"name": "下料", "planned_qty": 100, "worker": "甲"})
    r = mod.report_operation(store, op["id"], {"qty": 10, "worker": "乙"})
    assert r["worker"] == "乙"


def test_report_operation_exceeds_plan(store, wo):
    op = mod.add_operation(store, wo, {"name": "下料", "planned_qty": 50})
    mod.report_operation(store, op["id"], {"qty": 40})
    with pytest.raises(ValidationError):
        mod.report_operation(store, op["id"], {"qty": 20})


def test_report_operation_zero_qty(store, wo):
    op = mod.add_operation(store, wo, {"name": "下料", "planned_qty": 50})
    with pytest.raises(ValidationError):
        mod.report_operation(store, op["id"], {"qty": 0})


def test_report_operation_not_found(store):
    with pytest.raises(NotFound):
        mod.report_operation(store, 999, {"qty": 5})


# ── delete_operation ──────────────────────────────────────────────────────
def test_delete_operation_ok(store, wo):
    op = mod.add_operation(store, wo, {"name": "下料", "planned_qty": 50})
    mod.delete_operation(store, op["id"])
    assert mod.list_operations(store, wo) == []


def test_delete_operation_not_found(store):
    with pytest.raises(NotFound):
        mod.delete_operation(store, 999)
