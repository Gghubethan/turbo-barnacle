/* ============================================================
   NEXUS Library OS — 演示数据 (seed)
   纯前端，localStorage 持久化；点顶栏重置按钮可恢复。
   ============================================================ */
window.SEED = (function () {
  const COVERS = [
    ["#3d7bff", "#9a6bff"], ["#22e0ff", "#3d7bff"], ["#1ff0a8", "#22e0ff"],
    ["#ffc24b", "#ff5a7a"], ["#9a6bff", "#ff5a7a"], ["#ff5a7a", "#ffc24b"],
    ["#22e0ff", "#1ff0a8"], ["#3d7bff", "#22e0ff"]
  ];
  const cat = (n) => n;

  const books = [
    { id: "BK-1001", title: "三体", author: "刘慈欣", isbn: "978-7-5366-9293-0", cat: "科幻", year: 2008, zone: "A-12", total: 8, available: 3, rating: 4.9, hot: 98 },
    { id: "BK-1002", title: "人类简史", author: "尤瓦尔·赫拉利", isbn: "978-7-5086-4348-5", cat: "历史", year: 2014, zone: "C-03", total: 6, available: 0, rating: 4.7, hot: 91 },
    { id: "BK-1003", title: "深度学习", author: "Ian Goodfellow", isbn: "978-7-115-46147-6", cat: "计算机", year: 2017, zone: "E-21", total: 5, available: 2, rating: 4.6, hot: 88 },
    { id: "BK-1004", title: "百年孤独", author: "加西亚·马尔克斯", isbn: "978-7-5442-5399-4", cat: "文学", year: 1967, zone: "B-07", total: 4, available: 1, rating: 4.8, hot: 84 },
    { id: "BK-1005", title: "算法导论", author: "Thomas Cormen", isbn: "978-7-111-40701-0", cat: "计算机", year: 2009, zone: "E-22", total: 7, available: 4, rating: 4.7, hot: 79 },
    { id: "BK-1006", title: "时间简史", author: "史蒂芬·霍金", isbn: "978-7-5354-3230-3", cat: "科普", year: 1988, zone: "D-11", total: 5, available: 0, rating: 4.5, hot: 76 },
    { id: "BK-1007", title: "明朝那些事儿", author: "当年明月", isbn: "978-7-80211-558-9", cat: "历史", year: 2009, zone: "C-05", total: 9, available: 6, rating: 4.6, hot: 73 },
    { id: "BK-1008", title: "解忧杂货店", author: "东野圭吾", isbn: "978-7-5442-6738-0", cat: "文学", year: 2012, zone: "B-09", total: 6, available: 2, rating: 4.5, hot: 70 },
    { id: "BK-1009", title: "图解密码技术", author: "结城浩", isbn: "978-7-115-43512-5", cat: "计算机", year: 2016, zone: "E-18", total: 4, available: 3, rating: 4.4, hot: 64 },
    { id: "BK-1010", title: "国富论", author: "亚当·斯密", isbn: "978-7-100-04153-5", cat: "经济", year: 1776, zone: "F-02", total: 3, available: 1, rating: 4.3, hot: 58 },
    { id: "BK-1011", title: "未来简史", author: "尤瓦尔·赫拉利", isbn: "978-7-5086-6537-1", cat: "历史", year: 2017, zone: "C-04", total: 5, available: 0, rating: 4.5, hot: 81 },
    { id: "BK-1012", title: "球状闪电", author: "刘慈欣", isbn: "978-7-220-08092-2", cat: "科幻", year: 2004, zone: "A-13", total: 6, available: 4, rating: 4.6, hot: 67 },
    { id: "BK-1013", title: "活着", author: "余华", isbn: "978-7-5063-7505-7", cat: "文学", year: 1993, zone: "B-01", total: 7, available: 0, rating: 4.9, hot: 89 },
    { id: "BK-1014", title: "经济学原理", author: "曼昆", isbn: "978-7-301-22321-0", cat: "经济", year: 2014, zone: "F-05", total: 5, available: 2, rating: 4.2, hot: 52 },
    { id: "BK-1015", title: "宇宙的琴弦", author: "布莱恩·格林", isbn: "978-7-5356-8295-2", cat: "科普", year: 1999, zone: "D-14", total: 3, available: 1, rating: 4.4, hot: 49 },
    { id: "BK-1016", title: "代码大全", author: "Steve McConnell", isbn: "978-7-121-02298-2", cat: "计算机", year: 2004, zone: "E-25", total: 6, available: 5, rating: 4.7, hot: 62 },
  ].map((b, i) => ({ ...b, cover: COVERS[i % COVERS.length] }));

  const members = [
    { id: "RD-2001", name: "陈思远", level: "黄金", since: "2021-03", borrowed: 2, quota: 8, overdue: 0, credit: 720, contact: "139****2048", dept: "计算机学院" },
    { id: "RD-2002", name: "林婉清", level: "白银", since: "2022-09", borrowed: 1, quota: 5, overdue: 1, credit: 540, contact: "138****8821", dept: "外国语学院" },
    { id: "RD-2003", name: "赵立honoré", level: "铂金", since: "2019-06", borrowed: 4, quota: 12, overdue: 0, credit: 880, contact: "137****3390", dept: "物理系" },
    { id: "RD-2004", name: "王梓萱", level: "黄金", since: "2020-11", borrowed: 3, quota: 8, overdue: 0, credit: 690, contact: "135****1177", dept: "经济学院" },
    { id: "RD-2005", name: "刘宇航", level: "普通", since: "2023-04", borrowed: 0, quota: 3, overdue: 0, credit: 410, contact: "131****6654", dept: "历史系" },
    { id: "RD-2006", name: "周慕云", level: "白银", since: "2022-01", borrowed: 2, quota: 5, overdue: 2, credit: 360, contact: "133****9902", dept: "文学院" },
    { id: "RD-2007", name: "孙若曦", level: "铂金", since: "2018-09", borrowed: 5, quota: 12, overdue: 0, credit: 910, contact: "150****4471", dept: "计算机学院" },
    { id: "RD-2008", name: "黄景行", level: "普通", since: "2024-02", borrowed: 1, quota: 3, overdue: 0, credit: 470, contact: "188****2235", dept: "数学系" },
  ].map(m => { const fix = m.name.replace("honoré", "诚"); return { ...m, name: fix }; });

  // 流通记录
  const loans = [
    { id: "LN-30021", book: "BK-1002", member: "RD-2002", out: "2026-06-01", due: "2026-06-15", status: "overdue" },
    { id: "LN-30022", book: "BK-1006", member: "RD-2006", out: "2026-06-10", due: "2026-06-24", status: "overdue" },
    { id: "LN-30023", book: "BK-1001", member: "RD-2001", out: "2026-06-20", due: "2026-07-04", status: "active" },
    { id: "LN-30024", book: "BK-1013", member: "RD-2007", out: "2026-06-22", due: "2026-07-06", status: "active" },
    { id: "LN-30025", book: "BK-1011", member: "RD-2004", out: "2026-06-25", due: "2026-07-09", status: "active" },
    { id: "LN-30026", book: "BK-1005", member: "RD-2003", out: "2026-06-26", due: "2026-07-10", status: "active" },
    { id: "LN-30027", book: "BK-1003", member: "RD-2008", out: "2026-06-12", due: "2026-06-26", status: "returned", back: "2026-06-25" },
    { id: "LN-30028", book: "BK-1007", member: "RD-2001", out: "2026-05-30", due: "2026-06-13", status: "returned", back: "2026-06-12" },
    { id: "LN-30029", book: "BK-1013", member: "RD-2006", out: "2026-06-18", due: "2026-07-02", status: "active" },
    { id: "LN-30030", book: "BK-1011", member: "RD-2007", out: "2026-06-23", due: "2026-07-07", status: "active" },
  ];

  const activity = [
    { type: "borrow", who: "孙若曦", what: "借出《活着》", time: "08:42", color: "#22e0ff" },
    { type: "return", who: "陈思远", what: "归还《明朝那些事儿》", time: "08:30", color: "#1ff0a8" },
    { type: "overdue", who: "周慕云", what: "《时间简史》逾期 4 天", time: "08:11", color: "#ff5a7a" },
    { type: "new", who: "系统", what: "新书《代码大全》入库 ×6", time: "07:55", color: "#9a6bff" },
    { type: "member", who: "黄景行", what: "新读者注册 · 数学系", time: "07:40", color: "#ffc24b" },
    { type: "borrow", who: "赵立诚", what: "借出《算法导论》", time: "07:22", color: "#22e0ff" },
  ];

  // 近 7 天借/还趋势
  const trend = [
    { d: "周一", borrow: 42, ret: 38 },
    { d: "周二", borrow: 51, ret: 44 },
    { d: "周三", borrow: 47, ret: 49 },
    { d: "周四", borrow: 63, ret: 52 },
    { d: "周五", borrow: 78, ret: 61 },
    { d: "周六", borrow: 95, ret: 70 },
    { d: "周日", borrow: 88, ret: 84 },
  ];

  const categories = [
    { name: "计算机", count: 22, color: "#22e0ff" },
    { name: "文学", count: 17, color: "#9a6bff" },
    { name: "历史", count: 19, color: "#3d7bff" },
    { name: "科幻", count: 14, color: "#1ff0a8" },
    { name: "科普", count: 11, color: "#ffc24b" },
    { name: "经济", count: 8, color: "#ff5a7a" },
  ];

  const zones = [
    { code: "A", name: "科幻 · 幻想", cap: 64, used: 49 },
    { code: "B", name: "文学 · 小说", cap: 64, used: 58 },
    { code: "C", name: "历史 · 人文", cap: 64, used: 41 },
    { code: "D", name: "科普 · 自然", cap: 64, used: 33 },
    { code: "E", name: "计算机 · 工程", cap: 64, used: 60 },
    { code: "F", name: "经济 · 社科", cap: 64, used: 22 },
  ];

  return { books, members, loans, activity, trend, categories, zones };
})();
