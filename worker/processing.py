"""Bounded text processing; no user data is executed or used as configuration."""
import io
import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024
MAX_CHARS = 2_000_000
MAX_CHUNKS = 4096
CHUNK_SIZE = 800
CHUNK_STRATEGY = 'page-paragraph-800-v1'


class ProcessingError(Exception):
    def __init__(self, code, transient=False):
        super().__init__(code)
        self.code = code
        self.transient = transient


@dataclass(frozen=True)
class Chunk:
    content: str
    location: str


def parse_document(content, media_type):
    if not content or len(content) > MAX_BYTES:
        raise ProcessingError('invalid_file_size')
    if media_type in {'txt', 'md'}:
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            raise ProcessingError('invalid_utf8') from None
        if '\x00' in text:
            raise ProcessingError('invalid_text')
        pages = [(text, 'text')]
    elif media_type == 'pdf':
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ProcessingError('encrypted_pdf')
            if len(reader.pages) > 500:
                raise ProcessingError('too_many_pages')
            pages, count = [], 0
            for i, page in enumerate(reader.pages, 1):
                # Bound uncompressed page streams before extracting text.
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > MAX_BYTES:
                    raise ProcessingError('pdf_page_too_large')
                text = page.extract_text() or ''
                count += len(text)
                if count > MAX_CHARS:
                    raise ProcessingError('too_much_text')
                pages.append((text, f'page:{i}'))
        except ProcessingError:
            raise
        except Exception:
            raise ProcessingError('invalid_pdf') from None
    else:
        raise ProcessingError('unsupported_file')
    if sum(len(text) for text, _ in pages) > MAX_CHARS:
        raise ProcessingError('too_much_text')
    if not any(text.strip() for text, _ in pages):
        raise ProcessingError('no_extractable_text')
    return pages


def split_document(pages):
    chunks = []
    for text, location in pages:
        # Offsets refer to the parsed page/text, not rendered HTML or model output.
        for start in range(0, len(text), CHUNK_SIZE):
            part = text[start:start + CHUNK_SIZE]
            if part.strip():
                chunks.append(Chunk(part, f'{location}:chars:{start}-{start + len(part)}'))
                if len(chunks) > MAX_CHUNKS:
                    raise ProcessingError('too_many_chunks')
    return chunks


def read_upload(storage_key, expected_sha):
    import hashlib
    root = Path(os.environ.get('UPLOAD_DIR', 'uploads')).resolve()
    if Path(storage_key).name != storage_key or '/' in storage_key or '\\' in storage_key:
        raise ProcessingError('invalid_storage_key')
    path = root / storage_key
    if path.is_symlink() or path.resolve().parent != root:
        raise ProcessingError('invalid_storage_key')
    try:
        with path.open('rb') as stream:
            content = stream.read(MAX_BYTES + 1)
    except OSError:
        raise ProcessingError('upload_unavailable', transient=True) from None
    if len(content) > MAX_BYTES:
        raise ProcessingError('invalid_file_size')
    if hashlib.sha256(content).hexdigest() != expected_sha:
        raise ProcessingError('checksum_mismatch')
    return content


def embed_chunks(chunks):
    """Real provider only. Tests inject a separate fake at the call boundary."""
    base = os.environ.get('EMBEDDING_BASE_URL', '').rstrip('/')
    model = os.environ.get('EMBEDDING_MODEL', '')
    key = os.environ.get('EMBEDDING_API_KEY', '')
    if not base.startswith('https://') or not model or not key:
        raise ProcessingError('embedding_not_configured')
    try:
        dimension = int(os.environ.get('EMBEDDING_DIMENSIONS', '1536'))
    except ValueError:
        raise ProcessingError('invalid_embedding_config') from None
    if not 1 <= dimension <= 4096:
        raise ProcessingError('invalid_embedding_config')
    vectors = []
    for start in range(0, len(chunks), 32):
        batch = chunks[start:start + 32]
        body = json.dumps({'model': model, 'input': [c.content for c in batch]}).encode()
        request = urllib.request.Request(base + '/embeddings', data=body, headers={
            'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
        # No redirects: do not forward credentials or documents to a redirected origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ProcessingError('embedding_response_too_large')
            data = json.loads(raw)['data']
            if len(data) != len(batch) or sorted(x['index'] for x in data) != list(range(len(batch))):
                raise ProcessingError('invalid_embedding_response')
            for item in sorted(data, key=lambda x: x['index']):
                vector = item['embedding']
                if not isinstance(vector, list) or len(vector) != dimension or not all(
                    type(v) in (int, float) and math.isfinite(v) for v in vector
                ):
                    raise ProcessingError('invalid_embedding_response')
                vectors.append(vector)
        except urllib.error.HTTPError as exc:
            raise ProcessingError('embedding_http_error', exc.code == 429 or exc.code >= 500) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProcessingError('embedding_unavailable', transient=True) from None
        except (ValueError, KeyError, TypeError):
            raise ProcessingError('invalid_embedding_response') from None
    return model, dimension, vectors
