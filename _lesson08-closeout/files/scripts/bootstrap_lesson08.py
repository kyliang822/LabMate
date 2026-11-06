"""Initialize fictional password-login accounts; output is private and never a report."""
import argparse
import json
import os
import secrets
from pathlib import Path

from backend.app.async_tasks.service import connect
from backend.app.lesson08_service import password_hash
from scripts.seed_security import fixture_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='/tmp/lesson08-login.json')
    args = parser.parse_args()
    output = Path(args.output)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        data = {'actors': {}}
        with connect() as db:
            db.execute('INSERT INTO auth_signing_keys VALUES (1,%s) ON CONFLICT DO NOTHING', (secrets.token_bytes(32),))
            for lab in ('A', 'B'):
                db.execute('INSERT INTO labs VALUES (%s,%s) ON CONFLICT DO NOTHING',
                           (fixture_id('lab-' + lab), 'Fictional laboratory ' + lab))
            for name, lab, role in [('adminA', 'A', 'admin'), ('adminB', 'B', 'admin'),
                                     ('userA1', 'A', 'user'), ('userA2', 'A', 'user'), ('userB1', 'B', 'user')]:
                user, password = fixture_id(name), secrets.token_urlsafe(24)
                db.execute('''INSERT INTO app_users(id,lab_id,role,login_name,password_hash)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE
                    SET login_name=excluded.login_name,password_hash=excluded.password_hash''',
                    (user, fixture_id('lab-' + lab), role, name, password_hash(password)))
                db.execute('DELETE FROM access_tokens WHERE user_id=%s', (user,))
                data['actors'][name] = {'username': name, 'password': password}
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        output.unlink(missing_ok=True)
        raise
    print('Fictional login accounts initialized; private output file mode 0600. Previous fixture tokens revoked.')


if __name__ == '__main__':
    main()
