"""Explicit, serialized, checksummed migrations; no application startup DDL."""
import hashlib
import os
from pathlib import Path

import psycopg


def main():
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(80301)')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, digest text NOT NULL)')
        for path in sorted(Path('migrations').glob('*.sql')):
            sql = path.read_text()
            digest = hashlib.sha256(sql.encode()).hexdigest()
            row = conn.execute('SELECT digest FROM schema_migrations WHERE name=%s', (path.name,)).fetchone()
            if row:
                if row[0] != digest:
                    raise RuntimeError(f'Migration changed: {path.name}')
                continue
            if any(line.strip() and not line.lstrip().startswith('--') for line in sql.splitlines()):
                conn.execute(sql)
            conn.execute('INSERT INTO schema_migrations VALUES (%s,%s)', (path.name, digest))
            print(f'applied {path.name}')


if __name__ == '__main__':
    main()
