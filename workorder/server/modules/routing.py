"""工序/工艺路线（routing）模块。

把工单拆成有序工序，按工序报工、跟踪每道工序的进度与状态。
- 表 ``wo_operations`` 记录工单下的工序（序号、工位、计划/完成数、操作工、状态）。
- 工序状态机：pending(待开工) → doing(进行中) → done(已完成)，由报工累计驱动。
"""

from server.store import ValidationError, NotFound, _now, _num, _require

# 工序状态：待开工 / 进行中 / 已完成
OP_STATUS = {"pending": "待开工", "doing": "进行中", "done": "已完成"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS wo_operations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id  INTEGER NOT NULL REFERENCES work_orders(id),
    seq            INTEGER NOT NULL DEFAULT 1,
    name           TEXT NOT NULL,
    workstation    TEXT DEFAULT '',
    planned_qty    REAL NOT NULL,
    completed_qty  REAL NOT NULL DEFAULT 0,
    worker         TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wo_op_wo ON wo_operations(work_order_id);
"""


def _label(op: dict) -> dict:
    """补充展示用派生字段：状态中文、进度百分比。"""
    planned = op.get("planned_qty") or 0
    op["status_label"] = OP_STATUS.get(op["status"], op["status"])
    op["progress"] = round((op["completed_qty"] / planned) * 100, 1) if planned else 0.0
    return op


def list_operations(store, wo_id: int) -> list[dict]:
    """返回某工单的工序，按 seq 升序，每条附带 status_label 与 progress。"""
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM wo_operations WHERE work_order_id = ? ORDER BY seq ASC, id ASC",
            (wo_id,),
        ).fetchall()
    return [_label(dict(r)) for r in rows]


def add_operation(store, wo_id: int, data: dict) -> dict:
    """给工单新增一道工序。"""
    name = _require(data, "name", "工序名")
    planned_qty = _num(data.get("planned_qty"), "计划数量", allow_zero=False)
    with store._lock, store._conn() as conn:
        if not conn.execute("SELECT 1 FROM work_orders WHERE id = ?", (wo_id,)).fetchone():
            raise NotFound(f"工单 {wo_id} 不存在")
        if data.get("seq") is not None and str(data.get("seq")).strip() != "":
            seq = int(_num(data.get("seq"), "工序号"))
        else:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM wo_operations WHERE work_order_id = ?",
                (wo_id,),
            ).fetchone()
            seq = int(row["m"]) + 1
        now = _now()
        cur = conn.execute(
            """INSERT INTO wo_operations
               (work_order_id, seq, name, workstation, planned_qty, completed_qty,
                worker, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (wo_id, seq, name, str(data.get("workstation", "")).strip(), planned_qty, 0,
             str(data.get("worker", "")).strip(), "pending", now, now),
        )
        row = conn.execute(
            "SELECT * FROM wo_operations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _label(dict(row))


def report_operation(store, op_id: int, data: dict) -> dict:
    """对某工序报工：累加完成数并推进状态。"""
    qty = _num(data.get("qty"), "报工数量", allow_zero=False)
    with store._lock, store._conn() as conn:
        row = conn.execute("SELECT * FROM wo_operations WHERE id = ?", (op_id,)).fetchone()
        if not row:
            raise NotFound(f"工序 {op_id} 不存在")
        op = dict(row)
        new_completed = op["completed_qty"] + qty
        if new_completed > op["planned_qty"]:
            raise ValidationError(
                f"报工数量超出计划：计划 {op['planned_qty']}，已完成 {op['completed_qty']}"
            )
        status = "doing" if op["status"] == "pending" else op["status"]
        if new_completed >= op["planned_qty"]:
            status = "done"
        worker = op["worker"]
        if data.get("worker") is not None and str(data.get("worker")).strip():
            worker = str(data.get("worker")).strip()
        conn.execute(
            "UPDATE wo_operations SET completed_qty = ?, status = ?, worker = ?, updated_at = ? WHERE id = ?",
            (new_completed, status, worker, _now(), op_id),
        )
        row = conn.execute("SELECT * FROM wo_operations WHERE id = ?", (op_id,)).fetchone()
    return _label(dict(row))


def delete_operation(store, op_id: int) -> dict:
    """删除一道工序。"""
    with store._lock, store._conn() as conn:
        if not conn.execute("SELECT 1 FROM wo_operations WHERE id = ?", (op_id,)).fetchone():
            raise NotFound(f"工序 {op_id} 不存在")
        conn.execute("DELETE FROM wo_operations WHERE id = ?", (op_id,))
    return {"ok": True, "id": op_id}


def routes(store):
    return [
        ("GET", r"/api/work-orders/(?P<id>\d+)/operations",
         lambda req, p: (200, list_operations(store, int(p["id"])))),
        ("POST", r"/api/work-orders/(?P<id>\d+)/operations",
         lambda req, p: (201, add_operation(store, int(p["id"]), req["body"]))),
        ("POST", r"/api/operations/(?P<id>\d+)/report",
         lambda req, p: (200, report_operation(store, int(p["id"]), req["body"]))),
        ("POST", r"/api/operations/(?P<id>\d+)/delete",
         lambda req, p: (200, delete_operation(store, int(p["id"])))),
    ]


def seed(store):
    """幂等：若工序表为空，为一张生产中工单添加 3 道工序并报工第一道。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM wo_operations LIMIT 1").fetchone():
            return
        wo = conn.execute(
            "SELECT id, planned_qty FROM work_orders WHERE status = 'producing' ORDER BY id LIMIT 1"
        ).fetchone()
    if not wo:
        return
    wo_id = wo["id"]
    qty = wo["planned_qty"]
    for name, ws in [("下料", "锯床01"), ("加工", "CNC03"), ("质检", "检测台")]:
        add_operation(store, wo_id, {
            "name": name, "workstation": ws, "planned_qty": qty,
        })
    ops = list_operations(store, wo_id)
    if ops:
        first = ops[0]
        report_operation(store, first["id"], {
            "qty": max(1, round(first["planned_qty"] * 0.4)), "worker": "李师傅",
        })
