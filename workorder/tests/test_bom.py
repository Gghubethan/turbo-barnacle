"""BOM 物料清单模块测试：用料维护、需求测算、缺口计算、校验分支。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.bom as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "bom.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


@pytest.fixture
def fixtures(store):
    p = store.create_product({"code": "P-1", "name": "成品A"})
    m1 = store.create_material({"code": "M-1", "name": "钢板", "unit": "kg", "stock": 100})
    m2 = store.create_material({"code": "M-2", "name": "螺栓", "unit": "个", "stock": 5})
    return store, p, m1, m2


# ── 新增 / 列表 ────────────────────────────────────────────────────────────
def test_add_and_list(fixtures):
    store, p, m1, _ = fixtures
    item = mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 2, "loss_rate": 5})
    assert item["material_name"] == "钢板"
    rows = mod.list_bom(store, p["id"])
    assert len(rows) == 1
    assert rows[0]["material_code"] == "M-1"
    assert rows[0]["unit"] == "kg"
    assert rows[0]["stock"] == 100


def test_list_requires_product(store):
    with pytest.raises(ValidationError):
        mod.list_bom(store, None)


def test_add_requires_material(fixtures):
    store, p, _, _ = fixtures
    with pytest.raises(ValidationError):
        mod.add_bom_item(store, p["id"], {"qty_per": 1})


def test_add_zero_qty_blocked(fixtures):
    store, p, m1, _ = fixtures
    with pytest.raises(ValidationError):
        mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 0})


def test_add_unknown_product(fixtures):
    store, _, m1, _ = fixtures
    with pytest.raises(ValidationError):
        mod.add_bom_item(store, 999, {"material_id": m1["id"], "qty_per": 1})


def test_add_unknown_material(fixtures):
    store, p, _, _ = fixtures
    with pytest.raises(ValidationError):
        mod.add_bom_item(store, p["id"], {"material_id": 999, "qty_per": 1})


def test_duplicate_material_blocked(fixtures):
    store, p, m1, _ = fixtures
    mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 1})
    with pytest.raises(ValidationError):
        mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 2})


# ── 删除 ────────────────────────────────────────────────────────────────
def test_delete(fixtures):
    store, p, m1, _ = fixtures
    item = mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 1})
    mod.delete_bom_item(store, item["id"])
    assert mod.list_bom(store, p["id"]) == []


def test_delete_missing(store):
    with pytest.raises(NotFound):
        mod.delete_bom_item(store, 12345)


# ── 需求测算 ──────────────────────────────────────────────────────────────
def test_requirements_with_loss_and_shortage(fixtures):
    store, p, m1, m2 = fixtures
    mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 2, "loss_rate": 0})   # 钢板库存100
    mod.add_bom_item(store, p["id"], {"material_id": m2["id"], "qty_per": 1, "loss_rate": 10})  # 螺栓库存5
    res = mod.requirements(store, p["id"], 100)
    assert res["qty"] == 100
    by_name = {i["material_name"]: i for i in res["items"]}
    # 钢板：2 * 100 = 200，库存 100 → 缺 100
    assert by_name["钢板"]["required"] == 200
    assert by_name["钢板"]["shortage"] == 100
    # 螺栓：1 * 100 * 1.1 = 110，库存 5 → 缺 105
    assert by_name["螺栓"]["required"] == 110
    assert by_name["螺栓"]["shortage"] == 105
    assert res["has_shortage"] is True


def test_requirements_sufficient(fixtures):
    store, p, m1, _ = fixtures
    mod.add_bom_item(store, p["id"], {"material_id": m1["id"], "qty_per": 0.5, "loss_rate": 0})
    res = mod.requirements(store, p["id"], 100)  # 需 50，库存 100
    assert res["items"][0]["shortage"] == 0
    assert res["has_shortage"] is False


def test_requirements_zero_qty_blocked(fixtures):
    store, p, _, _ = fixtures
    with pytest.raises(ValidationError):
        mod.requirements(store, p["id"], 0)


def test_requirements_unknown_product(store):
    with pytest.raises(ValidationError):
        mod.requirements(store, 999, 10)


# ── 路由 / 种子 ────────────────────────────────────────────────────────────
def test_routes_registered(store):
    paths = [r[1] for r in mod.routes(store)]
    assert r"/api/bom/items" in paths
    assert r"/api/bom/requirements" in paths


def test_seed_idempotent(fixtures):
    store, p, _, _ = fixtures
    mod.seed(store)
    n1 = len(mod.list_bom(store, p["id"]))
    mod.seed(store)
    n2 = len(mod.list_bom(store, p["id"]))
    assert n1 == n2 and n1 > 0
