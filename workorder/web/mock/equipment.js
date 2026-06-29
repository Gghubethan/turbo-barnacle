"use strict";
/*
 * 设备管理 mock：复刻 server/modules/equipment.py。
 * 设备台账 + 点检/保养/维修记录，跟踪设备状态。
 * 表：equipment / equipment_logs（与 .py 一致）。
 */
(function () {
  if (!window.Mock) return;
  const M = window.Mock;

  // 设备状态：运行中 / 闲置 / 保养中 / 故障
  const EQUIPMENT_STATUS = {
    running: "运行中",
    idle: "闲置",
    maintenance: "保养中",
    fault: "故障",
  };
  // 维护记录类型：点检 / 保养 / 维修
  const LOG_TYPE = {
    inspect: "点检",
    maintain: "保养",
    repair: "维修",
  };

  function equipLabel(d) {
    d.status_label = EQUIPMENT_STATUS[d.status] || d.status;
    return d;
  }
  function logLabel(d) {
    d.type_label = LOG_TYPE[d.type] || d.type;
    return d;
  }

  // 给日志补 equipment_name（JOIN equipment 的 name）
  function logWithEquip(l) {
    const e = M.db.byId("equipment", l.equipment_id);
    return logLabel(Object.assign({}, l, { equipment_name: e ? e.name : "" }));
  }

  function listEquipment() {
    return M.db.table("equipment").slice().sort((a, b) => b.id - a.id).map((r) => equipLabel(Object.assign({}, r)));
  }

  function createEquipment(data) {
    const code = M.require(data, "code", "设备编码");
    const name = M.require(data, "name", "设备名称");
    const status = data.status || "running";
    if (!EQUIPMENT_STATUS[status]) M.bad("未知设备状态：" + status);
    if (M.db.table("equipment").some((e) => e.code === code)) M.bad(`设备编码 ${code} 已存在`);
    const row = M.db.insert("equipment", {
      code,
      name,
      model: String(data.model || "").trim(),
      location: String(data.location || "").trim(),
      owner: String(data.owner || "").trim(),
      status,
      created_at: M.now(),
    });
    M.db.save();
    return equipLabel(Object.assign({}, row));
  }

  function setStatus(eid, status) {
    if (!EQUIPMENT_STATUS[status]) M.bad("未知设备状态：" + status);
    const e = M.db.byId("equipment", eid);
    if (!e) M.notfound(`设备 ${eid} 不存在`);
    e.status = status;
    M.db.save();
    return equipLabel(Object.assign({}, e));
  }

  function listLogs(equipmentId) {
    let rows = M.db.table("equipment_logs").slice();
    if (equipmentId) rows = rows.filter((l) => l.equipment_id === Number(equipmentId));
    rows.sort((a, b) => b.id - a.id);
    return rows.map(logWithEquip);
  }

  function addLog(eid, data) {
    const logType = M.require(data, "type", "记录类型");
    if (!LOG_TYPE[logType]) M.bad("未知记录类型：" + logType);
    const content = M.require(data, "content", "记录内容");
    const cost = M.num(data.cost === undefined || data.cost === null ? 0 : data.cost, "费用");
    const e = M.db.byId("equipment", eid);
    if (!e) M.notfound(`设备 ${eid} 不存在`);
    const row = M.db.insert("equipment_logs", {
      equipment_id: Number(eid),
      type: logType,
      content,
      operator: String(data.operator || "").trim(),
      cost,
      created_at: M.now(),
    });
    // 维修时把设备置为保养中，完成后用户可再手动改回
    if (logType === "repair") e.status = "maintenance";
    M.db.save();
    return logWithEquip(row);
  }

  // ── 路由（以 .py routes() 为准）─────────────────────────────────
  M.register("GET", "/api/equipment", () => ({ body: listEquipment() }));
  M.register("POST", "/api/equipment", (ctx) => ({ status: 201, body: createEquipment(ctx.body) }));
  M.register("POST", "/api/equipment/(?<id>\\d+)/status", (ctx) =>
    ({ body: setStatus(Number(ctx.params.id), (ctx.body && ctx.body.status) || "") }));
  M.register("GET", "/api/equipment/(?<id>\\d+)/logs", (ctx) =>
    ({ body: listLogs(Number(ctx.params.id)) }));
  M.register("POST", "/api/equipment/(?<id>\\d+)/logs", (ctx) =>
    ({ status: 201, body: addLog(Number(ctx.params.id), ctx.body) }));
  M.register("GET", "/api/equipment-logs", () => ({ body: listLogs() }));

  // ── 种子（与 .py seed 一致：3 台设备 + 首台一条点检记录）────────
  M.onSeed(function (M) {
    if (M.db.table("equipment").length) return;
    const e1 = createEquipment({
      code: "CNC-01", name: "数控车床", model: "CK6140",
      location: "一号车间", owner: "张工", status: "running",
    });
    createEquipment({
      code: "INJ-02", name: "注塑机", model: "HTF160",
      location: "二号车间", owner: "王工", status: "idle",
    });
    createEquipment({
      code: "WELD-03", name: "焊接机器人", model: "AR-1440",
      location: "三号车间", owner: "赵工", status: "fault",
    });
    addLog(e1.id, {
      type: "inspect", content: "日常点检：油位正常，导轨润滑良好",
      operator: "李师傅",
    });
  });
})();
