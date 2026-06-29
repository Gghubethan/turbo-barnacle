"use strict";
/*
 * 浏览器内 Mock 后端（核心）。
 * 当系统部署为纯静态站点（无 Python 后端）时启用：拦截 fetch("/api/...")，
 * 用 localStorage 充当数据库，在浏览器里复刻后端逻辑，让整套 SPA 离线可玩。
 *
 * 真实后端存在时不激活（app.js 启动探测 /api/modules，命中 JSON 即走真实后端）。
 *
 * 模块化：core 提供 DB / 路由注册 / 错误助手 / 标签字典 / 种子编排；
 * 其余模块在 web/mock/<name>.js 里调用 window.Mock.register / Mock.onSeed 接入。
 */
(function () {
  const LS_KEY = "wo_mock_db_v2";

  // ── 标签字典（与后端 store.py 对齐）─────────────────────────────
  const STATUS = { pending: "待派工", dispatched: "已派工", producing: "生产中", paused: "已暂停", completed: "已完工", closed: "已关闭" };
  const PRIORITY = { low: "低", normal: "普通", high: "高", urgent: "紧急" };
  const TRANSITIONS = {
    dispatch: [["pending"], "dispatched"], start: [["dispatched", "paused"], "producing"],
    pause: [["producing"], "paused"], complete: [["producing", "paused"], "completed"],
    close: [["completed"], "closed"], cancel: [["pending", "dispatched", "paused"], "closed"],
  };
  const EXC = { equipment: "设备故障", material: "物料缺料", quality: "质量问题", process: "工艺异常", other: "其他" };
  const STAFF_ROLE = { operator: "操作工", inspector: "质检员", leader: "班组长", planner: "计划员", manager: "管理员" };
  const MAT_CAT = { raw: "原料", semi: "半成品", finished: "成品" };
  const TXN_IN = { purchase: "采购入库", produce_in: "完工入库", return: "退料入库", adjust_in: "盘盈入库" };
  const TXN_OUT = { issue: "生产领料", scrap: "报废出库", adjust_out: "盘亏出库" };
  const TXN = Object.assign({}, TXN_IN, TXN_OUT);
  const INSPECT = { pass: "合格", concession: "让步接收", reject: "拒收" };
  const ROLE = { admin: "管理员", planner: "计划员", operator: "操作工", inspector: "质检员", viewer: "访客" };
  const PERMISSIONS = {
    admin: ["*"],
    planner: ["dashboard", "sales", "bom", "planning", "orders", "purchasing", "inventory", "reports", "export", "products"],
    operator: ["dashboard", "orders", "routing", "inventory"],
    inspector: ["dashboard", "inspections", "orders", "exceptions"],
    viewer: ["dashboard", "reports"],
  };
  // 与 web/modules/*.js 文件名一致（静态部署下供 loadPlugins 注入）
  const MODULE_FILES = ["bom.js", "equipment.js", "export.js", "planning.js", "purchasing.js", "reports.js", "routing.js", "sales.js"];

  // ── 错误助手 ───────────────────────────────────────────────────
  function bad(m) { throw Object.assign(new Error(m), { status: 400 }); }
  function notfound(m) { throw Object.assign(new Error(m), { status: 404 }); }
  function num(v, field, allowZero = true) {
    const n = Number(v);
    if (v === null || v === undefined || v === "" || Number.isNaN(n)) bad(field + " 必须是数字");
    if (n < 0) bad(field + " 不能为负数");
    if (!allowZero && n === 0) bad(field + " 必须大于 0");
    return n;
  }
  function require_(data, field, label) {
    const v = data[field];
    if (v === null || v === undefined || (typeof v === "string" && !v.trim())) bad(label + "不能为空");
    return typeof v === "string" ? v.trim() : v;
  }

  // ── 时间 ───────────────────────────────────────────────────────
  function pad(n) { return String(n).padStart(2, "0"); }
  function now() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  function today() { return now().slice(0, 10); }
  function ymd() { const d = new Date(); return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`; }

  // ── DB ─────────────────────────────────────────────────────────
  let DB = null;
  function load() { try { const j = localStorage.getItem(LS_KEY); if (j) return JSON.parse(j); } catch (e) {} return null; }
  function save() { localStorage.setItem(LS_KEY, JSON.stringify(DB)); }
  function table(name) { if (!DB[name]) DB[name] = []; return DB[name]; }
  function nextId(name) { DB.seq[name] = (DB.seq[name] || 0) + 1; return DB.seq[name]; }
  function insert(name, row) { row.id = nextId(name); table(name).push(row); return row; }
  function byId(name, id) { return table(name).find((r) => r.id === Number(id)); }

  // ── 路由 ───────────────────────────────────────────────────────
  const routes = [];
  const seeders = [];
  window.Mock = {
    labels: { STATUS, PRIORITY, EXC, STAFF_ROLE, MAT_CAT, TXN_IN, TXN_OUT, TXN, INSPECT, ROLE, PERMISSIONS },
    bad, notfound, num, require: require_, now, today, ymd,
    db: { table, nextId, insert, byId, save, get: () => DB },
    register(method, pattern, handler) { routes.push({ method, re: new RegExp("^" + pattern + "$"), handler }); },
    onSeed(fn) { seeders.push(fn); },
    activate, // 由 app.js 在静态模式下调用
    // 供其它模块 mock 复用的核心业务操作（跨模块联动用）
    core: {
      createWorkOrder: (data) => createWO(data),
      stockMove: (material_id, biz_type, qty, opts) => stockMove(material_id, biz_type, qty, opts),
      enrichWO,
    },
  };

  // ── 业务派生字段 ───────────────────────────────────────────────
  function enrichWO(w) {
    const planned = w.planned_qty || 0;
    w.progress = planned ? Math.round((w.completed_qty / planned) * 1000) / 10 : 0;
    w.status_label = STATUS[w.status] || w.status;
    w.priority_label = PRIORITY[w.priority] || w.priority;
    let overdue = false;
    if (w.planned_end && w.status !== "completed" && w.status !== "closed") overdue = w.planned_end.slice(0, 10) < today();
    w.overdue = overdue;
    return Object.assign({}, w);
  }
  function enrichMat(m) {
    const x = Object.assign({}, m);
    x.category_label = MAT_CAT[m.category] || m.category;
    x.low_stock = m.safety_stock > 0 && m.stock < m.safety_stock;
    return x;
  }
  function enrichInsp(i) {
    const x = Object.assign({}, i);
    x.result_label = INSPECT[i.result] || i.result;
    x.pass_rate = i.qty_inspected ? Math.round((i.qty_qualified / i.qty_inspected) * 1000) / 10 : 0;
    return x;
  }

  // ── 核心路由：产品 ─────────────────────────────────────────────
  Mock.register("GET", "/api/products", () => ({ body: table("products").slice().reverse() }));
  Mock.register("POST", "/api/products", (ctx) => {
    const code = require_(ctx.body, "code", "产品编码");
    const name = require_(ctx.body, "name", "产品名称");
    if (table("products").some((p) => p.code === code)) bad(`产品编码 ${code} 已存在`);
    const row = insert("products", { code, name, spec: (ctx.body.spec || "").trim ? (ctx.body.spec || "").trim() : (ctx.body.spec || ""), unit: (ctx.body.unit || "件").trim() || "件", created_at: now() });
    save();
    return { status: 201, body: row };
  });

  // ── 核心路由：工单 ─────────────────────────────────────────────
  function genOrderNo() {
    const prefix = "WO" + ymd();
    const c = table("work_orders").filter((w) => (w.order_no || "").startsWith(prefix)).length;
    return `${prefix}-${String(c + 1).padStart(3, "0")}`;
  }
  Mock.register("GET", "/api/work-orders", (ctx) => {
    let rows = table("work_orders").slice();
    const status = ctx.query.status, kw = ctx.query.keyword;
    if (status && status !== "all") rows = rows.filter((w) => w.status === status);
    if (kw) rows = rows.filter((w) => (w.order_no + w.product_name + (w.assignee || "")).includes(kw));
    rows.sort((a, b) => b.id - a.id);
    return { body: rows.map(enrichWO) };
  });
  Mock.register("POST", "/api/work-orders", (ctx) => ({ status: 201, body: createWO(ctx.body) }));
  Mock.register("GET", "/api/work-orders/(?<id>\\d+)", (ctx) => {
    const w = byId("work_orders", ctx.params.id); if (!w) notfound("工单不存在"); return { body: enrichWO(w) };
  });
  Mock.register("POST", "/api/work-orders/(?<id>\\d+)/transition", (ctx) => ({ body: transition(ctx.params.id, ctx.body.action, ctx.body) }));
  Mock.register("POST", "/api/work-orders/(?<id>\\d+)/reports", (ctx) => ({ status: 201, body: report(ctx.params.id, ctx.body) }));
  Mock.register("GET", "/api/work-orders/(?<id>\\d+)/reports", (ctx) =>
    ({ body: table("reports").filter((r) => r.work_order_id === Number(ctx.params.id)).slice().reverse() }));
  Mock.register("GET", "/api/work-orders/(?<id>\\d+)/exceptions", (ctx) =>
    ({ body: listExc({ wo_id: Number(ctx.params.id) }) }));
  Mock.register("POST", "/api/work-orders/(?<id>\\d+)/issue", (ctx) => ({ status: 201, body: issueToWO(ctx.params.id, ctx.body) }));
  Mock.register("GET", "/api/work-orders/(?<id>\\d+)/inventory", (ctx) =>
    ({ body: listTxns({ work_order_id: Number(ctx.params.id) }) }));
  Mock.register("POST", "/api/work-orders/(?<id>\\d+)/inspections", (ctx) => ({ status: 201, body: createInsp(ctx.params.id, ctx.body) }));
  Mock.register("GET", "/api/work-orders/(?<id>\\d+)/inspections", (ctx) =>
    ({ body: listInsp(Number(ctx.params.id)) }));

  function createWO(data) {
    const product_id = require_(data, "product_id", "产品");
    const planned_qty = num(data.planned_qty, "计划数量", false);
    const priority = data.priority || "normal";
    if (!PRIORITY[priority]) bad("未知优先级：" + priority);
    const product = byId("products", product_id);
    if (!product) bad("所选产品不存在");
    const t = now();
    const row = insert("work_orders", {
      order_no: genOrderNo(), product_id: Number(product_id), product_name: product.name,
      planned_qty, completed_qty: 0, defect_qty: 0, status: "pending", priority,
      assignee: (data.assignee || "").trim(), workshop: (data.workshop || "").trim(),
      planned_start: (data.planned_start || "").trim(), planned_end: (data.planned_end || "").trim(),
      actual_start: "", actual_end: "", remark: (data.remark || "").trim(), created_at: t, updated_at: t,
    });
    save();
    return enrichWO(row);
  }
  function transition(id, action, payload) {
    payload = payload || {};
    if (!TRANSITIONS[action]) bad("未知操作：" + action);
    const [allowed, target] = TRANSITIONS[action];
    const w = byId("work_orders", id); if (!w) notfound("工单不存在");
    if (!allowed.includes(w.status)) bad(`当前状态「${STATUS[w.status]}」不允许执行该操作`);
    const t = now();
    w.status = target; w.updated_at = t;
    if (action === "dispatch") { const a = (payload.assignee || w.assignee || "").trim(); if (!a) bad("派工必须指定负责人"); w.assignee = a; }
    if (action === "start" && !w.actual_start) w.actual_start = t;
    if (action === "complete") w.actual_end = t;
    save();
    return enrichWO(w);
  }
  function report(id, data) {
    const reporter = require_(data, "reporter", "报工人");
    const qty_ok = num(data.qty_ok || 0, "合格数量");
    const qty_defect = num(data.qty_defect || 0, "不良数量");
    if (qty_ok === 0 && qty_defect === 0) bad("合格数量与不良数量不能同时为 0");
    const w = byId("work_orders", id); if (!w) notfound("工单不存在");
    if (w.status !== "producing" && w.status !== "paused") bad("仅生产中或暂停的工单可以报工");
    const t = now();
    insert("reports", { work_order_id: w.id, reporter, qty_ok, qty_defect, remark: (data.remark || "").trim(), report_time: t });
    w.completed_qty += qty_ok; w.defect_qty += qty_defect; w.updated_at = t;
    if (w.completed_qty >= w.planned_qty && w.status !== "completed") { w.status = "completed"; w.actual_end = t; }
    save();
    return enrichWO(w);
  }

  // ── 核心路由：异常 ─────────────────────────────────────────────
  function listExc(opts) {
    opts = opts || {};
    let rows = table("exceptions").slice();
    if (opts.status === "open" || opts.status === "resolved") rows = rows.filter((e) => e.status === opts.status);
    if (opts.wo_id) rows = rows.filter((e) => e.work_order_id === opts.wo_id);
    rows.sort((a, b) => b.id - a.id);
    return rows.map((e) => {
      const w = byId("work_orders", e.work_order_id);
      return Object.assign({}, e, { order_no: w ? w.order_no : "", category_label: EXC[e.category] || e.category });
    });
  }
  Mock.register("GET", "/api/exceptions", (ctx) => ({ body: listExc({ status: ctx.query.status }) }));
  Mock.register("POST", "/api/exceptions", (ctx) => {
    const d = ctx.body;
    const wo_id = require_(d, "work_order_id", "工单");
    const description = require_(d, "description", "异常描述");
    const category = d.category || "other";
    if (!EXC[category]) bad("未知异常类型：" + category);
    if (!byId("work_orders", wo_id)) bad("关联的工单不存在");
    const row = insert("exceptions", { work_order_id: Number(wo_id), category, description, reporter: (d.reporter || "").trim(), status: "open", resolution: "", created_at: now(), resolved_at: "" });
    save();
    const w = byId("work_orders", row.work_order_id);
    return { status: 201, body: Object.assign({}, row, { order_no: w.order_no, category_label: EXC[row.category] }) };
  });
  Mock.register("POST", "/api/exceptions/(?<id>\\d+)/resolve", (ctx) => {
    const e = byId("exceptions", ctx.params.id); if (!e) notfound("异常不存在");
    const resolution = require_(ctx.body, "resolution", "处理结果");
    if (e.status === "resolved") bad("该异常已处理");
    e.status = "resolved"; e.resolution = resolution; e.resolved_at = now(); save();
    const w = byId("work_orders", e.work_order_id);
    return { body: Object.assign({}, e, { order_no: w.order_no, category_label: EXC[e.category] }) };
  });

  // ── 核心路由：员工 ─────────────────────────────────────────────
  Mock.register("GET", "/api/staff", (ctx) => {
    let rows = table("staff").slice();
    if (ctx.query.active === "1") rows = rows.filter((s) => s.active);
    rows.sort((a, b) => b.id - a.id);
    return { body: rows.map((s) => Object.assign({}, s, { role_label: STAFF_ROLE[s.role] || s.role, active: !!s.active })) };
  });
  Mock.register("POST", "/api/staff", (ctx) => {
    const name = require_(ctx.body, "name", "姓名");
    const role = ctx.body.role || "operator";
    if (!STAFF_ROLE[role]) bad("未知角色：" + role);
    const row = insert("staff", { name, role, team: (ctx.body.team || "").trim(), active: 1, created_at: now() });
    save();
    return { status: 201, body: Object.assign({}, row, { role_label: STAFF_ROLE[role], active: true }) };
  });
  Mock.register("POST", "/api/staff/(?<id>\\d+)/active", (ctx) => {
    const s = byId("staff", ctx.params.id); if (!s) notfound("员工不存在");
    s.active = ctx.body.active ? 1 : 0; save();
    return { body: Object.assign({}, s, { role_label: STAFF_ROLE[s.role], active: !!s.active }) };
  });

  // ── 核心路由：物料 / 库存 ──────────────────────────────────────
  Mock.register("GET", "/api/materials", () => ({ body: table("materials").slice().reverse().map(enrichMat) }));
  Mock.register("POST", "/api/materials", (ctx) => ({ status: 201, body: createMaterial(ctx.body) }));
  Mock.register("POST", "/api/materials/(?<id>\\d+)/move", (ctx) =>
    ({ status: 201, body: stockMove(ctx.params.id, ctx.body.biz_type, ctx.body.qty, ctx.body) }));
  Mock.register("GET", "/api/inventory-txns", (ctx) =>
    ({ body: listTxns({ material_id: ctx.query.material_id ? Number(ctx.query.material_id) : null }) }));

  function createMaterial(d) {
    const code = require_(d, "code", "物料编码");
    const name = require_(d, "name", "物料名称");
    const category = d.category || "raw";
    if (!MAT_CAT[category]) bad("未知物料类别：" + category);
    const stock = num(d.stock || 0, "初始库存");
    const safety = num(d.safety_stock || 0, "安全库存");
    if (table("materials").some((m) => m.code === code)) bad(`物料编码 ${code} 已存在`);
    const t = now();
    const row = insert("materials", { code, name, spec: (d.spec || "").trim(), unit: (d.unit || "件").trim() || "件", category, stock, safety_stock: safety, created_at: t });
    if (stock > 0) writeTxn(row, "in", "adjust_in", stock, stock, null, (d.operator || "").trim(), "期初库存", t);
    save();
    return enrichMat(row);
  }
  function writeTxn(mat, kind, biz_type, qty, balance_after, work_order_id, operator, remark, t) {
    insert("inventory_txns", { material_id: mat.id, material_name: mat.name, kind, biz_type, qty, balance_after, work_order_id, operator, remark, created_at: t });
  }
  function stockMove(material_id, biz_type, qty, opts) {
    opts = opts || {};
    if (!TXN[biz_type]) bad("未知出入库类型：" + biz_type);
    const kind = TXN_IN[biz_type] ? "in" : "out";
    qty = num(qty, "数量", false);
    const mat = byId("materials", material_id); if (!mat) notfound("物料不存在");
    if (opts.work_order_id && !byId("work_orders", opts.work_order_id)) bad("关联的工单不存在");
    const delta = kind === "in" ? qty : -qty;
    const newStock = mat.stock + delta;
    if (newStock < 0) bad(`库存不足：当前 ${mat.stock} ${mat.unit}，本次出库 ${qty}`);
    const t = now();
    mat.stock = newStock;
    writeTxn(mat, kind, biz_type, qty, newStock, opts.work_order_id || null, (opts.operator || "").trim(), (opts.remark || "").trim(), t);
    save();
    return enrichMat(mat);
  }
  function issueToWO(wo_id, data) {
    const material_id = require_(data, "material_id", "物料");
    const w = byId("work_orders", wo_id); if (!w) notfound("工单不存在");
    if (w.status === "completed" || w.status === "closed") bad("已完工/已关闭的工单不能再领料");
    return stockMove(material_id, "issue", data.qty, { operator: data.operator, remark: data.remark, work_order_id: Number(wo_id) });
  }
  function listTxns(opts) {
    opts = opts || {};
    let rows = table("inventory_txns").slice();
    if (opts.material_id) rows = rows.filter((r) => r.material_id === opts.material_id);
    if (opts.work_order_id) rows = rows.filter((r) => r.work_order_id === opts.work_order_id);
    rows.sort((a, b) => b.id - a.id);
    return rows.map((r) => Object.assign({}, r, { biz_label: TXN[r.biz_type] || r.biz_type }));
  }

  // ── 核心路由：质检 ─────────────────────────────────────────────
  function createInsp(wo_id, d) {
    const inspector = require_(d, "inspector", "质检员");
    const qi = num(d.qty_inspected, "送检数量", false);
    const qq = num(d.qty_qualified || 0, "合格数量");
    const qd = num(d.qty_defective || 0, "不良数量");
    if (qq + qd > qi) bad("合格 + 不良数量不能大于送检数量");
    const result = d.result || "pass";
    if (!INSPECT[result]) bad("未知质检结论：" + result);
    const w = byId("work_orders", wo_id); if (!w) notfound("工单不存在");
    const row = insert("inspections", { work_order_id: Number(wo_id), inspector, qty_inspected: qi, qty_qualified: qq, qty_defective: qd, result, defect_reason: (d.defect_reason || "").trim(), remark: (d.remark || "").trim(), created_at: now() });
    save();
    return Object.assign(enrichInsp(row), { order_no: w.order_no });
  }
  function listInsp(wo_id) {
    let rows = table("inspections").slice();
    if (wo_id) rows = rows.filter((i) => i.work_order_id === wo_id);
    rows.sort((a, b) => b.id - a.id);
    return rows.map((i) => { const w = byId("work_orders", i.work_order_id); return Object.assign(enrichInsp(i), { order_no: w ? w.order_no : "" }); });
  }
  Mock.register("GET", "/api/inspections", () => ({ body: listInsp(null) }));

  // ── 核心路由：看板 ─────────────────────────────────────────────
  Mock.register("GET", "/api/dashboard", () => {
    const wos = table("work_orders");
    const by_status = {}; Object.keys(STATUS).forEach((k) => (by_status[k] = 0));
    wos.forEach((w) => (by_status[w.status] = (by_status[w.status] || 0) + 1));
    const planned = wos.reduce((s, w) => s + (w.planned_qty || 0), 0);
    const completed = wos.reduce((s, w) => s + (w.completed_qty || 0), 0);
    const defect = wos.reduce((s, w) => s + (w.defect_qty || 0), 0);
    const produced = completed + defect;
    const td = today();
    const today_completed = table("reports").filter((r) => (r.report_time || "").startsWith(td)).reduce((s, r) => s + (r.qty_ok || 0), 0);
    const overdue = wos.filter((w) => w.planned_end && w.planned_end.slice(0, 10) < td && w.status !== "completed" && w.status !== "closed").length;
    const insp = table("inspections");
    const insI = insp.reduce((s, i) => s + (i.qty_inspected || 0), 0);
    const insQ = insp.reduce((s, i) => s + (i.qty_qualified || 0), 0);
    const low = table("materials").filter((m) => m.safety_stock > 0 && m.stock < m.safety_stock).length;
    const r1 = (a, b) => (b ? Math.round((a / b) * 1000) / 10 : 0);
    return {
      body: {
        by_status, status_labels: STATUS, total_orders: wos.length,
        planned_qty: planned, completed_qty: completed, defect_qty: defect,
        completion_rate: r1(completed, planned), defect_rate: r1(defect, produced),
        open_exceptions: table("exceptions").filter((e) => e.status === "open").length,
        today_completed, overdue_orders: overdue,
        inspect_pass_rate: r1(insQ, insI),
        low_stock_materials: low,
      },
    };
  });

  // ── 模块清单（静态部署下供 loadPlugins 注入）────────────────────
  Mock.register("GET", "/api/modules", () => ({ body: MODULE_FILES.slice() }));

  // ── 登录与权限 ─────────────────────────────────────────────────
  function userPublic(u) {
    return { id: u.id, username: u.username, name: u.name, role: u.role, role_label: ROLE[u.role] || u.role, active: !!u.active, permissions: PERMISSIONS[u.role] || ["dashboard"] };
  }
  Mock.register("POST", "/api/auth/login", (ctx) => {
    const username = require_(ctx.body, "username", "用户名");
    const password = require_(ctx.body, "password", "密码");
    const u = table("users").find((x) => x.username === username);
    if (!u || u.password !== password) bad("用户名或密码错误");
    if (!u.active) bad("账号已停用，请联系管理员");
    const token = "mock-" + Math.abs((Date.now() ^ (u.id * 2654435761)) >>> 0).toString(16) + u.id;
    DB.sessions[token] = u.id; save();
    return { body: { token, user: userPublic(u) } };
  });
  Mock.register("POST", "/api/auth/logout", (ctx) => {
    const tok = bearer(ctx); if (tok) { delete DB.sessions[tok]; save(); } return { body: { ok: true } };
  });
  Mock.register("GET", "/api/auth/me", (ctx) => {
    const tok = bearer(ctx); const uid = tok && DB.sessions[tok];
    const u = uid && byId("users", uid);
    if (!u || !u.active) return { status: 401, body: { error: "未登录或登录已过期" } };
    return { body: userPublic(u) };
  });
  Mock.register("GET", "/api/auth/users", () => ({ body: table("users").map(userPublic) }));
  function bearer(ctx) {
    const h = ctx.headers || {};
    const raw = h["Authorization"] || h["authorization"] || "";
    return raw.startsWith("Bearer ") ? raw.slice(7).trim() : null;
  }

  // ── 种子（核心 + 用户）─────────────────────────────────────────
  function coreSeed() {
    const prods = [
      { code: "P-1001", name: "精密轴承 6204", spec: "内径20mm", unit: "个" },
      { code: "P-1002", name: "不锈钢法兰盘", spec: "DN50", unit: "片" },
      { code: "P-1003", name: "铝合金外壳", spec: "120×80×40", unit: "件" },
    ].map((p) => createMaterialSafe("products", p));
    const pid = (i) => table("products")[i].id;

    const wo1 = createWO({ product_id: pid(0), planned_qty: 1000, priority: "high", assignee: "张工", workshop: "一号车间", planned_start: "2026-06-25", planned_end: "2026-06-30", remark: "客户加急订单" });
    transition(wo1.id, "dispatch", { assignee: "张工" }); transition(wo1.id, "start");
    report(wo1.id, { reporter: "李师傅", qty_ok: 420, qty_defect: 8 });

    const wo2 = createWO({ product_id: pid(1), planned_qty: 300, priority: "normal", assignee: "王工", workshop: "二号车间", planned_start: "2026-06-20", planned_end: "2026-06-26" });
    transition(wo2.id, "dispatch", { assignee: "王工" }); transition(wo2.id, "start");
    report(wo2.id, { reporter: "赵师傅", qty_ok: 180, qty_defect: 5 });

    createWO({ product_id: pid(2), planned_qty: 500, priority: "urgent", workshop: "三号车间", planned_start: "2026-06-29", planned_end: "2026-07-05", remark: "等待排产" });

    [{ name: "张工", role: "leader", team: "一号车间" }, { name: "王工", role: "leader", team: "二号车间" },
     { name: "李师傅", role: "operator", team: "一号车间" }, { name: "赵师傅", role: "operator", team: "二号车间" },
     { name: "陈质检", role: "inspector", team: "质检组" }].forEach((s) => insert("staff", Object.assign({ active: 1, created_at: now() }, s)));

    const mSteel = createMaterial({ code: "M-2001", name: "304 不锈钢板", spec: "1.5mm", unit: "kg", category: "raw", stock: 800, safety_stock: 200 });
    const mAlu = createMaterial({ code: "M-2002", name: "6061 铝型材", spec: "40×40", unit: "根", category: "raw", stock: 60, safety_stock: 100 });
    createMaterial({ code: "M-2003", name: "润滑脂", spec: "2# 锂基", unit: "桶", category: "raw", stock: 12, safety_stock: 5 });

    issueToWO(wo2.id, { material_id: mSteel.id, qty: 150, operator: "王工", remark: "法兰盘下料" });
    stockMove(mAlu.id, "purchase", 200, { operator: "采购员", remark: "补货 PO-0617" });

    createInsp(wo1.id, { inspector: "陈质检", qty_inspected: 420, qty_qualified: 412, qty_defective: 8, result: "pass", defect_reason: "尺寸偏差" });
    createExcSeed(wo2.id, { category: "material", description: "不锈钢原料批次到货延迟，预计影响 1 天", reporter: "王工" });

    [{ username: "admin", name: "系统管理员", role: "admin", password: "admin123" },
     { username: "planner", name: "王计划", role: "planner", password: "plan123" },
     { username: "operator", name: "李操作", role: "operator", password: "op123" },
     { username: "inspector", name: "陈质检", role: "inspector", password: "insp123" }]
      .forEach((u) => insert("users", Object.assign({ active: 1, created_at: now() }, u)));
  }
  function createMaterialSafe(t, p) { return insert(t, Object.assign({ spec: "", unit: "件", created_at: now() }, p)); }
  function createExcSeed(wo_id, d) { insert("exceptions", { work_order_id: wo_id, category: d.category, description: d.description, reporter: d.reporter || "", status: "open", resolution: "", created_at: now(), resolved_at: "" }); }

  // ── 激活（仅静态模式）──────────────────────────────────────────
  function blankDB() { return { seq: {}, sessions: {}, products: [], work_orders: [], reports: [], exceptions: [], materials: [], inventory_txns: [], inspections: [], staff: [], users: [] }; }
  let installed = false;
  function activate() {
    DB = load();
    if (!DB) { DB = blankDB(); coreSeed(); seeders.forEach((fn) => { try { fn(Mock); } catch (e) { console.warn("mock seed failed", e); } }); save(); }
    if (installed) return;
    installed = true;
    const realFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : input.url;
      let u; try { u = new URL(url, location.origin); } catch (e) { return realFetch(input, init); }
      if (!u.pathname.startsWith("/api/")) return realFetch(input, init);
      const method = (init && init.method) || "GET";
      let body = {}; try { if (init && init.body) body = JSON.parse(init.body); } catch (e) {}
      const query = {}; u.searchParams.forEach((v, k) => { query[k] = v; });
      const headers = (init && init.headers) || {};
      for (const r of routes) {
        if (r.method !== method) continue;
        const m = r.re.exec(u.pathname); if (!m) continue;
        try {
          const res = r.handler({ params: m.groups || {}, query, body, headers });
          if (res && res.raw) return Promise.resolve(new Response(res.text, { status: res.status || 200, headers: { "Content-Type": res.contentType || "text/plain; charset=utf-8" } }));
          return Promise.resolve(jsonResp(res.status || 200, res.body));
        } catch (e) {
          return Promise.resolve(jsonResp(e.status || 500, { error: e.message }));
        }
      }
      return Promise.resolve(jsonResp(404, { error: "接口不存在(mock)：" + u.pathname }));
    };
  }
  function jsonResp(status, obj) {
    return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json; charset=utf-8" } });
  }
})();
