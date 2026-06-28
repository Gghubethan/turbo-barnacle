# workorder — 黑湖工单系统（复刻）

对标黑湖科技「黑湖工单」的轻量复刻：面向数字化车间的**工单全流程协同**——
建单 → 派工 → 开工 → 报工 → 完工 → 关闭，并配套**异常上报/处理**与**生产看板**。

> **零第三方依赖**：仅用 Python 标准库（`http.server` + `sqlite3`）和原生前端
> （HTML/CSS/JS）。`git clone` 后开箱即跑，不需要 `pip install`。

## 快速开始

```bash
cd workorder
python3 app.py                 # 启动后访问 http://127.0.0.1:8000
```

首次启动会自动灌入一批演示数据（产品、工单、报工、异常），方便直接体验。

常用参数：

```bash
python3 app.py --port 9000     # 换端口
python3 app.py --db prod.db    # 指定数据库文件
python3 app.py --no-seed       # 不灌演示数据（用于真实使用）
python3 app.py --host 0.0.0.0  # 监听所有网卡，局域网/平板可访问
```

## 功能

| 模块 | 能力 |
| --- | --- |
| **生产看板** | 工单总数、计划完成率、不良率、今日产出、超期工单、待处理异常、**质检合格率**、**低库存物料**、各状态分布 |
| **工单管理** | 新建工单（自动生成工单号 `WOyyyymmdd-NNN`）、按状态/关键字筛选、详情抽屉 |
| **状态流转** | 派工 / 开工 / 暂停 / 恢复 / 完工 / 关闭 / 取消，非法跳转后端拦截 |
| **报工** | 记录合格/不良数量，累计完成达到计划数量**自动完工** |
| **质量检验** | 按工单建检验单，记录送检/合格/不良与结论（合格/让步接收/拒收），自动算合格率 |
| **物料库存** | 物料档案 + 安全库存预警；采购/领料/报废/盘点出入库，带结余的流水台账 |
| **工单领料** | 在工单详情直接领料出库并挂账到工单，库存不足后端拦截 |
| **异常处理** | 按类型（设备/物料/质量/工艺/其他）上报，闭环处理并记录处理结果 |
| **产品档案** | 维护产品编码、名称、规格、单位 |
| **员工班组** | 维护员工角色（操作工/质检员/班组长/计划员/管理员）与班组，支持停用/启用 |
| **计划排产** | 甘特看板：工单按计划周期排到时间轴，按车间分组、状态着色，支持产线排产 |
| **工序管理** | 工单拆工序、按工序报工，跟踪每道工序进度与状态（待开工/进行中/已完成） |
| **设备管理** | 设备台账 + 点检/保养/维修记录，设备状态（运行中/闲置/保养中/故障）流转 |
| **报表中心** | 日产量趋势、质检合格率趋势、工单状态分布、车间产出、物料出入库汇总（纯 CSS/SVG 图表） |
| **销售订单** | 客户订单管理，一键「下推生产」自动生成关联工单，发货/关闭流转 |
| **采购管理** | 采购订单管理，收货时自动入库（写库存流水），部分/全部收货状态流转 |
| **物料清单** | 产品 BOM（用料 + 单位用量 + 损耗率）；按产量测算用料需求、对比库存给出缺口与采购建议 |
| **数据导出** | 工单/报工/质检/库存/物料/产品/员工/异常 一键导出 CSV（UTF-8 BOM，Excel 友好，枚举转中文） |

> **业务闭环**：销售订单 → 下推生产 → 工单 → 领料（出库）→ 报工 → 工序 → 质检 → 完工；
> 采购订单 → 收货入库 → 领料消耗。物料库存、质量、设备数据随业务沉淀，看板与报表实时反映
> 合格率、库存预警与产出趋势 —— 对齐黑湖「小工单」「销售 + 生产 + 质量 + 库存 + 采购」一体化定位。

## 工单状态机

```
待派工 ──派工──▶ 已派工 ──开工──▶ 生产中 ──完工──▶ 已完工 ──关闭──▶ 已关闭
                              ▲  │暂停
                              └──┘恢复（已暂停）
（待派工/已派工/已暂停 可直接「取消」→ 已关闭）
```

状态机集中定义在 `server/store.py` 的 `TRANSITIONS` 表，是唯一裁决方；
前端按钮只是它的投影，任何非法跳转都会被后端以 400 拒绝。

## 目录结构

```
workorder/
├── app.py              # 启动入口（argparse + 起服务）
├── server/
│   ├── store.py        # 核心数据访问 + 业务逻辑（状态机/报工/异常/库存/质检/统计）
│   ├── api.py          # HTTP 路由 + JSON REST + 静态资源 + 功能模块自动加载
│   └── modules/        # 功能模块插件（约定式自动发现，零中心化注册）
│       ├── CONTRACT.md # 模块开发契约（后端/前端/测试约定）
│       ├── planning.py # 计划排产
│       ├── routing.py  # 工序管理
│       ├── equipment.py# 设备管理
│       ├── reports.py  # 报表中心
│       ├── sales.py    # 销售订单
│       ├── purchasing.py # 采购管理
│       ├── bom.py      # 物料清单 BOM
│       └── export.py   # 数据导出（CSV）
├── web/                # 原生前端 SPA
│   ├── index.html
│   ├── app.js          # 含插件机制：动态加载 web/modules/*.js 注册标签页
│   ├── styles.css
│   └── modules/        # 功能模块前端（planning.js / routing.js / equipment.js / reports.js）
└── tests/              # pytest：业务逻辑 + HTTP 端到端 + 各功能模块
    ├── test_store.py    # 工单/报工/异常/状态机
    ├── test_modules.py  # 员工/物料库存/质检
    ├── test_http.py     # HTTP 端到端
    ├── test_planning.py # 计划排产
    ├── test_routing.py  # 工序管理
    ├── test_equipment.py# 设备管理
    ├── test_reports.py  # 报表中心
    ├── test_sales.py    # 销售订单
    ├── test_purchasing.py # 采购管理
    ├── test_bom.py      # 物料清单 BOM
    └── test_export.py   # 数据导出
```

### 插件式功能模块

`server/modules/` 与 `web/modules/` 下的模块**约定式自动加载**，新增模块无需改动任何中心文件：
后端自动 import 各模块的建表 SQL 与路由，前端通过 `/api/modules` 动态加载并注册标签页。
开发约定见 [`server/modules/CONTRACT.md`](server/modules/CONTRACT.md)。

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/dashboard` | 看板统计 |
| GET/POST | `/api/products` | 产品列表 / 新建 |
| GET/POST | `/api/work-orders` | 工单列表（`?status=&keyword=`）/ 新建 |
| GET | `/api/work-orders/{id}` | 工单详情 |
| POST | `/api/work-orders/{id}/transition` | 状态流转（body 含 `action`） |
| GET/POST | `/api/work-orders/{id}/reports` | 报工记录 / 提交报工 |
| GET | `/api/work-orders/{id}/exceptions` | 工单关联异常 |
| GET/POST | `/api/exceptions` | 异常列表（`?status=`）/ 上报 |
| POST | `/api/exceptions/{id}/resolve` | 处理异常 |
| POST | `/api/work-orders/{id}/issue` | 工单领料（物料出库挂账） |
| GET | `/api/work-orders/{id}/inventory` | 工单领料流水 |
| GET/POST | `/api/work-orders/{id}/inspections` | 工单质检记录 / 新建检验单 |
| GET/POST | `/api/staff` | 员工列表（`?active=1`）/ 新建 |
| POST | `/api/staff/{id}/active` | 启用/停用员工 |
| GET/POST | `/api/materials` | 物料列表 / 新建 |
| POST | `/api/materials/{id}/move` | 物料出入库 |
| GET | `/api/inventory-txns` | 出入库流水（`?material_id=`） |
| GET | `/api/inspections` | 全部质检记录 |

## 测试

```bash
cd workorder
pip install pytest      # 仅测试用
python3 -m pytest tests/ -q
```

## 设计取舍

- **零依赖**：标准库即可运行，部署/演示成本最低，与本仓库「完整可运行」一脉相承。
- **业务与传输解耦**：`store.py` 不依赖 HTTP；校验失败抛 `ValidationError`，
  由 `api.py` 统一翻成 400，便于单测与复用。
- **状态机单一真相源**：所有流转规则集中一处，前端不做权威判断。
- **SQLite 单文件**：免装数据库；`*.db` 已在 `.gitignore` 中忽略。
