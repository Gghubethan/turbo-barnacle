"use strict";

// 销售订单：管理客户订单，一键下推生成生产工单，打通「销售→生产」。
WO.registerModule({
  id: "sales",
  label: "销售订单",
  async refresh(container) {
    const self = this;
    const doc = container.ownerDocument;

    // 状态 → 徽章色
    const badgeCls = (s) =>
      s === "pending" ? "s-pending"
        : s === "in_production" ? "s-producing"
        : s === "shipped" ? "s-completed"
        : "s-closed";

    // 当前筛选状态（默认全部）
    const filter = self._filter || "all";

    let rows = [];
    try {
      const q = filter && filter !== "all" ? `?status=${encodeURIComponent(filter)}` : "";
      rows = await WO.api(`/sales${q}`);
    } catch (e) {
      WO.toast(e.message, true);
    }

    const statusOpts = [
      ["all", "全部"],
      ["pending", "待生产"],
      ["in_production", "生产中"],
      ["shipped", "已发货"],
      ["closed", "已关闭"],
    ].map(([v, t]) =>
      `<option value="${v}" ${v === filter ? "selected" : ""}>${t}</option>`).join("");

    container.innerHTML = `
      <div class="toolbar">
        <label class="field" style="margin:0">
          <span>状态</span>
          <select id="sl-filter">${statusOpts}</select>
        </label>
        <span class="grow"></span>
        <button class="btn" id="sl-new">+ 新建订单</button>
      </div>
      <div class="card">
        <table>
          <thead><tr>
            <th>订单号</th><th>客户</th><th>产品</th>
            <th class="num">数量</th><th class="hide-sm">交期</th>
            <th>状态</th><th class="hide-sm">关联工单</th><th>操作</th>
          </tr></thead>
          <tbody>${rows.map((r) => `
            <tr>
              <td><strong>${WO.esc(r.order_no)}</strong></td>
              <td>${WO.esc(r.customer)}</td>
              <td>${WO.esc(r.product_name)}</td>
              <td class="num">${WO.fmt(r.qty)}</td>
              <td class="hide-sm">${WO.esc(r.due_date) || "—"}</td>
              <td><span class="badge ${badgeCls(r.status)}">${WO.esc(r.status_label)}</span></td>
              <td class="hide-sm">${r.work_order_id ? "#" + r.work_order_id : "—"}</td>
              <td>
                ${r.status === "pending"
                  ? `<button class="btn sm" data-push="${r.id}">下推生产</button>`
                  : r.status === "in_production"
                  ? `<button class="btn sm" data-ship="${r.id}">发货</button>`
                  : r.status === "shipped"
                  ? `<button class="btn subtle sm" data-close="${r.id}">关闭</button>`
                  : "—"}
              </td>
            </tr>`).join("")}</tbody>
        </table>
        ${rows.length ? "" : '<div class="empty">暂无销售订单，点击右上角新建。</div>'}
      </div>`;

    // 状态筛选
    container.querySelector("#sl-filter").addEventListener("change", (e) => {
      self._filter = e.target.value;
      self.refresh(container);
    });

    // 操作：下推 / 发货 / 关闭
    async function act(path, okMsg) {
      try {
        await WO.api(path, { method: "POST", body: {} });
        WO.toast(okMsg);
        self.refresh(container);
      } catch (e) {
        WO.toast(e.message, true);
      }
    }
    container.querySelectorAll("[data-push]").forEach((b) =>
      b.addEventListener("click", () => act(`/sales/${b.dataset.push}/push`, "已下推生产")));
    container.querySelectorAll("[data-ship]").forEach((b) =>
      b.addEventListener("click", () => act(`/sales/${b.dataset.ship}/ship`, "已发货")));
    container.querySelectorAll("[data-close]").forEach((b) =>
      b.addEventListener("click", () => act(`/sales/${b.dataset.close}/close`, "已关闭")));

    // 新建订单
    container.querySelector("#sl-new").addEventListener("click", async () => {
      let products = [];
      try {
        products = await WO.api("/products");
      } catch (e) {
        WO.toast(e.message, true);
        return;
      }
      if (!products.length) {
        WO.toast("暂无产品，请先在产品档案中添加", true);
        return;
      }
      const pOpts = products
        .map((p) => `<option value="${p.id}">${WO.esc(p.name)}</option>`)
        .join("");
      WO.openModal("新建销售订单", `
        <label class="field"><span class="req">客户</span><input id="sl-customer" placeholder="如：华东机械有限公司" /></label>
        <label class="field"><span class="req">产品</span><select id="sl-product">${pOpts}</select></label>
        <label class="field"><span class="req">数量</span><input id="sl-qty" type="number" min="0" step="any" /></label>
        <label class="field"><span>交期</span><input id="sl-due" type="date" /></label>
        <label class="field"><span>备注</span><input id="sl-remark" placeholder="选填" /></label>`,
        async () => {
          await WO.api("/sales", {
            method: "POST",
            body: {
              customer: doc.getElementById("sl-customer").value.trim(),
              product_id: Number(doc.getElementById("sl-product").value),
              qty: Number(doc.getElementById("sl-qty").value || 0),
              due_date: doc.getElementById("sl-due").value,
              remark: doc.getElementById("sl-remark").value.trim(),
            },
          });
          WO.toast("已创建订单");
          self.refresh(container);
        });
    });
  },
});
