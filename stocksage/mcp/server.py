"""Unified MCP Server that exposes both StockSage skills and data/compute tools.

Combines skill_server (high-level multi-agent analysis) and tool_server
(low-level data fetching and indicator calculation) into a single MCP endpoint.

Usage::

    python -m stocksage.mcp.server

Or register in nanobot / Claude Desktop config::

    {
      "mcpServers": {
        "stocksage": {
          "command": "python",
          "args": ["-m", "stocksage.mcp.server"]
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_unified_mcp_server():
    """Create a single MCP Server that registers both skill and data/compute tools.

    Returns the Server instance (not yet running).
    """
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError:
        raise ImportError("MCP SDK not installed. Run: pip install mcp")

    from stocksage.data.fetcher import DataFetcher
    from stocksage.llm.factory import create_llm
    from stocksage.skill_engine.executor import SkillExecutor
    from stocksage.skill_engine.registry import SkillRegistry

    server = Server("stocksage")
    fetcher = DataFetcher()

    # ── data & compute tools ──────────────────────────────────────
    from stocksage.mcp.tool_server import _build_tools

    data_tools = _build_tools(fetcher)
    logger.info("Unified server: registered %d data/compute tools", len(data_tools))

    # ── skills ────────────────────────────────────────────────────
    import stocksage as _pkg

    skills_dir = Path(_pkg.__file__).parent / "skills"
    skill_registry = SkillRegistry()
    skill_count = skill_registry.load_from_dir(skills_dir)
    logger.info("Unified server: registered %d skills", skill_count)

    llm = create_llm()
    skill_executor = SkillExecutor(llm, fetcher)

    # Helper: build JSON Schema for a skill tool
    def _skill_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol, e.g. '600519' or 'AAPL'",
                },
                "stock_name": {
                    "type": "string",
                    "description": "Stock name (optional)",
                    "default": "",
                },
            },
            "required": ["symbol"],
        }

    # ── MCP handlers ──────────────────────────────────────────────

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        result: list[Tool] = []

        # Data / compute tools
        for tool_obj in data_tools.values():
            result.append(
                Tool(
                    name=f"stocksage_{tool_obj.name}",
                    description=tool_obj.description,
                    inputSchema=tool_obj.parameters,
                )
            )

        # Skill tools
        for name in skill_registry.list_names():
            skill = skill_registry.get(name)
            if skill is None:
                continue
            result.append(
                Tool(
                    name=f"stocksage_{name}",
                    description=skill.description or f"StockSage skill: {name} ({skill.type})",
                    inputSchema=_skill_schema(),
                )
            )

        return result

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        short_name = name.replace("stocksage_", "", 1)

        # ── Try data/compute tool first ───────────────────────────
        tool_obj = data_tools.get(short_name)
        if tool_obj is not None:
            try:
                casted = tool_obj.cast_params(arguments)
                result = await tool_obj.execute(**casted)
                return [TextContent(type="text", text=result)]
            except Exception as e:
                logger.exception("Tool '%s' failed: %s", short_name, e)
                return [TextContent(type="text", text=json.dumps(
                    {"error": str(e)}, ensure_ascii=False,
                ))]

        # ── Try skill ─────────────────────────────────────────────
        skill = skill_registry.get(short_name)
        if skill is not None:
            symbol = arguments.get("symbol", "")
            stock_name = arguments.get("stock_name", "")
            state: dict[str, Any] = {
                "meta": {"symbol": symbol, "stock_name": stock_name, "market": "cn"},
                "data": {},
                "analysis": {},
                "debate": {},
                "expert_panel": {},
                "decision": {},
                "errors": [],
            }
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: skill_executor.execute(skill, state),
                )
                return [TextContent(type="text", text=json.dumps(
                    result, ensure_ascii=False, default=str,
                ))]
            except Exception as e:
                logger.exception("Skill '%s' failed: %s", short_name, e)
                return [TextContent(type="text", text=json.dumps(
                    {"error": str(e)}, ensure_ascii=False,
                ))]

        # ── Not found ─────────────────────────────────────────────
        return [TextContent(type="text", text=json.dumps(
            {"error": f"'{short_name}' is not a known tool or skill"},
            ensure_ascii=False,
        ))]

    return server


async def main():
    """Run the unified MCP server over stdio."""
    from mcp.server.stdio import stdio_server

    server = create_unified_mcp_server()

    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
