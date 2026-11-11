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
from app.security.agent_scope import DEFAULT_TTL_SECONDS, MAX_STUDIES, scope_active, sign_for_patient
from app.security.models import User
from app.security.resource_access import authorize_study_id

router = APIRouter(prefix="/agent-scope", tags=["Agent platform"])


class AgentScopeRequest(BaseModel):
    study_ids: List[UUID] = Field(..., min_length=1, max_length=MAX_STUDIES)
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9:_.@-]{1,128}$")


class AgentScopeResponse(BaseModel):
    token: str
    expires_in: int


@router.post("", response_model=AgentScopeResponse)
async def issue_agent_scope(body: AgentScopeRequest, current_user: User = Depends(get_current_active_user)):
    from fastapi import HTTPException, status
    if scope_active():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="An agent request cannot issue an agent scope")
    ids = [str(s) for s in body.study_ids]
    patients = {await authorize_study_id(sid, current_user) for sid in ids}      # CAPA-009, 404 when denied
    token = sign_for_patient(current_user, patients, ids, run_id=body.run_id, ttl_seconds=DEFAULT_TTL_SECONDS)
    return AgentScopeResponse(token=token, expires_in=DEFAULT_TTL_SECONDS)
