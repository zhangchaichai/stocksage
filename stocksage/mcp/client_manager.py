"""MCPClientManager: 管理 MCP Server 子进程和工具调用。

设计原则：
- 惰性启动：首次使用时才启动 MCP Server 子进程
- 容错降级：Server 启动失败标记为不可用，不阻塞后续流程
- 同步桥接：后台线程持有 event loop，call_tool_sync() 线程安全
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any

from stocksage.mcp.config import MCPServerConfig, load_mcp_config

logger = logging.getLogger(__name__)


class MCPClientManager:
    """管理多个 MCP Server 的连接和工具调用。"""

    def __init__(self, configs: list[MCPServerConfig] | None = None):
        self._configs = {c.name: c for c in (configs or load_mcp_config())}
        self._sessions: dict[str, Any] = {}
        self._transports: dict[str, Any] = {}
        self._available: dict[str, bool] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._build_capability_index()

        # 后台 event loop，所有 async 操作在此 loop 上执行
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        # 预创建每个 server 的 Lock（必须在后台 loop 上创建）
        for name in self._configs:
            future = asyncio.run_coroutine_threadsafe(self._create_lock(name), self._loop)
            future.result(timeout=5)

    async def _create_lock(self, name: str) -> None:
        self._session_locks[name] = asyncio.Lock()

    def _build_capability_index(self) -> None:
        """构建 capability → [server_name] 反向索引。"""
        for name, cfg in self._configs.items():
            for cap in cfg.capabilities:
                self._capability_index.setdefault(cap, []).append(name)

    def find_servers_for(self, capability: str, market: str = "CN") -> list[str]:
        """查找支持指定 capability 和 market 的 server 列表。"""
        candidates = self._capability_index.get(capability, [])
        return [
            name for name in candidates
            if not self._configs[name].market or market in self._configs[name].market
        ]

    async def _ensure_session(self, server_name: str) -> Any:
        """惰性启动 MCP Server 并创建 session（加锁防止并发重复启动）。"""
        if server_name in self._sessions:
            return self._sessions[server_name]

        lock = self._session_locks.get(server_name)
        if not lock:
            return None

        async with lock:
            # double-check：拿到锁后再检查一次
            if server_name in self._sessions:
                return self._sessions[server_name]

            if self._available.get(server_name) is False:
                return None

            cfg = self._configs.get(server_name)
            if not cfg:
                return None

            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                env = {**os.environ, **cfg.env} if cfg.env else None
                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=env,
                )

                transport_ctx = stdio_client(params)
                transport = await transport_ctx.__aenter__()
                self._transports[server_name] = transport_ctx

                session = ClientSession(*transport)
                await session.__aenter__()
                await session.initialize()

                self._sessions[server_name] = session
                self._available[server_name] = True
                logger.info("MCP Server '%s' 启动成功", server_name)
                return session

            except Exception as e:
                logger.warning("MCP Server '%s' 启动失败: %s", server_name, e)
                self._available[server_name] = False
                return None

    async def call_tool(self, server_name: str, tool_name: str,
                        arguments: dict) -> dict | None:
        """在指定 MCP Server 上调用工具。失败返回 None。"""
        session = await self._ensure_session(server_name)
        if not session:
            return None

        try:
            result = await session.call_tool(tool_name, arguments)
            if not result or not hasattr(result, 'content'):
                return None
            # MCP SDK 标记的错误响应
            if getattr(result, 'isError', False):
                text = result.content[0].text if result.content else ""
                logger.warning("MCP 工具返回错误 %s/%s: %s", server_name, tool_name, text[:200])
                return None
            for item in result.content:
                if hasattr(item, 'text'):
                    try:
                        parsed = json.loads(item.text)
                        # 确保返回 dict（MCP 可能返回 JSON 数组）
                        if isinstance(parsed, list):
                            return {"data": parsed}
                        if isinstance(parsed, dict):
                            return parsed
                        return {"raw": parsed}
                    except (json.JSONDecodeError, TypeError):
                        return {"raw": item.text}
            return None
        except Exception as e:
            logger.warning("MCP 工具调用失败 %s/%s: %s", server_name, tool_name, e)
            return None

    def call_tool_sync(self, server_name: str, tool_name: str,
                       arguments: dict) -> dict | None:
        """同步版本：将 async 调用提交到后台 event loop，线程安全。"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.call_tool(server_name, tool_name, arguments),
                self._loop,
            )
            return future.result(timeout=30)
        except Exception as e:
            logger.warning("MCP 同步调用失败: %s", e)
            return None

    def shutdown(self) -> None:
        """优雅关闭所有 MCP Server session 和后台 loop。"""
        async def _cleanup():
            for name, session in self._sessions.items():
                try:
                    await session.__aexit__(None, None, None)
                except Exception:
                    pass
            for name, transport_ctx in self._transports.items():
                try:
                    await transport_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
            self._sessions.clear()
            self._transports.clear()

        try:
            future = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
            future.result(timeout=10)
        except Exception:
            pass

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        logger.info("所有 MCP Server 已关闭")
