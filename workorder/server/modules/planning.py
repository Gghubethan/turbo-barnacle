"""计划排产模块：生产排产甘特看板 + 把工单显式排到某条产线/日期/顺序。

- 看板（board）把未关闭工单按计划周期映射到时间轴；
- 排产条目（planning_entries）记录“工单 → 产线 / 日期 / 顺序”的显式排程。

业务逻辑写成普通函数，便于 pytest 直接调用。
"""

from __future__ import annotations

from datetime import date, timedelta

from server.store import (
    ValidationError,
    NotFound,
    _now,
    _require,
    STATUS,
    PRIORITY,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS planning_entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id  INTEGER NOT NULL REFERENCES work_orders(id),
    line           TEXT NOT NULL,
    plan_date      TEXT DEFAULT '',
    seq            INTEGER NOT NULL DEFAULT 0,
    remark         TEXT DEFAULT '',
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_wo ON planning_entries(work_order_id);
CREATE INDEX IF NOT EXISTS idx_plan_date ON planning_entries(plan_date);
"""


# ── 看板 ──────────────────────────────────────────────────────────────────
def _date_list(start_iso: str, days: int) -> list[str]:
    """从 start 起连续 days 天的日期字符串列表（'YYYY-MM-DD'）。"""
    base = date.fromisoformat(start_iso)
    return [(base + timedelta(days=i)).isoformat() for i in range(days)]


def _parse_start(start) -> str:
    """解析起始日期；缺省取“今天减 3 天”。非法输入回退到缺省。"""
    if start:
        try:
            return date.fromisoformat(str(start)[:10]).isoformat()
        except ValueError:
            pass
    return (date.today() - timedelta(days=3)).isoformat()


def board(store, start=None, days=14) -> dict:
    """排产看板数据。

    读取 status != 'closed' 的工单，输出起始日期、天数、日期列表与工单列表。
    每个工单附带展示用派生字段（中文标签、完成率等）。
    """
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 14
    if days <= 0:
        days = 14
    start_iso = _parse_start(start)
    dates = _date_list(start_iso, days)

    with store._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM work_orders WHERE status != 'closed' "
            "ORDER BY priority DESC, id ASC"
        ).fetchall()

    orders = []
    for r in rows:
        wo = dict(r)
        planned = wo.get("planned_qty") or 0
        completed = wo.get("completed_qty") or 0
        progress = round((completed / planned) * 100, 1) if planned else 0.0
        orders.append({
            "order_no": wo["order_no"],
            "work_order_id": wo["id"],
            "product_name": wo["product_name"],
            "status": wo["status"],
            "status_label": STATUS.get(wo["status"], wo["status"]),
            "priority": wo["priority"],
            "priority_label": PRIORITY.get(wo["priority"], wo["priority"]),
            "assignee": wo.get("assignee") or "",
            "workshop": wo.get("workshop") or "",
            "planned_start": (wo.get("planned_start") or "")[:10],
            "planned_end": (wo.get("planned_end") or "")[:10],
            "planned_qty": planned,
            "completed_qty": completed,
            "progress": progress,
        })

    return {"start": start_iso, "days": days, "dates": dates, "orders": orders}


# ── 排产条目 ────────────────────────────────────────────────────────────────
def list_entries(store) -> list[dict]:
    """列出排产条目，JOIN work_orders 带出 order_no、product_name。"""
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT pe.*, w.order_no, w.product_name "
            "FROM planning_entries pe "
            "JOIN work_orders w ON w.id = pe.work_order_id "
            "ORDER BY pe.plan_date ASC, pe.line ASC, pe.seq ASC, pe.id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_entry(store, data: dict) -> dict:
    """新建排产条目。必填 work_order_id（校验存在）、line；plan_date / seq 选填。"""
    wo_id = _require(data, "work_order_id", "工单")
    line = _require(data, "line", "产线")
    plan_date = str(data.get("plan_date", "")).strip()
    if plan_date:
        try:
            plan_date = date.fromisoformat(plan_date[:10]).isoformat()
        except ValueError:
            raise ValidationError("排产日期格式应为 YYYY-MM-DD")
    try:
        seq = int(data.get("seq", 0) or 0)
    except (TypeError, ValueError):
        raise ValidationError("顺序必须是整数")

    with store._lock, store._conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM work_orders WHERE id = ?", (wo_id,)
        ).fetchone():
            raise ValidationError("关联的工单不存在")
        cur = conn.execute(
            """INSERT INTO planning_entries
               (work_order_id, line, plan_date, seq, remark, created_at)
               VALUES (?,?,?,?,?,?)""",
            (wo_id, line, plan_date, seq,
             str(data.get("remark", "")).strip(), _now()),
        )
        row = conn.execute(
            "SELECT pe.*, w.order_no, w.product_name "
            "FROM planning_entries pe "
            "JOIN work_orders w ON w.id = pe.work_order_id "
            "WHERE pe.id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


def delete_entry(store, eid: int) -> dict:
    """删除排产条目，找不到抛 NotFound。"""
    with store._lock, store._conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM planning_entries WHERE id = ?", (eid,)
        ).fetchone()
        if not row:
            raise NotFound(f"排产条目 {eid} 不存在")
        conn.execute("DELETE FROM planning_entries WHERE id = ?", (eid,))
    return {"ok": True, "id": eid}


# ── 路由 ──────────────────────────────────────────────────────────────────
def routes(store):
    def get_board(req, p):
        q = req["query"]
        return 200, board(
            store,
            start=q.get("start", [None])[0],
            days=q.get("days", [14])[0] or 14,
        )

    return [
        ("GET", r"/api/planning/board", get_board),
        ("GET", r"/api/planning/entries",
         lambda req, p: (200, list_entries(store))),
        ("POST", r"/api/planning/entries",
         lambda req, p: (201, create_entry(store, req["body"]))),
        ("POST", r"/api/planning/entries/(?P<id>\d+)/delete",
         lambda req, p: (200, delete_entry(store, int(p["id"])))),
    ]


# ── 演示数据 ────────────────────────────────────────────────────────────────
def seed(store) -> None:
    """幂等：planning_entries 为空且存在非关闭工单时，给前两张各建一条排产。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM planning_entries LIMIT 1").fetchone():
            return
        wos = conn.execute(
            "SELECT id, workshop, planned_start FROM work_orders "
            "WHERE status != 'closed' ORDER BY id ASC LIMIT 2"
        ).fetchall()
    if not wos:
        return
    for wo in wos:
        create_entry(store, {
            "work_order_id": wo["id"],
            "line": (wo["workshop"] or "").strip() or "一号产线",
            "plan_date": (wo["planned_start"] or "")[:10],
        })
