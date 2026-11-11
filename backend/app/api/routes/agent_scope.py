"""Agent scope issuance — RC-121 (HAZ-021), DRAFT, PENDING owner approval.

``POST /api/v1/agent-scope``: the agent platform asks, on behalf of the signed-in clinician, for a capability
that limits ONE agent run to the listed studies of one patient (app/security/agent_scope.py). Every study is
authorized with the CAPA-009 resolver first (404 when the clinician may not see it); the response is a signed,
short-lived token and nothing is stored. An agent-scoped request cannot reach this route (the guard allows
agent requests only on the assistant's read routes) and cannot mint a wider scope.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security import get_current_active_user
from app.security.agent_scope import DEFAULT_TTL_SECONDS, MAX_STUDIES, issue_for_studies, preview_studies
from app.security.models import User

router = APIRouter(prefix="/agent-scope", tags=["Agent platform"])


class AgentScopeRequest(BaseModel):
    study_ids: List[UUID] = Field(..., min_length=1, max_length=MAX_STUDIES)
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9:_.@-]{1,128}$")
    # Seventh review of PR #79 (R1): the description the physician confirms before the pass is issued
    preview: bool = False


@router.post("")
async def issue_agent_scope(body: AgentScopeRequest, current_user: User = Depends(get_current_active_user)):
    # Sixth review of PR #79, C2: the ONE implementation (agent_scope.issue_for_studies): every study authorized
    # with the CAPA-009 resolver (404 when denied), deduplicated, one patient, and no agent-scoped request.
    if body.preview:
        return await preview_studies([str(s) for s in body.study_ids], current_user)
    token = await issue_for_studies([str(s) for s in body.study_ids], current_user, run_id=body.run_id,
                                    ttl_seconds=DEFAULT_TTL_SECONDS)
    return {"token": token, "expires_in": DEFAULT_TTL_SECONDS}
