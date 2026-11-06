"""Create fictional authorization fixtures. Tokens go only to a private local file."""
import argparse
import hashlib
import json
import os
import secrets
import uuid
from pathlib import Path

from backend.app.async_tasks.service import connect

NAMESPACE = uuid.UUID('25803fe7-359e-4147-b4c7-6ef360238004')


def fixture_id(name):
    return uuid.uuid5(NAMESPACE, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='/tmp/labmate-security-identities.json')
    args = parser.parse_args()
    data = {'labs': {}, 'actors': {}, 'devices': {}}
    output = Path(args.output)
    # O_EXCL prevents accidentally following an existing symlink or overwriting credentials.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with connect() as db:
            for name in ('A', 'B'):
                lab = fixture_id('lab-' + name)
                data['labs'][name] = str(lab)
                db.execute('INSERT INTO labs VALUES (%s,%s) ON CONFLICT DO NOTHING', (lab, '虚构实验室' + name))
                device = fixture_id('device-' + name)
                data['devices'][name] = str(device)
                db.execute('INSERT INTO devices VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                           (device, lab, '虚构设备' + name))
            for name, lab, role in [('adminA', 'A', 'admin'), ('userA1', 'A', 'user'),
                                     ('userA2', 'A', 'user'), ('userB1', 'B', 'user'),
                                     ('adminB', 'B', 'admin')]:
                user, token = fixture_id(name), secrets.token_urlsafe(32)
                db.execute('INSERT INTO app_users(id,lab_id,role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                           (user, fixture_id('lab-' + lab), role))
                db.execute("INSERT INTO access_tokens VALUES (%s,%s,now()+interval '2 hours')",
                           (hashlib.sha256(token.encode()).hexdigest(), user))
                data['actors'][name] = {'id': str(user), 'lab': lab, 'token': token}
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        output.unlink(missing_ok=True)
        raise
    print('Fictional identities created; credentials written to the private output file (2-hour expiry).')


if __name__ == '__main__':
    main()
