"use strict";
/* 数据导出 mock：复刻后端 /api/export 系列，返回 CSV（带 UTF-8 BOM）。 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock, L = M.labels;

  function csv(headers, rows) {
    const esc = (v) => {
      const s = v === null || v === undefined ? "" : String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return "﻿" + [headers, ...rows].map((r) => r.map(esc).join(",")).join("\r\n");
  }
  const t = (n) => M.db.table(n);
  const wo = (id) => { const w = M.db.byId("work_orders", id); return w ? w.order_no : ""; };

  const DATASETS = {
    work_orders: ["工单", "工单.csv", () => [["工单号", "产品", "计划数", "完成数", "不良数", "状态", "优先级", "负责人", "车间", "计划开工", "计划完工", "创建时间"],
      t("work_orders").map((r) => [r.order_no, r.product_name, r.planned_qty, r.completed_qty, r.defect_qty, L.STATUS[r.status], L.PRIORITY[r.priority], r.assignee, r.workshop, r.planned_start, r.planned_end, r.created_at])]],
    reports: ["报工记录", "报工记录.csv", () => [["工单号", "报工人", "合格数", "不良数", "备注", "报工时间"],
      t("reports").map((r) => [wo(r.work_order_id), r.reporter, r.qty_ok, r.qty_defect, r.remark, r.report_time])]],
    inspections: ["质检记录", "质检记录.csv", () => [["工单号", "质检员", "送检数", "合格数", "不良数", "结论", "不良原因", "时间"],
      t("inspections").map((r) => [wo(r.work_order_id), r.inspector, r.qty_inspected, r.qty_qualified, r.qty_defective, L.INSPECT[r.result], r.defect_reason, r.created_at])]],
    inventory: ["库存流水", "库存流水.csv", () => [["时间", "物料", "方向", "业务类型", "数量", "结余", "关联工单", "操作人", "备注"],
      t("inventory_txns").map((r) => [r.created_at, r.material_name, r.kind === "in" ? "入库" : "出库", L.TXN[r.biz_type], r.qty, r.balance_after, r.work_order_id || "", r.operator, r.remark])]],
    materials: ["物料档案", "物料档案.csv", () => [["编码", "名称", "规格", "单位", "类别", "当前库存", "安全库存"],
      t("materials").map((r) => [r.code, r.name, r.spec, r.unit, L.MAT_CAT[r.category], r.stock, r.safety_stock])]],
    products: ["产品档案", "产品档案.csv", () => [["编码", "名称", "规格", "单位", "创建时间"],
      t("products").map((r) => [r.code, r.name, r.spec, r.unit, r.created_at])]],
    staff: ["员工", "员工.csv", () => [["姓名", "角色", "班组", "状态", "创建时间"],
      t("staff").map((r) => [r.name, L.STAFF_ROLE[r.role], r.team, r.active ? "在职" : "停用", r.created_at])]],
    exceptions: ["异常", "异常.csv", () => [["工单号", "类型", "描述", "上报人", "状态", "处理结果", "创建时间", "处理时间"],
      t("exceptions").map((r) => [wo(r.work_order_id), L.EXC[r.category], r.description, r.reporter, r.status === "resolved" ? "已处理" : "待处理", r.resolution, r.created_at, r.resolved_at])]],
  };

  M.register("GET", "/api/export", () => ({ body: Object.keys(DATASETS).map((k) => ({ key: k, label: DATASETS[k][0] })) }));
  M.register("GET", "/api/export/(?<key>[a-z_]+)\\.csv", (ctx) => {
    const ds = DATASETS[ctx.params.key];
    if (!ds) M.bad("未知数据集：" + ctx.params.key);
    const [, filename, build] = ds;
    const [headers, rows] = build();
    return { raw: true, text: csv(headers, rows), contentType: "text/csv; charset=utf-8", _filename: filename };
  });
})();
