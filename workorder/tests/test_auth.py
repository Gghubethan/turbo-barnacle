"""登录与权限模块测试：口令哈希、登录、会话、用户管理、权限映射。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store, ValidationError, NotFound  # noqa: E402
import server.modules.auth as mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "auth.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s


@pytest.fixture
def admin(store):
    return mod.create_user(store, {
        "username": "boss", "name": "老板", "role": "admin", "password": "secret1"})


# ── 口令哈希 ──────────────────────────────────────────────────────────────
def test_hash_roundtrip():
    salt, h = mod.hash_password("hunter2")
    assert mod.verify_password("hunter2", salt, h)
    assert not mod.verify_password("wrong", salt, h)


def test_hash_uses_random_salt():
    s1, h1 = mod.hash_password("same")
    s2, h2 = mod.hash_password("same")
    assert s1 != s2 and h1 != h2  # 加盐后同口令哈希也不同


def test_no_plaintext_password(store, admin):
    with store._conn() as c:
        row = dict(c.execute("SELECT * FROM users WHERE id=?", (admin["id"],)).fetchone())
    assert "secret1" not in row["pw_hash"]
    assert row.get("password") is None


# ── 用户管理 ──────────────────────────────────────────────────────────────
def test_create_user_public_has_no_hash(admin):
    assert "pw_hash" not in admin and "pw_salt" not in admin
    assert admin["role_label"] == "管理员"
    assert admin["permissions"] == ["*"]


def test_create_requires_fields(store):
    with pytest.raises(ValidationError):
        mod.create_user(store, {"username": "x", "name": "y"})  # 缺密码


def test_create_short_password(store):
    with pytest.raises(ValidationError):
        mod.create_user(store, {"username": "x", "name": "y", "password": "12"})


def test_create_unknown_role(store):
    with pytest.raises(ValidationError):
        mod.create_user(store, {"username": "x", "name": "y", "password": "1234", "role": "king"})


def test_duplicate_username(store, admin):
    with pytest.raises(ValidationError):
        mod.create_user(store, {"username": "boss", "name": "z", "password": "1234"})


# ── 登录 / 会话 ────────────────────────────────────────────────────────────
def test_login_success(store, admin):
    res = mod.login(store, {"username": "boss", "password": "secret1"})
    assert res["token"]
    assert res["user"]["username"] == "boss"


def test_login_wrong_password(store, admin):
    with pytest.raises(ValidationError):
        mod.login(store, {"username": "boss", "password": "nope"})


def test_login_unknown_user(store):
    with pytest.raises(ValidationError):
        mod.login(store, {"username": "ghost", "password": "whatever"})


def test_login_inactive_blocked(store, admin):
    mod.set_active(store, admin["id"], False)
    with pytest.raises(ValidationError):
        mod.login(store, {"username": "boss", "password": "secret1"})


def test_session_user_and_logout(store, admin):
    token = mod.login(store, {"username": "boss", "password": "secret1"})["token"]
    assert mod.session_user(store, token)["username"] == "boss"
    mod.logout(token)
    assert mod.session_user(store, token) is None


def test_session_user_invalid_token(store):
    assert mod.session_user(store, "garbage") is None
    assert mod.session_user(store, None) is None


def test_deactivated_session_invalidated(store, admin):
    token = mod.login(store, {"username": "boss", "password": "secret1"})["token"]
    mod.set_active(store, admin["id"], False)
    assert mod.session_user(store, token) is None  # 停用后旧会话失效


def test_set_active_missing(store):
    with pytest.raises(NotFound):
        mod.set_active(store, 999, False)


# ── 权限映射 ──────────────────────────────────────────────────────────────
def test_permissions_per_role():
    assert mod.permissions_for("admin") == ["*"]
    assert "inspections" in mod.permissions_for("inspector")
    assert "dashboard" in mod.permissions_for("operator")
    assert mod.permissions_for("unknown") == ["dashboard"]  # 兜底


def test_seed_idempotent(store):
    mod.seed(store)
    n1 = len(mod.list_users(store))
    mod.seed(store)
    assert len(mod.list_users(store)) == n1 == 4
