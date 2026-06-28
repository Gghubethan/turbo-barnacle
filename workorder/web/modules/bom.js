"use strict";

// BOM 物料清单：选产品 → 维护其用料清单；并按产量测算用料需求与缺口（采购建议）。
WO.registerModule({
  id: "bom",
  label: "物料清单",
  async refresh(container) {
    const self = this;
    const doc = container.ownerDocument;

    let products = [];
    try {
      products = await WO.api("/products");
    } catch (e) {
      WO.toast(e.message, true);
    }

    if (!products.length) {
      container.innerHTML = '<div class="card"><div class="empty">请先在「产品档案」中创建产品</div></div>';
      return;
    }

    // products 按 id 倒序；默认选最早建的产品（与后端 seed 对齐），首屏即展示已配好的 BOM。
    const defaultId = (products[products.length - 1] || {}).id;
    const opts = products
      .map((p) => `<option value="${p.id}"${p.id === defaultId ? " selected" : ""}>${WO.esc(p.code)} · ${WO.esc(p.name)}</option>`)
      .join("");

    container.innerHTML = `
      <div class="toolbar">
        <label class="field" style="margin:0">
          <span>产品</span>
          <select id="bom-product">${opts}</select>
        </label>
        <span class="grow"></span>
        <button class="btn" id="bom-add">+ 新增用料</button>
      </div>
      <div class="card" id="bom-table"></div>

      <div class="card" style="margin-top:14px;padding:16px;">
        <div class="section-title"><h2>用料需求测算</h2></div>
        <div class="toolbar">
          <label class="field" style="margin:0">
            <span>计划产量</span>
            <input id="bom-qty" type="number" min="0" step="any" value="100" style="width:140px" />
          </label>
          <button class="btn ghost" id="bom-calc">测算</button>
          <span class="grow"></span>
          <span id="bom-flag"></span>
        </div>
        <div id="bom-req"></div>
      </div>`;

    const sel = container.querySelector("#bom-product");
    const tableEl = container.querySelector("#bom-table");
    const reqEl = container.querySelector("#bom-req");
    const flagEl = container.querySelector("#bom-flag");

    async function renderBom() {
      let items = [];
      try {
        items = await WO.api("/bom/items?product_id=" + sel.value);
      } catch (e) {
        WO.toast(e.message, true);
        return;
      }
      tableEl.innerHTML = `
        <table>
          <thead><tr>
            <th>物料编码</th><th>物料</th><th class="num">单位用量</th>
            <th class="num">损耗率</th><th class="num hide-sm">当前库存</th><th>操作</th>
          </tr></thead>
          <tbody>${items.map((b) => `
            <tr>
              <td><strong>${WO.esc(b.material_code) || "—"}</strong></td>
              <td>${WO.esc(b.material_name)}</td>
              <td class="num">${WO.fmt(b.qty_per)} ${WO.esc(b.unit) || ""}</td>
              <td class="num">${WO.fmt(b.loss_rate)}%</td>
              <td class="num hide-sm">${WO.fmt(b.stock || 0)}</td>
              <td><button class="btn subtle sm" data-del="${b.id}">删除</button></td>
            </tr>`).join("")}</tbody>
        </table>
        ${items.length ? "" : '<div class="empty">该产品暂无 BOM，点击右上角新增用料。</div>'}`;
      tableEl.querySelectorAll("[data-del]").forEach((btn) =>
        btn.addEventListener("click", () => delItem(btn.dataset.del)));
      reqEl.innerHTML = "";
      flagEl.innerHTML = "";
    }

    async function delItem(id) {
      try {
        await WO.api(`/bom/items/${id}/delete`, { method: "POST", body: {} });
        WO.toast("已删除");
        renderBom();
      } catch (e) {
        WO.toast(e.message, true);
      }
    }

    function openAdd() {
      WO.api("/materials").then((mats) => {
        if (!mats.length) { WO.toast("请先在「物料库存」中建立物料", true); return; }
        const mopts = mats
          .map((m) => `<option value="${m.id}">${WO.esc(m.code)} · ${WO.esc(m.name)}（库存 ${WO.fmt(m.stock)}${WO.esc(m.unit)}）</option>`)
          .join("");
        WO.openModal("新增用料", `
          <label class="field"><span class="req">物料</span><select id="bm-mat">${mopts}</select></label>
          <label class="field"><span class="req">单位用量</span><input id="bm-qty" type="number" min="0" step="any" placeholder="每件产品消耗" /></label>
          <label class="field"><span>损耗率(%)</span><input id="bm-loss" type="number" min="0" step="any" value="0" /></label>`,
          async () => {
            await WO.api("/bom/items", {
              method: "POST",
              body: {
                product_id: Number(sel.value),
                material_id: Number(doc.getElementById("bm-mat").value),
                qty_per: Number(doc.getElementById("bm-qty").value || 0),
                loss_rate: Number(doc.getElementById("bm-loss").value || 0),
              },
            });
            WO.toast("已新增用料");
            renderBom();
          });
      });
    }

    async function calc() {
      const qty = Number(container.querySelector("#bom-qty").value || 0);
      let res;
      try {
        res = await WO.api(`/bom/requirements?product_id=${sel.value}&qty=${qty}`);
      } catch (e) {
        WO.toast(e.message, true);
        return;
      }
      flagEl.innerHTML = res.items.length
        ? `<span class="badge ${res.has_shortage ? "p-urgent" : "s-completed"}">${res.has_shortage ? "存在缺料" : "库存充足"}</span>`
        : "";
      if (!res.items.length) {
        reqEl.innerHTML = '<div class="empty">该产品暂无 BOM，无法测算。</div>';
        return;
      }
      reqEl.innerHTML = `
        <table>
          <thead><tr>
            <th>物料</th><th class="num">需求量</th><th class="num">现有库存</th>
            <th class="num">缺口</th><th>采购建议</th>
          </tr></thead>
          <tbody>${res.items.map((it) => `
            <tr>
              <td>${WO.esc(it.material_name)}</td>
              <td class="num">${WO.fmt(it.required)} ${WO.esc(it.unit) || ""}</td>
              <td class="num">${WO.fmt(it.stock)}</td>
              <td class="num ${it.shortage > 0 ? "overdue" : ""}">${WO.fmt(it.shortage)}</td>
              <td>${it.shortage > 0
                ? `<span class="badge p-high">需采购 ${WO.fmt(it.shortage)} ${WO.esc(it.unit) || ""}</span>`
                : '<span class="badge s-completed">充足</span>'}</td>
            </tr>`).join("")}</tbody>
        </table>`;
    }

    sel.addEventListener("change", renderBom);
    container.querySelector("#bom-add").addEventListener("click", openAdd);
    container.querySelector("#bom-calc").addEventListener("click", calc);
    await renderBom();
  },
});
