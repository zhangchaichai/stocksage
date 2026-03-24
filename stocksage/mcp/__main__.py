"""Allow ``python -m stocksage.mcp`` to launch the unified MCP server."""

from stocksage.mcp.server import main as _main
import asyncio

if __name__ == "__main__":
    asyncio.run(_main())
