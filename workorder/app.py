#!/usr/bin/env python3
"""黑湖工单系统（复刻）—— 启动入口。

零第三方依赖，标准库即可运行：

    python3 app.py                     # 默认 127.0.0.1:8000，自动灌演示数据
    python3 app.py --port 9000         # 指定端口
    python3 app.py --db my.db          # 指定数据库文件
    python3 app.py --no-seed           # 不灌演示数据
    python3 app.py --host 0.0.0.0      # 监听所有网卡（局域网可访问）
"""

import argparse

from server.api import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="黑湖工单系统（复刻）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--db", default="workorder.db", help="SQLite 数据库文件路径")
    parser.add_argument("--no-seed", action="store_true", help="不灌入演示数据")
    args = parser.parse_args()

    serve(host=args.host, port=args.port, db_path=args.db, seed=not args.no_seed)


if __name__ == "__main__":
    main()
