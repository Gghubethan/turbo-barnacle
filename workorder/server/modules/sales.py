"""销售订单模块：管理客户订单，并能一键下推生成生产工单，打通「销售→生产」。

- 订单录入（客户 / 产品 / 数量 / 交期）；
- 一键下推：调用核心 ``store.create_work_order`` 生成生产工单并回填关联；
- 发货 / 关闭等状态流转。

业务逻辑写成普通函数，便于 pytest 直接调用。
"""

from __future__ import annotations

from datetime import datetime

from server.store import (
    ValidationError,
    NotFound,
    _now,
    _num,
    _require,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales_orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no       TEXT NOT NULL UNIQUE,
    customer       TEXT NOT NULL,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    product_name   TEXT NOT NULL,
    qty            REAL NOT NULL,
    due_date       TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'pending',
    work_order_id  INTEGER REFERENCES work_orders(id),
    remark         TEXT DEFAULT '',
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sales_status ON sales_orders(status);
CREATE INDEX IF NOT EXISTS idx_sales_wo ON sales_orders(work_order_id);
"""

# 销售订单状态 → 中文标签
SALES_STATUS = {
    "pending": "待生产",
    "in_production": "生产中",
    "shipped": "已发货",
    "closed": "已关闭",
}


def _label(row: dict) -> dict:
    """补充展示用派生字段：中文 status_label。"""
    row["status_label"] = SALES_STATUS.get(row["status"], row["status"])
    return row


def _gen_order_no(conn) -> str:
    """订单号：SO + 当天 yyyymmdd + -NNN 序号（按当天已有数量自增）。"""
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"SO{today}"
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM sales_orders WHERE order_no LIKE ?",
        (prefix + "%",),
    ).fetchone()
    return f"{prefix}-{row['c'] + 1:03d}"


# ── 查询 ──────────────────────────────────────────────────────────────────
def list_sales(store, status=None) -> list[dict]:
    """列出销售订单，附中文 status_label；可按 status 过滤。"""
    sql = "SELECT * FROM sales_orders WHERE 1=1"
    params: list = []
    if status and status != "all":
        if status not in SALES_STATUS:
            raise ValidationError(f"未知状态：{status}")
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id DESC"
    with store._conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_label(dict(r)) for r in rows]


# ── 创建 ──────────────────────────────────────────────────────────────────
def create_sales(store, data: dict) -> dict:
    """新建销售订单。

    - customer 必填；
    - product_id 必填且必须存在于 products 表（取 name 存入 product_name）；
    - qty 必须大于 0；due_date 选填；
    - 新订单 status='pending'。
    """
    customer = _require(data, "customer", "客户")
    product_id = _require(data, "product_id", "产品")
    qty = _num(data.get("qty"), "数量", allow_zero=False)
    due_date = str(data.get("due_date", "")).strip()

    with store._lock, store._conn() as conn:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if not product:
            raise ValidationError("所选产品不存在")
        order_no = _gen_order_no(conn)
        cur = conn.execute(
            """INSERT INTO sales_orders
               (order_no, customer, product_id, product_name, qty, due_date,
                status, remark, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (order_no, customer, product_id, product["name"], qty, due_date,
             "pending", str(data.get("remark", "")).strip(), _now()),
        )
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _label(dict(row))


# ── 下推生产 ────────────────────────────────────────────────────────────────
def push_to_production(store, so_id: int) -> dict:
    """把订单下推为生产工单。

    找不到订单抛 NotFound；若订单已有 work_order_id 或 status!='pending' 抛
    ValidationError（避免重复下推）。生成工单后回填 work_order_id，status 改
    'in_production'。返回更新后的订单（含 work_order_no 字段=工单号）。
    """
    with store._conn() as conn:
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (so_id,)
        ).fetchone()
    if not row:
        raise NotFound(f"销售订单 {so_id} 不存在")
    so = dict(row)
    if so["work_order_id"] or so["status"] != "pending":
        raise ValidationError("该订单已下推，不能重复下推")

    # 调用核心方法生成生产工单
    wo = store.create_work_order({
        "product_id": so["product_id"],
        "planned_qty": so["qty"],
        "planned_end": so["due_date"],
        "remark": "销售订单 " + so["order_no"],
    })

    with store._lock, store._conn() as conn:
        conn.execute(
            "UPDATE sales_orders SET work_order_id = ?, status = ? WHERE id = ?",
            (wo["id"], "in_production", so_id),
        )
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (so_id,)
        ).fetchone()
    out = _label(dict(row))
    out["work_order_no"] = wo["order_no"]
    return out


# ── 发货 ──────────────────────────────────────────────────────────────────
def ship(store, so_id: int) -> dict:
    """状态置 'shipped'（仅 in_production 可发货，否则 ValidationError）。"""
    with store._lock, store._conn() as conn:
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (so_id,)
        ).fetchone()
        if not row:
            raise NotFound(f"销售订单 {so_id} 不存在")
        if row["status"] != "in_production":
            raise ValidationError("仅生产中的订单可以发货")
        conn.execute(
            "UPDATE sales_orders SET status = 'shipped' WHERE id = ?", (so_id,)
        )
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (so_id,)
        ).fetchone()
    return _label(dict(row))


# ── 关闭 ──────────────────────────────────────────────────────────────────
def close_sales(store, so_id: int) -> dict:
    """状态置 'closed'。"""
    with store._lock, store._conn() as conn:
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (so_id,)
        ).fetchone()
        if not row:
            raise NotFound(f"销售订单 {so_id} 不存在")
        conn.execute(
            "UPDATE sales_orders SET status = 'closed' WHERE id = ?", (so_id,)
        )
        row = conn.execute(
            "SELECT * FROM sales_orders WHERE id = ?", (so_id,)
        ).fetchone()
    return _label(dict(row))


# ── 路由 ──────────────────────────────────────────────────────────────────
def routes(store):
    def get_list(req, p):
        status = req["query"].get("status", [None])[0]
        return 200, list_sales(store, status)

    return [
        ("GET",  r"/api/sales", get_list),
        ("POST", r"/api/sales",
         lambda req, p: (201, create_sales(store, req["body"]))),
        ("POST", r"/api/sales/(?P<id>\d+)/push",
         lambda req, p: (200, push_to_production(store, int(p["id"])))),
        ("POST", r"/api/sales/(?P<id>\d+)/ship",
         lambda req, p: (200, ship(store, int(p["id"])))),
        ("POST", r"/api/sales/(?P<id>\d+)/close",
         lambda req, p: (200, close_sales(store, int(p["id"])))),
    ]


# ── 演示数据 ────────────────────────────────────────────────────────────────
def seed(store) -> None:
    """幂等：sales_orders 为空且 products 有数据时，建 2 条订单，
    其中一条下推成工单作演示。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM sales_orders LIMIT 1").fetchone():
            return
        products = conn.execute(
            "SELECT id, name FROM products ORDER BY id ASC LIMIT 2"
        ).fetchall()
    if not products:
        return

    so1 = create_sales(store, {
        "customer": "华东机械有限公司",
        "product_id": products[0]["id"],
        "qty": 500,
        "due_date": "2026-07-10",
        "remark": "首批订单",
    })
    push_to_production(store, so1["id"])

    second = products[1] if len(products) > 1 else products[0]
    create_sales(store, {
        "customer": "南方精工厂",
        "product_id": second["id"],
        "qty": 200,
        "due_date": "2026-07-20",
        "remark": "等待排产",
    })
