// 报表中心：只读聚合现有数据，画统计卡 + 纯 CSS / 内联 SVG 图表（无任何外部库）。
WO.registerModule({
  id: "reports",
  label: "报表中心",

  async refresh(container) {
    const esc = WO.esc, fmt = WO.fmt;

    // 并行拉取全部报表数据
    const [sum, output, quality, status, workshop, flow] = await Promise.all([
      WO.api("/reports/summary"),
      WO.api("/reports/output-trend"),
      WO.api("/reports/quality-trend"),
      WO.api("/reports/status-distribution"),
      WO.api("/reports/workshop-output"),
      WO.api("/reports/material-flow"),
    ]);

    // ── 头条统计卡 ──────────────────────────────────────────────
    const stats = [
      { label: "工单总数", value: fmt(sum.total_orders) },
      { label: "完工数", value: fmt(sum.completed_orders), cls: "ok" },
      { label: "累计产出", value: fmt(sum.total_output), cls: "accent" },
      { label: "累计不良", value: fmt(sum.total_defect), cls: "danger" },
      { label: "平均合格率", value: sum.avg_pass_rate + "%", cls: "warn" },
      { label: "物料数", value: fmt(sum.materials) },
    ];
    const statsHtml = `<div class="stats">${stats.map((s) => `
      <div class="stat ${s.cls || ""}">
        <div class="label">${esc(s.label)}</div>
        <div class="value">${esc(String(s.value))}</div>
      </div>`).join("")}</div>`;

    // ── 近 14 天日产量柱状图 ─────────────────────────────────────
    const maxOut = Math.max(1, ...output.map((d) => d.qty_ok + d.qty_defect));
    const outHasData = output.some((d) => d.qty_ok || d.qty_defect);
    const outBars = output.map((d, i) => {
      const total = d.qty_ok + d.qty_defect;
      const okH = Math.round((d.qty_ok / maxOut) * 100);
      const defH = Math.round((d.qty_defect / maxOut) * 100);
      const showDate = i % 2 === 0 || i === output.length - 1;
      const md = d.date.slice(5);
      return `<div class="rp-col" title="${esc(d.date)} 合格 ${fmt(d.qty_ok)} / 不良 ${fmt(d.qty_defect)}">
        <div class="rp-bar-wrap">
          <div class="rp-seg rp-defect" style="height:${defH}%"></div>
          <div class="rp-seg rp-ok" style="height:${okH}%"></div>
        </div>
        <div class="rp-xlabel">${showDate ? esc(md) : ""}</div>
      </div>`;
    }).join("");
    const outputCard = `
      <div class="card">
        <div class="section-title"><h2>近 14 天日产量</h2>
          <span class="rp-legend"><i class="rp-ok"></i>合格 <i class="rp-defect"></i>不良</span>
        </div>
        ${outHasData
          ? `<div class="rp-chart">${outBars}</div>`
          : '<div class="empty">暂无产量数据</div>'}
      </div>`;

    // ── 近 14 天质检合格率（内联 SVG 折线）──────────────────────
    const qHasData = quality.some((d) => d.inspected);
    let qualityCard;
    if (qHasData) {
      const W = 560, H = 160, padL = 30, padB = 22, padT = 10;
      const innerW = W - padL - 10, innerH = H - padB - padT;
      const n = quality.length;
      const x = (i) => padL + (n <= 1 ? innerW / 2 : (innerW * i) / (n - 1));
      const y = (v) => padT + innerH - (v / 100) * innerH;
      const pts = quality.map((d, i) => `${x(i).toFixed(1)},${y(d.pass_rate).toFixed(1)}`).join(" ");
      const dots = quality.map((d, i) =>
        `<circle cx="${x(i).toFixed(1)}" cy="${y(d.pass_rate).toFixed(1)}" r="2.5" fill="var(--accent)">
          <title>${esc(d.date)} 合格率 ${d.pass_rate}%（送检 ${fmt(d.inspected)}）</title></circle>`).join("");
      const grid = [0, 50, 100].map((v) =>
        `<line x1="${padL}" y1="${y(v)}" x2="${W - 10}" y2="${y(v)}" stroke="var(--line)" stroke-width="1"/>
         <text x="2" y="${(y(v) + 3).toFixed(1)}" font-size="9" fill="var(--muted)">${v}</text>`).join("");
      const xlabels = quality.map((d, i) =>
        (i % 2 === 0 || i === n - 1)
          ? `<text x="${x(i).toFixed(1)}" y="${H - 6}" font-size="9" fill="var(--muted)" text-anchor="middle">${esc(d.date.slice(5))}</text>`
          : "").join("");
      qualityCard = `
        <div class="card">
          <div class="section-title"><h2>近 14 天质检合格率</h2></div>
          <svg viewBox="0 0 ${W} ${H}" class="rp-svg" preserveAspectRatio="none">
            ${grid}
            <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2"/>
            ${dots}
            ${xlabels}
          </svg>
        </div>`;
    } else {
      qualityCard = `<div class="card"><div class="section-title"><h2>近 14 天质检合格率</h2></div>
        <div class="empty">暂无质检数据</div></div>`;
    }

    // ── 工单状态分布 ────────────────────────────────────────────
    const totalWo = status.reduce((a, s) => a + s.count, 0);
    const statusRows = status.map((s) => {
      const pct = totalWo ? Math.round((s.count / totalWo) * 100) : 0;
      return `<div class="rp-row">
        <span class="badge s-${s.status}">${esc(s.status_label)}</span>
        <div class="bar rp-grow"><span style="width:${pct}%"></span></div>
        <span class="rp-val">${fmt(s.count)}</span>
      </div>`;
    }).join("");
    const statusCard = `
      <div class="card">
        <div class="section-title"><h2>工单状态分布</h2></div>
        ${totalWo ? statusRows : '<div class="empty">暂无工单</div>'}
      </div>`;

    // ── 车间产出 ────────────────────────────────────────────────
    const workshopRows = workshop.map((w) => {
      const pct = Math.min(100, w.rate);
      return `<div class="rp-row">
        <span class="rp-name">${esc(w.workshop)}</span>
        <div class="bar rp-grow"><span style="width:${pct}%"></span></div>
        <span class="rp-val">${fmt(w.completed)}/${fmt(w.planned)} · ${w.rate}%</span>
      </div>`;
    }).join("");
    const workshopCard = `
      <div class="card">
        <div class="section-title"><h2>车间产出</h2></div>
        ${workshop.length ? workshopRows : '<div class="empty">暂无车间数据</div>'}
      </div>`;

    // ── 物料出入库汇总 ──────────────────────────────────────────
    const flowRows = flow.map((m) => `
      <tr>
        <td>${esc(m.material_name)}</td>
        <td class="num">${fmt(m.in_qty)}</td>
        <td class="num">${fmt(m.out_qty)}</td>
      </tr>`).join("");
    const flowCard = `
      <div class="card">
        <div class="section-title"><h2>物料出入库汇总</h2></div>
        ${flow.length
          ? `<table><thead><tr><th>物料</th><th class="num">入库</th><th class="num">出库</th></tr></thead>
             <tbody>${flowRows}</tbody></table>`
          : '<div class="empty">暂无库存流水</div>'}
      </div>`;

    container.innerHTML = `
      <style>
        .rp-chart { display:flex; align-items:flex-end; gap:6px; height:160px; padding-top:8px; }
        .rp-col { flex:1; display:flex; flex-direction:column; align-items:center; height:100%; }
        .rp-bar-wrap { flex:1; width:100%; display:flex; flex-direction:column; justify-content:flex-end; }
        .rp-seg { width:100%; }
        .rp-ok { background:var(--accent); border-radius:3px 3px 0 0; }
        .rp-defect { background:var(--danger); border-radius:3px 3px 0 0; }
        .rp-xlabel { font-size:10px; color:var(--muted); margin-top:4px; height:12px; }
        .rp-legend { font-size:12px; color:var(--muted); display:flex; align-items:center; gap:6px; }
        .rp-legend i { display:inline-block; width:10px; height:10px; border-radius:2px; }
        .rp-legend i.rp-ok { background:var(--accent); }
        .rp-legend i.rp-defect { background:var(--danger); }
        .rp-svg { width:100%; height:auto; display:block; }
        .rp-row { display:flex; align-items:center; gap:10px; margin:8px 0; }
        .rp-grow { flex:1; height:10px; width:auto; }
        .rp-val { min-width:120px; text-align:right; font-size:13px; color:var(--muted); }
        .rp-name { min-width:80px; font-weight:600; font-size:13px; }
      </style>
      ${statsHtml}
      ${outputCard}
      ${qualityCard}
      ${statusCard}
      ${workshopCard}
      ${flowCard}`;
  },
});
