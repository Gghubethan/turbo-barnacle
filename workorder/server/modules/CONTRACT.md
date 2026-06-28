# 功能模块开发契约

本系统（黑湖工单系统，纯 Python 标准库 + 原生前端，**零第三方依赖**）支持插件式功能模块。
新增一个模块只需创建 **3 个文件**，且**严禁修改任何其它已存在文件**：

1. `server/modules/<NAME>.py` —— 后端：建表 + 路由 + 可选种子
2. `web/modules/<NAME>.js` —— 前端：注册一个标签页
3. `tests/test_<NAME>.py` —— pytest 测试

加载是约定式的：`server/api.py` 会自动 import `server/modules/*.py` 并应用其 `SCHEMA`、挂载其
`routes()`；前端 `app.js` 会请求 `/api/modules` 拿到 `web/modules/*.js` 列表并动态加载，每个脚本
通过 `WO.registerModule(...)` 注册自己。**无需改动任何中心化注册表。**

---

## 后端契约 `server/modules/<NAME>.py`

```python
from server.store import ValidationError, NotFound, _now, _num, _require

SCHEMA = """
CREATE TABLE IF NOT EXISTS <name>_xxx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ...
    created_at TEXT NOT NULL
);
"""   # 表名带模块前缀，避免与其它模块冲突

def create_xxx(store, data):          # 业务逻辑写成普通函数，便于测试直接调用
    name = _require(data, "name", "名称")
    with store._conn() as conn:        # with 退出自动提交；row_factory=Row
        cur = conn.execute("INSERT ...", (...))
        row = conn.execute("SELECT * FROM <name>_xxx WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)

def routes(store):                     # 返回 (方法, 路径正则, 处理函数)
    return [
        ("GET",  r"/api/<name>",            lambda req, p: (200, list_xxx(store))),
        ("POST", r"/api/<name>",            lambda req, p: (201, create_xxx(store, req["body"]))),
        ("POST", r"/api/<name>/(?P<id>\d+)/action",
                                            lambda req, p: (200, do_action(store, int(p["id"]), req["body"]))),
    ]

def seed(store):                       # 可选，幂等：先判断是否已有数据再插
    ...
```

约定：
- **方法**只用 `"GET"` / `"POST"`。
- **路径**以 `/api/<NAME>` 命名空间开头（模块规格里若需挂到工单子路径会特别说明）；路径参数用命名组，
  如 `(?P<id>\d+)`，`params["id"]` 是字符串需 `int()`。
- **handler** 签名 `handler(req, params) -> (status_code, payload)`。`req["body"]` 是 dict（POST JSON），
  `req["query"]` 是 `parse_qs` 结果（`dict[str, list]`，取值用 `req["query"].get("k", [None])[0]`）。
  payload 是 dict 或 list。
- 校验失败抛 `ValidationError`（→400）；找不到资源抛 `NotFound`（→404）。
- 枚举字段在返回里附带中文 `*_label`，与现有模块风格一致。

辅助函数（从 `server.store` 导入）：
- `_now() -> str`：当前时间 `"YYYY-MM-DD HH:MM:SS"`。
- `_num(value, field, allow_zero=True) -> float`：数字校验，负数/非数字抛 `ValidationError`。
- `_require(data, field, label) -> value`：必填校验，空值抛 `"<label>不能为空"`。
- `store._conn()`：sqlite3 连接（`row_factory=Row`、外键开启）。

---

## 前端契约 `web/modules/<NAME>.js`

```js
WO.registerModule({
  id: "<name>",            // 与后端命名空间一致的英文 id
  label: "中文标签",
  async refresh(container) {           // 每次切到本标签时调用，把界面渲染进 container(<section>)
    const rows = await WO.api("/<name>");
    container.innerHTML = `
      <div class="toolbar"><span class="grow"></span>
        <button class="btn" id="x-new">+ 新建</button></div>
      <div class="card"><table><thead><tr><th>名称</th></tr></thead>
        <tbody>${rows.map(r => `<tr><td>${WO.esc(r.name)}</td></tr>`).join("")}</tbody></table>
        ${rows.length ? "" : '<div class="empty">暂无数据</div>'}</div>`;
    container.querySelector("#x-new").addEventListener("click", () => {
      WO.openModal("新建", `<label class="field"><span class="req">名称</span><input id="f-name"/></label>`,
        async () => {
          await WO.api("/<name>", { method: "POST", body: { name: container.ownerDocument.getElementById("f-name").value.trim() } });
          WO.toast("已创建"); this.refresh(container);
        });
    });
  },
});
```

`WO` 提供的工具（**不要**自己写 fetch / 弹窗）：
- `WO.api(path, opts)`：fetch 封装，自动加 `/api` 前缀与 JSON 头；`opts.body` 传对象自动 `JSON.stringify`；
  非 2xx 抛中文 `Error`。返回解析后的 JSON。
- `WO.toast(msg, isErr=false)`、`WO.esc(s)`、`WO.fmt(n)`。
- `WO.openModal(title, bodyHtml, async onSubmit)`：表单弹窗；onSubmit 抛错会 toast 并保持打开。
- `WO.$ / WO.$$`：querySelector / querySelectorAll 简写（在 document 上）。模块内优先用 `container.querySelector`。

可复用的 CSS 类（已在 `styles.css` 定义，务必复用以保持风格统一）：
- 布局：`card`、`toolbar`、`grow`、`section-title`(内含 h2)、`empty`、`stats`(4 列网格)、
  `stat`(含 `.label`/`.value`，修饰 `.accent/.ok/.warn/.danger`)。
- 表格：列可加 `class="num"`(右对齐数字) 或 `hide-sm`(窄屏隐藏)；`tbody tr:hover` 已有高亮。
- 按钮：`btn`、`btn ghost`、`btn subtle`、`btn sm`。
- 徽章：`badge` + 状态色 `s-producing/s-pending/s-paused/s-completed/s-closed/p-urgent/p-high/p-normal`。
- 进度条：`<div class="bar"><span style="width:60%"></span></div>`。
- 详情：`kv`(dl 两列)、`sub-card`(含 h4)、`timeline-item`(含 `.meta`)。
- 颜色变量：`var(--brand)` #1857c4、`var(--accent)` #00b1a4、`var(--ok)`、`var(--warn)`、
  `var(--danger)`、`var(--muted)`、`var(--line)`。

**禁止**引入任何外部 CDN / 库（系统须离线可用）。图表用纯 CSS / 内联 SVG / div 实现。

---

## 测试 `tests/test_<NAME>.py`

```python
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.store import Store, ValidationError, NotFound
import server.modules.<NAME> as mod

@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    with s._conn() as c:
        c.executescript(mod.SCHEMA)
    return s
```

- `Store()` 已建好核心表，可直接 `store.create_product(...)`、`store.create_work_order(...)`、
  `store.transition(...)`、`store.report_production(...)` 准备前置数据。
- 直接调用你的服务函数，覆盖正常路径 + 异常分支（校验失败、找不到资源等），**至少 8 个用例**。
- **只运行自己的测试**（其它模块可能正被同时编写）：
  `cd /home/user/turbo-barnacle/workorder && python3 -m pytest tests/test_<NAME>.py -q`

---

## 现有核心表（只读可用）

- `work_orders(id, order_no, product_id, product_name, planned_qty, completed_qty, defect_qty,
  status, priority, assignee, workshop, planned_start, planned_end, actual_start, actual_end,
  remark, created_at, updated_at)` —— status ∈ pending/dispatched/producing/paused/completed/closed。
- `reports(id, work_order_id, reporter, qty_ok, qty_defect, remark, report_time)`
- `inspections(id, work_order_id, inspector, qty_inspected, qty_qualified, qty_defective, result,
  defect_reason, remark, created_at)`
- `inventory_txns(id, material_id, material_name, kind('in'/'out'), biz_type, qty, balance_after,
  work_order_id, operator, remark, created_at)`
- `products(id, code, name, spec, unit, created_at)`
- `materials(id, code, name, spec, unit, category, stock, safety_stock, created_at)`
- `staff(id, name, role, team, active, created_at)`
