/* ============================================================
   NEXUS Library OS — 应用逻辑
   ============================================================ */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const KEY = "nexus-library-state-v1";

  /* ---------- 状态持久化 ---------- */
  const State = {
    load() {
      try {
        const raw = localStorage.getItem(KEY);
        if (raw) return JSON.parse(raw);
      } catch (e) {}
      return clone(window.SEED);
    },
    save() { try { localStorage.setItem(KEY, JSON.stringify(db)); } catch (e) {} },
    reset() { db = clone(window.SEED); this.save(); }
  };
  const clone = (o) => JSON.parse(JSON.stringify(o));
  let db = State.load();

  /* ---------- 工具 ---------- */
  const bookById = (id) => db.books.find(b => b.id === id);
  const memberById = (id) => db.members.find(m => m.id === id);
  const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtCover = (b) => `<div class="cover" style="background:linear-gradient(135deg,${b.cover[0]},${b.cover[1]})">${esc(b.title[0])}</div>`;
  function bookStatusTag(b) {
    if (b.available === 0) return `<span class="tag tag--red">已借罄</span>`;
    if (b.available <= 2) return `<span class="tag tag--amber">紧张 ${b.available}</span>`;
    return `<span class="tag tag--green">在架 ${b.available}</span>`;
  }
  const todayISO = "2026-06-28";
  function daysBetween(a, b) { return Math.round((new Date(b) - new Date(a)) / 86400000); }

  function toast(msg, kind = "") {
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.innerHTML = `<div class="toast__bar"></div><div>${esc(msg)}</div>`;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(30px)"; }, 2600);
    setTimeout(() => el.remove(), 3000);
  }

  /* ---------- 开机动画 ---------- */
  function boot() {
    const lines = [
      "> init kernel ........ ok",
      "> mount catalog db ... ok",
      "> index 18,420 vols .. ok",
      "> sync sync-link ..... ok",
      "> auth ROOT .......... granted",
      "> launch interface ... ready",
    ];
    let i = 0, p = 0;
    const fill = $("#bootFill"), log = $("#bootLog");
    const t = setInterval(() => {
      p += Math.random() * 22 + 8;
      if (p > 100) p = 100;
      fill.style.width = p + "%";
      if (i < lines.length) { log.textContent = lines[i]; i++; }
      if (p >= 100) {
        clearInterval(t);
        setTimeout(() => {
          $("#boot").classList.add("is-done");
          $("#app").hidden = false;
          render("dashboard");
        }, 350);
      }
    }, 230);
  }

  /* ---------- 背景粒子 ---------- */
  function particles() {
    const c = $("#bgParticles"), ctx = c.getContext("2d");
    let w, h, pts;
    function resize() {
      w = c.width = innerWidth; h = c.height = innerHeight;
      pts = Array.from({ length: 70 }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25,
        r: Math.random() * 1.6 + .4
      }));
    }
    function tick() {
      ctx.clearRect(0, 0, w, h);
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7);
        ctx.fillStyle = "rgba(120,180,255,.5)"; ctx.fill();
      }
      for (let a = 0; a < pts.length; a++) for (let b = a + 1; b < pts.length; b++) {
        const dx = pts[a].x - pts[b].x, dy = pts[a].y - pts[b].y, d = Math.hypot(dx, dy);
        if (d < 120) {
          ctx.beginPath(); ctx.moveTo(pts[a].x, pts[a].y); ctx.lineTo(pts[b].x, pts[b].y);
          ctx.strokeStyle = `rgba(80,140,240,${(1 - d / 120) * .14})`; ctx.stroke();
        }
      }
      requestAnimationFrame(tick);
    }
    addEventListener("resize", resize); resize(); tick();
  }

  /* ---------- 时钟 + 系统表 ---------- */
  function liveClock() {
    function pad(n) { return String(n).padStart(2, "0"); }
    setInterval(() => {
      const d = new Date();
      $("#sysClock").textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }, 1000);
    function jitter(el, base) {
      setInterval(() => {
        const v = Math.max(8, Math.min(96, base + (Math.random() - .5) * 22));
        el.style.width = v.toFixed(0) + "%";
      }, 2200);
    }
    jitter($("#loadCore"), 46); jitter($("#loadIndex"), 62); jitter($("#loadSync"), 30);
  }

  /* ============================================================
     视图渲染
     ============================================================ */
  const TITLES = {
    dashboard: "控制中枢", catalog: "书目矩阵", members: "读者档案",
    circulation: "流通调度", analytics: "数据透析", shelf: "馆藏拓扑"
  };
  let current = "dashboard";

  function render(view) {
    current = view;
    $("#viewTitle").textContent = TITLES[view];
    $$(".nav__item").forEach(b => b.classList.toggle("is-active", b.dataset.view === view));
    const host = $("#views");
    host.innerHTML = VIEWS[view]();
    host.scrollTop = 0;
    if (AFTER[view]) AFTER[view]();
  }

  /* ---------- 派生统计 ---------- */
  function stats() {
    const totalVol = db.books.reduce((s, b) => s + b.total, 0);
    const avail = db.books.reduce((s, b) => s + b.available, 0);
    const outNow = totalVol - avail;
    const overdue = db.loans.filter(l => l.status === "overdue").length;
    const activeLoans = db.loans.filter(l => l.status === "active" || l.status === "overdue").length;
    return { titles: db.books.length, totalVol, avail, outNow, overdue, activeLoans, members: db.members.length };
  }

  /* ============================================================ */
  const VIEWS = {
    /* ---------------- 控制中枢 ---------------- */
    dashboard() {
      const s = stats();
      const hotBooks = [...db.books].sort((a, b) => b.hot - a.hot).slice(0, 5);
      const kpis = [
        { label: "馆藏品种", val: s.titles, delta: "+3 本周", up: true, accent: "#22e0ff44", color: "#22e0ff" },
        { label: "在借册数", val: s.outNow, delta: "+12 今日", up: true, accent: "#9a6bff44", color: "#9a6bff" },
        { label: "活跃读者", val: s.members, delta: "+1 今日", up: true, accent: "#1ff0a844", color: "#1ff0a8" },
        { label: "逾期记录", val: s.overdue, delta: s.overdue ? "需跟进" : "无", up: false, accent: "#ff5a7a44", color: "#ff5a7a" },
      ];
      return `<div class="view">
        <div class="section-head">
          <div><h2><span class="tagdot"></span>控制中枢 · 实时概览</h2>
          <p>OPERATIONS OVERVIEW · 数据截至 ${todayISO} ${TITLES ? "" : ""}</p></div>
          <button class="btn" onclick="NEXUS.openLoanForm()"><i class="ico ico-plus"></i>登记借阅</button>
        </div>

        <div class="kpi-grid">
          ${kpis.map(k => `
            <div class="kpi" style="--accent:${k.accent}">
              <div class="kpi__label">${k.label}</div>
              <div class="kpi__val" style="color:${k.color}">${k.val}</div>
              <div class="kpi__delta ${k.up ? "up" : "down"}">${k.up ? "▲" : "▼"} ${k.delta}</div>
              <svg class="kpi__spark" width="70" height="28" viewBox="0 0 70 28">
                <polyline fill="none" stroke="${k.color}" stroke-width="2" opacity=".7"
                  points="0,22 12,16 24,19 36,9 48,13 60,5 70,8"/></svg>
            </div>`).join("")}
        </div>

        <div class="grid-2">
          <div class="panel">
            <div class="panel__head"><h3>借还趋势 · 近 7 日</h3><span class="more">BORROW / RETURN</span></div>
            <canvas id="trendChart" class="linechart"></canvas>
            <div style="display:flex;gap:18px;margin-top:8px;font-size:11px;font-family:var(--mono);color:var(--txt-mut)">
              <span style="color:var(--cyan)">● 借出</span><span style="color:var(--violet)">● 归还</span>
            </div>
          </div>
          <div class="panel">
            <div class="panel__head"><h3>实时动态</h3><span class="more">LIVE FEED</span></div>
            <div class="feed">
              ${db.activity.map(a => `
                <div class="feed__row">
                  <span class="feed__dot" style="background:${a.color};box-shadow:0 0 8px ${a.color}"></span>
                  <div class="feed__txt">${esc(a.what)}<small>${esc(a.who)}</small></div>
                  <span class="feed__time">${a.time}</span>
                </div>`).join("")}
            </div>
          </div>
        </div>

        <div class="grid-2">
          <div class="panel">
            <div class="panel__head"><h3>热门借阅 TOP 5</h3><span class="more">HOTLIST</span></div>
            <div class="feed">
              ${hotBooks.map((b, i) => `
                <div class="feed__row" style="cursor:pointer" onclick="NEXUS.bookDetail('${b.id}')">
                  <span style="font-family:var(--mono);width:22px;color:${i < 3 ? "var(--cyan)" : "var(--txt-mut)"}">${String(i + 1).padStart(2, "0")}</span>
                  ${fmtCover(b)}
                  <div class="feed__txt">${esc(b.title)}<small>${esc(b.author)} · ${esc(b.cat)}</small></div>
                  <div style="width:90px"><div class="bar"><i style="width:${b.hot}%"></i></div></div>
                </div>`).join("")}
            </div>
          </div>
          <div class="panel">
            <div class="panel__head"><h3>馆藏构成</h3><span class="more">BY CATEGORY</span></div>
            <div style="display:flex;align-items:center;gap:20px">
              <div class="ring" id="catRing" style="--p:0"><b id="catRingNum">0</b><small>总品种</small></div>
              <div style="flex:1">
                ${db.categories.map(c => `
                  <div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;font-size:12px">
                    <span style="width:8px;height:8px;border-radius:50%;background:${c.color}"></span>
                    <span style="flex:1">${esc(c.name)}</span>
                    <span style="font-family:var(--mono);color:var(--txt-mut)">${c.count}</span>
                  </div>`).join("")}
              </div>
            </div>
          </div>
        </div>
      </div>`;
    },

    /* ---------------- 书目矩阵 ---------------- */
    catalog() {
      const cats = ["全部", ...new Set(db.books.map(b => b.cat))];
      return `<div class="view">
        <div class="section-head">
          <div><h2><span class="tagdot"></span>书目矩阵</h2><p>CATALOG MATRIX · 共 ${db.books.length} 个品种</p></div>
          <button class="btn" onclick="NEXUS.openBookForm()"><i class="ico ico-plus"></i>新增书目</button>
        </div>
        <div class="toolbar">
          ${cats.map((c, i) => `<button class="chip ${i === 0 ? "is-active" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("")}
          <div class="spacer"></div>
          <div class="segmented" id="catViewToggle">
            <button data-mode="table" class="${catMode === "table" ? "is-active" : ""}"><i class="ico ico-grid"></i>表格</button>
            <button data-mode="cards" class="${catMode === "cards" ? "is-active" : ""}"><i class="ico ico-book"></i>画廊</button>
          </div>
          <input class="mini-input" id="catSearch" placeholder="筛选书名 / 作者…" style="width:200px" />
        </div>
        <div id="catTableWrap" class="table-wrap" ${catMode === "cards" ? "hidden" : ""}>
          <table id="bookTable">
            <thead><tr>
              <th data-sort="title">书目</th><th data-sort="cat">分类</th><th data-sort="year">年份</th>
              <th data-sort="zone">位置</th><th data-sort="rating">评分</th><th data-sort="available">在架</th><th>状态</th><th></th>
            </tr></thead>
            <tbody id="bookBody"></tbody>
          </table>
        </div>
        <div id="catCards" class="book-cards" ${catMode === "table" ? "hidden" : ""}></div>
      </div>`;
    },

    /* ---------------- 读者档案 ---------------- */
    members() {
      const levelTag = { 铂金: "violet", 黄金: "amber", 白银: "blue", 普通: "green" };
      return `<div class="view">
        <div class="section-head">
          <div><h2><span class="tagdot"></span>读者档案</h2><p>MEMBER REGISTRY · 共 ${db.members.length} 名读者</p></div>
          <button class="btn" onclick="NEXUS.openMemberForm()"><i class="ico ico-plus"></i>注册读者</button>
        </div>
        <div class="grid-3" style="margin-bottom:14px">
          ${["铂金", "黄金", "白银"].map(lv => {
            const n = db.members.filter(m => m.level === lv).length;
            return `<div class="panel" style="text-align:center">
              <div style="font-size:11px;color:var(--txt-mut);font-family:var(--mono)">${lv}会员</div>
              <div style="font-size:28px;font-weight:800;font-family:var(--mono);margin-top:4px">${n}</div>
            </div>`;
          }).join("")}
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>读者</th><th>等级</th><th>院系</th><th>在借/配额</th><th>逾期</th><th>信用分</th><th></th></tr></thead>
            <tbody>
              ${db.members.map(m => `
                <tr>
                  <td><div class="book-cell">
                    <div class="op__avatar" style="width:34px;height:34px;border-radius:8px;font-size:13px">${esc(m.name[0])}</div>
                    <div><div class="cell-title">${esc(m.name)}</div><div class="cell-sub">${m.id} · 自 ${m.since}</div></div>
                  </div></td>
                  <td><span class="tag tag--${levelTag[m.level]}">${esc(m.level)}</span></td>
                  <td>${esc(m.dept)}</td>
                  <td><span style="font-family:var(--mono)">${m.borrowed} / ${m.quota}</span>
                    <div class="bar" style="margin-top:4px;width:80px"><i style="width:${m.borrowed / m.quota * 100}%"></i></div></td>
                  <td>${m.overdue ? `<span class="tag tag--red">${m.overdue}</span>` : `<span style="color:var(--txt-mut)">—</span>`}</td>
                  <td><span style="font-family:var(--mono);color:${m.credit > 700 ? "var(--green)" : m.credit > 450 ? "var(--amber)" : "var(--red)"}">${m.credit}</span></td>
                  <td><button class="btn btn--ghost" onclick="NEXUS.memberDetail('${m.id}')">详情</button></td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>`;
    },

    /* ---------------- 流通调度 ---------------- */
    circulation() {
      const rows = db.loans.map(l => {
        const b = bookById(l.book), m = memberById(l.member);
        let status, days = "";
        if (l.status === "returned") status = `<span class="tag tag--green">已归还</span>`;
        else if (l.status === "overdue") { const od = daysBetween(l.due, todayISO); status = `<span class="tag tag--red">逾期 ${od}天</span>`; }
        else { const left = daysBetween(todayISO, l.due); status = `<span class="tag tag--blue">在借 ${left}天</span>`; }
        const action = l.status === "returned"
          ? `<span style="color:var(--txt-mut)">—</span>`
          : `<button class="btn btn--ghost" onclick="NEXUS.returnLoan('${l.id}')">办理归还</button>`;
        return `<tr>
          <td><span class="cell-sub">${l.id}</span></td>
          <td><div class="book-cell">${b ? fmtCover(b) : ""}<div><div class="cell-title">${b ? esc(b.title) : l.book}</div><div class="cell-sub">${b ? esc(b.author) : ""}</div></div></div></td>
          <td>${m ? esc(m.name) : l.member}<div class="cell-sub">${l.member}</div></td>
          <td class="cell-sub">${l.out}</td><td class="cell-sub">${l.due}</td>
          <td>${status}</td><td>${action}</td>
        </tr>`;
      }).join("");
      const s = stats();
      return `<div class="view">
        <div class="section-head">
          <div><h2><span class="tagdot"></span>流通调度</h2><p>CIRCULATION CONTROL · ${s.activeLoans} 笔在借</p></div>
          <button class="btn" onclick="NEXUS.openLoanForm()"><i class="ico ico-plus"></i>登记借阅</button>
        </div>
        <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">
          <div class="kpi" style="--accent:#22e0ff44"><div class="kpi__label">今日借出</div><div class="kpi__val" style="color:var(--cyan)">37</div><div class="kpi__delta up">▲ 较昨 +9</div></div>
          <div class="kpi" style="--accent:#1ff0a844"><div class="kpi__label">今日归还</div><div class="kpi__val" style="color:var(--green)">29</div><div class="kpi__delta up">▲ 较昨 +4</div></div>
          <div class="kpi" style="--accent:#ff5a7a44"><div class="kpi__label">待催还</div><div class="kpi__val" style="color:var(--red)">${s.overdue}</div><div class="kpi__delta down">需处理</div></div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>单号</th><th>书目</th><th>读者</th><th>借出</th><th>应还</th><th>状态</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
    },

    /* ---------------- 数据透析 ---------------- */
    analytics() {
      const maxCat = Math.max(...db.categories.map(c => c.count));
      const s = stats();
      const utilization = Math.round(s.outNow / s.totalVol * 100);
      return `<div class="view">
        <div class="section-head">
          <div><h2><span class="tagdot"></span>数据透析</h2><p>ANALYTICS ENGINE · 运营画像与馆藏健康度</p></div>
        </div>
        <div class="grid-2">
          <div class="panel">
            <div class="panel__head"><h3>分类藏量分布</h3><span class="more">DISTRIBUTION</span></div>
            <div class="barchart">
              ${db.categories.map(c => `
                <div class="col">
                  <i style="height:0" data-h="${c.count / maxCat * 100}" data-color="${c.color}"></i>
                  <span>${esc(c.name)}</span>
                </div>`).join("")}
            </div>
          </div>
          <div class="panel">
            <div class="panel__head"><h3>馆藏健康度</h3><span class="more">HEALTH</span></div>
            <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">
              <div class="ring" id="utilRing" style="--p:0"><b id="utilNum">0%</b><small>周转率</small></div>
              <div style="flex:1;min-width:160px">
                <div style="margin-bottom:14px"><div style="font-size:12px;color:var(--txt-mut);margin-bottom:5px">可借率</div><div class="bar"><i style="width:${Math.round(s.avail / s.totalVol * 100)}%"></i></div></div>
                <div style="margin-bottom:14px"><div style="font-size:12px;color:var(--txt-mut);margin-bottom:5px">逾期占比</div><div class="bar"><i style="width:${Math.round(s.overdue / Math.max(1, s.activeLoans) * 100)}%;background:linear-gradient(90deg,var(--amber),var(--red))"></i></div></div>
                <div><div style="font-size:12px;color:var(--txt-mut);margin-bottom:5px">读者活跃度</div><div class="bar"><i style="width:74%;background:linear-gradient(90deg,var(--green),var(--cyan))"></i></div></div>
              </div>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel__head"><h3>借还趋势分析 · 近 7 日</h3><span class="more">TREND</span></div>
          <canvas id="trendChart2" class="linechart" style="height:220px"></canvas>
        </div>
      </div>`;
    },

    /* ---------------- 馆藏拓扑 ---------------- */
    shelf() {
      return `<div class="view">
        <div class="section-head">
          <div><h2><span class="tagdot"></span>馆藏拓扑</h2><p>SHELF TOPOLOGY · 6 个分区 · 实时占用</p></div>
        </div>
        <div class="shelf-grid">
          ${db.zones.map(z => {
            const cells = Array.from({ length: 64 }, (_, i) => {
              if (i < z.used) return '<i class="f"></i>';
              if (i < z.used + 4) return '<i class="h"></i>';
              return "<i></i>";
            }).join("");
            const pct = Math.round(z.used / z.cap * 100);
            return `<div class="zone" onclick="NEXUS.toast('分区 ${z.code} · 占用 ${pct}%','')">
              <div class="zone__code">ZONE ${z.code}</div>
              <div class="zone__name">${esc(z.name)}</div>
              <div class="zone__cells">${cells}</div>
              <div class="zone__meta"><span>${z.used}/${z.cap}</span><span style="color:${pct > 85 ? "var(--red)" : pct > 60 ? "var(--amber)" : "var(--green)"}">${pct}%</span></div>
            </div>`;
          }).join("")}
        </div>
      </div>`;
    }
  };

  /* ============================================================
     渲染后副作用（图表/表格填充）
     ============================================================ */
  const AFTER = {
    dashboard() {
      drawTrend("trendChart");
      animateRing("catRing", "catRingNum", db.categories.reduce((s, c) => s + c.count, 0), 100, "");
    },
    catalog() {
      renderCatalog();
      $("#catSearch").addEventListener("input", renderCatalog);
      $$(".chip").forEach(c => c.addEventListener("click", () => {
        $$(".chip").forEach(x => x.classList.remove("is-active"));
        c.classList.add("is-active"); renderCatalog();
      }));
      $$("#bookTable thead th[data-sort]").forEach(th => th.addEventListener("click", () => {
        const k = th.dataset.sort;
        sortState.dir = sortState.key === k ? -sortState.dir : 1;
        sortState.key = k; renderCatalog();
      }));
      $("#catViewToggle").addEventListener("click", e => {
        const b = e.target.closest("button"); if (!b) return;
        catMode = b.dataset.mode;
        $$("#catViewToggle button").forEach(x => x.classList.toggle("is-active", x === b));
        $("#catTableWrap").hidden = catMode !== "table";
        $("#catCards").hidden = catMode !== "cards";
        renderCatalog();
      });
    },
    analytics() {
      $$(".barchart .col i").forEach(el => {
        const h = el.dataset.h;
        el.style.background = `linear-gradient(180deg,${el.dataset.color},${el.dataset.color}66)`;
        requestAnimationFrame(() => { el.style.height = h + "%"; });
      });
      const s = stats();
      animateRing("utilRing", "utilNum", Math.round(s.outNow / s.totalVol * 100), 100, "%");
      drawTrend("trendChart2", true);
    }
  };

  let sortState = { key: "title", dir: 1 };
  let catMode = "table";
  function filteredBooks() {
    const cat = $(".chip.is-active")?.dataset.cat || "全部";
    const q = ($("#catSearch")?.value || "").trim().toLowerCase();
    let list = db.books.filter(b =>
      (cat === "全部" || b.cat === cat) &&
      (!q || b.title.toLowerCase().includes(q) || b.author.toLowerCase().includes(q) || b.isbn.includes(q))
    );
    const { key, dir } = sortState;
    list.sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir);
    return list;
  }
  function renderCatalog() {
    if (catMode === "cards") renderBookCards(); else renderBookTable();
  }
  function renderBookCards() {
    const list = filteredBooks();
    const host = $("#catCards"); if (!host) return;
    if (!list.length) { host.innerHTML = `<div class="empty" style="grid-column:1/-1">无匹配书目</div>`; return; }
    host.innerHTML = list.map(b => `
      <div class="bcard" onclick="NEXUS.bookDetail('${b.id}')">
        <div class="bcard__top" style="background:linear-gradient(140deg,${b.cover[0]},${b.cover[1]})">
          <span class="bcard__zone">${b.zone}</span>
          <span class="bcard__big">${esc(b.title[0])}</span>
        </div>
        <div class="bcard__body">
          <div class="bcard__title">${esc(b.title)}</div>
          <div class="bcard__sub">${esc(b.author)} · ${esc(b.cat)}</div>
          <div class="bcard__foot">${bookStatusTag(b)}<span style="color:var(--amber);font-size:12px">★ ${b.rating}</span></div>
        </div>
      </div>`).join("");
  }
  function renderBookTable() {
    const list = filteredBooks();
    $$("#bookTable thead th[data-sort]").forEach(th => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === sortState.key) th.classList.add(sortState.dir === 1 ? "sort-asc" : "sort-desc");
    });
    const body = $("#bookBody");
    if (!list.length) { body.innerHTML = `<tr><td colspan="8"><div class="empty">无匹配书目</div></td></tr>`; return; }
    body.innerHTML = list.map(b => `
      <tr>
        <td><div class="book-cell">${fmtCover(b)}<div><div class="cell-title">${esc(b.title)}</div><div class="cell-sub">${esc(b.author)} · ${b.isbn}</div></div></div></td>
        <td><span class="tag tag--blue">${esc(b.cat)}</span></td>
        <td class="cell-sub">${b.year}</td>
        <td><span style="font-family:var(--mono);color:var(--cyan)">${b.zone}</span></td>
        <td><span style="color:var(--amber)">★ ${b.rating}</span></td>
        <td><span style="font-family:var(--mono)">${b.available}/${b.total}</span></td>
        <td>${bookStatusTag(b)}</td>
        <td><button class="btn btn--ghost" onclick="NEXUS.bookDetail('${b.id}')">详情</button></td>
      </tr>`).join("");
  }

  /* ---------- 折线图(canvas) ---------- */
  function drawTrend(id, big) {
    const c = $("#" + id); if (!c) return;
    const dpr = devicePixelRatio || 1;
    const rect = c.getBoundingClientRect();
    c.width = rect.width * dpr; c.height = rect.height * dpr;
    const ctx = c.getContext("2d"); ctx.scale(dpr, dpr);
    const W = rect.width, H = rect.height, pad = 28;
    const data = db.trend;
    const max = Math.max(...data.map(d => Math.max(d.borrow, d.ret))) * 1.15;
    const X = i => pad + i * (W - pad * 2) / (data.length - 1);
    const Y = v => H - pad - v / max * (H - pad * 1.5);
    // grid
    ctx.strokeStyle = "rgba(120,170,255,.08)"; ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) { const y = pad / 2 + g * (H - pad * 1.5) / 4; ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W - pad, y); ctx.stroke(); }
    function line(key, color, fill) {
      ctx.beginPath();
      data.forEach((d, i) => { const x = X(i), y = Y(d[key]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.strokeStyle = color; ctx.lineWidth = 2.4; ctx.shadowColor = color; ctx.shadowBlur = 12; ctx.stroke(); ctx.shadowBlur = 0;
      if (fill) {
        ctx.lineTo(X(data.length - 1), H - pad); ctx.lineTo(X(0), H - pad); ctx.closePath();
        const g = ctx.createLinearGradient(0, pad, 0, H); g.addColorStop(0, color + "33"); g.addColorStop(1, color + "00");
        ctx.fillStyle = g; ctx.fill();
      }
      data.forEach((d, i) => { ctx.beginPath(); ctx.arc(X(i), Y(d[key]), 3, 0, 7); ctx.fillStyle = color; ctx.fill(); });
    }
    line("borrow", "#22e0ff", true);
    line("ret", "#9a6bff", false);
    ctx.fillStyle = "rgba(123,139,181,.8)"; ctx.font = "11px monospace"; ctx.textAlign = "center";
    data.forEach((d, i) => ctx.fillText(d.d, X(i), H - 6));
  }

  function animateRing(ringId, numId, target, scale, suffix) {
    const ring = $("#" + ringId), num = $("#" + numId); if (!ring) return;
    let cur = 0; const step = target / 40;
    const t = setInterval(() => {
      cur += step; if (cur >= target) { cur = target; clearInterval(t); }
      const p = suffix === "%" ? cur : Math.min(100, cur);
      ring.style.setProperty("--p", p);
      num.textContent = Math.round(cur) + suffix;
    }, 18);
  }

  /* ============================================================
     抽屉 / 表单 / 详情
     ============================================================ */
  function openDrawer(title, html) {
    $("#drawerTitle").textContent = title;
    $("#drawerBody").innerHTML = html;
    $("#drawer").hidden = false;
  }
  function closeDrawer() { $("#drawer").hidden = true; }

  function bookDetail(id) {
    const b = bookById(id); if (!b) return;
    openDrawer("书目详情", `
      <div style="display:flex;gap:18px;margin-bottom:20px">
        <div class="detail-cover" style="background:linear-gradient(135deg,${b.cover[0]},${b.cover[1]})">${esc(b.title[0])}</div>
        <div><h3 style="margin:0 0 6px">${esc(b.title)}</h3>
          <div style="color:var(--txt-dim);font-size:13px">${esc(b.author)}</div>
          <div style="margin-top:10px">${bookStatusTag(b)} <span class="tag tag--blue">${esc(b.cat)}</span></div>
          <div style="margin-top:10px;color:var(--amber)">★ ${b.rating} · 热度 ${b.hot}</div>
        </div>
      </div>
      <dl class="kv">
        <dt>书目编号</dt><dd>${b.id}</dd>
        <dt>ISBN</dt><dd>${b.isbn}</dd>
        <dt>出版年份</dt><dd>${b.year}</dd>
        <dt>馆藏位置</dt><dd style="color:var(--cyan);font-family:var(--mono)">${b.zone}</dd>
        <dt>库存</dt><dd>${b.available} 在架 / 共 ${b.total} 册</dd>
      </dl>
      <div class="drawer__foot">
        ${b.available > 0 ? `<button class="btn" onclick="NEXUS.quickBorrow('${b.id}')"><i class="ico ico-swap"></i>快速借出</button>` : `<button class="btn btn--ghost" disabled>暂无可借</button>`}
        <button class="btn btn--ghost" onclick="NEXUS.openBookForm('${b.id}')">编辑</button>
        <button class="btn btn--danger" onclick="NEXUS.deleteBook('${b.id}')">下架</button>
      </div>`);
  }

  function memberDetail(id) {
    const m = memberById(id); if (!m) return;
    const loans = db.loans.filter(l => l.member === id);
    openDrawer("读者档案", `
      <div style="display:flex;gap:16px;align-items:center;margin-bottom:20px">
        <div class="op__avatar" style="width:60px;height:60px;border-radius:14px;font-size:24px">${esc(m.name[0])}</div>
        <div><h3 style="margin:0">${esc(m.name)}</h3><div style="color:var(--txt-mut);font-size:13px">${m.id} · ${esc(m.dept)}</div>
        <div style="margin-top:8px"><span class="tag tag--violet">${esc(m.level)}会员</span></div></div>
      </div>
      <dl class="kv">
        <dt>注册时间</dt><dd>${m.since}</dd>
        <dt>联系方式</dt><dd>${m.contact}</dd>
        <dt>借阅配额</dt><dd>${m.borrowed} / ${m.quota} 册</dd>
        <dt>逾期次数</dt><dd style="color:${m.overdue ? "var(--red)" : "var(--green)"}">${m.overdue}</dd>
        <dt>信用积分</dt><dd style="color:var(--cyan);font-family:var(--mono)">${m.credit}</dd>
      </dl>
      <div class="panel" style="margin-top:18px">
        <div class="panel__head"><h3>借阅记录</h3></div>
        ${loans.length ? loans.map(l => { const b = bookById(l.book);
          return `<div class="feed__row"><span class="feed__dot" style="background:${l.status === "overdue" ? "var(--red)" : l.status === "returned" ? "var(--green)" : "var(--cyan)"}"></span>
          <div class="feed__txt">${b ? esc(b.title) : l.book}<small>${l.out} → ${l.due}</small></div>
          <span class="feed__time">${l.status === "returned" ? "已还" : l.status === "overdue" ? "逾期" : "在借"}</span></div>`;
        }).join("") : `<div class="empty" style="padding:20px">暂无借阅记录</div>`}
      </div>
      <div class="drawer__foot"><button class="btn btn--ghost" onclick="NEXUS.closeDrawer()">关闭</button></div>`);
  }

  function openBookForm(id) {
    const b = id ? bookById(id) : null;
    openDrawer(b ? "编辑书目" : "新增书目", `
      <form id="bookForm">
        <div class="form-row"><label>书名 *</label><input name="title" required value="${b ? esc(b.title) : ""}" /></div>
        <div class="form-grid">
          <div class="form-row"><label>作者 *</label><input name="author" required value="${b ? esc(b.author) : ""}" /></div>
          <div class="form-row"><label>分类</label><select name="cat">${["科幻","文学","历史","计算机","科普","经济"].map(c => `<option ${b && b.cat === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
        </div>
        <div class="form-grid">
          <div class="form-row"><label>ISBN</label><input name="isbn" value="${b ? esc(b.isbn) : ""}" placeholder="978-..." /></div>
          <div class="form-row"><label>出版年份</label><input name="year" type="number" value="${b ? b.year : 2024}" /></div>
        </div>
        <div class="form-grid">
          <div class="form-row"><label>馆藏位置</label><input name="zone" value="${b ? esc(b.zone) : "A-01"}" /></div>
          <div class="form-row"><label>馆藏册数</label><input name="total" type="number" value="${b ? b.total : 3}" min="1" /></div>
        </div>
        <div class="drawer__foot">
          <button type="submit" class="btn"><i class="ico ico-plus"></i>${b ? "保存修改" : "确认入库"}</button>
          <button type="button" class="btn btn--ghost" onclick="NEXUS.closeDrawer()">取消</button>
        </div>
      </form>`);
    $("#bookForm").addEventListener("submit", e => {
      e.preventDefault();
      const f = new FormData(e.target);
      if (b) {
        Object.assign(b, { title: f.get("title"), author: f.get("author"), cat: f.get("cat"), isbn: f.get("isbn"), year: +f.get("year"), zone: f.get("zone") });
        const newTotal = +f.get("total"); b.available += newTotal - b.total; b.total = newTotal;
        if (b.available < 0) b.available = 0;
        toast("书目已更新：" + b.title, "ok");
      } else {
        const total = +f.get("total");
        const palette = [["#3d7bff", "#9a6bff"], ["#22e0ff", "#1ff0a8"], ["#ffc24b", "#ff5a7a"]];
        db.books.push({ id: "BK-" + (1000 + db.books.length + 1), title: f.get("title"), author: f.get("author"),
          isbn: f.get("isbn") || "—", cat: f.get("cat"), year: +f.get("year"), zone: f.get("zone"),
          total, available: total, rating: 4.0, hot: 30, cover: palette[db.books.length % 3] });
        toast("新书已入库：" + f.get("title"), "ok");
      }
      State.save(); closeDrawer(); render(current);
    });
  }

  function openMemberForm() {
    openDrawer("注册读者", `
      <form id="memForm">
        <div class="form-row"><label>姓名 *</label><input name="name" required /></div>
        <div class="form-grid">
          <div class="form-row"><label>院系</label><input name="dept" value="计算机学院" /></div>
          <div class="form-row"><label>会员等级</label><select name="level"><option>普通</option><option>白银</option><option>黄金</option><option>铂金</option></select></div>
        </div>
        <div class="form-row"><label>联系方式</label><input name="contact" placeholder="手机号" /></div>
        <div class="drawer__foot">
          <button type="submit" class="btn"><i class="ico ico-plus"></i>确认注册</button>
          <button type="button" class="btn btn--ghost" onclick="NEXUS.closeDrawer()">取消</button>
        </div>
      </form>`);
    $("#memForm").addEventListener("submit", e => {
      e.preventDefault();
      const f = new FormData(e.target);
      const quota = { 普通: 3, 白银: 5, 黄金: 8, 铂金: 12 }[f.get("level")];
      db.members.push({ id: "RD-" + (2000 + db.members.length + 1), name: f.get("name"), level: f.get("level"),
        since: "2026-06", borrowed: 0, quota, overdue: 0, credit: 500, contact: f.get("contact") || "—", dept: f.get("dept") });
      toast("读者已注册：" + f.get("name"), "ok");
      State.save(); closeDrawer(); render(current);
    });
  }

  function openLoanForm() {
    const avail = db.books.filter(b => b.available > 0);
    openDrawer("登记借阅", `
      <form id="loanForm">
        <div class="form-row"><label>选择书目 *</label><select name="book" required>${avail.map(b => `<option value="${b.id}">${esc(b.title)} · 在架 ${b.available}</option>`).join("")}</select></div>
        <div class="form-row"><label>选择读者 *</label><select name="member" required>${db.members.map(m => `<option value="${m.id}">${esc(m.name)} · ${m.borrowed}/${m.quota}</option>`).join("")}</select></div>
        <div class="form-row"><label>借期</label><select name="span"><option value="14">14 天（标准）</option><option value="30">30 天（教师）</option><option value="7">7 天（短借）</option></select></div>
        <div class="drawer__foot">
          <button type="submit" class="btn"><i class="ico ico-swap"></i>确认借出</button>
          <button type="button" class="btn btn--ghost" onclick="NEXUS.closeDrawer()">取消</button>
        </div>
      </form>`);
    $("#loanForm").addEventListener("submit", e => {
      e.preventDefault();
      const f = new FormData(e.target);
      doBorrow(f.get("book"), f.get("member"), +f.get("span"));
      closeDrawer();
    });
  }

  function doBorrow(bookId, memberId, span = 14) {
    const b = bookById(bookId), m = memberById(memberId);
    if (!b || !m) return;
    if (b.available <= 0) return toast("该书已无可借库存", "err");
    if (m.borrowed >= m.quota) return toast(m.name + " 已达借阅配额", "warn");
    b.available--; m.borrowed++;
    const due = new Date(todayISO); due.setDate(due.getDate() + span);
    const dueISO = due.toISOString().slice(0, 10);
    db.loans.unshift({ id: "LN-" + (30030 + db.loans.length + 1), book: bookId, member: memberId, out: todayISO, due: dueISO, status: "active" });
    db.activity.unshift({ type: "borrow", who: m.name, what: `借出《${b.title}》`, time: "现在", color: "#22e0ff" });
    if (db.activity.length > 8) db.activity.pop();
    toast(`${m.name} 借出《${b.title}》，应还 ${dueISO}`, "ok");
    State.save(); render(current);
  }

  function returnLoan(loanId) {
    const l = db.loans.find(x => x.id === loanId); if (!l) return;
    const b = bookById(l.book), m = memberById(l.member);
    l.status = "returned"; l.back = todayISO;
    if (b) b.available = Math.min(b.total, b.available + 1);
    if (m) m.borrowed = Math.max(0, m.borrowed - 1);
    db.activity.unshift({ type: "return", who: m ? m.name : l.member, what: `归还《${b ? b.title : l.book}》`, time: "现在", color: "#1ff0a8" });
    if (db.activity.length > 8) db.activity.pop();
    toast("已办理归还：" + (b ? b.title : l.book), "ok");
    State.save(); render(current);
  }

  function deleteBook(id) {
    const b = bookById(id); if (!b) return;
    if (b.available < b.total) return toast("仍有在借册次，无法下架", "warn");
    db.books = db.books.filter(x => x.id !== id);
    toast("已下架：" + b.title, "ok");
    State.save(); closeDrawer(); render(current);
  }

  /* ---------- 全局检索 ---------- */
  function globalSearch(q) {
    q = q.trim().toLowerCase(); if (!q) return;
    const book = db.books.find(b => b.title.toLowerCase().includes(q) || b.author.toLowerCase().includes(q) || b.isbn.includes(q));
    const mem = db.members.find(m => m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q));
    if (book) { render("catalog"); bookDetail(book.id); }
    else if (mem) { render("members"); memberDetail(mem.id); }
    else toast("未找到匹配：" + q, "warn");
  }

  /* ============================================================
     命令面板 ⌘K / Ctrl+K
     ============================================================ */
  const CMDK = { el: null, items: [], active: 0 };
  function cmdkActions() {
    return [
      { group: "导航", icon: "ico-grid", label: "前往 · 控制中枢", hint: "Dashboard", run: () => render("dashboard") },
      { group: "导航", icon: "ico-book", label: "前往 · 书目矩阵", hint: "Catalog", run: () => render("catalog") },
      { group: "导航", icon: "ico-user", label: "前往 · 读者档案", hint: "Members", run: () => render("members") },
      { group: "导航", icon: "ico-swap", label: "前往 · 流通调度", hint: "Circulation", run: () => render("circulation") },
      { group: "导航", icon: "ico-chart", label: "前往 · 数据透析", hint: "Analytics", run: () => render("analytics") },
      { group: "导航", icon: "ico-shelf", label: "前往 · 馆藏拓扑", hint: "Shelf", run: () => render("shelf") },
      { group: "操作", icon: "ico-plus", label: "新增书目", hint: "New book", run: () => openBookForm() },
      { group: "操作", icon: "ico-plus", label: "注册读者", hint: "New member", run: () => openMemberForm() },
      { group: "操作", icon: "ico-swap", label: "登记借阅", hint: "New loan", run: () => openLoanForm() },
      { group: "操作", icon: "ico-reset", label: "重置演示数据", hint: "Reset", run: () => { State.reset(); render(current); toast("演示数据已重置", "ok"); } },
    ];
  }
  function openCmdk() {
    if (CMDK.el) return;
    const el = document.createElement("div");
    el.className = "cmdk";
    el.innerHTML = `
      <div class="cmdk__mask" data-cmclose></div>
      <div class="cmdk__box">
        <div class="cmdk__input"><i class="ico ico-search"></i><input id="cmdkInput" placeholder="输入命令、视图或书名…" /></div>
        <div class="cmdk__list" id="cmdkList"></div>
        <div class="cmdk__foot"><span><kbd>↑↓</kbd>选择</span><span><kbd>↵</kbd>执行</span><span><kbd>esc</kbd>关闭</span></div>
      </div>`;
    document.body.appendChild(el);
    CMDK.el = el;
    el.querySelector("[data-cmclose]").addEventListener("click", closeCmdk);
    const input = $("#cmdkInput");
    input.addEventListener("input", () => buildCmdkList(input.value));
    input.addEventListener("keydown", cmdkKeys);
    buildCmdkList("");
    setTimeout(() => input.focus(), 0);
  }
  function closeCmdk() { if (CMDK.el) { CMDK.el.remove(); CMDK.el = null; CMDK.items = []; CMDK.active = 0; } }
  function buildCmdkList(q) {
    q = q.trim().toLowerCase();
    let items = cmdkActions().filter(a => !q || a.label.toLowerCase().includes(q) || a.hint.toLowerCase().includes(q));
    if (q) {
      db.books.filter(b => b.title.toLowerCase().includes(q) || b.author.toLowerCase().includes(q)).slice(0, 6)
        .forEach(b => items.push({ group: "书目", icon: "ico-book", label: b.title, hint: b.author, run: () => { render("catalog"); bookDetail(b.id); } }));
      db.members.filter(m => m.name.toLowerCase().includes(q)).slice(0, 4)
        .forEach(m => items.push({ group: "读者", icon: "ico-user", label: m.name, hint: m.dept, run: () => { render("members"); memberDetail(m.id); } }));
    }
    CMDK.items = items; CMDK.active = 0;
    const list = $("#cmdkList");
    if (!items.length) { list.innerHTML = `<div class="empty" style="padding:30px">无匹配项</div>`; return; }
    let html = "", lastG = "";
    items.forEach((it, i) => {
      if (it.group !== lastG) { html += `<div class="cmdk__group">${it.group}</div>`; lastG = it.group; }
      html += `<div class="cmdk__item ${i === 0 ? "is-active" : ""}" data-i="${i}"><i class="ico ${it.icon}"></i><span>${esc(it.label)}</span><small>${esc(it.hint)}</small></div>`;
    });
    list.innerHTML = html;
    $$("#cmdkList .cmdk__item").forEach(node => {
      node.addEventListener("mouseenter", () => setCmdkActive(+node.dataset.i));
      node.addEventListener("click", () => runCmdk(+node.dataset.i));
    });
  }
  function setCmdkActive(i) {
    CMDK.active = i;
    $$("#cmdkList .cmdk__item").forEach(n => n.classList.toggle("is-active", +n.dataset.i === i));
  }
  function runCmdk(i) { const it = CMDK.items[i]; if (it) { closeCmdk(); it.run(); } }
  function cmdkKeys(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); setCmdkActive(Math.min(CMDK.items.length - 1, CMDK.active + 1)); scrollCmdk(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCmdkActive(Math.max(0, CMDK.active - 1)); scrollCmdk(); }
    else if (e.key === "Enter") { e.preventDefault(); runCmdk(CMDK.active); }
    else if (e.key === "Escape") { e.preventDefault(); closeCmdk(); }
  }
  function scrollCmdk() { const n = $(`#cmdkList .cmdk__item[data-i="${CMDK.active}"]`); if (n) n.scrollIntoView({ block: "nearest" }); }

  /* ============================================================
     绑定 & 启动
     ============================================================ */
  function bind() {
    $("#nav").addEventListener("click", e => {
      const item = e.target.closest(".nav__item"); if (item) render(item.dataset.view);
    });
    $$("[data-close]").forEach(el => el.addEventListener("click", closeDrawer));
    $("#seedBtn").addEventListener("click", () => { State.reset(); toast("演示数据已重置", "ok"); render(current); });
    $("#cmdkBtn").addEventListener("click", () => CMDK.el ? closeCmdk() : openCmdk());
    const gs = $("#globalSearch");
    gs.addEventListener("keydown", e => { if (e.key === "Enter") globalSearch(gs.value); });
    document.addEventListener("keydown", e => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); CMDK.el ? closeCmdk() : openCmdk(); return; }
      if (e.key === "/" && document.activeElement !== gs && !CMDK.el) { e.preventDefault(); gs.focus(); }
      if (e.key === "Escape") closeDrawer();
    });
  }

  window.NEXUS = { bookDetail, memberDetail, openBookForm, openMemberForm, openLoanForm,
    quickBorrow: (id) => { closeDrawer(); openLoanForm(); setTimeout(() => { const sel = $("#loanForm [name=book]"); if (sel) sel.value = id; }, 0); },
    returnLoan, deleteBook, closeDrawer, toast };

  // 启动
  particles(); liveClock(); bind(); boot();
})();
