"""ToolBridge: Skill tools URI 路由器。

支持两种 URI 协议：
  mcp://server/tool  → MCPClientManager.call_tool_sync()
  local://module.func → importlib 动态加载 stocksage.tools.{module}.{func}
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ToolBridge:
    """将 tool URI 分发到对应的实现。"""

    def __init__(self, mcp_manager=None):
        self._mcp = mcp_manager
        self._local_cache: dict[str, Callable] = {}

    def call(self, tool_uri: str, arguments: dict) -> Any:
        """根据 URI scheme 分发工具调用。"""
        if tool_uri.startswith("mcp://"):
            return self._call_mcp(tool_uri, arguments)
        if tool_uri.startswith("local://"):
            return self._call_local(tool_uri, arguments)
        logger.warning("未知工具 URI scheme: %s", tool_uri)
        return None

    def _call_mcp(self, uri: str, arguments: dict) -> Any:
        """解析 mcp://server/tool 并调用 MCPClientManager。"""
        if not self._mcp:
            logger.debug("MCP 不可用，跳过: %s", uri)
            return None

        path = uri[len("mcp://"):]
        parts = path.split("/", 1)
        if len(parts) != 2:
            logger.warning("无效 MCP URI: %s", uri)
            return None

        server_name, tool_name = parts
        return self._mcp.call_tool_sync(server_name, tool_name, arguments)

    def _call_local(self, uri: str, arguments: dict) -> Any:
        """解析 local://module.func 并调用本地 Python 函数。"""
        path = uri[len("local://"):]

        if path not in self._local_cache:
            parts = path.rsplit(".", 1)
            if len(parts) != 2:
                logger.warning("无效 local 工具 URI: %s", uri)
                return None
            module_path, func_name = parts
            try:
                module = importlib.import_module(f"stocksage.tools.{module_path}")
                self._local_cache[path] = getattr(module, func_name)
            except (ImportError, AttributeError) as e:
                logger.warning("加载本地工具失败 %s: %s", uri, e)
                return None

        fn = self._local_cache.get(path)
        return fn(**arguments) if fn else None
