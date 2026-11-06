import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.lesson08_api import Configuration, Login, SkillRequest
from backend.app.lesson08_service import password_hash, password_matches, signature
from backend.app.main import app


def test_password_hash_salted_and_wrong_password_rejected():
    one, two = password_hash('fictional-password'), password_hash('fictional-password')
    assert one != two and 'fictional-password' not in one
    assert password_matches('fictional-password', one)
    assert not password_matches('wrong', one)
    assert not password_matches('anything', 'malformed')


def test_signature_detects_payload_and_key_changes():
    assert signature('v1.payload', b'a' * 32) != signature('v1.changed', b'a' * 32)
    assert signature('v1.payload', b'a' * 32) != signature('v1.payload', b'b' * 32)


@pytest.mark.parametrize('model,payload', [
    (Login, {'username': 'admin', 'password': 'test', 'role': 'admin'}),
    (SkillRequest, {'query': 'device', 'lab_id': 'forged'}),
    (Configuration, {'version': 0, 'assistant_name': 'x', 'prompt_prefix': 'x', 'result_limit': 21}),
])
def test_clients_cannot_inject_identity_or_unbounded_limits(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/v1/search?q=device'), ('GET', '/api/v1/ai-config'),
    ('PUT', '/api/v1/ai-config'), ('POST', '/api/v1/skills/material-guide'),
    ('GET', '/api/v1/skill-runs/00000000-0000-0000-0000-000000000001'),
])
def test_closeout_endpoints_require_authentication(method, path):
    with TestClient(app) as client:
        response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()['code'] == 'unauthorized'
