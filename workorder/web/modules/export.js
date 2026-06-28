"use strict";

// 数据导出：列出可导出的数据集，一键下载 CSV（后端返回带 BOM 的文件，Excel 直接可读）。
WO.registerModule({
  id: "export",
  label: "数据导出",
  async refresh(container) {
    let datasets = [];
    try {
      datasets = await WO.api("/export");
    } catch (e) {
      WO.toast(e.message, true);
    }

    container.innerHTML = `
      <div class="card" style="padding:18px;">
        <div class="section-title"><h2>数据导出</h2></div>
        <p style="color:var(--muted);margin:0 0 16px;">选择数据集导出为 CSV（UTF-8 含 BOM，Excel 可直接打开，枚举值已转中文）。</p>
        <div class="stats" id="ex-grid">
          ${datasets.map((d) => `
            <div class="stat">
              <div class="label">数据集</div>
              <div class="value" style="font-size:18px;">${WO.esc(d.label)}</div>
              <a class="btn sm" style="margin-top:10px;display:inline-block;text-decoration:none;"
                 href="/api/export/${encodeURIComponent(d.key)}.csv">导出 CSV</a>
            </div>`).join("")}
        </div>
        ${datasets.length ? "" : '<div class="empty">暂无可导出的数据集</div>'}
      </div>`;
  },
});
