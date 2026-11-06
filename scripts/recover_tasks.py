"""Explicit operator recovery. Dry-run by default; never steals an active worker lock."""
import argparse
import uuid

from backend.app.async_tasks.service import connect
from worker.tasks import acquire


def recover(stale_seconds=1200, apply=False, limit=100):
    if stale_seconds < 900 or not 1 <= limit <= 1000:
        raise ValueError('stale_seconds must be >=900 and limit between 1 and 1000')
    results = []
    with connect() as db:
        rows = db.execute('''SELECT id FROM async_tasks WHERE
            (status='queued' AND created_at<now()-(%s * interval '1 second')) OR
            (status='processing' AND started_at<now()-(%s * interval '1 second'))
            ORDER BY created_at LIMIT %s''', (stale_seconds, stale_seconds, limit)).fetchall()
        db.commit()
        for item in rows:
            task_id = item['id']
            if not acquire(db, task_id):
                db.rollback()
                results.append({'task_id': str(task_id), 'action': 'active_skipped'})
                continue
            try:
                row = db.execute('SELECT * FROM async_tasks WHERE id=%s FOR UPDATE', (task_id,)).fetchone()
                # Recheck after locking: a queued task may have just completed.
                eligible = db.execute('''SELECT (status='queued' AND
                    created_at<now()-(%s * interval '1 second')) OR (status='processing' AND
                    started_at<now()-(%s * interval '1 second')) AS eligible FROM async_tasks WHERE id=%s''',
                    (stale_seconds, stale_seconds, task_id)).fetchone()['eligible']
                if not eligible:
                    continue
                if apply and row['status'] == 'processing' and row['retries'] >= 2:
                    db.execute("""UPDATE async_tasks SET status='failed',error_code='worker_lost',
                        finished_at=now() WHERE id=%s""", (task_id,))
                    db.execute("""INSERT INTO task_dead_letters(task_id,cycle,stage,error_code)
                        VALUES (%s,%s,%s,'worker_lost') ON CONFLICT DO NOTHING""",
                        (task_id, row['cycle'], row['stage']))
                    db.execute("""INSERT INTO task_audit(id,actor_id,task_id,action,request_id)
                        VALUES (%s,%s,%s,'material.recovery_exhausted',%s)""",
                        (uuid.uuid4(), row['user_id'], task_id, uuid.uuid4()))
                    db.commit()
                    results.append({'task_id': str(task_id), 'action': 'failed_retry_exhausted'})
                    continue
                if apply:
                    if row['status'] == 'processing':
                        db.execute('UPDATE async_tasks SET retries=retries+1 WHERE id=%s', (task_id,))
                    db.execute('''UPDATE async_tasks SET status='queued',stage='queued',
                        started_at=NULL,finished_at=NULL,error_code='recovered' WHERE id=%s''', (task_id,))
                    db.execute('''UPDATE task_outbox SET published_at=NULL,available_at=now()
                        WHERE task_id=%s''', (task_id,))
                    db.execute('''INSERT INTO task_audit(id,actor_id,task_id,action,request_id)
                        VALUES (%s,%s,%s,'material.operator_recovery',%s)''',
                        (uuid.uuid4(), row['user_id'], task_id, uuid.uuid4()))
                    db.commit()
                results.append({'task_id': str(task_id), 'action': 'requeued' if apply else 'would_requeue'})
            finally:
                db.rollback()
                db.execute('SELECT pg_advisory_unlock(hashtextextended(%s,804))', (str(task_id),))
                db.commit()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--stale-seconds', type=int, default=1200)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    for item in recover(args.stale_seconds, args.apply, args.limit):
        print(item['task_id'], item['action'])


if __name__ == '__main__':
    main()
