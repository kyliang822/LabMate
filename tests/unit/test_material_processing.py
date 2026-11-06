import hashlib
import io
import json
import urllib.error
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter

from worker import processing as p


def test_text_chunks_preserve_source_positions():
    text = '虚构设备说明' * 230
    chunks = p.split_document(p.parse_document(text.encode(), 'md'))
    assert ''.join(c.content for c in chunks) == text
    assert chunks[0].location == 'text:chars:0-800'
    assert all(len(c.content) <= 800 for c in chunks)


@pytest.mark.parametrize('content,kind,code', [
    (b'\xff', 'txt', 'invalid_utf8'), (b'  ', 'md', 'no_extractable_text'),
    (b'\x00', 'txt', 'invalid_text'), (b'%PDF-broken', 'pdf', 'invalid_pdf'),
    (b'x', 'exe', 'unsupported_file'),
])
def test_permanent_parse_failures(content, kind, code):
    with pytest.raises(p.ProcessingError) as caught:
        p.parse_document(content, kind)
    assert caught.value.code == code
    assert not caught.value.transient


def test_pdf_no_text_and_encrypted_are_not_ready():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = io.BytesIO()
    writer.write(stream)
    with pytest.raises(p.ProcessingError, match='no_extractable_text'):
        p.parse_document(stream.getvalue(), 'pdf')
    writer.encrypt('fictional-test-only')
    stream = io.BytesIO()
    writer.write(stream)
    with pytest.raises(p.ProcessingError, match='encrypted_pdf'):
        p.parse_document(stream.getvalue(), 'pdf')


def test_upload_checks_hash_and_never_trusts_path(tmp_path, monkeypatch):
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path))
    body = '虚构资料'.encode()
    (tmp_path / 'random.txt').write_bytes(body)
    checksum = hashlib.sha256(body).hexdigest()
    assert p.read_upload('random.txt', checksum) == body
    for name in ['../escape.txt', '/absolute', 'folder\\escape', 'folder/name']:
        with pytest.raises(p.ProcessingError, match='invalid_storage_key'):
            p.read_upload(name, checksum)
    with pytest.raises(p.ProcessingError, match='checksum_mismatch'):
        p.read_upload('random.txt', 'wrong')


def provider(monkeypatch, data=None, error=None):
    monkeypatch.setenv('EMBEDDING_BASE_URL', 'https://provider.invalid/v1')
    monkeypatch.setenv('EMBEDDING_API_KEY', 'fictional-test-key')
    monkeypatch.setenv('EMBEDDING_MODEL', 'test-model')
    monkeypatch.setenv('EMBEDDING_DIMENSIONS', '2')
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({'data': data}).encode()
    opener = Mock()
    opener.open.side_effect = error
    if error is None:
        opener.open.return_value = response
    monkeypatch.setattr(p.urllib.request, 'build_opener', lambda *args: opener)
    return opener


def test_embedding_preserves_provider_index_and_checks_payload(monkeypatch):
    opener = provider(monkeypatch, [{'index': 1, 'embedding': [3, 4]}, {'index': 0, 'embedding': [1, 2]}])
    model, dim, vectors = p.embed_chunks([p.Chunk('one', '1'), p.Chunk('two', '2')])
    assert (model, dim, vectors) == ('test-model', 2, [[1, 2], [3, 4]])
    request = opener.open.call_args.args[0]
    assert request.full_url == 'https://provider.invalid/v1/embeddings'
    assert json.loads(request.data) == {'model': 'test-model', 'input': ['one', 'two']}
    assert opener.open.call_args.kwargs['timeout'] == 10


@pytest.mark.parametrize('data', [
    [], [{'index': 0, 'embedding': [float('nan'), 1]}],
    [{'index': 0, 'embedding': [1]}], [{'index': 0, 'embedding': [True, 1]}],
    [{'index': 1, 'embedding': [1, 2]}],
])
def test_invalid_embeddings_cannot_be_stored(monkeypatch, data):
    provider(monkeypatch, data)
    with pytest.raises(p.ProcessingError, match='invalid_embedding_response'):
        p.embed_chunks([p.Chunk('x', '1')])


@pytest.mark.parametrize('status,transient', [(429, True), (503, True), (401, False), (302, False)])
def test_provider_failures_are_bounded_and_sanitized(monkeypatch, status, transient):
    provider(monkeypatch, error=urllib.error.HTTPError('https://secret.invalid', status, 'private text', {}, None))
    with pytest.raises(p.ProcessingError) as caught:
        p.embed_chunks([p.Chunk('x', '1')])
    assert str(caught.value) == 'embedding_http_error'
    assert caught.value.transient is transient


def test_no_production_fake_embeddings(monkeypatch):
    monkeypatch.delenv('EMBEDDING_BASE_URL', raising=False)
    with pytest.raises(p.ProcessingError, match='embedding_not_configured'):
        p.embed_chunks([p.Chunk('x', '1')])
