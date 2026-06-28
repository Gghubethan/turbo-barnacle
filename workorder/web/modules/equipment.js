"use strict";

// 设备管理：设备台账 + 点检/保养/维修记录，跟踪设备状态。
(function () {
  const STATUS = [
    ["running", "运行中"], ["idle", "闲置"],
    ["maintenance", "保养中"], ["fault", "故障"],
  ];
  const STATUS_LABEL = Object.fromEntries(STATUS);
  // 状态 → 徽章样式
  const STATUS_BADGE = {
    running: "s-producing",
    idle: "s-pending",
    maintenance: "s-paused",
    fault: "p-urgent",
  };
  const LOG_TYPES = [
    ["inspect", "点检"], ["maintain", "保养"], ["repair", "维修"],
  ];
  const LOG_BADGE = {
    inspect: "s-producing",
    maintain: "s-paused",
    repair: "p-high",
  };

  // 维护流水卡片的展开状态（在一次会话内保持）
  let showLogs = false;

  function statusBadge(s) {
    return `<span class="badge ${STATUS_BADGE[s] || ""}">${WO.esc(STATUS_LABEL[s] || s)}</span>`;
  }

  WO.registerModule({
    id: "equipment",
    label: "设备管理",
    async refresh(container) {
      const rows = await WO.api("/equipment");
      const doc = container.ownerDocument;

      container.innerHTML = `
        <div class="toolbar">
          <span class="grow"></span>
          <button class="btn ghost" id="eq-toggle-logs">${showLogs ? "收起维护流水" : "维护流水"}</button>
          <button class="btn" id="eq-new">+ 新建设备</button>
        </div>
        <div class="card">
          <table>
            <thead><tr>
              <th>编码</th><th>名称</th><th class="hide-sm">型号</th>
              <th class="hide-sm">位置</th><th>负责人</th><th>状态</th><th>操作</th>
            </tr></thead>
            <tbody>${rows.map((r) => `
              <tr>
                <td>${WO.esc(r.code)}</td>
                <td>${WO.esc(r.name)}</td>
                <td class="hide-sm">${WO.esc(r.model || "")}</td>
                <td class="hide-sm">${WO.esc(r.location || "")}</td>
                <td>${WO.esc(r.owner || "")}</td>
                <td>${statusBadge(r.status)}</td>
                <td>
                  <button class="btn sm subtle" data-act="status" data-id="${r.id}" data-status="${r.status}">改状态</button>
                  <button class="btn sm ghost" data-act="log" data-id="${r.id}" data-name="${WO.esc(r.name)}">维护记录</button>
                </td>
              </tr>`).join("")}</tbody>
          </table>
          ${rows.length ? "" : '<div class="empty">暂无设备</div>'}
        </div>
        <div id="eq-logs-wrap"></div>`;

      // 新建设备
      container.querySelector("#eq-new").addEventListener("click", () => {
        WO.openModal("新建设备", `
          <label class="field"><span class="req">设备编码</span><input id="eq-f-code" placeholder="如：CNC-04" /></label>
          <label class="field"><span class="req">设备名称</span><input id="eq-f-name" /></label>
          <label class="field"><span>型号</span><input id="eq-f-model" /></label>
          <label class="field"><span>位置</span><input id="eq-f-location" /></label>
          <label class="field"><span>负责人</span><input id="eq-f-owner" /></label>`,
          async () => {
            await WO.api("/equipment", {
              method: "POST",
              body: {
                code: doc.getElementById("eq-f-code").value.trim(),
                name: doc.getElementById("eq-f-name").value.trim(),
                model: doc.getElementById("eq-f-model").value.trim(),
                location: doc.getElementById("eq-f-location").value.trim(),
                owner: doc.getElementById("eq-f-owner").value.trim(),
              },
            });
            WO.toast("已创建");
            this.refresh(container);
          });
      });

      // 改状态 / 维护记录
      container.querySelectorAll("button[data-act]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.dataset.id;
          if (btn.dataset.act === "status") {
            const cur = btn.dataset.status;
            WO.openModal("修改设备状态", `
              <label class="field"><span class="req">状态</span><select id="eq-st">
                ${STATUS.map(([v, l]) => `<option value="${v}" ${v === cur ? "selected" : ""}>${l}</option>`).join("")}
              </select></label>`,
              async () => {
                await WO.api(`/equipment/${id}/status`, {
                  method: "POST",
                  body: { status: doc.getElementById("eq-st").value },
                });
                WO.toast("状态已更新");
                this.refresh(container);
              });
          } else {
            const name = btn.dataset.name;
            WO.openModal("维护记录 · " + name, `
              <label class="field"><span class="req">类型</span><select id="eq-lt">
                ${LOG_TYPES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
              </select></label>
              <label class="field"><span class="req">内容</span><textarea id="eq-lc" placeholder="点检/保养/维修内容…"></textarea></label>
              <label class="field"><span>操作人</span><input id="eq-lo" /></label>
              <label class="field"><span>费用</span><input id="eq-lcost" type="number" min="0" step="any" value="0" /></label>`,
              async () => {
                await WO.api(`/equipment/${id}/logs`, {
                  method: "POST",
                  body: {
                    type: doc.getElementById("eq-lt").value,
                    content: doc.getElementById("eq-lc").value.trim(),
                    operator: doc.getElementById("eq-lo").value.trim(),
                    cost: doc.getElementById("eq-lcost").value || 0,
                  },
                });
                WO.toast("记录已保存");
                this.refresh(container);
              });
          }
        });
      });

      // 维护流水开关
      container.querySelector("#eq-toggle-logs").addEventListener("click", async () => {
        showLogs = !showLogs;
        await renderLogs(container);
        container.querySelector("#eq-toggle-logs").textContent =
          showLogs ? "收起维护流水" : "维护流水";
      });

      if (showLogs) await renderLogs(container);
    },
  });

  async function renderLogs(container) {
    const wrap = container.querySelector("#eq-logs-wrap");
    if (!wrap) return;
    if (!showLogs) {
      wrap.innerHTML = "";
      return;
    }
    const logs = await WO.api("/equipment-logs");
    wrap.innerHTML = `
      <div class="section-title"><h2>维护流水</h2></div>
      <div class="card">
        <table>
          <thead><tr>
            <th>时间</th><th>设备</th><th>类型</th><th>内容</th>
            <th>操作人</th><th class="num">费用</th>
          </tr></thead>
          <tbody>${logs.map((l) => `
            <tr>
              <td>${WO.esc(l.created_at)}</td>
              <td>${WO.esc(l.equipment_name)}</td>
              <td><span class="badge ${LOG_BADGE[l.type] || ""}">${WO.esc(l.type_label)}</span></td>
              <td>${WO.esc(l.content)}</td>
              <td>${WO.esc(l.operator || "")}</td>
              <td class="num">${WO.fmt(l.cost || 0)}</td>
            </tr>`).join("")}</tbody>
        </table>
        ${logs.length ? "" : '<div class="empty">暂无维护记录</div>'}
      </div>`;
  }
})();
