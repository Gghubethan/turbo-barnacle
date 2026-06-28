"""数据导出模块测试：数据集清单、CSV 内容/表头、枚举转中文、未知数据集。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, FileResponse, ValidationError  # noqa: E402
import server.modules.export as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "ex.db")


@pytest.fixture
def seeded(store):
    p = store.create_product({"code": "P-1", "name": "件A", "unit": "个"})
    w = store.create_work_order({"product_id": p["id"], "planned_qty": 50, "assignee": "张三"})
    store.transition(w["id"], "dispatch", {"assignee": "张三"})
    store.transition(w["id"], "start")
    store.report_production(w["id"], {"reporter": "李四", "qty_ok": 20, "qty_defect": 2})
    return store, w


def _text(fr: FileResponse) -> str:
    # 去掉 utf-8-sig 的 BOM 再解码
    return fr.body.decode("utf-8-sig")


def test_list_datasets():
    keys = {d["key"] for d in mod.list_datasets()}
    assert {"work_orders", "reports", "inspections", "inventory",
            "materials", "products", "staff", "exceptions"} <= keys
    # 每项都有中文 label
    assert all(d["label"] for d in mod.list_datasets())


def test_unknown_dataset(store):
    with pytest.raises(ValidationError):
        mod.build_csv(store, "nope")


def test_export_returns_fileresponse_with_bom(seeded):
    store, _ = seeded
    fr = mod.build_csv(store, "work_orders")
    assert isinstance(fr, FileResponse)
    assert fr.filename.endswith(".csv")
    assert fr.body[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM
    assert "text/csv" in fr.content_type


def test_work_orders_csv_content(seeded):
    store, w = seeded
    text = _text(mod.build_csv(store, "work_orders"))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("工单号,产品,计划数")
    assert len(lines) == 2  # 表头 + 1 行
    assert w["order_no"] in text
    assert "生产中" in text  # 状态枚举转中文


def test_reports_csv_content(seeded):
    store, w = seeded
    text = _text(mod.build_csv(store, "reports"))
    assert text.splitlines()[0].startswith("工单号,报工人")
    assert "李四" in text
    assert w["order_no"] in text


def test_materials_csv_enum_label(store):
    store.create_material({"code": "M-1", "name": "钢板", "category": "raw", "stock": 100})
    text = _text(mod.build_csv(store, "materials"))
    assert "原料" in text  # category 枚举转中文
    assert "钢板" in text


def test_staff_csv_enum_label(store):
    store.create_staff({"name": "王五", "role": "inspector", "team": "质检组"})
    text = _text(mod.build_csv(store, "staff"))
    assert "质检员" in text
    assert "在职" in text


def test_empty_dataset_has_only_header(store):
    text = _text(mod.build_csv(store, "products"))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) == 1  # 仅表头
    assert lines[0].startswith("编码,名称")


def test_inspections_export(seeded):
    store, w = seeded
    store.create_inspection(w["id"], {
        "inspector": "陈质检", "qty_inspected": 20, "qty_qualified": 18,
        "qty_defective": 2, "result": "pass"})
    text = _text(mod.build_csv(store, "inspections"))
    assert "陈质检" in text
    assert "合格" in text


def test_routes_registered(store):
    paths = [r[1] for r in mod.routes(store)]
    assert r"/api/export" in paths
