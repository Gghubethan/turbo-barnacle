"use strict";
/*
 * BOM 物料清单 mock：复刻 server/modules/bom.py。
 * 维护「产品 → 所需物料 + 单位用量 + 损耗率」，并据此测算某产量下的用料需求、
 * 对比现有库存给出缺口（采购建议）。表名 bom_items，与 .py 一致。
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock;

  // 校验产品存在（与 .py _product 一致：不存在抛 400）
  function ensureProduct(product_id) {
    const p = M.db.byId("products", product_id);
    if (!p) M.bad("所选产品不存在");
    return p;
  }

  // LEFT JOIN materials：带出 material_code / unit / stock
  function joinRow(b) {
    const m = M.db.byId("materials", b.material_id);
    return Object.assign({}, b, {
      material_code: m ? m.code : null,
      unit: m ? m.unit : null,
      stock: m ? m.stock : null,
    });
  }

  function listBom(product_id) {
    if (!product_id) M.bad("请选择产品");
    return M.db.table("bom_items")
      .filter((b) => b.product_id === Number(product_id))
      .sort((a, b) => a.id - b.id)
      .map(joinRow);
  }

  function addBomItem(product_id, data) {
    if (!product_id) M.bad("请选择产品");
    const material_id = M.require(data, "material_id", "物料");
    const qty_per = M.num(data.qty_per, "单位用量", false);
    const loss_rate = M.num(data.loss_rate === undefined ? 0 : data.loss_rate, "损耗率");
    ensureProduct(product_id);
    const mat = M.db.byId("materials", material_id);
    if (!mat) M.bad("所选物料不存在");
    const dup = M.db.table("bom_items").some(
      (b) => b.product_id === Number(product_id) && b.material_id === Number(material_id)
    );
    if (dup) M.bad("该物料已在此产品的 BOM 中");
    const row = M.db.insert("bom_items", {
      product_id: Number(product_id),
      material_id: Number(material_id),
      material_name: mat.name,
      qty_per,
      loss_rate,
      created_at: M.now(),
    });
    M.db.save();
    return row;
  }

  function deleteBomItem(item_id) {
    const b = M.db.byId("bom_items", item_id);
    if (!b) M.notfound(`BOM 行 ${item_id} 不存在`);
    const tbl = M.db.table("bom_items");
    tbl.splice(tbl.indexOf(b), 1);
    M.db.save();
    return { ok: true, id: Number(item_id) };
  }

  // 保留 3 位（与 Python round(x, 3) 对齐）
  function round3(n) { return Math.round(n * 1000) / 1000; }

  function requirements(product_id, qty) {
    if (!product_id) M.bad("请选择产品");
    qty = M.num(qty, "产量", false);
    ensureProduct(product_id);
    const rows = M.db.table("bom_items")
      .filter((b) => b.product_id === Number(product_id))
      .sort((a, b) => a.id - b.id)
      .map(joinRow);
    const items = [];
    let has_shortage = false;
    for (const d of rows) {
      const required = round3(d.qty_per * qty * (1 + (d.loss_rate || 0) / 100));
      const stock = d.stock || 0;
      const shortage = round3(Math.max(0, required - stock));
      if (shortage > 0) has_shortage = true;
      items.push({
        material_id: d.material_id,
        material_code: d.material_code,
        material_name: d.material_name,
        unit: d.unit,
        qty_per: d.qty_per,
        loss_rate: d.loss_rate,
        required,
        stock,
        shortage,
      });
    }
    return { product_id: Number(product_id), qty, items, has_shortage };
  }

  // ── 路由 ───────────────────────────────────────────────────────
  M.register("GET", "/api/bom/items", (ctx) =>
    ({ body: listBom(ctx.query.product_id ? Number(ctx.query.product_id) : null) }));
  M.register("POST", "/api/bom/items", (ctx) =>
    ({ status: 201, body: addBomItem(ctx.body.product_id, ctx.body) }));
  M.register("POST", "/api/bom/items/(?<id>\\d+)/delete", (ctx) =>
    ({ body: deleteBomItem(Number(ctx.params.id)) }));
  M.register("GET", "/api/bom/requirements", (ctx) =>
    ({ body: requirements(
        ctx.query.product_id ? Number(ctx.query.product_id) : null,
        ctx.query.qty === undefined ? null : ctx.query.qty
      ) }));

  // ── 种子（在 core 种子后运行，products/materials 已就绪）─────────
  M.onSeed(function (Mk) {
    if (Mk.db.table("bom_items").length) return;
    const product = Mk.db.table("products").slice().sort((a, b) => a.id - b.id)[0];
    const mats = Mk.db.table("materials").slice().sort((a, b) => a.id - b.id).slice(0, 2);
    if (!product || mats.length < 1) return;
    addBomItem(product.id, { material_id: mats[0].id, qty_per: 0.5, loss_rate: 3 });
    if (mats.length > 1) {
      addBomItem(product.id, { material_id: mats[1].id, qty_per: 0.02, loss_rate: 0 });
    }
  });
})();
