"""
MSTool agent platform core: the shared layer every AI agent of the app runs through.

DRAFT, PENDING owner approval (REQ-AGT-001..008; HAZ-020..HAZ-024; RC-110..RC-120). Not yet in the path of
any live agent: adoption by the report route (PR #78) and the MCP assistant is described step by step in
docs/iec62304/agent_platform/Integration_Plan.md.

Modules (standard library only; no new third-party dependency):
- registry    identity, approval, tools (read-only by default), model allow-list with retirement dates,
              per-agent kill switch read at every call, cost caps per study and per day; fail closed.
- untrusted   text from DICOM tags, NIfTI descriptions, file names, prior reports and tool outputs reaches a
              model only as quoted, escaped data; tool results are checked for scope, size and shape.
- tracing     spans after the OpenTelemetry GenAI semantic conventions v1.37.0 (Development stability),
              content only as SHA-256, linked to the audit log and to the radiologist's sign-off.
- runtime     the one loop that calls models and tools: every call re-authorized, bounded and traced.
- provenance  per-sentence marking of model-written text for the signed report and the UI.
- oversight   per-reader acceptance, edit size and time-to-sign, aggregated without patient data.
- cards       model and prompt card (SOUP record) per agent and its CI check.
- evals       offline eval harness with pass^k over recorded output variants.
"""

PLATFORM_VERSION = "0.1.0-draft"
