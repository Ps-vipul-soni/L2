from mcp.server.fastmcp import FastMCP
from server import get_thresholds_for_ingredient
import sys

# Wrap the existing function as an MCP tool without modifying its internals
mcp = FastMCP("RegulationLookup")
mcp.tool()(get_thresholds_for_ingredient)

if __name__ == "__main__":
    # Start the stdio MCP server
    mcp.run()
