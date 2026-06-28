"""BOM 物料清单模块。

维护「产品 → 所需物料 + 单位用量 + 损耗率」，并据此测算某产量下的用料需求、
对比现有库存给出缺口（采购建议）。打通 产品 ↔ 物料 ↔ 库存 的计划环。
"""

from __future__ import annotations

from server.store import ValidationError, NotFound, _now, _num, _require

SCHEMA = """
CREATE TABLE IF NOT EXISTS bom_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL,
    material_id   INTEGER NOT NULL,
    material_name TEXT NOT NULL,
    qty_per       REAL NOT NULL,
    loss_rate     REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bom_product ON bom_items(product_id);
"""


def _qint(req, key):
    v = req["query"].get(key, [None])[0]
    return int(v) if v not in (None, "") else None


def _product(conn, product_id):
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise ValidationError("所选产品不存在")
    return dict(row)


def list_bom(store, product_id):
    if not product_id:
        raise ValidationError("请选择产品")
    sql = ("SELECT b.*, m.code AS material_code, m.unit AS unit, m.stock AS stock "
           "FROM bom_items b LEFT JOIN materials m ON m.id = b.material_id "
           "WHERE b.product_id = ? ORDER BY b.id")
    with store._conn() as conn:
        rows = conn.execute(sql, (product_id,)).fetchall()
    return [dict(r) for r in rows]


def add_bom_item(store, product_id, data):
    if not product_id:
        raise ValidationError("请选择产品")
    material_id = _require(data, "material_id", "物料")
    qty_per = _num(data.get("qty_per"), "单位用量", allow_zero=False)
    loss_rate = _num(data.get("loss_rate", 0), "损耗率")
    with store._lock, store._conn() as conn:
        _product(conn, product_id)
        mat = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
        if not mat:
            raise ValidationError("所选物料不存在")
        dup = conn.execute(
            "SELECT 1 FROM bom_items WHERE product_id = ? AND material_id = ?",
            (product_id, material_id),
        ).fetchone()
        if dup:
            raise ValidationError("该物料已在此产品的 BOM 中")
        cur = conn.execute(
            """INSERT INTO bom_items
               (product_id, material_id, material_name, qty_per, loss_rate, created_at)
               VALUES (?,?,?,?,?,?)""",
            (product_id, material_id, mat["name"], qty_per, loss_rate, _now()),
        )
        row = conn.execute("SELECT * FROM bom_items WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def delete_bom_item(store, item_id):
    with store._lock, store._conn() as conn:
        if not conn.execute("SELECT 1 FROM bom_items WHERE id = ?", (item_id,)).fetchone():
            raise NotFound(f"BOM 行 {item_id} 不存在")
        conn.execute("DELETE FROM bom_items WHERE id = ?", (item_id,))
    return {"ok": True, "id": item_id}


def requirements(store, product_id, qty):
    """按产量测算用料需求，对比库存给出缺口。"""
    if not product_id:
        raise ValidationError("请选择产品")
    qty = _num(qty, "产量", allow_zero=False)
    with store._conn() as conn:
        _product(conn, product_id)
        rows = conn.execute(
            "SELECT b.*, m.code AS material_code, m.unit AS unit, m.stock AS stock "
            "FROM bom_items b LEFT JOIN materials m ON m.id = b.material_id "
            "WHERE b.product_id = ? ORDER BY b.id",
            (product_id,),
        ).fetchall()
    items = []
    has_shortage = False
    for r in rows:
        d = dict(r)
        required = round(d["qty_per"] * qty * (1 + (d["loss_rate"] or 0) / 100), 3)
        stock = d["stock"] or 0
        shortage = round(max(0, required - stock), 3)
        if shortage > 0:
            has_shortage = True
        items.append({
            "material_id": d["material_id"],
            "material_code": d["material_code"],
            "material_name": d["material_name"],
            "unit": d["unit"],
            "qty_per": d["qty_per"],
            "loss_rate": d["loss_rate"],
            "required": required,
            "stock": stock,
            "shortage": shortage,
        })
    return {"product_id": product_id, "qty": qty, "items": items, "has_shortage": has_shortage}


def routes(store):
    return [
        ("GET", r"/api/bom/items",
         lambda req, p: (200, list_bom(store, _qint(req, "product_id")))),
        ("POST", r"/api/bom/items",
         lambda req, p: (201, add_bom_item(store, req["body"].get("product_id"), req["body"]))),
        ("POST", r"/api/bom/items/(?P<id>\d+)/delete",
         lambda req, p: (200, delete_bom_item(store, int(p["id"])))),
        ("GET", r"/api/bom/requirements",
         lambda req, p: (200, requirements(store, _qint(req, "product_id"),
                                           req["query"].get("qty", [None])[0]))),
    ]


def seed(store):
    """幂等：给第一个产品配一份 BOM（用现有物料）。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM bom_items LIMIT 1").fetchone():
            return
        product = conn.execute("SELECT id FROM products ORDER BY id LIMIT 1").fetchone()
        mats = conn.execute("SELECT id FROM materials ORDER BY id LIMIT 2").fetchall()
    if not product or len(mats) < 1:
        return
    pid = product["id"]
    add_bom_item(store, pid, {"material_id": mats[0]["id"], "qty_per": 0.5, "loss_rate": 3})
    if len(mats) > 1:
        add_bom_item(store, pid, {"material_id": mats[1]["id"], "qty_per": 0.02, "loss_rate": 0})
