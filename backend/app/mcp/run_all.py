"""
Launch an MCP (assistant) server over STDIO.

Usage (Claude Desktop / Claude Code start the process and talk to it over stdio):
    python -m app.mcp.run_all imaging
    python -m app.mcp.run_all ms_clinical

Environment variables:
    API_BASE_URL:      Backend API URL (default: http://localhost:8000)
    API_SERVICE_TOKEN: the access token of the clinician operating the assistant — never a
                       shared, service or administrator account. The backend applies that
                       user's own object-level authorization (RC-029).

CAPA-008: STDIO only. The former SSE (HTTP) mode had no authentication: any local process,
or a web page reaching the port by DNS rebinding, could act with the clinician's token.
The segmentation, report and PACS servers were retired: they called routes without
object-level authorization, wrote records, generated text without measurements, offered
diagnostic output outside the intended use, or called routes that do not exist.
"""

import argparse
import sys

SERVERS = ("imaging", "ms_clinical")


def main():
    parser = argparse.ArgumentParser(description="Launch a read-only MCP server over stdio")
    parser.add_argument("server", choices=SERVERS, help="Which MCP server to launch")
    args = parser.parse_args()

    if args.server == "imaging":
        from app.mcp.imaging_server import mcp
    else:
        from app.mcp.ms_clinical_server import mcp

    print(f"Starting {args.server} MCP server on stdio...", file=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
