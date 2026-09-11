"""MCP Server 入口。

对外通过 Streamable HTTP 暴露工具:query_metrics / query_logs / exec_command /
get_host_info / list_alarms / create_schedule / send_notify / search_runbook。

TODO: 接入 MCP SDK,注册 tools/ 下的各工具函数。
"""


def main() -> None:
    raise NotImplementedError("MCP server entrypoint not yet implemented")


if __name__ == "__main__":
    main()
