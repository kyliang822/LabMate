"""Operator-only: fictional account, one-hour token printed once. Never run in CI logs."""
import hashlib
import secrets
import uuid

from backend.app.async_tasks.service import connect

LAB = uuid.UUID('00000000-0000-0000-0000-000000000001')
USER = uuid.UUID('00000000-0000-0000-0000-000000000002')


def main():
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO labs VALUES (%s,%s) ON CONFLICT DO NOTHING', (LAB, '虚构演示实验室'))
        db.execute('INSERT INTO app_users(id,lab_id,role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                   (USER, LAB, 'admin'))
        db.execute("INSERT INTO access_tokens VALUES (%s,%s,now()+interval '1 hour')",
                   (hashlib.sha256(token.encode()).hexdigest(), USER))
    print(token)


if __name__ == '__main__':
    main()
