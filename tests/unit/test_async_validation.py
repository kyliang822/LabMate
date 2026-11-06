import pytest
from fastapi import HTTPException

from backend.app.async_tasks.service import validate_file


def test_utf8_and_path_are_not_storage_keys():
    assert validate_file('../../设备.md', '虚构演示资料'.encode()) == '.md'


@pytest.mark.parametrize('name,body', [('a.exe', b'x'), ('a.txt', b'\xff'),
                                       ('a.pdf', b'not pdf'), ('a.md', b''), ('a.txt', b'\0')])
def test_invalid_file(name, body):
    with pytest.raises(HTTPException) as exc:
        validate_file(name, body)
    assert exc.value.status_code == 422
