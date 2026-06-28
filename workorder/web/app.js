"use strict";

// ── 工具 ────────────────────────────────────────────────────────────────
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = isErr ? "show err" : "show";
  setTimeout(() => (t.className = ""), 2600);
}

async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (_) { /* 可能无 body */ }
  if (!res.ok) throw new Error((data && data.error) || `请求失败 (${res.status})`);
  return data;
}

const PRIORITIES = [
  ["urgent", "紧急"], ["high", "高"], ["normal", "普通"], ["low", "低"],
];
const EXC_CATS = [
  ["equipment", "设备故障"], ["material", "物料缺料"], ["quality", "质量问题"],
  ["process", "工艺异常"], ["other", "其他"],
];
// 各状态可执行的动作（前端按钮渲染用；后端是唯一裁决方）
const ACTIONS = {
  pending: [["dispatch", "派工", "btn"], ["cancel", "取消", "subtle"]],
  dispatched: [["start", "开工", "btn"], ["cancel", "取消", "subtle"]],
  producing: [["pause", "暂停", "subtle"], ["complete", "完工", "btn"]],
  paused: [["start", "恢复", "btn"], ["complete", "完工", "ghost"], ["cancel", "取消", "subtle"]],
  completed: [["close", "关闭工单", "subtle"]],
  closed: [],
};

let STATUS_LABELS = {};
let PRODUCTS_CACHE = [];

// ── 视图切换 ──────────────────────────────────────────────────────────────
$$("nav.tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("nav.tabs button").forEach((b) => b.classList.remove("active"));
    $$(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.view).classList.add("active");
    refreshView(btn.dataset.view);
  });
});

function refreshView(view) {
  if (view === "dashboard") loadDashboard();
  else if (view === "orders") loadOrders();
  else if (view === "exceptions") loadExceptions();
  else if (view === "products") loadProducts();
}

// ── 看板 ────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const d = await api("/dashboard");
    STATUS_LABELS = d.status_labels;
    const cards = [
      { label: "工单总数", value: d.total_orders, cls: "accent" },
      { label: "计划完成率", value: d.completion_rate + "%", cls: "ok" },
      { label: "待处理异常", value: d.open_exceptions, cls: d.open_exceptions ? "danger" : "" },
      { label: "超期工单", value: d.overdue_orders, cls: d.overdue_orders ? "warn" : "" },
      { label: "计划总量", value: fmt(d.planned_qty) },
      { label: "已完成", value: fmt(d.completed_qty), cls: "ok" },
      { label: "不良率", value: d.defect_rate + "%", cls: d.defect_rate > 5 ? "danger" : "" },
      { label: "今日产出", value: fmt(d.today_completed), cls: "accent" },
    ];
    $("#stat-cards").innerHTML = cards.map((c) => `
      <div class="stat ${c.cls || ""}">
        <div class="label">${c.label}</div>
        <div class="value">${c.value}</div>
      </div>`).join("");

    $("#status-grid").innerHTML = Object.entries(d.status_labels).map(([k, label]) => `
      <div class="status-pill">
        <div class="n">${d.by_status[k] || 0}</div>
        <div class="t"><span class="badge s-${k}">${label}</span></div>
      </div>`).join("");
  } catch (e) { toast(e.message, true); }
}

const fmt = (n) => Number(n).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

// ── 工单列表 ──────────────────────────────────────────────────────────────
async function loadOrders() {
  await ensureStatusLabels();
  populateStatusFilter();
  const status = $("#filter-status").value;
  const keyword = $("#search").value.trim();
  const qs = new URLSearchParams();
  if (status && status !== "all") qs.set("status", status);
  if (keyword) qs.set("keyword", keyword);
  try {
    const rows = await api("/work-orders" + (qs.toString() ? "?" + qs : ""));
    const tbody = $("#orders-tbody");
    $("#orders-empty").style.display = rows.length ? "none" : "block";
    tbody.innerHTML = rows.map((w) => `
      <tr data-id="${w.id}">
        <td><strong>${esc(w.order_no)}</strong></td>
        <td>${esc(w.product_name)}</td>
        <td class="num">${fmt(w.completed_qty)} / ${fmt(w.planned_qty)}</td>
        <td>
          <div class="bar"><span style="width:${Math.min(100, w.progress)}%"></span></div>
          <small>${w.progress}%</small>
        </td>
        <td><span class="badge p-${w.priority}">${esc(w.priority_label)}</span></td>
        <td><span class="badge s-${w.status}">${esc(w.status_label)}</span></td>
        <td class="hide-sm">${esc(w.assignee) || "—"}</td>
        <td class="hide-sm ${w.overdue ? "overdue" : ""}">${esc(w.planned_end) || "—"}${w.overdue ? " ⚠" : ""}</td>
      </tr>`).join("");
    $$("#orders-tbody tr").forEach((tr) =>
      tr.addEventListener("click", () => openOrder(tr.dataset.id)));
  } catch (e) { toast(e.message, true); }
}

async function ensureStatusLabels() {
  if (Object.keys(STATUS_LABELS).length) return;
  const d = await api("/dashboard");
  STATUS_LABELS = d.status_labels;
}

function populateStatusFilter() {
  const sel = $("#filter-status");
  if (sel.options.length > 1) return;
  Object.entries(STATUS_LABELS).forEach(([k, v]) => {
    const o = document.createElement("option");
    o.value = k; o.textContent = v; sel.appendChild(o);
  });
}

$("#btn-refresh").addEventListener("click", loadOrders);
$("#filter-status").addEventListener("change", loadOrders);
let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadOrders, 300);
});

// ── 工单详情抽屉 ──────────────────────────────────────────────────────────
async function openOrder(id) {
  try {
    const [w, reports, excs] = await Promise.all([
      api("/work-orders/" + id),
      api(`/work-orders/${id}/reports`),
      api(`/work-orders/${id}/exceptions`),
    ]);
    $("#drawer-title").textContent = w.order_no;
    $("#drawer-body").innerHTML = renderOrderDetail(w, reports, excs);
    bindOrderActions(w);
    showDrawer();
  } catch (e) { toast(e.message, true); }
}

function renderOrderDetail(w, reports, excs) {
  const actions = (ACTIONS[w.status] || []).map(([a, label, cls]) =>
    `<button class="btn ${cls} sm" data-action="${a}">${label}</button>`).join("");
  const reportBtn = (w.status === "producing" || w.status === "paused")
    ? `<button class="btn sm" data-report>+ 报工</button>` : "";
  const excBtn = `<button class="btn ghost sm" data-add-exc>+ 上报异常</button>`;

  return `
    <div class="action-row">${actions}${reportBtn}${excBtn}</div>
    <div class="sub-card">
      <dl class="kv">
        <dt>产品</dt><dd>${esc(w.product_name)}</dd>
        <dt>状态</dt><dd><span class="badge s-${w.status}">${esc(w.status_label)}</span>
          <span class="badge p-${w.priority}">${esc(w.priority_label)}</span></dd>
        <dt>计划数量</dt><dd>${fmt(w.planned_qty)}</dd>
        <dt>已完成</dt><dd>${fmt(w.completed_qty)}（${w.progress}%）　不良 ${fmt(w.defect_qty)}</dd>
        <dt>负责人</dt><dd>${esc(w.assignee) || "—"}</dd>
        <dt>车间</dt><dd>${esc(w.workshop) || "—"}</dd>
        <dt>计划周期</dt><dd>${esc(w.planned_start) || "—"} ~ ${esc(w.planned_end) || "—"}
          ${w.overdue ? '<span class="overdue">（已超期）</span>' : ""}</dd>
        <dt>实际开工</dt><dd>${esc(w.actual_start) || "—"}</dd>
        <dt>实际完工</dt><dd>${esc(w.actual_end) || "—"}</dd>
        ${w.remark ? `<dt>备注</dt><dd>${esc(w.remark)}</dd>` : ""}
      </dl>
    </div>

    <div class="sub-card">
      <h4>报工记录 <span style="color:var(--muted);font-weight:400">${reports.length} 条</span></h4>
      ${reports.length ? reports.map((r) => `
        <div class="timeline-item">
          <div><strong>${esc(r.reporter)}</strong> 合格 ${fmt(r.qty_ok)}，不良 ${fmt(r.qty_defect)}</div>
          <div class="meta">${esc(r.report_time)}${r.remark ? " · " + esc(r.remark) : ""}</div>
        </div>`).join("") : '<div class="empty">暂无报工</div>'}
    </div>

    <div class="sub-card">
      <h4>关联异常 <span style="color:var(--muted);font-weight:400">${excs.length} 条</span></h4>
      ${excs.length ? excs.map((e) => `
        <div class="timeline-item">
          <div><span class="badge ${e.status === "open" ? "p-high" : "s-completed"}">${e.status === "open" ? "待处理" : "已处理"}</span>
            ${esc(e.category_label)}：${esc(e.description)}</div>
          <div class="meta">${esc(e.reporter) || "—"} · ${esc(e.created_at)}${e.resolution ? " · 处理：" + esc(e.resolution) : ""}</div>
        </div>`).join("") : '<div class="empty">暂无异常</div>'}
    </div>`;
}

function bindOrderActions(w) {
  $$("#drawer-body [data-action]").forEach((btn) =>
    btn.addEventListener("click", () => doTransition(w, btn.dataset.action)));
  const rep = $("#drawer-body [data-report]");
  if (rep) rep.addEventListener("click", () => openReportModal(w));
  $("#drawer-body [data-add-exc]").addEventListener("click", () => openExcModal(w.id));
}

async function doTransition(w, action) {
  // 派工需要补负责人
  if (action === "dispatch") {
    openModal("派工", `
      <label class="field"><span class="req">负责人</span>
        <input id="f-assignee" value="${esc(w.assignee)}" placeholder="如：张工" /></label>`,
      async () => {
        const assignee = $("#f-assignee").value.trim();
        if (!assignee) throw new Error("请填写负责人");
        await api(`/work-orders/${w.id}/transition`, { method: "POST", body: { action, assignee } });
        afterChange("已派工");
        openOrder(w.id);
      });
    return;
  }
  const confirmText = { cancel: "确认取消该工单？", close: "确认关闭该工单？" }[action];
  if (confirmText && !confirm(confirmText)) return;
  try {
    await api(`/work-orders/${w.id}/transition`, { method: "POST", body: { action } });
    afterChange("操作成功");
    openOrder(w.id);
  } catch (e) { toast(e.message, true); }
}

function openReportModal(w) {
  openModal("报工 · " + w.order_no, `
    <label class="field"><span class="req">报工人</span><input id="r-reporter" placeholder="如：李师傅" /></label>
    <label class="field"><span>合格数量</span><input id="r-ok" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>不良数量</span><input id="r-defect" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>备注</span><textarea id="r-remark"></textarea></label>
    <div class="meta" style="color:var(--muted);font-size:12px">提示：累计完成达到计划数量将自动完工。</div>`,
    async () => {
      await api(`/work-orders/${w.id}/reports`, {
        method: "POST",
        body: {
          reporter: $("#r-reporter").value.trim(),
          qty_ok: Number($("#r-ok").value || 0),
          qty_defect: Number($("#r-defect").value || 0),
          remark: $("#r-remark").value.trim(),
        },
      });
      afterChange("报工成功");
      openOrder(w.id);
    });
}

function afterChange(msg) {
  toast(msg);
}

// ── 新建工单 ──────────────────────────────────────────────────────────────
$("#btn-new-order").addEventListener("click", async () => {
  await ensureProducts();
  if (!PRODUCTS_CACHE.length) {
    toast("请先在「产品档案」中创建产品", true);
    return;
  }
  const opts = PRODUCTS_CACHE.map((p) =>
    `<option value="${p.id}">${esc(p.code)} · ${esc(p.name)}</option>`).join("");
  openModal("新建工单", `
    <label class="field"><span class="req">产品</span><select id="o-product">${opts}</select></label>
    <label class="field"><span class="req">计划数量</span><input id="o-qty" type="number" min="0" step="any" placeholder="如：1000" /></label>
    <label class="field"><span>优先级</span><select id="o-priority">
      ${PRIORITIES.map(([v, l]) => `<option value="${v}" ${v === "normal" ? "selected" : ""}>${l}</option>`).join("")}
    </select></label>
    <label class="field"><span>负责人</span><input id="o-assignee" placeholder="可在派工时再填" /></label>
    <label class="field"><span>车间</span><input id="o-workshop" placeholder="如：一号车间" /></label>
    <label class="field"><span>计划开工</span><input id="o-start" type="date" /></label>
    <label class="field"><span>计划完工</span><input id="o-end" type="date" /></label>
    <label class="field"><span>备注</span><textarea id="o-remark"></textarea></label>`,
    async () => {
      const wo = await api("/work-orders", {
        method: "POST",
        body: {
          product_id: Number($("#o-product").value),
          planned_qty: Number($("#o-qty").value || 0),
          priority: $("#o-priority").value,
          assignee: $("#o-assignee").value.trim(),
          workshop: $("#o-workshop").value.trim(),
          planned_start: $("#o-start").value,
          planned_end: $("#o-end").value,
          remark: $("#o-remark").value.trim(),
        },
      });
      toast("工单已创建：" + wo.order_no);
      loadOrders();
    });
});

// ── 异常 ────────────────────────────────────────────────────────────────
async function loadExceptions() {
  const status = $("#filter-exc").value;
  try {
    const rows = await api("/exceptions" + (status ? "?status=" + status : ""));
    $("#exc-empty").style.display = rows.length ? "none" : "block";
    $("#exc-tbody").innerHTML = rows.map((e) => `
      <tr>
        <td><strong>${esc(e.order_no)}</strong></td>
        <td>${esc(e.category_label)}</td>
        <td>${esc(e.description)}</td>
        <td>${esc(e.reporter) || "—"}</td>
        <td><span class="badge ${e.status === "open" ? "p-high" : "s-completed"}">${e.status === "open" ? "待处理" : "已处理"}</span></td>
        <td>${e.status === "open" ? `<button class="btn sm ghost" data-resolve="${e.id}">处理</button>` : esc(e.resolution || "")}</td>
      </tr>`).join("");
    $$("#exc-tbody [data-resolve]").forEach((b) =>
      b.addEventListener("click", () => resolveExc(b.dataset.resolve)));
  } catch (e) { toast(e.message, true); }
}
$("#filter-exc").addEventListener("change", loadExceptions);

$("#btn-new-exc").addEventListener("click", () => openExcModal(null));

async function openExcModal(woId) {
  let woOptions = "";
  if (!woId) {
    const orders = await api("/work-orders");
    const open = orders.filter((w) => w.status !== "closed");
    if (!open.length) { toast("暂无可关联的工单", true); return; }
    woOptions = `<label class="field"><span class="req">关联工单</span><select id="e-wo">
      ${open.map((w) => `<option value="${w.id}">${esc(w.order_no)} · ${esc(w.product_name)}</option>`).join("")}
    </select></label>`;
  }
  openModal("上报异常", `
    ${woOptions}
    <label class="field"><span class="req">异常类型</span><select id="e-cat">
      ${EXC_CATS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select></label>
    <label class="field"><span class="req">异常描述</span><textarea id="e-desc" placeholder="描述问题与影响…"></textarea></label>
    <label class="field"><span>上报人</span><input id="e-reporter" /></label>`,
    async () => {
      await api("/exceptions", {
        method: "POST",
        body: {
          work_order_id: woId || Number($("#e-wo").value),
          category: $("#e-cat").value,
          description: $("#e-desc").value.trim(),
          reporter: $("#e-reporter").value.trim(),
        },
      });
      toast("异常已上报");
      loadExceptions();
      if (woId && $("#drawer").classList.contains("show")) openOrder(woId);
    });
}

function resolveExc(id) {
  openModal("处理异常", `
    <label class="field"><span class="req">处理结果</span><textarea id="x-res" placeholder="如何解决的…"></textarea></label>`,
    async () => {
      await api(`/exceptions/${id}/resolve`, { method: "POST", body: { resolution: $("#x-res").value.trim() } });
      toast("异常已处理");
      loadExceptions();
    });
}

// ── 产品 ────────────────────────────────────────────────────────────────
async function ensureProducts() {
  PRODUCTS_CACHE = await api("/products");
}
async function loadProducts() {
  await ensureProducts();
  $("#products-empty").style.display = PRODUCTS_CACHE.length ? "none" : "block";
  $("#products-tbody").innerHTML = PRODUCTS_CACHE.map((p) => `
    <tr>
      <td><strong>${esc(p.code)}</strong></td>
      <td>${esc(p.name)}</td>
      <td>${esc(p.spec) || "—"}</td>
      <td>${esc(p.unit)}</td>
      <td>${esc(p.created_at)}</td>
    </tr>`).join("");
}
$("#btn-new-product").addEventListener("click", () => {
  openModal("新建产品", `
    <label class="field"><span class="req">产品编码</span><input id="p-code" placeholder="如：P-1004" /></label>
    <label class="field"><span class="req">产品名称</span><input id="p-name" /></label>
    <label class="field"><span>规格</span><input id="p-spec" /></label>
    <label class="field"><span>单位</span><input id="p-unit" value="件" /></label>`,
    async () => {
      await api("/products", {
        method: "POST",
        body: {
          code: $("#p-code").value.trim(),
          name: $("#p-name").value.trim(),
          spec: $("#p-spec").value.trim(),
          unit: $("#p-unit").value.trim() || "件",
        },
      });
      toast("产品已创建");
      loadProducts();
    });
});

// ── 抽屉 / 弹窗 基础设施 ────────────────────────────────────────────────────
function showDrawer() { $("#overlay").classList.add("show"); $("#drawer").classList.add("show"); }
function hideDrawer() { $("#overlay").classList.remove("show"); $("#drawer").classList.remove("show"); }
$$("[data-close-drawer]").forEach((b) => b.addEventListener("click", hideDrawer));
$("#overlay").addEventListener("click", () => { hideDrawer(); hideModal(); });

let modalSubmit = null;
function openModal(title, bodyHtml, onSubmit) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = bodyHtml;
  modalSubmit = onSubmit;
  $("#overlay").classList.add("show");
  $("#modal").classList.add("show");
  const first = $("#modal-body input, #modal-body select, #modal-body textarea");
  if (first) first.focus();
}
function hideModal() {
  $("#modal").classList.remove("show");
  if (!$("#drawer").classList.contains("show")) $("#overlay").classList.remove("show");
  modalSubmit = null;
}
$$("[data-close-modal]").forEach((b) => b.addEventListener("click", hideModal));
$("#modal-submit").addEventListener("click", async () => {
  if (!modalSubmit) return;
  const btn = $("#modal-submit");
  btn.disabled = true;
  try {
    await modalSubmit();
    hideModal();
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
  }
});

// ── 启动 ────────────────────────────────────────────────────────────────
loadDashboard();
