"use strict";

// 工序/工艺路线：选工单 → 查看/管理该工单的有序工序，按工序报工。
WO.registerModule({
  id: "routing",
  label: "工序管理",
  async refresh(container) {
    const self = this;
    const doc = container.ownerDocument;
    let currentWoId = null;

    // 工序状态 → 徽章色
    const badgeCls = (s) =>
      s === "doing" ? "s-producing" : s === "done" ? "s-completed" : "s-pending";

    let orders = [];
    try {
      orders = (await WO.api("/work-orders")).filter((w) => w.status !== "closed");
    } catch (e) {
      WO.toast(e.message, true);
    }

    const opts = orders
      .map((w) => `<option value="${w.id}">${WO.esc(w.order_no)} · ${WO.esc(w.product_name)}</option>`)
      .join("");

    container.innerHTML = `
      <div class="toolbar">
        <label class="field" style="margin:0">
          <span>工单</span>
          <select id="rt-wo">${opts || '<option value="">暂无可选工单</option>'}</select>
        </label>
        <span class="grow"></span>
        <button class="btn" id="rt-new" ${orders.length ? "" : "disabled"}>+ 新增工序</button>
      </div>
      <div class="card" id="rt-table"></div>`;

    const tableEl = container.querySelector("#rt-table");

    async function renderOps() {
      if (!currentWoId) {
        tableEl.innerHTML = '<div class="empty">请选择工单</div>';
        return;
      }
      let ops = [];
      try {
        ops = await WO.api(`/work-orders/${currentWoId}/operations`);
      } catch (e) {
        WO.toast(e.message, true);
        return;
      }
      tableEl.innerHTML = `
        <table>
          <thead><tr>
            <th class="num">工序号</th><th>工序名</th><th>工位</th>
            <th class="hide-sm">操作工</th><th class="num">计划数</th>
            <th class="num">完成数</th><th>进度</th><th>状态</th><th>操作</th>
          </tr></thead>
          <tbody>${ops.map((o) => `
            <tr>
              <td class="num">${o.seq}</td>
              <td><strong>${WO.esc(o.name)}</strong></td>
              <td>${WO.esc(o.workstation) || "—"}</td>
              <td class="hide-sm">${WO.esc(o.worker) || "—"}</td>
              <td class="num">${WO.fmt(o.planned_qty)}</td>
              <td class="num">${WO.fmt(o.completed_qty)}</td>
              <td>
                <div class="bar"><span style="width:${Math.min(100, o.progress)}%"></span></div>
                <small>${o.progress}%</small>
              </td>
              <td><span class="badge ${badgeCls(o.status)}">${WO.esc(o.status_label)}</span></td>
              <td>
                <button class="btn sm" data-report="${o.id}" ${o.status === "done" ? "disabled" : ""}>报工</button>
                <button class="btn subtle sm" data-del="${o.id}">删除</button>
              </td>
            </tr>`).join("")}</tbody>
        </table>
        ${ops.length ? "" : '<div class="empty">该工单暂无工序，点击右上角新增。</div>'}`;

      tableEl.querySelectorAll("[data-report]").forEach((btn) =>
        btn.addEventListener("click", () => openReport(btn.dataset.report)));
      tableEl.querySelectorAll("[data-del]").forEach((btn) =>
        btn.addEventListener("click", () => delOp(btn.dataset.del)));
    }

    function openReport(opId) {
      WO.openModal("工序报工", `
        <label class="field"><span class="req">报工数量</span><input id="rt-qty" type="number" min="0" step="any" placeholder="本次完成数量" /></label>
        <label class="field"><span>操作工</span><input id="rt-worker" placeholder="如：李师傅" /></label>`,
        async () => {
          await WO.api(`/operations/${opId}/report`, {
            method: "POST",
            body: {
              qty: Number(doc.getElementById("rt-qty").value || 0),
              worker: doc.getElementById("rt-worker").value.trim(),
            },
          });
          WO.toast("报工成功");
          renderOps();
        });
    }

    async function delOp(opId) {
      try {
        await WO.api(`/operations/${opId}/delete`, { method: "POST", body: {} });
        WO.toast("已删除");
        renderOps();
      } catch (e) {
        WO.toast(e.message, true);
      }
    }

    function openNew() {
      if (!currentWoId) {
        WO.toast("请先选择工单", true);
        return;
      }
      WO.openModal("新增工序", `
        <label class="field"><span class="req">工序名</span><input id="rt-name" placeholder="如：下料" /></label>
        <label class="field"><span>工位/设备</span><input id="rt-ws" placeholder="如：CNC03" /></label>
        <label class="field"><span class="req">计划数量</span><input id="rt-plan" type="number" min="0" step="any" /></label>
        <label class="field"><span>操作工</span><input id="rt-w" placeholder="如：王师傅" /></label>`,
        async () => {
          await WO.api(`/work-orders/${currentWoId}/operations`, {
            method: "POST",
            body: {
              name: doc.getElementById("rt-name").value.trim(),
              workstation: doc.getElementById("rt-ws").value.trim(),
              planned_qty: Number(doc.getElementById("rt-plan").value || 0),
              worker: doc.getElementById("rt-w").value.trim(),
            },
          });
          WO.toast("已新增工序");
          renderOps();
        });
    }

    const sel = container.querySelector("#rt-wo");
    container.querySelector("#rt-new").addEventListener("click", openNew);
    if (orders.length) {
      sel.addEventListener("change", () => {
        currentWoId = sel.value;
        renderOps();
      });
      currentWoId = sel.value;
    }
    await renderOps();
  },
});
