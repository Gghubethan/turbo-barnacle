# knowledge/ — vault 就绪的结构化笔记

这里放**已经三分完成**的笔记，目录名与 vault 一致（见 [`docs/obsidian-ai-integration.md`](../docs/obsidian-ai-integration.md) §4）。
frontmatter 按同一契约：`type / status / tags / source / related / ai_processed / ai_model`。
把整个子目录复制进 vault 对应位置即可，双链按文件名解析。

```
knowledge/
├── 10_Notes/        # 原子笔记（一条一个想法）
├── 20_Sources/      # 文献笔记；会议纪要/ 下按 YYYY-MM-DD-主题 命名
├── 30_Projects/     # 进行中的项目（含机器可读草案 *.yaml）
└── 60_MOC/          # 知识地图
```

## 当前内容：宝岛眼镜 MOC 入职 & 镜片功能标准化

入口：[`60_MOC/宝岛眼镜-MOC赋能中心.md`](60_MOC/宝岛眼镜-MOC赋能中心.md)
主线：[`30_Projects/镜片功能标准化与自动推荐.md`](30_Projects/镜片功能标准化与自动推荐.md)

来源是 2026-09-23 / 09-24 的会议**转写**，噪声大：数字以纪要为准但标了「待核」，品牌与系列名按转写原文记录。

## 校验

```bash
python3 scripts/check_notes.py   # 校验 knowledge/ 下 frontmatter 契约与双链是否可解析
```
