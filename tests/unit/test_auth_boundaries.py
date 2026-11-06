"""No DB substitution: these requests must stop at authentication before DB access."""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

ID = str(uuid.UUID(int=100))
CASES = [
    ('POST', '/api/v1/materials'),
    ('GET', '/api/v1/tasks'),
    ('GET', f'/api/v1/tasks/{ID}'),
    ('POST', f'/api/v1/tasks/{ID}/retry'),
    ('GET', '/api/v1/materials'),
    ('GET', f'/api/v1/materials/{ID}/versions/1/original'),
]


@pytest.mark.parametrize('method,path', CASES)
def test_unauthenticated_is_401_not_missing_resource(method, path):
    with TestClient(app) as client:
        response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()['code'] == 'unauthorized'
    assert set(response.json()) == {'code', 'message', 'request_id'}
    assert response.headers['x-request-id'] == response.json()['request_id']
