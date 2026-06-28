"""设备管理模块测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.equipment as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "eq.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


# ── create_equipment ───────────────────────────────────────────────────────
def test_create_equipment_ok(store):
    e = mod.create_equipment(store, {
        "code": "CNC-01", "name": "数控车床", "model": "CK6140",
        "location": "一号车间", "owner": "张工"})
    assert e["code"] == "CNC-01"
    assert e["status"] == "running"          # 默认
    assert e["status_label"] == "运行中"
    assert len(mod.list_equipment(store)) == 1


def test_create_equipment_missing_code(store):
    with pytest.raises(ValidationError):
        mod.create_equipment(store, {"name": "无编码"})


def test_create_equipment_duplicate_code(store):
    mod.create_equipment(store, {"code": "CNC-01", "name": "a"})
    with pytest.raises(ValidationError):
        mod.create_equipment(store, {"code": "CNC-01", "name": "b"})


def test_create_equipment_invalid_status(store):
    with pytest.raises(ValidationError):
        mod.create_equipment(store, {"code": "X-1", "name": "x", "status": "flying"})


def test_create_equipment_status_choice(store):
    e = mod.create_equipment(store, {"code": "X-2", "name": "x", "status": "idle"})
    assert e["status"] == "idle"
    assert e["status_label"] == "闲置"


# ── set_status ──────────────────────────────────────────────────────────────
def test_set_status_ok(store):
    e = mod.create_equipment(store, {"code": "X-3", "name": "x"})
    out = mod.set_status(store, e["id"], "fault")
    assert out["status"] == "fault"
    assert out["status_label"] == "故障"


def test_set_status_not_found(store):
    with pytest.raises(NotFound):
        mod.set_status(store, 999, "idle")


def test_set_status_invalid(store):
    e = mod.create_equipment(store, {"code": "X-4", "name": "x"})
    with pytest.raises(ValidationError):
        mod.set_status(store, e["id"], "broken")


# ── add_log ─────────────────────────────────────────────────────────────────
def test_add_log_ok(store):
    e = mod.create_equipment(store, {"code": "X-5", "name": "x"})
    log = mod.add_log(store, e["id"], {
        "type": "inspect", "content": "点检正常", "operator": "李师傅", "cost": 0})
    assert log["type_label"] == "点检"
    assert log["equipment_name"] == "x"
    assert log["cost"] == 0


def test_add_log_missing_type(store):
    e = mod.create_equipment(store, {"code": "X-6", "name": "x"})
    with pytest.raises(ValidationError):
        mod.add_log(store, e["id"], {"content": "缺类型"})


def test_add_log_invalid_type(store):
    e = mod.create_equipment(store, {"code": "X-7", "name": "x"})
    with pytest.raises(ValidationError):
        mod.add_log(store, e["id"], {"type": "explode", "content": "非法"})


def test_add_log_missing_content(store):
    e = mod.create_equipment(store, {"code": "X-8", "name": "x"})
    with pytest.raises(ValidationError):
        mod.add_log(store, e["id"], {"type": "inspect"})


def test_add_log_equipment_not_found(store):
    with pytest.raises(NotFound):
        mod.add_log(store, 999, {"type": "inspect", "content": "无设备"})


def test_add_log_cost_negative_blocked(store):
    e = mod.create_equipment(store, {"code": "X-9", "name": "x"})
    with pytest.raises(ValidationError):
        mod.add_log(store, e["id"], {"type": "repair", "content": "x", "cost": -5})


def test_repair_sets_status_maintenance(store):
    e = mod.create_equipment(store, {"code": "X-10", "name": "x", "status": "fault"})
    mod.add_log(store, e["id"], {"type": "repair", "content": "更换轴承", "cost": 300})
    after = mod.list_equipment(store)[0]
    assert after["status"] == "maintenance"
    assert after["status_label"] == "保养中"


# ── list_logs ───────────────────────────────────────────────────────────────
def test_list_logs_filter_and_order(store):
    e1 = mod.create_equipment(store, {"code": "A-1", "name": "甲"})
    e2 = mod.create_equipment(store, {"code": "A-2", "name": "乙"})
    mod.add_log(store, e1["id"], {"type": "inspect", "content": "1"})
    mod.add_log(store, e1["id"], {"type": "maintain", "content": "2"})
    mod.add_log(store, e2["id"], {"type": "inspect", "content": "3"})

    all_logs = mod.list_logs(store)
    assert len(all_logs) == 3
    # 倒序：最新的在最前
    assert all_logs[0]["content"] == "3"

    only_e1 = mod.list_logs(store, equipment_id=e1["id"])
    assert len(only_e1) == 2
    assert all(l["equipment_name"] == "甲" for l in only_e1)
    assert only_e1[0]["type_label"] == "保养"
    assert only_e1[1]["type_label"] == "点检"


def test_seed_idempotent(store):
    mod.seed(store)
    n1 = len(mod.list_equipment(store))
    assert n1 >= 2
    mod.seed(store)
    assert len(mod.list_equipment(store)) == n1   # 幂等
    # 种子里至少一条点检记录
    logs = mod.list_logs(store)
    assert any(l["type"] == "inspect" for l in logs)
