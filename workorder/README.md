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
| **生产看板** | 工单总数、计划完成率、不良率、今日产出、超期工单、待处理异常、各状态分布 |
| **工单管理** | 新建工单（自动生成工单号 `WOyyyymmdd-NNN`）、按状态/关键字筛选、详情抽屉 |
| **状态流转** | 派工 / 开工 / 暂停 / 恢复 / 完工 / 关闭 / 取消，非法跳转后端拦截 |
| **报工** | 记录合格/不良数量，累计完成达到计划数量**自动完工** |
| **异常处理** | 按类型（设备/物料/质量/工艺/其他）上报，闭环处理并记录处理结果 |
| **产品档案** | 维护产品编码、名称、规格、单位 |

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
│   ├── store.py        # 数据访问 + 业务逻辑（状态机/报工/异常/统计）
│   └── api.py          # HTTP 路由 + JSON REST + 静态资源服务
├── web/                # 原生前端 SPA
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── tests/              # pytest：业务逻辑 + HTTP 端到端
    ├── test_store.py
    └── test_http.py
```

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
