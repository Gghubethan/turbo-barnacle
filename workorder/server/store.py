"""数据访问 + 业务逻辑（工单状态机、报工、异常、看板统计）。

设计取舍：
- 用 SQLite 单文件库，零部署；每次操作开一个连接，配合 ``ThreadingHTTPServer`` 安全。
- 所有校验失败抛 :class:`ValidationError`，由 HTTP 层翻成 400，业务和传输解耦。
- 工单状态流转集中在 :data:`TRANSITIONS` 一张表里，便于审计与扩展。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional


# ── 工单状态 ──────────────────────────────────────────────────────────────
# 对齐黑湖工单的生命周期：待派工 → 已派工 → 生产中 →（暂停/恢复）→ 已完工 → 已关闭
STATUS = {
    "pending": "待派工",
    "dispatched": "已派工",
    "producing": "生产中",
    "paused": "已暂停",
    "completed": "已完工",
    "closed": "已关闭",
}

PRIORITY = {"low": "低", "normal": "普通", "high": "高", "urgent": "紧急"}

# 动作 → (允许的来源状态集合, 目标状态)。集中管理状态机，杜绝非法跳转。
TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "dispatch": ({"pending"}, "dispatched"),          # 派工
    "start": ({"dispatched", "paused"}, "producing"),  # 开工 / 恢复
    "pause": ({"producing"}, "paused"),                # 暂停
    "complete": ({"producing", "paused"}, "completed"),  # 完工
    "close": ({"completed"}, "closed"),                # 关闭
    "cancel": ({"pending", "dispatched", "paused"}, "closed"),  # 取消（未生产可直接关）
}

EXCEPTION_CATEGORY = {
    "equipment": "设备故障",
    "material": "物料缺料",
    "quality": "质量问题",
    "process": "工艺异常",
    "other": "其他",
}


class ValidationError(ValueError):
    """业务校验失败，HTTP 层应返回 400。"""


class NotFound(LookupError):
    """资源不存在，HTTP 层应返回 404。"""


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    spec        TEXT DEFAULT '',
    unit        TEXT DEFAULT '件',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no       TEXT NOT NULL UNIQUE,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    product_name   TEXT NOT NULL,
    planned_qty    REAL NOT NULL,
    completed_qty  REAL NOT NULL DEFAULT 0,
    defect_qty     REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'pending',
    priority       TEXT NOT NULL DEFAULT 'normal',
    assignee       TEXT DEFAULT '',
    workshop       TEXT DEFAULT '',
    planned_start  TEXT DEFAULT '',
    planned_end    TEXT DEFAULT '',
    actual_start   TEXT DEFAULT '',
    actual_end     TEXT DEFAULT '',
    remark         TEXT DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id  INTEGER NOT NULL REFERENCES work_orders(id),
    reporter       TEXT NOT NULL,
    qty_ok         REAL NOT NULL DEFAULT 0,
    qty_defect     REAL NOT NULL DEFAULT 0,
    remark         TEXT DEFAULT '',
    report_time    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exceptions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id  INTEGER NOT NULL REFERENCES work_orders(id),
    category       TEXT NOT NULL DEFAULT 'other',
    description    TEXT NOT NULL,
    reporter       TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'open',
    resolution     TEXT DEFAULT '',
    created_at     TEXT NOT NULL,
    resolved_at    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_report_wo ON reports(work_order_id);
CREATE INDEX IF NOT EXISTS idx_exc_wo ON exceptions(work_order_id);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _num(value: Any, field: str, *, allow_zero: bool = True) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 必须是数字")
    if n < 0:
        raise ValidationError(f"{field} 不能为负数")
    if not allow_zero and n == 0:
        raise ValidationError(f"{field} 必须大于 0")
    return n


def _require(data: dict, field: str, label: str) -> Any:
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError(f"{label}不能为空")
    return value.strip() if isinstance(value, str) else value


class Store:
    """工单系统数据仓库。线程安全：写操作走全局锁，连接按需创建。"""

    def __init__(self, db_path: str | Path = "workorder.db"):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self.init_schema()

    # ── 基础设施 ────────────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ── 产品 ────────────────────────────────────────────────────────────
    def list_products(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def create_product(self, data: dict) -> dict:
        code = _require(data, "code", "产品编码")
        name = _require(data, "name", "产品名称")
        with self._lock, self._conn() as conn:
            dup = conn.execute("SELECT 1 FROM products WHERE code = ?", (code,)).fetchone()
            if dup:
                raise ValidationError(f"产品编码 {code} 已存在")
            cur = conn.execute(
                "INSERT INTO products (code, name, spec, unit, created_at) VALUES (?,?,?,?,?)",
                (code, name, str(data.get("spec", "")).strip(),
                 str(data.get("unit", "件")).strip() or "件", _now()),
            )
            pid = cur.lastrowid
            row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        return dict(row)

    # ── 工单 ────────────────────────────────────────────────────────────
    def _gen_order_no(self, conn: sqlite3.Connection) -> str:
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"WO{today}"
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM work_orders WHERE order_no LIKE ?", (prefix + "%",)
        ).fetchone()
        return f"{prefix}-{row['c'] + 1:03d}"

    def list_work_orders(self, status: Optional[str] = None,
                         keyword: Optional[str] = None) -> list[dict]:
        sql = "SELECT * FROM work_orders WHERE 1=1"
        params: list[Any] = []
        if status and status != "all":
            if status not in STATUS:
                raise ValidationError(f"未知状态：{status}")
            sql += " AND status = ?"
            params.append(status)
        if keyword:
            sql += " AND (order_no LIKE ? OR product_name LIKE ? OR assignee LIKE ?)"
            like = f"%{keyword}%"
            params += [like, like, like]
        sql += " ORDER BY id DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._enrich(dict(r)) for r in rows]

    def get_work_order(self, wo_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
        if not row:
            raise NotFound(f"工单 {wo_id} 不存在")
        return self._enrich(dict(row))

    def _enrich(self, wo: dict) -> dict:
        """补充展示用派生字段：完成率、是否超期。"""
        planned = wo.get("planned_qty") or 0
        wo["progress"] = round((wo["completed_qty"] / planned) * 100, 1) if planned else 0.0
        wo["status_label"] = STATUS.get(wo["status"], wo["status"])
        wo["priority_label"] = PRIORITY.get(wo["priority"], wo["priority"])
        overdue = False
        if wo.get("planned_end") and wo["status"] not in ("completed", "closed"):
            try:
                overdue = wo["planned_end"][:10] < date.today().isoformat()
            except Exception:
                overdue = False
        wo["overdue"] = overdue
        return wo

    def create_work_order(self, data: dict) -> dict:
        product_id = _require(data, "product_id", "产品")
        planned_qty = _num(data.get("planned_qty"), "计划数量", allow_zero=False)
        priority = data.get("priority", "normal")
        if priority not in PRIORITY:
            raise ValidationError(f"未知优先级：{priority}")
        with self._lock, self._conn() as conn:
            product = conn.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if not product:
                raise ValidationError("所选产品不存在")
            order_no = self._gen_order_no(conn)
            now = _now()
            cur = conn.execute(
                """INSERT INTO work_orders
                   (order_no, product_id, product_name, planned_qty, priority,
                    assignee, workshop, planned_start, planned_end, remark,
                    status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_no, product_id, product["name"], planned_qty, priority,
                 str(data.get("assignee", "")).strip(),
                 str(data.get("workshop", "")).strip(),
                 str(data.get("planned_start", "")).strip(),
                 str(data.get("planned_end", "")).strip(),
                 str(data.get("remark", "")).strip(),
                 "pending", now, now),
            )
            wo_id = cur.lastrowid
            row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
        return self._enrich(dict(row))

    def transition(self, wo_id: int, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        if action not in TRANSITIONS:
            raise ValidationError(f"未知操作：{action}")
        allowed, target = TRANSITIONS[action]
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
            if not row:
                raise NotFound(f"工单 {wo_id} 不存在")
            wo = dict(row)
            if wo["status"] not in allowed:
                raise ValidationError(
                    f"当前状态「{STATUS[wo['status']]}」不允许执行该操作"
                )
            now = _now()
            updates: dict[str, Any] = {"status": target, "updated_at": now}
            if action == "dispatch":
                assignee = str(payload.get("assignee", wo["assignee"])).strip()
                if not assignee:
                    raise ValidationError("派工必须指定负责人")
                updates["assignee"] = assignee
            if action == "start" and not wo["actual_start"]:
                updates["actual_start"] = now
            if action == "complete":
                updates["actual_end"] = now
            self._apply(conn, wo_id, updates)
            row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
        return self._enrich(dict(row))

    @staticmethod
    def _apply(conn: sqlite3.Connection, wo_id: int, updates: dict) -> None:
        cols = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE work_orders SET {cols} WHERE id = ?",
                     (*updates.values(), wo_id))

    # ── 报工 ────────────────────────────────────────────────────────────
    def report_production(self, wo_id: int, data: dict) -> dict:
        reporter = _require(data, "reporter", "报工人")
        qty_ok = _num(data.get("qty_ok", 0), "合格数量")
        qty_defect = _num(data.get("qty_defect", 0), "不良数量")
        if qty_ok == 0 and qty_defect == 0:
            raise ValidationError("合格数量与不良数量不能同时为 0")
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
            if not row:
                raise NotFound(f"工单 {wo_id} 不存在")
            wo = dict(row)
            if wo["status"] not in ("producing", "paused"):
                raise ValidationError("仅生产中或暂停的工单可以报工")
            now = _now()
            conn.execute(
                """INSERT INTO reports
                   (work_order_id, reporter, qty_ok, qty_defect, remark, report_time)
                   VALUES (?,?,?,?,?,?)""",
                (wo_id, reporter, qty_ok, qty_defect,
                 str(data.get("remark", "")).strip(), now),
            )
            new_completed = wo["completed_qty"] + qty_ok
            new_defect = wo["defect_qty"] + qty_defect
            updates: dict[str, Any] = {
                "completed_qty": new_completed,
                "defect_qty": new_defect,
                "updated_at": now,
            }
            # 报到计划数自动完工
            if new_completed >= wo["planned_qty"] and wo["status"] != "completed":
                updates["status"] = "completed"
                updates["actual_end"] = now
            self._apply(conn, wo_id, updates)
            row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
        return self._enrich(dict(row))

    def list_reports(self, wo_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE work_order_id = ? ORDER BY id DESC", (wo_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 异常 ────────────────────────────────────────────────────────────
    def list_exceptions(self, status: Optional[str] = None,
                        wo_id: Optional[int] = None) -> list[dict]:
        sql = ("SELECT e.*, w.order_no FROM exceptions e "
               "JOIN work_orders w ON w.id = e.work_order_id WHERE 1=1")
        params: list[Any] = []
        if status in ("open", "resolved"):
            sql += " AND e.status = ?"
            params.append(status)
        if wo_id:
            sql += " AND e.work_order_id = ?"
            params.append(wo_id)
        sql += " ORDER BY e.id DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["category_label"] = EXCEPTION_CATEGORY.get(d["category"], d["category"])
            out.append(d)
        return out

    def create_exception(self, data: dict) -> dict:
        wo_id = _require(data, "work_order_id", "工单")
        description = _require(data, "description", "异常描述")
        category = data.get("category", "other")
        if category not in EXCEPTION_CATEGORY:
            raise ValidationError(f"未知异常类型：{category}")
        with self._lock, self._conn() as conn:
            if not conn.execute("SELECT 1 FROM work_orders WHERE id = ?", (wo_id,)).fetchone():
                raise ValidationError("关联的工单不存在")
            cur = conn.execute(
                """INSERT INTO exceptions
                   (work_order_id, category, description, reporter, status, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (wo_id, category, description,
                 str(data.get("reporter", "")).strip(), "open", _now()),
            )
            eid = cur.lastrowid
            row = conn.execute(
                "SELECT e.*, w.order_no FROM exceptions e "
                "JOIN work_orders w ON w.id = e.work_order_id WHERE e.id = ?", (eid,)
            ).fetchone()
        d = dict(row)
        d["category_label"] = EXCEPTION_CATEGORY.get(d["category"], d["category"])
        return d

    def resolve_exception(self, eid: int, data: dict) -> dict:
        resolution = _require(data, "resolution", "处理结果")
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM exceptions WHERE id = ?", (eid,)).fetchone()
            if not row:
                raise NotFound(f"异常 {eid} 不存在")
            if row["status"] == "resolved":
                raise ValidationError("该异常已处理")
            conn.execute(
                "UPDATE exceptions SET status='resolved', resolution=?, resolved_at=? WHERE id=?",
                (resolution, _now(), eid),
            )
            row = conn.execute(
                "SELECT e.*, w.order_no FROM exceptions e "
                "JOIN work_orders w ON w.id = e.work_order_id WHERE e.id = ?", (eid,)
            ).fetchone()
        d = dict(row)
        d["category_label"] = EXCEPTION_CATEGORY.get(d["category"], d["category"])
        return d

    # ── 看板统计 ──────────────────────────────────────────────────────────
    def dashboard_stats(self) -> dict:
        with self._conn() as conn:
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS c FROM work_orders GROUP BY status"
            ).fetchall()
            totals = conn.execute(
                "SELECT COUNT(*) AS orders, "
                "COALESCE(SUM(planned_qty),0) AS planned, "
                "COALESCE(SUM(completed_qty),0) AS completed, "
                "COALESCE(SUM(defect_qty),0) AS defect FROM work_orders"
            ).fetchone()
            open_exc = conn.execute(
                "SELECT COUNT(*) AS c FROM exceptions WHERE status='open'"
            ).fetchone()["c"]
            today = date.today().isoformat()
            today_ok = conn.execute(
                "SELECT COALESCE(SUM(qty_ok),0) AS c FROM reports WHERE report_time LIKE ?",
                (today + "%",),
            ).fetchone()["c"]
            overdue = conn.execute(
                "SELECT COUNT(*) AS c FROM work_orders "
                "WHERE planned_end != '' AND substr(planned_end,1,10) < ? "
                "AND status NOT IN ('completed','closed')",
                (today,),
            ).fetchone()["c"]

        by_status = {k: 0 for k in STATUS}
        for r in status_rows:
            by_status[r["status"]] = r["c"]

        planned = totals["planned"] or 0
        completed = totals["completed"] or 0
        defect = totals["defect"] or 0
        produced = completed + defect
        return {
            "by_status": by_status,
            "status_labels": STATUS,
            "total_orders": totals["orders"],
            "planned_qty": planned,
            "completed_qty": completed,
            "defect_qty": defect,
            "completion_rate": round((completed / planned) * 100, 1) if planned else 0.0,
            "defect_rate": round((defect / produced) * 100, 1) if produced else 0.0,
            "open_exceptions": open_exc,
            "today_completed": today_ok,
            "overdue_orders": overdue,
        }

    # ── 演示数据 ──────────────────────────────────────────────────────────
    def seed_demo(self) -> None:
        """灌入一批演示数据（仅当库为空时）。"""
        with self._conn() as conn:
            if conn.execute("SELECT 1 FROM products LIMIT 1").fetchone():
                return
        demo_products = [
            {"code": "P-1001", "name": "精密轴承 6204", "spec": "内径20mm", "unit": "个"},
            {"code": "P-1002", "name": "不锈钢法兰盘", "spec": "DN50", "unit": "片"},
            {"code": "P-1003", "name": "铝合金外壳", "spec": "120×80×40", "unit": "件"},
        ]
        pids = [self.create_product(p)["id"] for p in demo_products]

        wo1 = self.create_work_order({
            "product_id": pids[0], "planned_qty": 1000, "priority": "high",
            "assignee": "张工", "workshop": "一号车间",
            "planned_start": "2026-06-25", "planned_end": "2026-06-30",
            "remark": "客户加急订单",
        })
        self.transition(wo1["id"], "dispatch", {"assignee": "张工"})
        self.transition(wo1["id"], "start")
        self.report_production(wo1["id"], {"reporter": "李师傅", "qty_ok": 420, "qty_defect": 8})

        wo2 = self.create_work_order({
            "product_id": pids[1], "planned_qty": 300, "priority": "normal",
            "assignee": "王工", "workshop": "二号车间",
            "planned_start": "2026-06-20", "planned_end": "2026-06-26",
        })
        self.transition(wo2["id"], "dispatch", {"assignee": "王工"})
        self.transition(wo2["id"], "start")
        self.report_production(wo2["id"], {"reporter": "赵师傅", "qty_ok": 180, "qty_defect": 5})
        self.create_exception({
            "work_order_id": wo2["id"], "category": "material",
            "description": "不锈钢原料批次到货延迟，预计影响 1 天", "reporter": "王工",
        })

        self.create_work_order({
            "product_id": pids[2], "planned_qty": 500, "priority": "urgent",
            "workshop": "三号车间",
            "planned_start": "2026-06-29", "planned_end": "2026-07-05",
            "remark": "等待排产",
        })
