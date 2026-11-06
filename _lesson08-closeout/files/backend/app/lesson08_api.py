import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app import lesson08_service as service


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str = Field(min_length=1, max_length=256)


class Configuration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    assistant_name: str = Field(min_length=1, max_length=80)
    prompt_prefix: str = Field(min_length=1, max_length=1000)
    result_limit: int = Field(ge=1, le=20)


class SkillRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=200)
    device_id: uuid.UUID | None = None


def create_router(authenticated, administrator):
    router = APIRouter(prefix='/api/v1')

    @router.post('/auth/login')
    def login(body: Login):
        return service.login(body.username, body.password)

    @router.get('/search')
    def search(q: str = Query(min_length=1, max_length=200), device_id: uuid.UUID | None = None,
               limit: int = Query(5, ge=1, le=20), actor=Depends(authenticated)):
        return {'items': service.search(actor, q, device_id, limit)}

    @router.get('/ai-config')
    def configuration(actor=Depends(authenticated)):
        return service.get_config(actor)

    @router.put('/ai-config')
    def configure(body: Configuration, request: Request,
                  idempotency_key: str = Header(min_length=1, max_length=128), actor=Depends(administrator)):
        if any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key):
            raise HTTPException(422, 'invalid_idempotency_key')
        return service.put_config(actor, body.model_dump(), idempotency_key, request.state.request_id)

    @router.post('/skills/material-guide')
    def skill(body: SkillRequest, request: Request, actor=Depends(authenticated)):
        return service.run_skill(actor, body.query, body.device_id, request.state.request_id)

    @router.get('/skill-runs/{run_id}')
    def run(run_id: uuid.UUID, actor=Depends(authenticated)):
        return service.get_run(actor, run_id)

    return router
