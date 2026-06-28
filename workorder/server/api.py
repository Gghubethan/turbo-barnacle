"""HTTP 层：极简路由 + JSON REST + 静态资源服务（纯标准库 ``http.server``）。

路由表用 (方法, 正则) → 处理函数 的形式声明，处理函数统一返回
``(status_code, payload)``。业务异常自动翻译成 4xx。
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .store import Store, ValidationError, NotFound

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Router:
    """收集 (方法, 路径正则) → handler 的注册表。"""

    def __init__(self):
        self.routes: list[tuple[str, re.Pattern, callable]] = []

    def add(self, method: str, pattern: str, handler):
        self.routes.append((method, re.compile(f"^{pattern}$"), handler))

    def match(self, method: str, path: str):
        for m, pat, handler in self.routes:
            if m != method:
                continue
            mo = pat.match(path)
            if mo:
                return handler, mo.groupdict()
        return None, None


def build_router(store: Store) -> Router:
    r = Router()

    # 看板
    r.add("GET", r"/api/dashboard", lambda req, p: (200, store.dashboard_stats()))

    # 产品
    r.add("GET", r"/api/products", lambda req, p: (200, store.list_products()))
    r.add("POST", r"/api/products", lambda req, p: (201, store.create_product(req["body"])))

    # 工单
    def list_wo(req, p):
        q = req["query"]
        return 200, store.list_work_orders(
            status=q.get("status", [None])[0],
            keyword=q.get("keyword", [None])[0],
        )

    r.add("GET", r"/api/work-orders", list_wo)
    r.add("POST", r"/api/work-orders",
          lambda req, p: (201, store.create_work_order(req["body"])))
    r.add("GET", r"/api/work-orders/(?P<id>\d+)",
          lambda req, p: (200, store.get_work_order(int(p["id"]))))
    r.add("POST", r"/api/work-orders/(?P<id>\d+)/transition",
          lambda req, p: (200, store.transition(
              int(p["id"]), req["body"].get("action", ""), req["body"])))
    r.add("POST", r"/api/work-orders/(?P<id>\d+)/reports",
          lambda req, p: (201, store.report_production(int(p["id"]), req["body"])))
    r.add("GET", r"/api/work-orders/(?P<id>\d+)/reports",
          lambda req, p: (200, store.list_reports(int(p["id"]))))
    r.add("GET", r"/api/work-orders/(?P<id>\d+)/exceptions",
          lambda req, p: (200, store.list_exceptions(wo_id=int(p["id"]))))
    r.add("POST", r"/api/work-orders/(?P<id>\d+)/issue",
          lambda req, p: (201, store.issue_to_work_order(int(p["id"]), req["body"])))
    r.add("GET", r"/api/work-orders/(?P<id>\d+)/inventory",
          lambda req, p: (200, store.list_txns(work_order_id=int(p["id"]))))
    r.add("POST", r"/api/work-orders/(?P<id>\d+)/inspections",
          lambda req, p: (201, store.create_inspection(int(p["id"]), req["body"])))
    r.add("GET", r"/api/work-orders/(?P<id>\d+)/inspections",
          lambda req, p: (200, store.list_inspections(work_order_id=int(p["id"]))))

    # 员工 / 班组
    def list_staff(req, p):
        active = req["query"].get("active", [None])[0] == "1"
        return 200, store.list_staff(active_only=active)

    r.add("GET", r"/api/staff", list_staff)
    r.add("POST", r"/api/staff", lambda req, p: (201, store.create_staff(req["body"])))
    r.add("POST", r"/api/staff/(?P<id>\d+)/active",
          lambda req, p: (200, store.set_staff_active(int(p["id"]), bool(req["body"].get("active")))))

    # 物料 / 库存
    r.add("GET", r"/api/materials", lambda req, p: (200, store.list_materials()))
    r.add("POST", r"/api/materials", lambda req, p: (201, store.create_material(req["body"])))
    r.add("POST", r"/api/materials/(?P<id>\d+)/move",
          lambda req, p: (201, store.stock_move(
              int(p["id"]), req["body"].get("biz_type", ""), req["body"].get("qty"),
              operator=req["body"].get("operator", ""),
              remark=req["body"].get("remark", ""))))

    def list_txns(req, p):
        mid = req["query"].get("material_id", [None])[0]
        return 200, store.list_txns(material_id=int(mid) if mid else None)

    r.add("GET", r"/api/inventory-txns", list_txns)

    # 质检
    def list_insp(req, p):
        return 200, store.list_inspections()

    r.add("GET", r"/api/inspections", list_insp)

    # 异常
    def list_exc(req, p):
        q = req["query"]
        return 200, store.list_exceptions(status=q.get("status", [None])[0])

    r.add("GET", r"/api/exceptions", list_exc)
    r.add("POST", r"/api/exceptions",
          lambda req, p: (201, store.create_exception(req["body"])))
    r.add("POST", r"/api/exceptions/(?P<id>\d+)/resolve",
          lambda req, p: (200, store.resolve_exception(int(p["id"]), req["body"])))

    return r


def make_handler(store: Store):
    router = build_router(store)

    class Handler(BaseHTTPRequestHandler):
        server_version = "BlacklakeWO/1.0"

        # 静音默认日志，保留精简访问行
        def log_message(self, fmt, *args):
            print(f"[wo] {self.address_string()} {fmt % args}")

        def _send_json(self, status: int, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if not length:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise ValidationError("请求体不是合法 JSON")
            if not isinstance(data, dict):
                raise ValidationError("请求体必须是 JSON 对象")
            return data

        def _serve_static(self, path: str):
            if path == "/" or path == "":
                path = "/index.html"
            target = (WEB_DIR / path.lstrip("/")).resolve()
            # 目录穿越保护
            if not str(target).startswith(str(WEB_DIR)) or not target.is_file():
                self._send_json(404, {"error": "资源不存在"})
                return
            ctype = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, method: str):
            parsed = urlparse(self.path)
            path = parsed.path
            if not path.startswith("/api/"):
                if method == "GET":
                    self._serve_static(path)
                else:
                    self._send_json(404, {"error": "资源不存在"})
                return
            handler, params = router.match(method, path)
            if not handler:
                self._send_json(404, {"error": f"接口不存在：{method} {path}"})
                return
            try:
                body = self._read_body() if method in ("POST", "PUT", "PATCH") else {}
                req = {"body": body, "query": parse_qs(parsed.query)}
                status, payload = handler(req, params)
                self._send_json(status, payload)
            except ValidationError as e:
                self._send_json(400, {"error": str(e)})
            except NotFound as e:
                self._send_json(404, {"error": str(e)})
            except Exception as e:  # noqa: BLE001 —— 兜底，避免裸 500 断连
                self._send_json(500, {"error": f"服务器内部错误：{e}"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000,
          db_path: str = "workorder.db", seed: bool = True) -> None:
    store = Store(db_path)
    if seed:
        store.seed_demo()
    httpd = ThreadingHTTPServer((host, port), make_handler(store))
    print(f"黑湖工单系统已启动 →  http://{host}:{port}")
    print(f"数据库：{Path(db_path).resolve()}  （Ctrl+C 退出）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        httpd.server_close()
