"use strict";
/* 计划排产 mock：复刻 server/modules/planning.py。
 * - GET  /api/planning/board            排产甘特看板（{start, days, dates, orders}）
 * - GET  /api/planning/entries          列出排产条目（JOIN work_orders 带 order_no/product_name）
 * - POST /api/planning/entries          新建排产条目
 * - POST /api/planning/entries/:id/delete  删除排产条目
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock, L = M.labels;

  // ── 日期助手 ──────────────────────────────────────────────────────
  function pad(n) { return String(n).padStart(2, "0"); }
  function iso(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
  // 解析 'YYYY-MM-DD'，非法返回 null（对齐 date.fromisoformat 行为）
  function parseISO(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s).slice(0, 10));
    if (!m) return null;
    const y = Number(m[1]), mo = Number(m[2]), da = Number(m[3]);
    const d = new Date(y, mo - 1, da);
    if (d.getFullYear() !== y || d.getMonth() !== mo - 1 || d.getDate() !== da) return null;
    return d;
  }
  // 从 start 起连续 days 天的日期字符串列表
  function dateList(startIso, days) {
    const base = parseISO(startIso);
    const out = [];
    for (let i = 0; i < days; i++) {
      const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i);
      out.push(iso(d));
    }
    return out;
  }
  // 解析起始日期；缺省取“今天减 3 天”，非法输入回退缺省
  function parseStart(start) {
    if (start) {
      const d = parseISO(start);
      if (d) return iso(d);
    }
    const t = new Date();
    return iso(new Date(t.getFullYear(), t.getMonth(), t.getDate() - 3));
  }

  // ── 看板 ──────────────────────────────────────────────────────────
  function board(start, days) {
    let d = Number(days);
    if (!Number.isFinite(d) || Number.isNaN(d)) d = 14;
    d = Math.trunc(d);
    if (d <= 0) d = 14;
    const startIso = parseStart(start);
    const dates = dateList(startIso, d);

    let rows = M.db.table("work_orders").filter((w) => w.status !== "closed");
    // ORDER BY priority DESC, id ASC —— priority 是文本，与 .py 一致按文本排序
    rows = rows.slice().sort((a, b) => {
      if (a.priority < b.priority) return 1;
      if (a.priority > b.priority) return -1;
      return a.id - b.id;
    });

    const orders = rows.map((wo) => {
      const planned = wo.planned_qty || 0;
      const completed = wo.completed_qty || 0;
      const progress = planned ? Math.round((completed / planned) * 100 * 10) / 10 : 0.0;
      return {
        order_no: wo.order_no,
        work_order_id: wo.id,
        product_name: wo.product_name,
        status: wo.status,
        status_label: L.STATUS[wo.status] || wo.status,
        priority: wo.priority,
        priority_label: L.PRIORITY[wo.priority] || wo.priority,
        assignee: wo.assignee || "",
        workshop: wo.workshop || "",
        planned_start: (wo.planned_start || "").slice(0, 10),
        planned_end: (wo.planned_end || "").slice(0, 10),
        planned_qty: planned,
        completed_qty: completed,
        progress: progress,
      };
    });

    return { start: startIso, days: d, dates, orders };
  }

  // ── 排产条目 ────────────────────────────────────────────────────────
  function joinEntry(e) {
    const w = M.db.byId("work_orders", e.work_order_id);
    return Object.assign({}, e, {
      order_no: w ? w.order_no : "",
      product_name: w ? w.product_name : "",
    });
  }

  // 列出排产条目，JOIN work_orders；ORDER BY plan_date, line, seq, id
  function listEntries() {
    const rows = M.db.table("planning_entries").slice();
    rows.sort((a, b) => {
      if (a.plan_date < b.plan_date) return -1;
      if (a.plan_date > b.plan_date) return 1;
      if (a.line < b.line) return -1;
      if (a.line > b.line) return 1;
      if (a.seq !== b.seq) return a.seq - b.seq;
      return a.id - b.id;
    });
    return rows.map(joinEntry);
  }

  function createEntry(data) {
    const wo_id = M.require(data, "work_order_id", "工单");
    const line = M.require(data, "line", "产线");
    let plan_date = String(data.plan_date == null ? "" : data.plan_date).trim();
    if (plan_date) {
      const d = parseISO(plan_date);
      if (!d) M.bad("排产日期格式应为 YYYY-MM-DD");
      plan_date = iso(d);
    }
    let seq;
    const rawSeq = data.seq == null || data.seq === "" ? 0 : data.seq;
    seq = Number(rawSeq);
    if (Number.isNaN(seq) || !Number.isFinite(seq)) M.bad("顺序必须是整数");
    seq = Math.trunc(seq);

    if (!M.db.byId("work_orders", wo_id)) M.bad("关联的工单不存在");

    const row = M.db.insert("planning_entries", {
      work_order_id: Number(wo_id),
      line: typeof line === "string" ? line : String(line),
      plan_date,
      seq,
      remark: String(data.remark == null ? "" : data.remark).trim(),
      created_at: M.now(),
    });
    M.db.save();
    return joinEntry(row);
  }

  function deleteEntry(eid) {
    const row = M.db.byId("planning_entries", eid);
    if (!row) M.notfound(`排产条目 ${eid} 不存在`);
    const tbl = M.db.table("planning_entries");
    const idx = tbl.indexOf(row);
    tbl.splice(idx, 1);
    M.db.save();
    return { ok: true, id: Number(eid) };
  }

  // ── 路由 ──────────────────────────────────────────────────────────
  M.register("GET", "/api/planning/board", (ctx) =>
    ({ body: board(ctx.query.start, ctx.query.days != null && ctx.query.days !== "" ? ctx.query.days : 14) }));
  M.register("GET", "/api/planning/entries", () => ({ body: listEntries() }));
  M.register("POST", "/api/planning/entries", (ctx) => ({ status: 201, body: createEntry(ctx.body) }));
  M.register("POST", "/api/planning/entries/(?<id>\\d+)/delete", (ctx) =>
    ({ body: deleteEntry(Number(ctx.params.id)) }));

  // ── 种子（core 种子之后）──────────────────────────────────────────
  M.onSeed(function (M) {
    if (M.db.table("planning_entries").length) return;
    const wos = M.db.table("work_orders")
      .filter((w) => w.status !== "closed")
      .slice()
      .sort((a, b) => a.id - b.id)
      .slice(0, 2);
    if (!wos.length) return;
    for (const wo of wos) {
      createEntry({
        work_order_id: wo.id,
        line: (wo.workshop || "").trim() || "一号产线",
        plan_date: (wo.planned_start || "").slice(0, 10),
      });
    }
  });
})();
