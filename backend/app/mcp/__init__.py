"""
MCP (Model Context Protocol) Servers for Brain Imaging.

Three servers:
- imaging_server: Search studies, get metadata, view slices
- segmentation_server: AI segmentation, volumetry, measurement
- report_server: Report generation, templates, differential diagnosis

Each server can run standalone (stdio for Claude Desktop)
or integrated via SSE (HTTP transport for web clients).
"""
