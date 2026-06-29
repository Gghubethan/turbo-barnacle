"""登录与权限模块。

- 用户表 + 口令哈希（标准库 ``hashlib.pbkdf2_hmac`` + 随机盐），不存明文。
- 基于内存令牌的会话（重启失效，纯标准库无外部依赖）。
- 角色 → 可见标签的权限映射，前端据此控制菜单可见性。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading

from server.store import ValidationError, NotFound, _now, _require

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'operator',
    pw_salt     TEXT NOT NULL,
    pw_hash     TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
"""

ROLE = {
    "admin": "管理员",
    "planner": "计划员",
    "operator": "操作工",
    "inspector": "质检员",
    "viewer": "访客",
}

# 角色 → 可见标签 id（"*" 表示全部）。id 与前端标签 data-view 一致。
PERMISSIONS = {
    "admin": ["*"],
    "planner": ["dashboard", "sales", "bom", "planning", "orders",
                "purchasing", "inventory", "reports", "export", "products"],
    "operator": ["dashboard", "orders", "routing", "inventory"],
    "inspector": ["dashboard", "inspections", "orders", "exceptions"],
    "viewer": ["dashboard", "reports"],
}

_SESSIONS: dict[str, int] = {}   # token -> user_id（内存态）
_LOCK = threading.Lock()

_ITERATIONS = 100_000


def permissions_for(role: str) -> list[str]:
    return PERMISSIONS.get(role, ["dashboard"])


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), _ITERATIONS).hex()


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, _hash(password, salt)


def verify_password(password: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(_hash(password, salt), expected)


def _public(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "role_label": ROLE.get(row["role"], row["role"]),
        "active": bool(row["active"]),
        "permissions": permissions_for(row["role"]),
    }


def create_user(store, data: dict) -> dict:
    username = _require(data, "username", "用户名")
    name = _require(data, "name", "姓名")
    password = _require(data, "password", "密码")
    role = data.get("role", "operator")
    if role not in ROLE:
        raise ValidationError(f"未知角色：{role}")
    if len(password) < 4:
        raise ValidationError("密码至少 4 位")
    salt, pw = hash_password(password)
    with store._lock, store._conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise ValidationError(f"用户名 {username} 已存在")
        cur = conn.execute(
            """INSERT INTO users (username, name, role, pw_salt, pw_hash, active, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (username, name, role, salt, pw, 1, _now()),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _public(dict(row))


def list_users(store) -> list[dict]:
    with store._conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_public(dict(r)) for r in rows]


def set_active(store, uid: int, active: bool) -> dict:
    with store._lock, store._conn() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
            raise NotFound(f"用户 {uid} 不存在")
        conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, uid))
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _public(dict(row))


def login(store, data: dict) -> dict:
    username = _require(data, "username", "用户名")
    password = _require(data, "password", "密码")
    with store._conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not verify_password(password, row["pw_salt"], row["pw_hash"]):
        raise ValidationError("用户名或密码错误")
    if not row["active"]:
        raise ValidationError("账号已停用，请联系管理员")
    token = secrets.token_hex(24)
    with _LOCK:
        _SESSIONS[token] = row["id"]
    return {"token": token, "user": _public(dict(row))}


def session_user(store, token: str | None) -> dict | None:
    if not token:
        return None
    uid = _SESSIONS.get(token)
    if not uid:
        return None
    with store._conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row or not row["active"]:
        return None
    return _public(dict(row))


def logout(token: str | None) -> None:
    if token:
        with _LOCK:
            _SESSIONS.pop(token, None)


def _token(req) -> str | None:
    auth = req.get("headers")
    raw = auth.get("Authorization") if auth else None
    if raw and raw.startswith("Bearer "):
        return raw[7:].strip()
    return None


def routes(store):
    def do_login(req, p):
        return 200, login(store, req["body"])

    def do_logout(req, p):
        logout(_token(req))
        return 200, {"ok": True}

    def do_me(req, p):
        user = session_user(store, _token(req))
        if not user:
            return 401, {"error": "未登录或登录已过期"}
        return 200, user

    return [
        ("POST", r"/api/auth/login", do_login),
        ("POST", r"/api/auth/logout", do_logout),
        ("GET", r"/api/auth/me", do_me),
        ("GET", r"/api/auth/users", lambda req, p: (200, list_users(store))),
        ("POST", r"/api/auth/users", lambda req, p: (201, create_user(store, req["body"]))),
        ("POST", r"/api/auth/users/(?P<id>\d+)/active",
         lambda req, p: (200, set_active(store, int(p["id"]), bool(req["body"].get("active"))))),
    ]


def seed(store):
    """幂等：初始化默认账号（演示用，生产请尽快改密）。"""
    with store._conn() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
    defaults = [
        {"username": "admin", "name": "系统管理员", "role": "admin", "password": "admin123"},
        {"username": "planner", "name": "王计划", "role": "planner", "password": "plan123"},
        {"username": "operator", "name": "李操作", "role": "operator", "password": "op123"},
        {"username": "inspector", "name": "陈质检", "role": "inspector", "password": "insp123"},
    ]
    for u in defaults:
        create_user(store, u)
