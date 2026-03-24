"""MCP Server that exposes StockSage skills as MCP tools.

This allows external MCP clients (Claude Desktop, OpenClaw, etc.) to
discover and invoke StockSage analysis skills via the standard MCP protocol.

Usage::

    python -m stocksage.mcp.skill_server

Or register in mcp_servers.yaml / claude_desktop_config.json::

    {
      "stocksage-skills": {
        "command": "python",
        "args": ["-m", "stocksage.mcp.skill_server"]
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


def _build_tool_schema(skill) -> dict[str, Any]:
    """Build a JSON Schema for the tool input based on SkillDef."""
    properties: dict[str, Any] = {
        "symbol": {
            "type": "string",
            "description": "Stock symbol, e.g. '600519' or 'AAPL'",
        },
        "stock_name": {
            "type": "string",
            "description": "Stock name (optional)",
            "default": "",
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["symbol"],
    }


def create_skill_mcp_server():
    """Create and return an MCP Server exposing all StockSage skills.

    Returns the Server instance (not yet running).
    """
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError:
        raise ImportError(
            "MCP SDK not installed. Run: pip install mcp"
        )

    from stocksage.data.fetcher import DataFetcher
    from stocksage.llm.factory import create_llm
    from stocksage.skill_engine.executor import SkillExecutor
    from stocksage.skill_engine.registry import SkillRegistry

    server = Server("stocksage-skills")

    # Load skills
    import stocksage
    skills_dir = Path(stocksage.__file__).parent / "skills"
    registry = SkillRegistry()
    count = registry.load_from_dir(skills_dir)
    logger.info("Loaded %d skills for MCP server", count)

    # Create executor
    llm = create_llm()
    fetcher = DataFetcher()
    executor = SkillExecutor(llm, fetcher)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for name in registry.list_names():
            skill = registry.get(name)
            if skill is None:
                continue
            tools.append(
                Tool(
                    name=f"stocksage_{name}",
                    description=skill.description or f"StockSage skill: {name} ({skill.type})",
                    inputSchema=_build_tool_schema(skill),
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        skill_name = name.replace("stocksage_", "", 1)
        skill = registry.get(skill_name)
        if skill is None:
            return [TextContent(type="text", text=json.dumps(
                {"error": f"Skill '{skill_name}' not found"},
                ensure_ascii=False,
            ))]

        # Build minimal workflow state
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
            # Execute in thread pool (executor is synchronous)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: executor.execute(skill, state),
            )
            return [TextContent(type="text", text=json.dumps(
                result, ensure_ascii=False, default=str,
            ))]
        except Exception as e:
            logger.exception("Skill '%s' execution failed: %s", skill_name, e)
            return [TextContent(type="text", text=json.dumps(
                {"error": str(e)}, ensure_ascii=False,
            ))]

    return server


async def main():
    """Run the MCP server over stdio."""
    from mcp.server.stdio import stdio_server

    server = create_skill_mcp_server()

    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
