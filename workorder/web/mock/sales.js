"use strict";
/*
 * 销售订单 mock：复刻 server/modules/sales.py。
 * 管理客户订单，一键下推生成生产工单（调用核心 createWorkOrder），打通「销售→生产」。
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock;

  // 销售订单状态 → 中文标签（对齐 .py SALES_STATUS）
  const SALES_STATUS = {
    pending: "待生产",
    in_production: "生产中",
    shipped: "已发货",
    closed: "已关闭",
  };

  // 补充展示用派生字段：中文 status_label
  function label(row) {
    row.status_label = SALES_STATUS[row.status] || row.status;
    return row;
  }

  // 订单号：SO + 当天 yyyymmdd + -NNN 序号（按当天已有数量自增）
  function genOrderNo() {
    const prefix = "SO" + M.ymd();
    const c = M.db.table("sales_orders").filter((r) => (r.order_no || "").startsWith(prefix)).length;
    return `${prefix}-${String(c + 1).padStart(3, "0")}`;
  }

  // ── 查询 ──────────────────────────────────────────────────────────────────
  function listSales(status) {
    let rows = M.db.table("sales_orders").slice();
    if (status && status !== "all") {
      if (!SALES_STATUS[status]) M.bad("未知状态：" + status);
      rows = rows.filter((r) => r.status === status);
    }
    rows.sort((a, b) => b.id - a.id);
    return rows.map((r) => label(Object.assign({}, r)));
  }

  // ── 创建 ──────────────────────────────────────────────────────────────────
  function createSales(data) {
    const customer = M.require(data, "customer", "客户");
    const product_id = M.require(data, "product_id", "产品");
    const qty = M.num(data.qty, "数量", false);
    const due_date = String(data.due_date == null ? "" : data.due_date).trim();

    const product = M.db.byId("products", product_id);
    if (!product) M.bad("所选产品不存在");

    const row = M.db.insert("sales_orders", {
      order_no: genOrderNo(),
      customer,
      product_id: Number(product_id),
      product_name: product.name,
      qty,
      due_date,
      status: "pending",
      work_order_id: null,
      remark: String(data.remark == null ? "" : data.remark).trim(),
      created_at: M.now(),
    });
    M.db.save();
    return label(Object.assign({}, row));
  }

  // ── 下推生产 ────────────────────────────────────────────────────────────────
  function pushToProduction(so_id) {
    const so = M.db.byId("sales_orders", so_id);
    if (!so) M.notfound(`销售订单 ${so_id} 不存在`);
    if (so.work_order_id || so.status !== "pending") M.bad("该订单已下推，不能重复下推");

    // 调用核心方法生成生产工单
    const wo = M.core.createWorkOrder({
      product_id: so.product_id,
      planned_qty: so.qty,
      planned_end: so.due_date,
      remark: "销售订单 " + so.order_no,
    });

    so.work_order_id = wo.id;
    so.status = "in_production";
    M.db.save();
    const out = label(Object.assign({}, so));
    out.work_order_no = wo.order_no;
    return out;
  }

  // ── 发货 ──────────────────────────────────────────────────────────────────
  function ship(so_id) {
    const so = M.db.byId("sales_orders", so_id);
    if (!so) M.notfound(`销售订单 ${so_id} 不存在`);
    if (so.status !== "in_production") M.bad("仅生产中的订单可以发货");
    so.status = "shipped";
    M.db.save();
    return label(Object.assign({}, so));
  }

  // ── 关闭 ──────────────────────────────────────────────────────────────────
  function closeSales(so_id) {
    const so = M.db.byId("sales_orders", so_id);
    if (!so) M.notfound(`销售订单 ${so_id} 不存在`);
    so.status = "closed";
    M.db.save();
    return label(Object.assign({}, so));
  }

  // ── 路由 ──────────────────────────────────────────────────────────────────
  M.register("GET", "/api/sales", (ctx) => ({ body: listSales(ctx.query.status) }));
  M.register("POST", "/api/sales", (ctx) => ({ status: 201, body: createSales(ctx.body) }));
  M.register("POST", "/api/sales/(?<id>\\d+)/push", (ctx) => ({ body: pushToProduction(ctx.params.id) }));
  M.register("POST", "/api/sales/(?<id>\\d+)/ship", (ctx) => ({ body: ship(ctx.params.id) }));
  M.register("POST", "/api/sales/(?<id>\\d+)/close", (ctx) => ({ body: closeSales(ctx.params.id) }));

  // ── 演示数据（对应 .py seed）────────────────────────────────────────────────
  M.onSeed(function (M) {
    if (M.db.table("sales_orders").length) return;
    const products = M.db.table("products").slice().sort((a, b) => a.id - b.id).slice(0, 2);
    if (!products.length) return;

    const so1 = createSales({
      customer: "华东机械有限公司",
      product_id: products[0].id,
      qty: 500,
      due_date: "2026-07-10",
      remark: "首批订单",
    });
    pushToProduction(so1.id);

    const second = products.length > 1 ? products[1] : products[0];
    createSales({
      customer: "南方精工厂",
      product_id: second.id,
      qty: 200,
      due_date: "2026-07-20",
      remark: "等待排产",
    });
  });
})();
