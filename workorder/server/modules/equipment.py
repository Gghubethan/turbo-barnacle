"""设备管理模块：设备台账 + 点检/保养/维修记录，跟踪设备状态。

约定式插件：``server.api`` 自动应用 :data:`SCHEMA`、挂载 :func:`routes`、调用 :func:`seed`。
业务校验失败抛 :class:`ValidationError`（→400），资源不存在抛 :class:`NotFound`（→404）。
"""

from server.store import ValidationError, NotFound, _now, _num, _require

# 设备状态：运行中 / 闲置 / 保养中 / 故障
EQUIPMENT_STATUS = {
    "running": "运行中",
    "idle": "闲置",
    "maintenance": "保养中",
    "fault": "故障",
}

# 维护记录类型：点检 / 保养 / 维修
LOG_TYPE = {
    "inspect": "点检",
    "maintain": "保养",
    "repair": "维修",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    model       TEXT DEFAULT '',
    location    TEXT DEFAULT '',
    owner       TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id  INTEGER NOT NULL REFERENCES equipment(id),
    type          TEXT NOT NULL,
    content       TEXT NOT NULL,
    operator      TEXT DEFAULT '',
    cost          REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eqlog_eq ON equipment_logs(equipment_id);
"""


def _equip_label(d: dict) -> dict:
    d["status_label"] = EQUIPMENT_STATUS.get(d["status"], d["status"])
    return d


def _log_label(d: dict) -> dict:
    d["type_label"] = LOG_TYPE.get(d["type"], d["type"])
    return d


def list_equipment(store) -> list[dict]:
    with store._conn() as conn:
        rows = conn.execute("SELECT * FROM equipment ORDER BY id DESC").fetchall()
    return [_equip_label(dict(r)) for r in rows]


def create_equipment(store, data: dict) -> dict:
    code = _require(data, "code", "设备编码")
    name = _require(data, "name", "设备名称")
    status = data.get("status", "running") or "running"
    if status not in EQUIPMENT_STATUS:
        raise ValidationError(f"未知设备状态：{status}")
    with store._lock, store._conn() as conn:
        if conn.execute("SELECT 1 FROM equipment WHERE code = ?", (code,)).fetchone():
            raise ValidationError(f"设备编码 {code} 已存在")
        cur = conn.execute(
            """INSERT INTO equipment (code, name, model, location, owner, status, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (code, name, str(data.get("model", "")).strip(),
             str(data.get("location", "")).strip(),
             str(data.get("owner", "")).strip(), status, _now()),
        )
        row = conn.execute("SELECT * FROM equipment WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _equip_label(dict(row))


def set_status(store, eid: int, status: str) -> dict:
    if status not in EQUIPMENT_STATUS:
        raise ValidationError(f"未知设备状态：{status}")
    with store._lock, store._conn() as conn:
        if not conn.execute("SELECT 1 FROM equipment WHERE id = ?", (eid,)).fetchone():
            raise NotFound(f"设备 {eid} 不存在")
        conn.execute("UPDATE equipment SET status = ? WHERE id = ?", (status, eid))
        row = conn.execute("SELECT * FROM equipment WHERE id = ?", (eid,)).fetchone()
    return _equip_label(dict(row))


def list_logs(store, equipment_id=None) -> list[dict]:
    sql = ("SELECT l.*, e.name AS equipment_name FROM equipment_logs l "
           "JOIN equipment e ON e.id = l.equipment_id WHERE 1=1")
    params: list = []
    if equipment_id:
        sql += " AND l.equipment_id = ?"
        params.append(equipment_id)
    sql += " ORDER BY l.id DESC"
    with store._conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_log_label(dict(r)) for r in rows]


def add_log(store, eid: int, data: dict) -> dict:
    log_type = _require(data, "type", "记录类型")
    if log_type not in LOG_TYPE:
        raise ValidationError(f"未知记录类型：{log_type}")
    content = _require(data, "content", "记录内容")
    cost = _num(data.get("cost", 0), "费用")
    with store._lock, store._conn() as conn:
        if not conn.execute("SELECT 1 FROM equipment WHERE id = ?", (eid,)).fetchone():
            raise NotFound(f"设备 {eid} 不存在")
        now = _now()
        cur = conn.execute(
            """INSERT INTO equipment_logs
               (equipment_id, type, content, operator, cost, created_at)
               VALUES (?,?,?,?,?,?)""",
            (eid, log_type, content, str(data.get("operator", "")).strip(), cost, now),
        )
        # 维修时把设备置为保养中，完成后用户可再手动改回
        if log_type == "repair":
            conn.execute("UPDATE equipment SET status = 'maintenance' WHERE id = ?", (eid,))
        row = conn.execute(
            "SELECT l.*, e.name AS equipment_name FROM equipment_logs l "
            "JOIN equipment e ON e.id = l.equipment_id WHERE l.id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return _log_label(dict(row))


def routes(store):
    return [
        ("GET",  r"/api/equipment",
         lambda req, p: (200, list_equipment(store))),
        ("POST", r"/api/equipment",
         lambda req, p: (201, create_equipment(store, req["body"]))),
        ("POST", r"/api/equipment/(?P<id>\d+)/status",
         lambda req, p: (200, set_status(store, int(p["id"]), req["body"].get("status", "")))),
        ("GET",  r"/api/equipment/(?P<id>\d+)/logs",
         lambda req, p: (200, list_logs(store, equipment_id=int(p["id"])))),
        ("POST", r"/api/equipment/(?P<id>\d+)/logs",
         lambda req, p: (201, add_log(store, int(p["id"]), req["body"]))),
        ("GET",  r"/api/equipment-logs",
         lambda req, p: (200, list_logs(store))),
    ]


def seed(store):
    """幂等：仅当 equipment 为空时灌入演示设备与一条点检记录。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM equipment LIMIT 1").fetchone():
            return
    e1 = create_equipment(store, {
        "code": "CNC-01", "name": "数控车床", "model": "CK6140",
        "location": "一号车间", "owner": "张工", "status": "running"})
    create_equipment(store, {
        "code": "INJ-02", "name": "注塑机", "model": "HTF160",
        "location": "二号车间", "owner": "王工", "status": "idle"})
    create_equipment(store, {
        "code": "WELD-03", "name": "焊接机器人", "model": "AR-1440",
        "location": "三号车间", "owner": "赵工", "status": "fault"})
    add_log(store, e1["id"], {
        "type": "inspect", "content": "日常点检：油位正常，导轨润滑良好",
        "operator": "李师傅"})
