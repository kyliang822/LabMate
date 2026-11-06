import uuid
from typing import Optional

import psycopg
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.async_tasks import service

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


def administrator(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, 'unauthorized')
    actor = service.identity(credentials.credentials)
    if actor['role'] != 'admin':
        raise HTTPException(403, 'forbidden')
    return actor


@app.get('/health/ready')
def ready():
    with service.connect() as db:
        db.execute('SELECT 1 FROM async_tasks LIMIT 1')
    return {'status': 'ready', 'consumer': 'not_included_in_this_delivery'}


@app.post('/api/v1/materials', status_code=202)
def upload(request: Request, file: UploadFile = File(...),
           device_id: Optional[uuid.UUID] = Form(None),
           idempotency_key: str = Header(..., min_length=1, max_length=128),
           actor=Depends(administrator)):
    # Starlette spools large multipart files; never read an unbounded body into memory.
    content = file.file.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise HTTPException(422, 'file_too_large')
    if any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key):
        raise HTTPException(422, 'invalid_idempotency_key')
    ext = service.validate_file(file.filename, content)
    task_id = service.submit(actor, device_id, idempotency_key, content, ext, request.state.request_id)
    return {'task_id': task_id, 'status': 'accepted'}
