import uuid
from datetime import datetime
from typing import Optional

import psycopg
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.async_tasks import queries, service

app = FastAPI(title='LabMate asynchronous submission foundation', version='0.1.0')
bearer = HTTPBearer(auto_error=False)
LIMIT = 20 * 1024 * 1024


@app.middleware('http')
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4()
    response = await call_next(request)
    response.headers['X-Request-ID'] = str(request.state.request_id)
    return response


def error(request, status, code):
    return JSONResponse(status_code=status, content={
        'code': code, 'message': code, 'request_id': str(request.state.request_id)})


@app.exception_handler(HTTPException)
async def business_error(request, exc):
    return error(request, exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return error(request, 422, 'invalid_parameters')


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    return error(request, 503, 'database_unavailable')


def authenticated(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, 'unauthorized')
    actor = service.identity(credentials.credentials)
    return actor


def administrator(actor=Depends(authenticated)):
    if actor['role'] != 'admin':
        raise HTTPException(403, 'forbidden')
    return actor


@app.get('/health/ready')
def ready():
    with service.connect() as db:
        db.execute('SELECT 1 FROM async_tasks LIMIT 1')
    return {'status': 'ready', 'scope': 'api_database_only'}


@app.post('/api/v1/materials', status_code=202)
def upload(request: Request, file: UploadFile = File(...),
           device_id: Optional[uuid.UUID] = Form(None),
           material_id: Optional[uuid.UUID] = Form(None),
           idempotency_key: str = Header(..., min_length=1, max_length=128),
           actor=Depends(administrator)):
    # Starlette spools large multipart files; never read an unbounded body into memory.
    content = file.file.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise HTTPException(422, 'file_too_large')
    if any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key):
        raise HTTPException(422, 'invalid_idempotency_key')
    ext = service.validate_file(file.filename, content)
    task_id = service.submit(actor, device_id, idempotency_key, content, ext, request.state.request_id, material_id=material_id)
    return {'task_id': task_id, 'status': 'accepted'}


@app.get('/api/v1/tasks')
def tasks(limit: int = Query(30, ge=1, le=100), before: Optional[datetime] = None,
          actor=Depends(authenticated)):
    if before is not None and before.tzinfo is None:
        raise HTTPException(422, 'timezone_required')
    return {'items': queries.list_tasks(actor, limit, before)}


@app.get('/api/v1/tasks/{task_id}')
def task(task_id: uuid.UUID, actor=Depends(authenticated)):
    return queries.task_status(actor, task_id)


@app.post('/api/v1/tasks/{task_id}/retry', status_code=202)
def retry(request: Request, task_id: uuid.UUID,
          idempotency_key: str = Header(..., min_length=1, max_length=128),
          actor=Depends(administrator)):
    if any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key):
        raise HTTPException(422, 'invalid_idempotency_key')
    return queries.retry_task(actor, task_id, idempotency_key, request.state.request_id)


@app.get('/api/v1/materials')
def materials(limit: int = Query(30, ge=1, le=100), actor=Depends(authenticated)):
    return {'items': queries.list_materials(actor, limit)}


@app.get('/api/v1/materials/{material_id}/versions/{version}/original')
def original(material_id: uuid.UUID, version: int, actor=Depends(authenticated)):
    from worker.processing import ProcessingError, read_upload
    row = queries.original(actor, material_id, version)
    try:
        content = read_upload(row['storage_key'], row['sha256'])
    except ProcessingError:
        raise HTTPException(503, 'original_unavailable') from None
    # Download rather than render untrusted Markdown/HTML as a same-origin page.
    return Response(content, media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="material.{row["media_type"]}"',
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
        'X-Material-Version-State': 'inactive' if row['deleted_at'] else (
            'current' if row['is_current'] else 'historical')})
