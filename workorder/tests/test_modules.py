"""员工 / 物料库存 / 质检 模块测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "mod.db")


@pytest.fixture
def wo(store):
    p = store.create_product({"code": "P-1", "name": "件A"})
    w = store.create_work_order({"product_id": p["id"], "planned_qty": 100})
    store.transition(w["id"], "dispatch", {"assignee": "张三"})
    return store.transition(w["id"], "start")


# ── 员工 ────────────────────────────────────────────────────────────────
def test_create_and_list_staff(store):
    s = store.create_staff({"name": "李四", "role": "inspector", "team": "质检组"})
    assert s["role_label"] == "质检员"
    assert s["active"] is True
    assert len(store.list_staff()) == 1


def test_staff_requires_name(store):
    with pytest.raises(ValidationError):
        store.create_staff({"role": "operator"})


def test_staff_unknown_role(store):
    with pytest.raises(ValidationError):
        store.create_staff({"name": "x", "role": "ceo"})


def test_staff_deactivate_and_filter(store):
    a = store.create_staff({"name": "A"})
    store.create_staff({"name": "B"})
    store.set_staff_active(a["id"], False)
    assert len(store.list_staff(active_only=True)) == 1
    assert len(store.list_staff()) == 2


# ── 物料 / 库存 ───────────────────────────────────────────────────────────
def test_create_material_with_initial_stock(store):
    m = store.create_material({"code": "M-1", "name": "钢板", "stock": 100, "safety_stock": 20})
    assert m["stock"] == 100
    # 期初库存应有一条流水
    assert len(store.list_txns(material_id=m["id"])) == 1


def test_material_duplicate_code(store):
    store.create_material({"code": "M-1", "name": "a"})
    with pytest.raises(ValidationError):
        store.create_material({"code": "M-1", "name": "b"})


def test_low_stock_flag(store):
    m = store.create_material({"code": "M-1", "name": "a", "stock": 5, "safety_stock": 10})
    assert m["low_stock"] is True


def test_stock_in_and_out(store):
    m = store.create_material({"code": "M-1", "name": "a", "stock": 50})
    m = store.stock_move(m["id"], "purchase", 30)
    assert m["stock"] == 80
    m = store.stock_move(m["id"], "scrap", 10)
    assert m["stock"] == 70


def test_stock_out_insufficient_blocked(store):
    m = store.create_material({"code": "M-1", "name": "a", "stock": 5})
    with pytest.raises(ValidationError):
        store.stock_move(m["id"], "issue", 10)


def test_stock_move_unknown_biz(store):
    m = store.create_material({"code": "M-1", "name": "a", "stock": 5})
    with pytest.raises(ValidationError):
        store.stock_move(m["id"], "teleport", 1)


def test_txn_balance_recorded(store):
    m = store.create_material({"code": "M-1", "name": "a", "stock": 0})
    store.stock_move(m["id"], "purchase", 40)
    store.stock_move(m["id"], "issue", 15)
    txns = store.list_txns(material_id=m["id"])
    assert txns[0]["balance_after"] == 25  # 最新一条
    assert txns[0]["biz_label"] == "生产领料"


# ── 工单领料 ──────────────────────────────────────────────────────────────
def test_issue_to_work_order(store, wo):
    m = store.create_material({"code": "M-1", "name": "钢板", "stock": 100})
    store.issue_to_work_order(wo["id"], {"material_id": m["id"], "qty": 30, "operator": "张三"})
    assert store.list_materials()[0]["stock"] == 70
    txns = store.list_txns(work_order_id=wo["id"])
    assert len(txns) == 1
    assert txns[0]["biz_type"] == "issue"


def test_issue_blocked_when_completed(store):
    p = store.create_product({"code": "P-1", "name": "件A"})
    w = store.create_work_order({"product_id": p["id"], "planned_qty": 10})
    store.transition(w["id"], "dispatch", {"assignee": "a"})
    store.transition(w["id"], "start")
    store.report_production(w["id"], {"reporter": "x", "qty_ok": 10})  # 自动完工
    m = store.create_material({"code": "M-1", "name": "钢板", "stock": 100})
    with pytest.raises(ValidationError):
        store.issue_to_work_order(w["id"], {"material_id": m["id"], "qty": 5})


# ── 质检 ────────────────────────────────────────────────────────────────
def test_create_inspection(store, wo):
    i = store.create_inspection(wo["id"], {
        "inspector": "陈质检", "qty_inspected": 100,
        "qty_qualified": 95, "qty_defective": 5, "result": "pass"})
    assert i["result_label"] == "合格"
    assert i["pass_rate"] == 95.0
    assert i["order_no"] == wo["order_no"]


def test_inspection_qty_overflow_blocked(store, wo):
    with pytest.raises(ValidationError):
        store.create_inspection(wo["id"], {
            "inspector": "x", "qty_inspected": 50,
            "qty_qualified": 40, "qty_defective": 20})


def test_inspection_requires_inspector(store, wo):
    with pytest.raises(ValidationError):
        store.create_inspection(wo["id"], {"qty_inspected": 10})


def test_inspection_missing_order(store):
    with pytest.raises(NotFound):
        store.create_inspection(999, {"inspector": "x", "qty_inspected": 1})


# ── 看板新增指标 ────────────────────────────────────────────────────────────
def test_dashboard_quality_and_stock(store, wo):
    store.create_inspection(wo["id"], {
        "inspector": "x", "qty_inspected": 100, "qty_qualified": 90, "qty_defective": 10})
    store.create_material({"code": "M-1", "name": "a", "stock": 5, "safety_stock": 10})
    d = store.dashboard_stats()
    assert d["inspect_pass_rate"] == 90.0
    assert d["low_stock_materials"] == 1
