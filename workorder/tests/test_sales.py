"""销售订单模块测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.sales as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


@pytest.fixture
def product(store):
    return store.create_product({"code": "P-1", "name": "精密轴承"})


# ── create_sales ────────────────────────────────────────────────────────────
def test_create_sales_ok(store, product):
    so = mod.create_sales(store, {
        "customer": "华东机械", "product_id": product["id"], "qty": 100,
        "due_date": "2026-07-10", "remark": "急单"})
    assert so["customer"] == "华东机械"
    assert so["product_id"] == product["id"]
    assert so["product_name"] == "精密轴承"
    assert so["qty"] == 100
    assert so["due_date"] == "2026-07-10"
    assert so["status"] == "pending"
    assert so["status_label"] == "待生产"
    assert so["work_order_id"] is None
    assert so["order_no"].startswith("SO")


def test_create_sales_missing_customer(store, product):
    with pytest.raises(ValidationError):
        mod.create_sales(store, {"product_id": product["id"], "qty": 10})


def test_create_sales_missing_product_id(store):
    with pytest.raises(ValidationError):
        mod.create_sales(store, {"customer": "甲方", "qty": 10})


def test_create_sales_invalid_product_id(store):
    with pytest.raises(ValidationError):
        mod.create_sales(store, {"customer": "甲方", "product_id": 999, "qty": 10})


def test_create_sales_qty_zero(store, product):
    with pytest.raises(ValidationError):
        mod.create_sales(store, {
            "customer": "甲方", "product_id": product["id"], "qty": 0})


# ── 订单号 ──────────────────────────────────────────────────────────────────
def test_order_no_generation_and_unique(store, product):
    so1 = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 5})
    so2 = mod.create_sales(store, {
        "customer": "乙", "product_id": product["id"], "qty": 8})
    assert so1["order_no"] != so2["order_no"]
    assert so1["order_no"].endswith("-001")
    assert so2["order_no"].endswith("-002")


# ── push_to_production ──────────────────────────────────────────────────────
def test_push_to_production_ok(store, product):
    so = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 50,
        "due_date": "2026-07-15"})
    pushed = mod.push_to_production(store, so["id"])
    assert pushed["status"] == "in_production"
    assert pushed["status_label"] == "生产中"
    assert pushed["work_order_id"] is not None
    assert "work_order_no" in pushed
    # 工单确已生成且数量/产品一致
    wo = store.get_work_order(pushed["work_order_id"])
    assert wo["order_no"] == pushed["work_order_no"]
    assert wo["planned_qty"] == 50
    assert wo["product_id"] == product["id"]
    assert "销售订单" in wo["remark"]
    assert wo["planned_end"] == "2026-07-15"


def test_push_to_production_duplicate(store, product):
    so = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 50})
    mod.push_to_production(store, so["id"])
    with pytest.raises(ValidationError):
        mod.push_to_production(store, so["id"])


def test_push_to_production_not_found(store):
    with pytest.raises(NotFound):
        mod.push_to_production(store, 999)


# ── ship ────────────────────────────────────────────────────────────────────
def test_ship_ok_after_push(store, product):
    so = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 50})
    mod.push_to_production(store, so["id"])
    shipped = mod.ship(store, so["id"])
    assert shipped["status"] == "shipped"
    assert shipped["status_label"] == "已发货"


def test_ship_invalid_status(store, product):
    # pending 状态不能发货
    so = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 50})
    with pytest.raises(ValidationError):
        mod.ship(store, so["id"])


def test_ship_not_found(store):
    with pytest.raises(NotFound):
        mod.ship(store, 999)


# ── close_sales ─────────────────────────────────────────────────────────────
def test_close_sales_ok(store, product):
    so = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 50})
    closed = mod.close_sales(store, so["id"])
    assert closed["status"] == "closed"
    assert closed["status_label"] == "已关闭"


# ── list_sales ──────────────────────────────────────────────────────────────
def test_list_sales_filter_and_label(store, product):
    a = mod.create_sales(store, {
        "customer": "甲", "product_id": product["id"], "qty": 10})
    mod.create_sales(store, {
        "customer": "乙", "product_id": product["id"], "qty": 20})
    mod.push_to_production(store, a["id"])

    all_rows = mod.list_sales(store)
    assert len(all_rows) == 2
    assert all(r["status_label"] for r in all_rows)

    pending = mod.list_sales(store, status="pending")
    assert len(pending) == 1
    assert pending[0]["customer"] == "乙"

    in_prod = mod.list_sales(store, status="in_production")
    assert len(in_prod) == 1
    assert in_prod[0]["id"] == a["id"]
    assert in_prod[0]["status_label"] == "生产中"


def test_list_sales_unknown_status(store):
    with pytest.raises(ValidationError):
        mod.list_sales(store, status="bogus")
