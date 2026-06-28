// 计划排产：生产排产甘特看板。把未关闭工单按计划周期可视化到时间轴，
// 并支持把工单显式排到某条产线/日期/顺序（POST /planning/entries）。
WO.registerModule({
  id: "planning",
  label: "计划排产",

  async refresh(container) {
    // 闭包变量保存当前起始日期，供上一/下一周期平移。
    if (this._start === undefined) this._start = null;
    await render(this, container);
  },
});

// 状态 → 色条颜色变量
function barColor(status) {
  if (status === "producing") return "var(--accent)";
  if (status === "completed") return "var(--ok)";
  if (status === "paused") return "var(--muted)";
  return "var(--brand)";
}

async function render(self, container) {
  const q = self._start ? "?start=" + encodeURIComponent(self._start) : "";
  const data = await WO.api("/planning/board" + q);
  const { start, days, dates, orders } = data;
  self._start = start; // 同步真实起始（首次缺省由后端给出）
  const today = new Date().toISOString().slice(0, 10);
  const esc = WO.esc;

  // 按 workshop（车间）分组，未排期工单单独放
  const scheduled = orders.filter((o) => o.planned_start && o.planned_end);
  const unscheduled = orders.filter((o) => !o.planned_start || !o.planned_end);

  const groups = {};
  for (const o of scheduled) {
    const key = o.workshop || "未分配车间";
    (groups[key] = groups[key] || []).push(o);
  }

  // 网格列：固定左列 220px + days 列
  const gridCols = `grid-template-columns: 220px repeat(${days}, minmax(34px, 1fr));`;

  const headerCells = dates
    .map((d) => {
      const hi = d === today ? "background:#eef4ff;" : "";
      const mmdd = d.slice(5);
      return `<div class="pl-h" style="${hi}">${esc(mmdd)}</div>`;
    })
    .join("");

  function rowFor(o) {
    // 计算色条覆盖：planned_start..planned_end 落在 dates 范围内的列
    const si = dates.indexOf(o.planned_start);
    const ei = dates.indexOf(o.planned_end);
    let s = si, e = ei;
    // 部分超出窗口时裁剪到窗口边界（只要区间与窗口有交集）
    if (s < 0 && o.planned_start < dates[0] && o.planned_end >= dates[0]) s = 0;
    if (e < 0 && o.planned_end > dates[days - 1] && o.planned_start <= dates[days - 1]) e = days - 1;
    const visible = s >= 0 && e >= 0 && e >= s;

    const cells = dates
      .map((d, i) => {
        const hi = d === today ? "background:#eef4ff;" : "";
        let bar = "";
        if (visible && i >= s && i <= e) {
          const left = i === s;
          const right = i === e;
          const radius =
            (left ? "border-top-left-radius:6px;border-bottom-left-radius:6px;" : "") +
            (right ? "border-top-right-radius:6px;border-bottom-right-radius:6px;" : "");
          // 仅在起始格内渲染进度叠加文字，避免重复
          const prog = left
            ? `<span class="pl-prog" style="width:${Math.min(100, o.progress)}%"></span>` +
              `<span class="pl-lbl">${esc(o.order_no)}</span>`
            : "";
          bar = `<div class="pl-bar" style="background:${barColor(o.status)};${radius}">${prog}</div>`;
        }
        return `<div class="pl-cell" style="${hi}">${bar}</div>`;
      })
      .join("");

    return (
      `<div class="pl-fixed">` +
      `<div class="pl-no">${esc(o.order_no)}</div>` +
      `<div class="pl-sub">${esc(o.product_name)} ` +
      `<span class="badge s-${o.status}">${esc(o.status_label)}</span></div>` +
      `</div>` +
      cells
    );
  }

  let boardHtml = "";
  const groupKeys = Object.keys(groups);
  if (groupKeys.length) {
    boardHtml = groupKeys
      .map((g) => {
        const rows = groups[g].map(rowFor).join("");
        return (
          `<div class="pl-group">${esc(g)}</div>` +
          `<div class="pl-grid" style="${gridCols}">` +
          `<div class="pl-h pl-corner">工单 / 产品</div>${headerCells}${rows}</div>`
        );
      })
      .join("");
  } else {
    boardHtml = '<div class="empty">本周期内暂无已排期工单</div>';
  }

  const unschedHtml = unscheduled.length
    ? `<div class="card" style="margin-top:14px">
         <div class="section-title"><h2>未排期工单</h2></div>
         <table><thead><tr><th>工单号</th><th>产品</th><th>状态</th>
           <th class="num">计划数</th><th></th></tr></thead>
         <tbody>${unscheduled
           .map(
             (o) => `<tr>
               <td>${esc(o.order_no)}</td>
               <td>${esc(o.product_name)}</td>
               <td><span class="badge s-${o.status}">${esc(o.status_label)}</span></td>
               <td class="num">${WO.fmt(o.planned_qty)}</td>
               <td><button class="btn sm" data-plan="${o.work_order_id}"
                     data-no="${esc(o.order_no)}"
                     data-ws="${esc(o.workshop)}">排产</button></td>
             </tr>`
           )
           .join("")}</tbody></table></div>`
    : "";

  container.innerHTML = `
    <style>
      .pl-grid { display:grid; align-items:stretch; border:1px solid var(--line);
        border-radius:8px; overflow:hidden; background:var(--panel); margin-bottom:6px; }
      .pl-h { padding:8px 4px; font-size:11px; color:var(--muted); font-weight:600;
        text-align:center; background:#fafbfd; border-bottom:1px solid var(--line); }
      .pl-corner { text-align:left; padding-left:12px; }
      .pl-fixed { padding:8px 12px; border-bottom:1px solid var(--line);
        border-right:1px solid var(--line); }
      .pl-no { font-weight:600; font-size:13px; }
      .pl-sub { font-size:12px; color:var(--muted); margin-top:3px;
        display:flex; gap:6px; align-items:center; }
      .pl-cell { border-bottom:1px solid var(--line); position:relative;
        min-height:46px; display:flex; align-items:center; }
      .pl-bar { height:20px; width:100%; position:relative; opacity:.92;
        display:flex; align-items:center; overflow:hidden; }
      .pl-prog { position:absolute; left:0; top:0; bottom:0;
        background:rgba(0,0,0,.28); }
      .pl-lbl { position:relative; color:#fff; font-size:11px; font-weight:600;
        white-space:nowrap; padding-left:6px; z-index:1; }
      .pl-group { font-weight:600; margin:14px 0 6px; color:var(--brand); }
      .pl-legend { display:flex; gap:14px; align-items:center; font-size:12px;
        color:var(--muted); flex-wrap:wrap; }
      .pl-legend i { display:inline-block; width:14px; height:10px; border-radius:3px;
        margin-right:4px; vertical-align:middle; }
    </style>
    <div class="toolbar">
      <button class="btn ghost" id="pl-prev">‹ 上一周期</button>
      <button class="btn ghost" id="pl-next">下一周期 ›</button>
      <span class="grow"></span>
      <span class="pl-legend">
        <span><i style="background:var(--brand)"></i>计划</span>
        <span><i style="background:var(--accent)"></i>生产中</span>
        <span><i style="background:var(--ok)"></i>已完工</span>
        <span><i style="background:var(--muted)"></i>暂停</span>
      </span>
    </div>
    <div class="card">
      <div class="section-title"><h2>排产甘特 · ${esc(start)} 起 ${days} 天</h2></div>
      ${boardHtml}
    </div>
    ${unschedHtml}`;

  // 周期平移
  function shift(delta) {
    const base = new Date(start + "T00:00:00");
    base.setDate(base.getDate() + delta * days);
    self._start = base.toISOString().slice(0, 10);
    render(self, container);
  }
  container.querySelector("#pl-prev").addEventListener("click", () => shift(-1));
  container.querySelector("#pl-next").addEventListener("click", () => shift(1));

  // 未排期工单 → 排产弹窗
  container.querySelectorAll("[data-plan]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.dataset.plan;
      const ws = btn.dataset.ws || "";
      WO.openModal(
        "排产 · " + btn.dataset.no,
        `<label class="field"><span class="req">产线</span>
           <input id="pl-line" value="${esc(ws)}" placeholder="如 一号产线"/></label>
         <label class="field"><span>排产日期</span>
           <input id="pl-date" type="date"/></label>
         <label class="field"><span>顺序</span>
           <input id="pl-seq" type="number" value="0"/></label>
         <label class="field"><span>备注</span>
           <input id="pl-remark"/></label>`,
        async () => {
          const doc = container.ownerDocument;
          await WO.api("/planning/entries", {
            method: "POST",
            body: {
              work_order_id: Number(wid),
              line: doc.getElementById("pl-line").value.trim(),
              plan_date: doc.getElementById("pl-date").value,
              seq: Number(doc.getElementById("pl-seq").value || 0),
              remark: doc.getElementById("pl-remark").value.trim(),
            },
          });
          WO.toast("已排产");
          render(self, container);
        }
      );
    });
  });
}
