"""采购管理模块测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.purchasing as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "pu.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


def _material(store, code="M-9001", name="测试钢板", stock=0):
    return store.create_material({
        "code": code, "name": name, "unit": "kg",
        "category": "raw", "stock": stock, "safety_stock": 0})


def _stock_of(store, material_id):
    for m in store.list_materials():
        if m["id"] == material_id:
            return m["stock"]
    raise AssertionError("物料未找到")


# ── create_purchase ──────────────────────────────────────────────────────────
def test_create_purchase_ok(store):
    m = _material(store)
    po = mod.create_purchase(store, {
        "supplier": "宝钢", "material_id": m["id"], "qty": 500,
        "expected_date": "2026-07-05"})
    assert po["supplier"] == "宝钢"
    assert po["material_name"] == "测试钢板"      # 取自 materials 表
    assert po["qty"] == 500
    assert po["received_qty"] == 0
    assert po["status"] == "pending"
    assert po["status_label"] == "待收货"
    assert po["po_no"].startswith("PO")


def test_create_purchase_missing_supplier(store):
    m = _material(store)
    with pytest.raises(ValidationError):
        mod.create_purchase(store, {"material_id": m["id"], "qty": 10})


def test_create_purchase_missing_material(store):
    with pytest.raises(ValidationError):
        mod.create_purchase(store, {"supplier": "某供应商", "qty": 10})


def test_create_purchase_invalid_material(store):
    with pytest.raises(ValidationError):
        mod.create_purchase(store, {
            "supplier": "某供应商", "material_id": 9999, "qty": 10})


def test_create_purchase_zero_qty(store):
    m = _material(store)
    with pytest.raises(ValidationError):
        mod.create_purchase(store, {
            "supplier": "宝钢", "material_id": m["id"], "qty": 0})


# ── 单号生成与唯一 ────────────────────────────────────────────────────────────
def test_po_no_generation_unique(store):
    m = _material(store)
    a = mod.create_purchase(store, {"supplier": "A", "material_id": m["id"], "qty": 1})
    b = mod.create_purchase(store, {"supplier": "B", "material_id": m["id"], "qty": 1})
    assert a["po_no"] != b["po_no"]
    assert a["po_no"].endswith("-001")
    assert b["po_no"].endswith("-002")


# ── receive ───────────────────────────────────────────────────────────────────
def test_receive_partial_then_received(store):
    m = _material(store, stock=100)
    po = mod.create_purchase(store, {"supplier": "宝钢", "material_id": m["id"], "qty": 300})

    # 部分收货 → 库存增加、received 累加、状态 partial
    r1 = mod.receive(store, po["id"], {"qty": 120, "operator": "采购员"})
    assert r1["received_qty"] == 120
    assert r1["status"] == "partial"
    assert _stock_of(store, m["id"]) == 220

    # 收满 → 状态 received
    r2 = mod.receive(store, po["id"], {"qty": 180})
    assert r2["received_qty"] == 300
    assert r2["status"] == "received"
    assert _stock_of(store, m["id"]) == 400


def test_receive_over_quantity_blocked(store):
    m = _material(store)
    po = mod.create_purchase(store, {"supplier": "宝钢", "material_id": m["id"], "qty": 100})
    mod.receive(store, po["id"], {"qty": 60})
    with pytest.raises(ValidationError):
        mod.receive(store, po["id"], {"qty": 50})       # 60+50 > 100
    # 失败后库存不应被多加（只加了第一次的 60）
    assert _stock_of(store, m["id"]) == 60


def test_receive_after_received_blocked(store):
    m = _material(store)
    po = mod.create_purchase(store, {"supplier": "宝钢", "material_id": m["id"], "qty": 50})
    mod.receive(store, po["id"], {"qty": 50})            # 已收齐
    with pytest.raises(ValidationError):
        mod.receive(store, po["id"], {"qty": 1})


def test_receive_zero_qty_blocked(store):
    m = _material(store)
    po = mod.create_purchase(store, {"supplier": "宝钢", "material_id": m["id"], "qty": 50})
    with pytest.raises(ValidationError):
        mod.receive(store, po["id"], {"qty": 0})


def test_receive_not_found(store):
    with pytest.raises(NotFound):
        mod.receive(store, 9999, {"qty": 5})


# ── close ─────────────────────────────────────────────────────────────────────
def test_close_purchase(store):
    m = _material(store)
    po = mod.create_purchase(store, {"supplier": "宝钢", "material_id": m["id"], "qty": 50})
    out = mod.close_purchase(store, po["id"])
    assert out["status"] == "closed"
    assert out["status_label"] == "已关闭"


def test_close_then_receive_blocked(store):
    m = _material(store)
    po = mod.create_purchase(store, {"supplier": "宝钢", "material_id": m["id"], "qty": 50})
    mod.close_purchase(store, po["id"])
    with pytest.raises(ValidationError):
        mod.receive(store, po["id"], {"qty": 5})


def test_close_not_found(store):
    with pytest.raises(NotFound):
        mod.close_purchase(store, 9999)


# ── list_purchase ─────────────────────────────────────────────────────────────
def test_list_purchase_filter_and_label(store):
    m = _material(store)
    p1 = mod.create_purchase(store, {"supplier": "A", "material_id": m["id"], "qty": 100})
    mod.create_purchase(store, {"supplier": "B", "material_id": m["id"], "qty": 100})
    mod.receive(store, p1["id"], {"qty": 100})          # p1 → received

    all_pos = mod.list_purchase(store)
    assert len(all_pos) == 2
    assert all(po["status_label"] in ("待收货", "已收货") for po in all_pos)

    pending = mod.list_purchase(store, status="pending")
    assert len(pending) == 1 and pending[0]["supplier"] == "B"

    received = mod.list_purchase(store, status="received")
    assert len(received) == 1 and received[0]["supplier"] == "A"
    assert received[0]["status_label"] == "已收货"


def test_list_purchase_invalid_status(store):
    with pytest.raises(ValidationError):
        mod.list_purchase(store, status="bogus")


# ── seed ──────────────────────────────────────────────────────────────────────
def test_seed_idempotent_with_materials(store):
    _material(store, code="M-A", name="甲料")
    _material(store, code="M-B", name="乙料")
    mod.seed(store)
    n1 = len(mod.list_purchase(store))
    assert n1 == 2
    # 其中一条部分收货演示
    assert any(po["status"] == "partial" for po in mod.list_purchase(store))
    mod.seed(store)
    assert len(mod.list_purchase(store)) == n1          # 幂等


def test_seed_noop_without_materials(store):
    mod.seed(store)
    assert mod.list_purchase(store) == []
