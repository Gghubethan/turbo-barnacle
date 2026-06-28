"""工单系统业务逻辑测试：状态机、报工自动完工、异常、看板统计、校验。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    return s


@pytest.fixture
def product(store):
    return store.create_product({"code": "T-001", "name": "测试件", "unit": "个"})


def make_wo(store, product, qty=100, **kw):
    data = {"product_id": product["id"], "planned_qty": qty}
    data.update(kw)
    return store.create_work_order(data)


# ── 产品 ────────────────────────────────────────────────────────────────
def test_create_product_requires_code(store):
    with pytest.raises(ValidationError):
        store.create_product({"name": "无编码"})


def test_duplicate_product_code(store, product):
    with pytest.raises(ValidationError):
        store.create_product({"code": "T-001", "name": "重复"})


# ── 工单创建 ──────────────────────────────────────────────────────────────
def test_order_no_is_generated_and_unique(store, product):
    a = make_wo(store, product)
    b = make_wo(store, product)
    assert a["order_no"] != b["order_no"]
    assert a["order_no"].startswith("WO")


def test_create_requires_positive_qty(store, product):
    with pytest.raises(ValidationError):
        make_wo(store, product, qty=0)


def test_create_rejects_unknown_product(store):
    with pytest.raises(ValidationError):
        store.create_work_order({"product_id": 999, "planned_qty": 10})


def test_new_order_starts_pending(store, product):
    wo = make_wo(store, product)
    assert wo["status"] == "pending"
    assert wo["status_label"] == "待派工"


# ── 状态机 ────────────────────────────────────────────────────────────────
def test_full_lifecycle(store, product):
    wo = make_wo(store, product, qty=50)
    wo = store.transition(wo["id"], "dispatch", {"assignee": "张三"})
    assert wo["status"] == "dispatched" and wo["assignee"] == "张三"
    wo = store.transition(wo["id"], "start")
    assert wo["status"] == "producing" and wo["actual_start"]
    wo = store.transition(wo["id"], "complete")
    assert wo["status"] == "completed" and wo["actual_end"]
    wo = store.transition(wo["id"], "close")
    assert wo["status"] == "closed"


def test_dispatch_requires_assignee(store, product):
    wo = make_wo(store, product)
    with pytest.raises(ValidationError):
        store.transition(wo["id"], "dispatch", {})


def test_illegal_transition_blocked(store, product):
    wo = make_wo(store, product)
    # 待派工不能直接开工
    with pytest.raises(ValidationError):
        store.transition(wo["id"], "start")


def test_pause_and_resume(store, product):
    wo = make_wo(store, product)
    store.transition(wo["id"], "dispatch", {"assignee": "A"})
    store.transition(wo["id"], "start")
    wo = store.transition(wo["id"], "pause")
    assert wo["status"] == "paused"
    wo = store.transition(wo["id"], "start")
    assert wo["status"] == "producing"


def test_unknown_action(store, product):
    wo = make_wo(store, product)
    with pytest.raises(ValidationError):
        store.transition(wo["id"], "teleport")


def test_transition_missing_order(store):
    with pytest.raises(NotFound):
        store.transition(123, "dispatch", {"assignee": "x"})


# ── 报工 ────────────────────────────────────────────────────────────────
def producing_wo(store, product, qty=100):
    wo = make_wo(store, product, qty=qty)
    store.transition(wo["id"], "dispatch", {"assignee": "A"})
    return store.transition(wo["id"], "start")


def test_report_accumulates(store, product):
    wo = producing_wo(store, product, qty=100)
    wo = store.report_production(wo["id"], {"reporter": "李四", "qty_ok": 30, "qty_defect": 2})
    assert wo["completed_qty"] == 30
    assert wo["defect_qty"] == 2
    assert wo["progress"] == 30.0


def test_report_auto_completes(store, product):
    wo = producing_wo(store, product, qty=40)
    wo = store.report_production(wo["id"], {"reporter": "李四", "qty_ok": 40})
    assert wo["status"] == "completed"
    assert wo["actual_end"]


def test_report_blocked_when_not_producing(store, product):
    wo = make_wo(store, product)
    with pytest.raises(ValidationError):
        store.report_production(wo["id"], {"reporter": "x", "qty_ok": 1})


def test_report_requires_quantity(store, product):
    wo = producing_wo(store, product)
    with pytest.raises(ValidationError):
        store.report_production(wo["id"], {"reporter": "x", "qty_ok": 0, "qty_defect": 0})


def test_report_rejects_negative(store, product):
    wo = producing_wo(store, product)
    with pytest.raises(ValidationError):
        store.report_production(wo["id"], {"reporter": "x", "qty_ok": -5})


def test_reports_listed_newest_first(store, product):
    wo = producing_wo(store, product, qty=100)
    store.report_production(wo["id"], {"reporter": "a", "qty_ok": 10})
    store.report_production(wo["id"], {"reporter": "b", "qty_ok": 10})
    reports = store.list_reports(wo["id"])
    assert len(reports) == 2
    assert reports[0]["reporter"] == "b"


# ── 异常 ────────────────────────────────────────────────────────────────
def test_exception_lifecycle(store, product):
    wo = make_wo(store, product)
    exc = store.create_exception({
        "work_order_id": wo["id"], "category": "material",
        "description": "缺料", "reporter": "王五",
    })
    assert exc["status"] == "open"
    assert exc["category_label"] == "物料缺料"
    assert exc["order_no"] == wo["order_no"]
    resolved = store.resolve_exception(exc["id"], {"resolution": "已补料"})
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"]


def test_exception_requires_description(store, product):
    wo = make_wo(store, product)
    with pytest.raises(ValidationError):
        store.create_exception({"work_order_id": wo["id"], "description": ""})


def test_resolve_twice_blocked(store, product):
    wo = make_wo(store, product)
    exc = store.create_exception({"work_order_id": wo["id"], "description": "x"})
    store.resolve_exception(exc["id"], {"resolution": "done"})
    with pytest.raises(ValidationError):
        store.resolve_exception(exc["id"], {"resolution": "again"})


def test_exception_filter_by_status(store, product):
    wo = make_wo(store, product)
    e1 = store.create_exception({"work_order_id": wo["id"], "description": "a"})
    store.create_exception({"work_order_id": wo["id"], "description": "b"})
    store.resolve_exception(e1["id"], {"resolution": "ok"})
    assert len(store.list_exceptions(status="open")) == 1
    assert len(store.list_exceptions(status="resolved")) == 1


# ── 看板 ────────────────────────────────────────────────────────────────
def test_dashboard_stats(store, product):
    wo = producing_wo(store, product, qty=100)
    store.report_production(wo["id"], {"reporter": "x", "qty_ok": 60, "qty_defect": 10})
    make_wo(store, product, qty=50)  # 另一张 pending
    stats = store.dashboard_stats()
    assert stats["total_orders"] == 2
    assert stats["planned_qty"] == 150
    assert stats["completed_qty"] == 60
    assert stats["defect_qty"] == 10
    assert stats["by_status"]["producing"] == 1
    assert stats["by_status"]["pending"] == 1
    assert stats["completion_rate"] == 40.0  # 60/150
    assert round(stats["defect_rate"], 1) == round(10 / 70 * 100, 1)


# ── 搜索 / 过滤 ────────────────────────────────────────────────────────────
def test_list_filter_and_search(store, product):
    wo = make_wo(store, product, assignee="赵六")
    store.transition(wo["id"], "dispatch", {"assignee": "赵六"})
    make_wo(store, product, assignee="孙七")
    assert len(store.list_work_orders(status="dispatched")) == 1
    assert len(store.list_work_orders(keyword="赵六")) == 1
    assert len(store.list_work_orders(keyword="不存在")) == 0
