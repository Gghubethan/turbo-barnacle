"use strict";
/* 工序/工艺路线（routing）mock：复刻后端 server/modules/routing.py。
 * 把工单拆成有序工序，按工序报工、跟踪每道工序的进度与状态。
 * 表 wo_operations；状态机 pending(待开工) → doing(进行中) → done(已完成)。
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock;

  // 工序状态：待开工 / 进行中 / 已完成（与 .py OP_STATUS 对齐）
  const OP_STATUS = { pending: "待开工", doing: "进行中", done: "已完成" };

  // 补充展示用派生字段：状态中文、进度百分比（保留 1 位）
  function label(op) {
    const x = Object.assign({}, op);
    const planned = x.planned_qty || 0;
    x.status_label = OP_STATUS[x.status] || x.status;
    x.progress = planned ? Math.round((x.completed_qty / planned) * 1000) / 10 : 0.0;
    return x;
  }

  function listOperations(woId) {
    const rows = M.db.table("wo_operations").filter((r) => r.work_order_id === Number(woId)).slice();
    rows.sort((a, b) => (a.seq - b.seq) || (a.id - b.id));
    return rows.map(label);
  }

  function addOperation(woId, data) {
    data = data || {};
    const name = M.require(data, "name", "工序名");
    const planned_qty = M.num(data.planned_qty, "计划数量", false);
    if (!M.db.byId("work_orders", woId)) M.notfound(`工单 ${Number(woId)} 不存在`);
    let seq;
    if (data.seq !== null && data.seq !== undefined && String(data.seq).trim() !== "") {
      seq = Math.trunc(M.num(data.seq, "工序号"));
    } else {
      const existing = M.db.table("wo_operations").filter((r) => r.work_order_id === Number(woId));
      const maxSeq = existing.reduce((m, r) => Math.max(m, r.seq || 0), 0);
      seq = maxSeq + 1;
    }
    const t = M.now();
    const row = M.db.insert("wo_operations", {
      work_order_id: Number(woId), seq, name,
      workstation: String(data.workstation || "").trim(),
      planned_qty, completed_qty: 0,
      worker: String(data.worker || "").trim(),
      status: "pending", created_at: t, updated_at: t,
    });
    M.db.save();
    return label(row);
  }

  function reportOperation(opId, data) {
    data = data || {};
    const qty = M.num(data.qty, "报工数量", false);
    const op = M.db.byId("wo_operations", opId);
    if (!op) M.notfound(`工序 ${Number(opId)} 不存在`);
    const new_completed = op.completed_qty + qty;
    if (new_completed > op.planned_qty) {
      M.bad(`报工数量超出计划：计划 ${op.planned_qty}，已完成 ${op.completed_qty}`);
    }
    let status = op.status === "pending" ? "doing" : op.status;
    if (new_completed >= op.planned_qty) status = "done";
    let worker = op.worker;
    if (data.worker !== null && data.worker !== undefined && String(data.worker).trim()) {
      worker = String(data.worker).trim();
    }
    op.completed_qty = new_completed;
    op.status = status;
    op.worker = worker;
    op.updated_at = M.now();
    M.db.save();
    return label(op);
  }

  function deleteOperation(opId) {
    const op = M.db.byId("wo_operations", opId);
    if (!op) M.notfound(`工序 ${Number(opId)} 不存在`);
    const tbl = M.db.table("wo_operations");
    tbl.splice(tbl.indexOf(op), 1);
    M.db.save();
    return { ok: true, id: Number(opId) };
  }

  // ── 路由（与 .py routes() 完全一致）─────────────────────────────
  M.register("GET", "/api/work-orders/(?<id>\\d+)/operations", (ctx) =>
    ({ body: listOperations(ctx.params.id) }));
  M.register("POST", "/api/work-orders/(?<id>\\d+)/operations", (ctx) =>
    ({ status: 201, body: addOperation(ctx.params.id, ctx.body) }));
  M.register("POST", "/api/operations/(?<id>\\d+)/report", (ctx) =>
    ({ body: reportOperation(ctx.params.id, ctx.body) }));
  M.register("POST", "/api/operations/(?<id>\\d+)/delete", (ctx) =>
    ({ body: deleteOperation(ctx.params.id) }));

  // ── 种子（与 .py seed() 对齐）──────────────────────────────────
  M.onSeed(function (M) {
    if (M.db.table("wo_operations").length) return;
    const wo = M.db.table("work_orders")
      .filter((w) => w.status === "producing")
      .slice()
      .sort((a, b) => a.id - b.id)[0];
    if (!wo) return;
    const qty = wo.planned_qty;
    [["下料", "锯床01"], ["加工", "CNC03"], ["质检", "检测台"]].forEach(([name, ws]) => {
      addOperation(wo.id, { name, workstation: ws, planned_qty: qty });
    });
    const ops = listOperations(wo.id);
    if (ops.length) {
      const first = ops[0];
      reportOperation(first.id, {
        qty: Math.max(1, Math.round(first.planned_qty * 0.4)), worker: "李师傅",
      });
    }
  });
})();
