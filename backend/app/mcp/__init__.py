"""
MCP (Model Context Protocol) servers: read-only access for an AI assistant (CAPA-008).

Two servers, STDIO only, both through the read-only client in ``_backend.py``:
- imaging_server: image metadata (identifiers removed), slices, segmentation list
- ms_clinical_server: stored lesion measurements, DIS items, two-timepoint comparison
  candidates, draft report from measurements (investigational, not for diagnosis)
"""
