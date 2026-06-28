"use strict";

// 采购管理：管理采购订单，收货时自动入库，打通「采购→库存」。
(function () {
  const STATUS = [
    ["pending", "待收货"], ["partial", "部分收货"],
    ["received", "已收货"], ["closed", "已关闭"],
  ];
  const STATUS_LABEL = Object.fromEntries(STATUS);
  // 状态 → 徽章样式
  const STATUS_BADGE = {
    pending: "s-pending",
    partial: "s-paused",
    received: "s-completed",
    closed: "s-closed",
  };

  // 当前状态筛选（一次会话内保持）
  let filterStatus = "all";

  function statusBadge(s) {
    return `<span class="badge ${STATUS_BADGE[s] || ""}">${WO.esc(STATUS_LABEL[s] || s)}</span>`;
  }

  WO.registerModule({
    id: "purchasing",
    label: "采购管理",
    async refresh(container) {
      const doc = container.ownerDocument;
      const rows = await WO.api(
        "/purchasing" + (filterStatus !== "all" ? `?status=${filterStatus}` : "")
      );

      container.innerHTML = `
        <div class="toolbar">
          <label class="field" style="margin:0">
            <select id="pu-filter">
              <option value="all">全部</option>
              ${STATUS.map(([v, l]) => `<option value="${v}" ${v === filterStatus ? "selected" : ""}>${l}</option>`).join("")}
            </select>
          </label>
          <span class="grow"></span>
          <button class="btn" id="pu-new">+ 新建采购单</button>
        </div>
        <div class="card">
          <table>
            <thead><tr>
              <th>采购单号</th><th>供应商</th><th>物料</th>
              <th class="num">采购数</th><th class="num">已收</th>
              <th>状态</th><th class="hide-sm">预计到货</th><th>操作</th>
            </tr></thead>
            <tbody>${rows.map((r) => `
              <tr>
                <td>${WO.esc(r.po_no)}</td>
                <td>${WO.esc(r.supplier)}</td>
                <td>${WO.esc(r.material_name)}</td>
                <td class="num">${WO.fmt(r.qty)}</td>
                <td class="num">${WO.fmt(r.received_qty)}</td>
                <td>${statusBadge(r.status)}</td>
                <td class="hide-sm">${WO.esc(r.expected_date || "")}</td>
                <td>
                  ${(r.status === "pending" || r.status === "partial")
                    ? `<button class="btn sm" data-act="receive" data-id="${r.id}" data-po="${WO.esc(r.po_no)}" data-qty="${r.qty}" data-recv="${r.received_qty}">收货</button>` : ""}
                  ${r.status !== "closed"
                    ? `<button class="btn sm subtle" data-act="close" data-id="${r.id}" data-po="${WO.esc(r.po_no)}">关闭</button>` : ""}
                </td>
              </tr>`).join("")}</tbody>
          </table>
          ${rows.length ? "" : '<div class="empty">暂无采购单</div>'}
        </div>`;

      // 状态筛选
      container.querySelector("#pu-filter").addEventListener("change", (e) => {
        filterStatus = e.target.value;
        this.refresh(container);
      });

      // 新建采购单
      container.querySelector("#pu-new").addEventListener("click", async () => {
        const materials = await WO.api("/materials");
        WO.openModal("新建采购单", `
          <label class="field"><span class="req">供应商</span><input id="pu-f-supplier" /></label>
          <label class="field"><span class="req">物料</span><select id="pu-f-material">
            ${materials.map((m) => `<option value="${m.id}">${WO.esc(m.code)}·${WO.esc(m.name)}（库存 ${WO.fmt(m.stock)}）</option>`).join("")}
          </select></label>
          <label class="field"><span class="req">采购数量</span><input id="pu-f-qty" type="number" min="0" step="any" /></label>
          <label class="field"><span>预计到货</span><input id="pu-f-date" type="date" /></label>`,
          async () => {
            await WO.api("/purchasing", {
              method: "POST",
              body: {
                supplier: doc.getElementById("pu-f-supplier").value.trim(),
                material_id: doc.getElementById("pu-f-material").value,
                qty: doc.getElementById("pu-f-qty").value,
                expected_date: doc.getElementById("pu-f-date").value,
              },
            });
            WO.toast("已创建");
            this.refresh(container);
          });
      });

      // 收货 / 关闭
      container.querySelectorAll("button[data-act]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.dataset.id;
          if (btn.dataset.act === "receive") {
            const remain = Number(btn.dataset.qty) - Number(btn.dataset.recv);
            WO.openModal("采购收货 · " + btn.dataset.po, `
              <label class="field"><span class="req">收货数量</span>
                <input id="pu-r-qty" type="number" min="0" step="any" placeholder="剩余可收 ${WO.fmt(remain)}" /></label>
              <label class="field"><span>操作人</span><input id="pu-r-op" /></label>`,
              async () => {
                await WO.api(`/purchasing/${id}/receive`, {
                  method: "POST",
                  body: {
                    qty: doc.getElementById("pu-r-qty").value,
                    operator: doc.getElementById("pu-r-op").value.trim(),
                  },
                });
                WO.toast("收货成功，已入库");
                this.refresh(container);
              });
          } else {
            WO.openModal("关闭采购单", `
              <p>确认关闭采购单 <b>${WO.esc(btn.dataset.po)}</b>？关闭后不可再收货。</p>`,
              async () => {
                await WO.api(`/purchasing/${id}/close`, { method: "POST", body: {} });
                WO.toast("已关闭");
                this.refresh(container);
              });
          }
        });
      });
    },
  });
})();
