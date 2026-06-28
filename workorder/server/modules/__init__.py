"""功能模块插件目录。

放进本目录的每个 ``*.py`` 都会被 :func:`server.api.discover_modules` 自动加载，
无需修改任何中心化注册表。每个模块约定暴露：

- ``SCHEMA: str`` —— 该模块的建表 SQL（``CREATE TABLE IF NOT EXISTS``，表名带模块前缀避免冲突）。
- ``def routes(store) -> list[tuple[str, str, callable]]`` —— 返回 (HTTP 方法, 路径正则, 处理函数)。
  处理函数签名 ``handler(req, params) -> (status_code, payload)``；``req["body"]`` 是 dict，
  ``req["query"]`` 是 parse_qs 结果；路径参数用命名组（如 ``(?P<id>\\d+)``）。
- ``def seed(store) -> None`` —— 可选，幂等的演示数据填充。

业务校验失败请抛 ``server.store.ValidationError``（→400），资源不存在抛 ``NotFound``（→404）。
"""
