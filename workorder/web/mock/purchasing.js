"use strict";
/* 采购管理 mock：复刻后端 server/modules/purchasing.py。
 * 采购订单管理，收货时调用 core.stockMove 自动入库，打通「采购→库存」。
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock;

  // 采购单状态：待收货 / 部分收货 / 已收货 / 已关闭（与 .py PO_STATUS 对齐）
  const PO_STATUS = {
    pending: "待收货",
    partial: "部分收货",
    received: "已收货",
    closed: "已关闭",
  };

  function poLabel(d) {
    const x = Object.assign({}, d);
    x.status_label = PO_STATUS[d.status] || d.status;
    return x;
  }

  // 单号：PO + yyyymmdd + -NNN（复刻 _gen_po_no，按当天已有单数 +1）
  function genPoNo() {
    const prefix = "PO" + M.ymd();
    const c = M.db.table("purchase_orders").filter((p) => (p.po_no || "").startsWith(prefix)).length;
    return `${prefix}-${String(c + 1).padStart(3, "0")}`;
  }

  function createPurchase(data) {
    const supplier = M.require(data, "supplier", "供应商");
    const material_id = M.require(data, "material_id", "物料");
    const qty = M.num(data.qty, "采购数量", false);
    const expected_date = String(data.expected_date == null ? "" : data.expected_date).trim();
    const mat = M.db.byId("materials", material_id);
    if (!mat) M.bad("所选物料不存在");
    const row = M.db.insert("purchase_orders", {
      po_no: genPoNo(),
      supplier,
      material_id: Number(material_id),
      material_name: mat.name,
      qty,
      received_qty: 0,
      status: "pending",
      expected_date,
      remark: String(data.remark == null ? "" : data.remark).trim(),
      created_at: M.now(),
    });
    M.db.save();
    return poLabel(row);
  }

  function receive(po_id, data) {
    const qty = M.num(data.qty, "收货数量", false);
    const po = M.db.byId("purchase_orders", po_id);
    if (!po) M.notfound("采购单 " + po_id + " 不存在");
    if (po.status === "received" || po.status === "closed") {
      M.bad("采购单当前状态「" + PO_STATUS[po.status] + "」不可再收货");
    }
    const new_received = po.received_qty + qty;
    if (new_received > po.qty) {
      M.bad("收货数量超出：采购 " + po.qty + "，已收 " + po.received_qty + "，本次 " + qty);
    }
    // 入库（增加物料 stock + 记一条 purchase 流水）
    M.core.stockMove(po.material_id, "purchase", qty, {
      operator: data.operator || "",
      remark: "采购收货 " + po.po_no,
    });
    po.received_qty = new_received;
    po.status = new_received >= po.qty ? "received" : "partial";
    M.db.save();
    return poLabel(po);
  }

  function closePurchase(po_id) {
    const po = M.db.byId("purchase_orders", po_id);
    if (!po) M.notfound("采购单 " + po_id + " 不存在");
    po.status = "closed";
    M.db.save();
    return poLabel(po);
  }

  // ── 路由 ───────────────────────────────────────────────────────
  M.register("GET", "/api/purchasing", (ctx) => {
    const status = ctx.query.status;
    let rows = M.db.table("purchase_orders").slice();
    if (status && status !== "all") {
      if (!PO_STATUS[status]) M.bad("未知状态：" + status);
      rows = rows.filter((p) => p.status === status);
    }
    rows.sort((a, b) => b.id - a.id);
    return { body: rows.map(poLabel) };
  });
  M.register("POST", "/api/purchasing", (ctx) => ({ status: 201, body: createPurchase(ctx.body) }));
  M.register("POST", "/api/purchasing/(?<id>\\d+)/receive", (ctx) =>
    ({ body: receive(Number(ctx.params.id), ctx.body) }));
  M.register("POST", "/api/purchasing/(?<id>\\d+)/close", (ctx) =>
    ({ body: closePurchase(Number(ctx.params.id)) }));

  // ── 种子（核心种子后运行：复刻 .py seed，灌 2 条，其一部分收货）──
  M.onSeed(function (M) {
    if (M.db.table("purchase_orders").length) return;
    const mats = M.db.table("materials").slice().sort((a, b) => a.id - b.id).slice(0, 2);
    if (!mats.length) return;
    const first = mats[0].id;
    const second = mats.length > 1 ? mats[1].id : first;

    const po1 = createPurchase({
      supplier: "宝钢供应链", material_id: first, qty: 500,
      expected_date: "2026-07-05", remark: "原料补货",
    });
    // 部分收货演示（变 partial）
    receive(po1.id, { qty: 200, operator: "采购员" });

    createPurchase({
      supplier: "南山铝业", material_id: second, qty: 100,
      expected_date: "2026-07-10", remark: "型材采购",
    });
  });
})();
