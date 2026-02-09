"""
Launch all three MCP servers for brain imaging.

Usage:
    # Run individual servers (stdio mode for Claude Desktop):
    python -m app.mcp.run_all imaging
    python -m app.mcp.run_all segmentation
    python -m app.mcp.run_all report

    # Run with SSE transport (HTTP mode):
    python -m app.mcp.run_all imaging --sse --port 8001
    python -m app.mcp.run_all segmentation --sse --port 8002
    python -m app.mcp.run_all report --sse --port 8003

Environment variables:
    API_BASE_URL: Backend API URL (default: http://localhost:8000)
    API_SERVICE_TOKEN: Auth token for backend API calls
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Launch Brain MCP Server")
    parser.add_argument(
        "server",
        choices=["imaging", "segmentation", "report"],
        help="Which MCP server to launch",
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Use SSE (HTTP) transport instead of stdio",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for SSE transport (default: 8001/8002/8003)",
    )

    args = parser.parse_args()

    # Default ports per server
    default_ports = {
        "imaging": 8001,
        "segmentation": 8002,
        "report": 8003,
    }
    port = args.port or default_ports[args.server]

    # Import the right server
    if args.server == "imaging":
        from app.mcp.imaging_server import mcp
    elif args.server == "segmentation":
        from app.mcp.segmentation_server import mcp
    elif args.server == "report":
        from app.mcp.report_server import mcp

    # Run with chosen transport
    if args.sse:
        print(f"Starting {args.server} MCP server on SSE port {port}...")
        mcp.run(transport="sse", port=port)
    else:
        print(f"Starting {args.server} MCP server on stdio...", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
