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
const STAFF_ROLES = [
  ["operator", "操作工"], ["inspector", "质检员"], ["leader", "班组长"],
  ["planner", "计划员"], ["manager", "管理员"],
];
const MAT_CATS = [["raw", "原料"], ["semi", "半成品"], ["finished", "成品"]];
const INSP_RESULTS = [["pass", "合格"], ["concession", "让步接收"], ["reject", "拒收"]];
const TXN_IN = [["purchase", "采购入库"], ["produce_in", "完工入库"], ["return", "退料入库"], ["adjust_in", "盘盈入库"]];
const TXN_OUT = [["scrap", "报废出库"], ["adjust_out", "盘亏出库"]];
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
  else if (view === "inspections") loadInspections();
  else if (view === "inventory") loadMaterials();
  else if (view === "exceptions") loadExceptions();
  else if (view === "products") loadProducts();
  else if (view === "staff") loadStaff();
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
      { label: "质检合格率", value: d.inspect_pass_rate + "%", cls: d.inspect_pass_rate && d.inspect_pass_rate < 95 ? "warn" : "ok" },
      { label: "低库存物料", value: d.low_stock_materials, cls: d.low_stock_materials ? "danger" : "" },
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
    const [w, reports, excs, issues, insps] = await Promise.all([
      api("/work-orders/" + id),
      api(`/work-orders/${id}/reports`),
      api(`/work-orders/${id}/exceptions`),
      api(`/work-orders/${id}/inventory`),
      api(`/work-orders/${id}/inspections`),
    ]);
    $("#drawer-title").textContent = w.order_no;
    $("#drawer-body").innerHTML = renderOrderDetail(w, reports, excs, issues, insps);
    bindOrderActions(w);
    showDrawer();
  } catch (e) { toast(e.message, true); }
}

function renderOrderDetail(w, reports, excs, issues, insps) {
  const actions = (ACTIONS[w.status] || []).map(([a, label, cls]) =>
    `<button class="btn ${cls} sm" data-action="${a}">${label}</button>`).join("");
  const active = w.status !== "completed" && w.status !== "closed";
  const reportBtn = (w.status === "producing" || w.status === "paused")
    ? `<button class="btn sm" data-report>+ 报工</button>` : "";
  const issueBtn = active ? `<button class="btn subtle sm" data-issue>+ 领料</button>` : "";
  const inspBtn = `<button class="btn subtle sm" data-inspect>+ 质检</button>`;
  const excBtn = `<button class="btn ghost sm" data-add-exc>+ 上报异常</button>`;

  return `
    <div class="action-row">${actions}${reportBtn}${issueBtn}${inspBtn}${excBtn}</div>
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
      <h4>领料记录 <span style="color:var(--muted);font-weight:400">${issues.length} 条</span></h4>
      ${issues.length ? issues.map((t) => `
        <div class="timeline-item">
          <div><strong>${esc(t.material_name)}</strong> 出库 ${fmt(t.qty)}（结余 ${fmt(t.balance_after)}）</div>
          <div class="meta">${esc(t.created_at)}${t.operator ? " · " + esc(t.operator) : ""}${t.remark ? " · " + esc(t.remark) : ""}</div>
        </div>`).join("") : '<div class="empty">暂无领料</div>'}
    </div>

    <div class="sub-card">
      <h4>质检记录 <span style="color:var(--muted);font-weight:400">${insps.length} 条</span></h4>
      ${insps.length ? insps.map((i) => `
        <div class="timeline-item">
          <div><span class="badge ${i.result === "reject" ? "p-urgent" : i.result === "concession" ? "p-high" : "s-completed"}">${esc(i.result_label)}</span>
            送检 ${fmt(i.qty_inspected)}，合格 ${fmt(i.qty_qualified)}（${i.pass_rate}%）</div>
          <div class="meta">${esc(i.inspector)} · ${esc(i.created_at)}${i.defect_reason ? " · " + esc(i.defect_reason) : ""}</div>
        </div>`).join("") : '<div class="empty">暂无质检</div>'}
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
  const iss = $("#drawer-body [data-issue]");
  if (iss) iss.addEventListener("click", () => openIssueModal(w));
  $("#drawer-body [data-inspect]").addEventListener("click", () => openInspectModal(w));
  $("#drawer-body [data-add-exc]").addEventListener("click", () => openExcModal(w.id));
}

async function openIssueModal(w) {
  const mats = await api("/materials");
  if (!mats.length) { toast("请先在「物料库存」中建立物料", true); return; }
  const opts = mats.map((m) =>
    `<option value="${m.id}">${esc(m.code)} · ${esc(m.name)}（库存 ${fmt(m.stock)}${esc(m.unit)}）</option>`).join("");
  openModal("工单领料 · " + w.order_no, `
    <label class="field"><span class="req">物料</span><select id="i-mat">${opts}</select></label>
    <label class="field"><span class="req">领用数量</span><input id="i-qty" type="number" min="0" step="any" /></label>
    <label class="field"><span>领料人</span><input id="i-op" value="${esc(w.assignee)}" /></label>
    <label class="field"><span>备注</span><textarea id="i-remark"></textarea></label>`,
    async () => {
      await api(`/work-orders/${w.id}/issue`, {
        method: "POST",
        body: {
          material_id: Number($("#i-mat").value),
          qty: Number($("#i-qty").value || 0),
          operator: $("#i-op").value.trim(),
          remark: $("#i-remark").value.trim(),
        },
      });
      toast("领料成功");
      openOrder(w.id);
    });
}

function openInspectModal(w) {
  openModal("质量检验 · " + w.order_no, `
    <label class="field"><span class="req">质检员</span><input id="q-inspector" placeholder="如：陈质检" /></label>
    <label class="field"><span class="req">送检数量</span><input id="q-insp" type="number" min="0" step="any" /></label>
    <label class="field"><span>合格数量</span><input id="q-ok" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>不良数量</span><input id="q-ng" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>结论</span><select id="q-result">
      ${INSP_RESULTS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select></label>
    <label class="field"><span>不良原因</span><input id="q-reason" /></label>`,
    async () => {
      await api(`/work-orders/${w.id}/inspections`, {
        method: "POST",
        body: {
          inspector: $("#q-inspector").value.trim(),
          qty_inspected: Number($("#q-insp").value || 0),
          qty_qualified: Number($("#q-ok").value || 0),
          qty_defective: Number($("#q-ng").value || 0),
          result: $("#q-result").value,
          defect_reason: $("#q-reason").value.trim(),
        },
      });
      toast("检验单已提交");
      openOrder(w.id);
    });
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

// ── 质检 ────────────────────────────────────────────────────────────────
async function loadInspections() {
  try {
    const rows = await api("/inspections");
    $("#insp-empty").style.display = rows.length ? "none" : "block";
    $("#insp-tbody").innerHTML = rows.map((i) => `
      <tr>
        <td><strong>${esc(i.order_no)}</strong></td>
        <td>${esc(i.inspector)}</td>
        <td class="num">${fmt(i.qty_inspected)}</td>
        <td class="num">${fmt(i.qty_qualified)}</td>
        <td class="num">${fmt(i.qty_defective)}</td>
        <td>${i.pass_rate}%</td>
        <td><span class="badge ${i.result === "reject" ? "p-urgent" : i.result === "concession" ? "p-high" : "s-completed"}">${esc(i.result_label)}</span></td>
        <td class="hide-sm">${esc(i.created_at)}</td>
      </tr>`).join("");
  } catch (e) { toast(e.message, true); }
}
$("#btn-new-insp").addEventListener("click", async () => {
  const orders = await api("/work-orders");
  const pick = orders.filter((w) => w.status !== "pending" && w.status !== "closed");
  if (!pick.length) { toast("暂无可检验的工单", true); return; }
  const opts = pick.map((w) => `<option value="${w.id}">${esc(w.order_no)} · ${esc(w.product_name)}</option>`).join("");
  openModal("新建检验单", `
    <label class="field"><span class="req">工单</span><select id="qg-wo">${opts}</select></label>
    <label class="field"><span class="req">质检员</span><input id="qg-inspector" /></label>
    <label class="field"><span class="req">送检数量</span><input id="qg-insp" type="number" min="0" step="any" /></label>
    <label class="field"><span>合格数量</span><input id="qg-ok" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>不良数量</span><input id="qg-ng" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>结论</span><select id="qg-result">
      ${INSP_RESULTS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select></label>
    <label class="field"><span>不良原因</span><input id="qg-reason" /></label>`,
    async () => {
      await api(`/work-orders/${$("#qg-wo").value}/inspections`, {
        method: "POST",
        body: {
          inspector: $("#qg-inspector").value.trim(),
          qty_inspected: Number($("#qg-insp").value || 0),
          qty_qualified: Number($("#qg-ok").value || 0),
          qty_defective: Number($("#qg-ng").value || 0),
          result: $("#qg-result").value,
          defect_reason: $("#qg-reason").value.trim(),
        },
      });
      toast("检验单已提交");
      loadInspections();
    });
});

// ── 物料 / 库存 ───────────────────────────────────────────────────────────
async function loadMaterials() {
  try {
    const rows = await api("/materials");
    $("#materials-empty").style.display = rows.length ? "none" : "block";
    $("#materials-tbody").innerHTML = rows.map((m) => `
      <tr>
        <td><strong>${esc(m.code)}</strong></td>
        <td>${esc(m.name)}</td>
        <td class="hide-sm">${esc(m.spec) || "—"}</td>
        <td>${esc(m.category_label)}</td>
        <td class="num ${m.low_stock ? "overdue" : ""}">${fmt(m.stock)} ${esc(m.unit)}${m.low_stock ? " ⚠" : ""}</td>
        <td class="num hide-sm">${fmt(m.safety_stock)}</td>
        <td><button class="btn sm ghost" data-move="${m.id}" data-name="${esc(m.name)}" data-unit="${esc(m.unit)}" data-stock="${m.stock}">出入库</button></td>
      </tr>`).join("");
    $$("#materials-tbody [data-move]").forEach((b) =>
      b.addEventListener("click", () => openMoveModal(b.dataset)));
  } catch (e) { toast(e.message, true); }
}

function openMoveModal(d) {
  const allOpts = [...TXN_IN, ...TXN_OUT];
  openModal(`出入库 · ${d.name}（库存 ${fmt(d.stock)}${d.unit}）`, `
    <label class="field"><span class="req">类型</span><select id="mv-type">
      ${allOpts.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select></label>
    <label class="field"><span class="req">数量</span><input id="mv-qty" type="number" min="0" step="any" /></label>
    <label class="field"><span>操作人</span><input id="mv-op" /></label>
    <label class="field"><span>备注</span><textarea id="mv-remark"></textarea></label>`,
    async () => {
      await api(`/materials/${d.move}/move`, {
        method: "POST",
        body: {
          biz_type: $("#mv-type").value,
          qty: Number($("#mv-qty").value || 0),
          operator: $("#mv-op").value.trim(),
          remark: $("#mv-remark").value.trim(),
        },
      });
      toast("库存已更新");
      loadMaterials();
      if ($("#txns-card").style.display !== "none") loadTxns();
    });
}

$("#btn-new-material").addEventListener("click", () => {
  openModal("新建物料", `
    <label class="field"><span class="req">物料编码</span><input id="m-code" placeholder="如：M-2004" /></label>
    <label class="field"><span class="req">物料名称</span><input id="m-name" /></label>
    <label class="field"><span>规格</span><input id="m-spec" /></label>
    <label class="field"><span>单位</span><input id="m-unit" value="件" /></label>
    <label class="field"><span>类别</span><select id="m-cat">
      ${MAT_CATS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select></label>
    <label class="field"><span>初始库存</span><input id="m-stock" type="number" min="0" step="any" value="0" /></label>
    <label class="field"><span>安全库存</span><input id="m-safety" type="number" min="0" step="any" value="0" /></label>`,
    async () => {
      await api("/materials", {
        method: "POST",
        body: {
          code: $("#m-code").value.trim(),
          name: $("#m-name").value.trim(),
          spec: $("#m-spec").value.trim(),
          unit: $("#m-unit").value.trim() || "件",
          category: $("#m-cat").value,
          stock: Number($("#m-stock").value || 0),
          safety_stock: Number($("#m-safety").value || 0),
        },
      });
      toast("物料已创建");
      loadMaterials();
    });
});

let txnsVisible = false;
$("#btn-view-txns").addEventListener("click", () => {
  txnsVisible = !txnsVisible;
  $("#txns-card").style.display = txnsVisible ? "block" : "none";
  if (txnsVisible) loadTxns();
});
async function loadTxns() {
  const rows = await api("/inventory-txns");
  $("#txns-empty").style.display = rows.length ? "none" : "block";
  $("#txns-tbody").innerHTML = rows.map((t) => `
    <tr>
      <td>${esc(t.created_at)}</td>
      <td>${esc(t.material_name)}</td>
      <td><span class="badge ${t.kind === "in" ? "s-completed" : "p-high"}">${esc(t.biz_label)}</span></td>
      <td class="num">${t.kind === "in" ? "+" : "−"}${fmt(t.qty)}</td>
      <td class="num">${fmt(t.balance_after)}</td>
      <td class="hide-sm">${t.work_order_id ? "#" + t.work_order_id : "—"}</td>
      <td class="hide-sm">${esc(t.operator) || "—"}</td>
    </tr>`).join("");
}

// ── 员工 ────────────────────────────────────────────────────────────────
async function loadStaff() {
  try {
    const rows = await api("/staff");
    $("#staff-empty").style.display = rows.length ? "none" : "block";
    $("#staff-tbody").innerHTML = rows.map((s) => `
      <tr>
        <td><strong>${esc(s.name)}</strong></td>
        <td>${esc(s.role_label)}</td>
        <td>${esc(s.team) || "—"}</td>
        <td><span class="badge ${s.active ? "s-producing" : "s-closed"}">${s.active ? "在职" : "停用"}</span></td>
        <td><button class="btn sm subtle" data-toggle="${s.id}" data-active="${s.active ? 1 : 0}">${s.active ? "停用" : "启用"}</button></td>
      </tr>`).join("");
    $$("#staff-tbody [data-toggle]").forEach((b) =>
      b.addEventListener("click", async () => {
        await api(`/staff/${b.dataset.toggle}/active`, { method: "POST", body: { active: b.dataset.active !== "1" } });
        loadStaff();
      }));
  } catch (e) { toast(e.message, true); }
}
$("#btn-new-staff").addEventListener("click", () => {
  openModal("新建员工", `
    <label class="field"><span class="req">姓名</span><input id="s-name" /></label>
    <label class="field"><span>角色</span><select id="s-role">
      ${STAFF_ROLES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select></label>
    <label class="field"><span>班组</span><input id="s-team" placeholder="如：一号车间" /></label>`,
    async () => {
      await api("/staff", {
        method: "POST",
        body: { name: $("#s-name").value.trim(), role: $("#s-role").value, team: $("#s-team").value.trim() },
      });
      toast("员工已创建");
      loadStaff();
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
