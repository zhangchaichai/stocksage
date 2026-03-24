"""MCP Server that exposes StockSage data & compute tools.

Complements skill_server.py (which exposes high-level skills) by exposing
the lower-level data-fetching and indicator-calculation tools directly.

This lets MCP clients perform quick lookups (stock info, price, news) and
compute indicators without running a full multi-agent skill pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from stocksage.data.fetcher import DataFetcher

logger = logging.getLogger(__name__)


def _build_tools(fetcher: DataFetcher) -> dict[str, Any]:
    """Instantiate all data & compute Tool objects, keyed by name."""
    from stocksage.agent.tools.compute_tools import (
        CalcIndicatorTool,
        CalcValuationTool,
    )
    from stocksage.agent.tools.data_tools import (
        FetchBalanceSheetTool,
        FetchFinancialTool,
        FetchFundFlowTool,
        FetchMarginDataTool,
        FetchNewsTool,
        FetchNorthboundTool,
        FetchPriceDataTool,
        FetchQuarterlyTool,
        FetchSentimentTool,
        FetchStockInfoTool,
    )

    instances = [
        FetchStockInfoTool(fetcher),
        FetchPriceDataTool(fetcher),
        FetchFinancialTool(fetcher),
        FetchQuarterlyTool(fetcher),
        FetchNewsTool(fetcher),
        FetchFundFlowTool(fetcher),
        FetchSentimentTool(fetcher),
        FetchMarginDataTool(fetcher),
        FetchNorthboundTool(fetcher),
        FetchBalanceSheetTool(fetcher),
        CalcIndicatorTool(fetcher),
        CalcValuationTool(fetcher),
    ]
    return {t.name: t for t in instances}


def create_tool_mcp_server():
    """Create and return an MCP Server exposing data & compute tools.

    Returns the Server instance (not yet running).
    """
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError:
        raise ImportError(
            "MCP SDK not installed. Run: pip install mcp"
        )

    server = Server("stocksage-tools")
    fetcher = DataFetcher()
    tools = _build_tools(fetcher)
    logger.info("Registered %d data/compute tools for MCP", len(tools))

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        result = []
        for tool_obj in tools.values():
            result.append(
                Tool(
                    name=f"stocksage_{tool_obj.name}",
                    description=tool_obj.description,
                    inputSchema=tool_obj.parameters,
                )
            )
        return result

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        tool_name = name.replace("stocksage_", "", 1)
        tool_obj = tools.get(tool_name)
        if tool_obj is None:
            return [TextContent(type="text", text=json.dumps(
                {"error": f"Tool '{tool_name}' not found"},
                ensure_ascii=False,
            ))]

        try:
            casted = tool_obj.cast_params(arguments)
            result = await tool_obj.execute(**casted)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            logger.exception("Tool '%s' execution failed: %s", tool_name, e)
            return [TextContent(type="text", text=json.dumps(
                {"error": str(e)}, ensure_ascii=False,
            ))]

    return server


async def main():
    """Run the tool MCP server over stdio."""
    from mcp.server.stdio import stdio_server

    server = create_tool_mcp_server()

    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
