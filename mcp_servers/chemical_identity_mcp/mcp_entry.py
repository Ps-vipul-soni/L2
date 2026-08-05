from mcp.server.fastmcp import FastMCP
from server import resolve_ingredient
import sys

# Wrap the existing function as an MCP tool without modifying its internals
mcp = FastMCP("ChemicalIdentity")
mcp.tool()(resolve_ingredient)

if __name__ == "__main__":
    # Start the stdio MCP server
    mcp.run()
