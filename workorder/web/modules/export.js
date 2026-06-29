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
              <button class="btn sm" style="margin-top:10px;" data-export="${WO.esc(d.key)}" data-label="${WO.esc(d.label)}">导出 CSV</button>
            </div>`).join("")}
        </div>
        ${datasets.length ? "" : '<div class="empty">暂无可导出的数据集</div>'}
      </div>`;

    container.querySelectorAll("[data-export]").forEach((btn) =>
      btn.addEventListener("click", () => downloadCsv(btn.dataset.export, btn.dataset.label)));
  },
});

// 通过 fetch + Blob 下载，兼容真实后端与浏览器内 mock 两种模式。
async function downloadCsv(key, label) {
  try {
    const res = await fetch("/api/export/" + encodeURIComponent(key) + ".csv",
      { headers: AUTH && AUTH.token ? { Authorization: "Bearer " + AUTH.token } : {} });
    if (!res.ok) throw new Error("导出失败 (" + res.status + ")");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (label || key) + ".csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    WO.toast("已导出 " + (label || key));
  } catch (e) {
    WO.toast(e.message, true);
  }
}
