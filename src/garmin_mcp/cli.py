"""
CLI interface for Garmin Connect MCP tools.

Usage:
    garmin-cli list                              # list all tools
    garmin-cli get_stats --date 2026-03-01       # call a tool
    garmin-cli get_activities --start 0 --limit 10
"""

import argparse
import asyncio
import json
import sys

from mcp.server.fastmcp import FastMCP

from garmin_mcp import (
    activity_management,
    challenges,
    data_management,
    devices,
    gear_management,
    health_wellness,
    training,
    user_profile,
    weight_management,
    womens_health,
    workouts,
)
from garmin_mcp import init_api, email, password

ALL_MODULES = [
    activity_management,
    health_wellness,
    user_profile,
    devices,
    gear_management,
    weight_management,
    challenges,
    training,
    workouts,
    data_management,
    womens_health,
]

JSON_SCHEMA_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": lambda x: x.lower() in ("true", "1", "yes"),
}


def build_app():
    """Create FastMCP app with all tools registered (without running it)."""
    app = FastMCP("Garmin Connect CLI")
    for module in ALL_MODULES:
        module.register_tools(app)
    return app


def list_tools(app):
    """Print all available tools with descriptions."""
    tools = asyncio.run(app.list_tools())
    tools_sorted = sorted(tools, key=lambda t: t.name)
    max_name = max(len(t.name) for t in tools_sorted)
    for t in tools_sorted:
        desc = (t.description or "").split("\n")[0]
        print(f"  {t.name:<{max_name}}  {desc}")
    print(f"\n{len(tools_sorted)} tools available")


def call_tool(app, tool_name, raw_args):
    """Parse args for a specific tool and call it."""
    # Get tool schema
    tools = asyncio.run(app.list_tools())
    tool = next((t for t in tools if t.name == tool_name), None)
    if not tool:
        print(f"Unknown tool: {tool_name}", file=sys.stderr)
        print("Run 'garmin-cli list' to see available tools.", file=sys.stderr)
        sys.exit(1)

    schema = tool.inputSchema
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Build argparse for this tool
    parser = argparse.ArgumentParser(
        prog=f"garmin-cli {tool_name}",
        description=tool.description,
    )
    for param_name, param_info in properties.items():
        param_type = JSON_SCHEMA_TYPE_MAP.get(param_info.get("type", "string"), str)
        is_required = param_name in required
        kwargs = {"type": param_type, "required": is_required}
        if "default" in param_info:
            kwargs["default"] = param_info["default"]
            kwargs["required"] = False
        parser.add_argument(f"--{param_name}", **kwargs)

    args = parser.parse_args(raw_args)
    arguments = {k: v for k, v in vars(args).items() if v is not None}

    result = asyncio.run(app.call_tool(tool_name, arguments))
    # Handle both tuple (newer MCP) and sequence (older MCP) return types
    if isinstance(result, tuple):
        result = result[0]
    for content in result:
        text = content.text
        # Pretty-print if it's JSON
        try:
            parsed = json.loads(text)
            print(json.dumps(parsed, indent=2))
        except (json.JSONDecodeError, TypeError):
            print(text)


def main():
    # Manual argv parsing so --help passes through to per-tool parsers
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: garmin-cli <tool_name> [--arg value ...] | garmin-cli list")
        print("\nCLI for Garmin Connect data (wraps MCP tools)")
        print("\nCommands:")
        print("  list        Show all available tools")
        print("  <tool>      Call a tool (use --help for tool-specific args)")
        sys.exit(0)

    tool_name = argv[0]
    remaining = argv[1:]

    if tool_name == "list":
        app = build_app()
        list_tools(app)
        return

    app = build_app()

    # Validate tool exists before auth
    tools = asyncio.run(app.list_tools())
    tool = next((t for t in tools if t.name == tool_name), None)
    if not tool:
        print(f"Unknown tool: {tool_name}", file=sys.stderr)
        print("Run 'garmin-cli list' to see available tools.", file=sys.stderr)
        sys.exit(1)

    # For --help, no auth needed
    if "--help" in remaining or "-h" in remaining:
        call_tool(app, tool_name, remaining)
        return

    # Initialize Garmin client
    garmin_client = init_api(email, password)
    if not garmin_client:
        print("Failed to authenticate with Garmin Connect.", file=sys.stderr)
        sys.exit(1)

    # Configure all modules
    for module in ALL_MODULES:
        module.configure(garmin_client)

    call_tool(app, tool_name, remaining)


if __name__ == "__main__":
    main()
