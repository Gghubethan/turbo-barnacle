"use strict";
/*
 * 报表中心 mock：复刻后端 server/modules/reports.py 的只读聚合逻辑。
 * 本模块不建表，只聚合现有核心表：
 * work_orders / reports / inspections / inventory_txns / materials。
 * 数值算法、字段名、四舍五入位数均与 .py 完全一致（前端图表依赖）。
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock, L = M.labels;
  const t = (n) => M.db.table(n);

  // 与 .py 一致：round 到 1 位小数（Python round 同 JS Math.round * 10 / 10）
  function r1(a, b) { return b ? Math.round((a / b) * 100 * 10) / 10 : 0.0; }

  // 把外部传入的 days 归一为正整数，非法回退默认值（对齐 _coerce_days）
  function coerceDays(days, def) {
    def = def === undefined ? 14 : def;
    const n = parseInt(days, 10);
    if (Number.isNaN(n)) return def;
    return n > 0 ? n : def;
  }

  // 最近 days 天的日期字符串（升序，含今天），对齐 _recent_dates
  function recentDates(days) {
    const out = [];
    const base = new Date();
    base.setHours(0, 0, 0, 0);
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(base);
      d.setDate(base.getDate() - i);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      out.push(`${y}-${m}-${day}`);
    }
    return out;
  }

  // ── 趋势 ──────────────────────────────────────────────────────────
  function outputTrend(days) {
    days = coerceDays(days);
    const dates = recentDates(days);
    const start = dates[0];
    const byDate = {};
    t("reports").forEach((r) => {
      const d = (r.report_time || "").slice(0, 10);
      if (d >= start) {
        if (!byDate[d]) byDate[d] = { qty_ok: 0, qty_defect: 0 };
        byDate[d].qty_ok += r.qty_ok || 0;
        byDate[d].qty_defect += r.qty_defect || 0;
      }
    });
    return dates.map((d) => {
      const r = byDate[d];
      return { date: d, qty_ok: r ? r.qty_ok : 0, qty_defect: r ? r.qty_defect : 0 };
    });
  }

  function qualityTrend(days) {
    days = coerceDays(days);
    const dates = recentDates(days);
    const start = dates[0];
    const byDate = {};
    t("inspections").forEach((r) => {
      const d = (r.created_at || "").slice(0, 10);
      if (d >= start) {
        if (!byDate[d]) byDate[d] = { inspected: 0, qualified: 0 };
        byDate[d].inspected += r.qty_inspected || 0;
        byDate[d].qualified += r.qty_qualified || 0;
      }
    });
    return dates.map((d) => {
      const r = byDate[d];
      const inspected = r ? r.inspected : 0;
      const qualified = r ? r.qualified : 0;
      return {
        date: d,
        inspected: inspected,
        qualified: qualified,
        pass_rate: inspected ? r1(qualified, inspected) : 0.0,
      };
    });
  }

  // ── 分布 / 汇总 ─────────────────────────────────────────────────────
  function statusDistribution() {
    const counts = {};
    t("work_orders").forEach((w) => { counts[w.status] = (counts[w.status] || 0) + 1; });
    return Object.keys(L.STATUS).map((s) => ({
      status: s,
      status_label: L.STATUS[s],
      count: counts[s] || 0,
    }));
  }

  function workshopOutput() {
    // 按 workshop 汇总；workshop 为空显示「未分配」；按 workshop 升序
    const groups = {};
    t("work_orders").forEach((w) => {
      const ws = ((w.workshop || "").trim()) || "未分配";
      if (!groups[ws]) groups[ws] = { planned: 0, completed: 0 };
      groups[ws].planned += w.planned_qty || 0;
      groups[ws].completed += w.completed_qty || 0;
    });
    return Object.keys(groups).sort().map((ws) => {
      const g = groups[ws];
      return {
        workshop: ws,
        planned: g.planned,
        completed: g.completed,
        rate: g.planned ? r1(g.completed, g.planned) : 0.0,
      };
    });
  }

  function materialFlow() {
    // 按物料汇总出入库；按 material_name 升序
    const groups = {};
    t("inventory_txns").forEach((r) => {
      const name = r.material_name;
      if (!(name in groups)) groups[name] = { in_qty: 0, out_qty: 0 };
      if (r.kind === "in") groups[name].in_qty += r.qty || 0;
      else if (r.kind === "out") groups[name].out_qty += r.qty || 0;
    });
    return Object.keys(groups).sort().map((name) => ({
      material_name: name,
      in_qty: groups[name].in_qty,
      out_qty: groups[name].out_qty,
    }));
  }

  function summary() {
    const wos = t("work_orders");
    const total = wos.length;
    let completed = 0;
    wos.forEach((w) => { if (w.status === "completed") completed += 1; });

    let ok = 0, defect = 0;
    t("reports").forEach((r) => { ok += r.qty_ok || 0; defect += r.qty_defect || 0; });

    let inspected = 0, qualified = 0;
    t("inspections").forEach((i) => { inspected += i.qty_inspected || 0; qualified += i.qty_qualified || 0; });

    return {
      total_orders: total,
      completed_orders: completed,
      total_output: ok,
      total_defect: defect,
      avg_pass_rate: inspected ? r1(qualified, inspected) : 0.0,
      materials: t("materials").length,
    };
  }

  // ── 路由 ──────────────────────────────────────────────────────────
  M.register("GET", "/api/reports/summary", () => ({ body: summary() }));
  M.register("GET", "/api/reports/output-trend", (ctx) => ({ body: outputTrend(ctx.query.days) }));
  M.register("GET", "/api/reports/quality-trend", (ctx) => ({ body: qualityTrend(ctx.query.days) }));
  M.register("GET", "/api/reports/status-distribution", () => ({ body: statusDistribution() }));
  M.register("GET", "/api/reports/workshop-output", () => ({ body: workshopOutput() }));
  M.register("GET", "/api/reports/material-flow", () => ({ body: materialFlow() }));
})();
