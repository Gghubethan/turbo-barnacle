"""HTTP 层端到端测试：真实起一个服务器，走 JSON REST 验证关键路径与错误码。"""

import json
import sys
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.store import Store  # noqa: E402
from server.api import make_handler  # noqa: E402


@pytest.fixture
def base_url(tmp_path):
    store = Store(tmp_path / "http.db")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_static_index_served(base_url):
    with urllib.request.urlopen(base_url + "/") as resp:
        assert resp.status == 200
        assert "黑湖工单系统" in resp.read().decode()


def test_full_flow_over_http(base_url):
    status, prod = req(base_url + "/api/products", "POST",
                       {"code": "H-1", "name": "螺栓", "unit": "个"})
    assert status == 201

    status, wo = req(base_url + "/api/work-orders", "POST",
                     {"product_id": prod["id"], "planned_qty": 20, "priority": "high"})
    assert status == 201
    assert wo["status"] == "pending"
    wid = wo["id"]

    status, _ = req(f"{base_url}/api/work-orders/{wid}/transition", "POST",
                    {"action": "dispatch", "assignee": "张工"})
    assert status == 200
    req(f"{base_url}/api/work-orders/{wid}/transition", "POST", {"action": "start"})

    status, wo = req(f"{base_url}/api/work-orders/{wid}/reports", "POST",
                     {"reporter": "李师傅", "qty_ok": 20})
    assert status == 201
    assert wo["status"] == "completed"

    status, stats = req(base_url + "/api/dashboard")
    assert status == 200
    assert stats["total_orders"] == 1
    assert stats["completed_qty"] == 20


def test_validation_returns_400(base_url):
    status, body = req(base_url + "/api/products", "POST", {"name": "无编码"})
    assert status == 400
    assert "error" in body


def test_missing_order_returns_404(base_url):
    status, body = req(base_url + "/api/work-orders/9999")
    assert status == 404


def test_unknown_endpoint_404(base_url):
    status, _ = req(base_url + "/api/nope")
    assert status == 404
