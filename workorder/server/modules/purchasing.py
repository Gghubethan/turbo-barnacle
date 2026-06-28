"""采购管理模块：采购订单管理，收货时自动入库，打通「采购→库存」。

约定式插件：``server.api`` 自动应用 :data:`SCHEMA`、挂载 :func:`routes`、调用 :func:`seed`。
业务校验失败抛 :class:`ValidationError`（→400），资源不存在抛 :class:`NotFound`（→404）。

收货核心：调用 ``store.stock_move(material_id, "purchase", qty, ...)`` 增加物料库存并记一条
``inventory_txns`` 入库流水，实现采购到库存的自动衔接。
"""

from datetime import datetime

from server.store import ValidationError, NotFound, _now, _num, _require

# 采购单状态：待收货 / 部分收货 / 已收货 / 已关闭
PO_STATUS = {
    "pending": "待收货",
    "partial": "部分收货",
    "received": "已收货",
    "closed": "已关闭",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    po_no          TEXT NOT NULL UNIQUE,
    supplier       TEXT NOT NULL,
    material_id    INTEGER NOT NULL REFERENCES materials(id),
    material_name  TEXT NOT NULL,
    qty            REAL NOT NULL,
    received_qty   REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'pending',
    expected_date  TEXT DEFAULT '',
    remark         TEXT DEFAULT '',
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_po_material ON purchase_orders(material_id);
"""


def _po_label(d: dict) -> dict:
    d["status_label"] = PO_STATUS.get(d["status"], d["status"])
    return d


def _gen_po_no(conn) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"PO{today}"
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM purchase_orders WHERE po_no LIKE ?", (prefix + "%",)
    ).fetchone()
    return f"{prefix}-{row['c'] + 1:03d}"


def list_purchase(store, status=None) -> list[dict]:
    sql = "SELECT * FROM purchase_orders WHERE 1=1"
    params: list = []
    if status and status != "all":
        if status not in PO_STATUS:
            raise ValidationError(f"未知状态：{status}")
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id DESC"
    with store._conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_po_label(dict(r)) for r in rows]


def create_purchase(store, data: dict) -> dict:
    supplier = _require(data, "supplier", "供应商")
    material_id = _require(data, "material_id", "物料")
    qty = _num(data.get("qty"), "采购数量", allow_zero=False)
    expected_date = str(data.get("expected_date", "")).strip()
    with store._lock, store._conn() as conn:
        mat = conn.execute(
            "SELECT * FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
        if not mat:
            raise ValidationError("所选物料不存在")
        po_no = _gen_po_no(conn)
        cur = conn.execute(
            """INSERT INTO purchase_orders
               (po_no, supplier, material_id, material_name, qty, received_qty,
                status, expected_date, remark, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (po_no, supplier, int(material_id), mat["name"], qty, 0,
             "pending", expected_date, str(data.get("remark", "")).strip(), _now()),
        )
        row = conn.execute(
            "SELECT * FROM purchase_orders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _po_label(dict(row))


def receive(store, po_id: int, data: dict) -> dict:
    """采购收货：核对数量后调用 stock_move 入库，并累加 received_qty / 更新状态。"""
    qty = _num(data.get("qty"), "收货数量", allow_zero=False)
    with store._conn() as conn:
        row = conn.execute(
            "SELECT * FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone()
    if not row:
        raise NotFound(f"采购单 {po_id} 不存在")
    po = dict(row)
    if po["status"] in ("received", "closed"):
        raise ValidationError(f"采购单当前状态「{PO_STATUS[po['status']]}」不可再收货")
    new_received = po["received_qty"] + qty
    if new_received > po["qty"]:
        raise ValidationError(
            f"收货数量超出：采购 {po['qty']}，已收 {po['received_qty']}，本次 {qty}"
        )
    # 入库（增加物料 stock + 记一条 purchase 流水）
    store.stock_move(
        po["material_id"], "purchase", qty,
        operator=data.get("operator", ""),
        remark="采购收货 " + po["po_no"],
    )
    new_status = "received" if new_received >= po["qty"] else "partial"
    with store._lock, store._conn() as conn:
        conn.execute(
            "UPDATE purchase_orders SET received_qty = ?, status = ? WHERE id = ?",
            (new_received, new_status, po_id),
        )
        row = conn.execute(
            "SELECT * FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone()
    return _po_label(dict(row))


def close_purchase(store, po_id: int) -> dict:
    with store._lock, store._conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone():
            raise NotFound(f"采购单 {po_id} 不存在")
        conn.execute(
            "UPDATE purchase_orders SET status = 'closed' WHERE id = ?", (po_id,)
        )
        row = conn.execute(
            "SELECT * FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone()
    return _po_label(dict(row))


def routes(store):
    return [
        ("GET",  r"/api/purchasing",
         lambda req, p: (200, list_purchase(
             store, status=req["query"].get("status", [None])[0]))),
        ("POST", r"/api/purchasing",
         lambda req, p: (201, create_purchase(store, req["body"]))),
        ("POST", r"/api/purchasing/(?P<id>\d+)/receive",
         lambda req, p: (200, receive(store, int(p["id"]), req["body"]))),
        ("POST", r"/api/purchasing/(?P<id>\d+)/close",
         lambda req, p: (200, close_purchase(store, int(p["id"])))),
    ]


def seed(store):
    """幂等：仅当 purchase_orders 为空且 materials 有数据时灌入 2 条采购单，
    其中一条部分收货作演示（变 partial）。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM purchase_orders LIMIT 1").fetchone():
            return
        mats = conn.execute(
            "SELECT id FROM materials ORDER BY id LIMIT 2"
        ).fetchall()
    if not mats:
        return
    first = mats[0]["id"]
    second = mats[1]["id"] if len(mats) > 1 else first

    po1 = create_purchase(store, {
        "supplier": "宝钢供应链", "material_id": first, "qty": 500,
        "expected_date": "2026-07-05", "remark": "原料补货"})
    # 部分收货演示
    receive(store, po1["id"], {"qty": 200, "operator": "采购员"})

    create_purchase(store, {
        "supplier": "南山铝业", "material_id": second, "qty": 100,
        "expected_date": "2026-07-10", "remark": "型材采购"})
