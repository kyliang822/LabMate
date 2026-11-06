"""Durable outbox relay, NOT the material processing worker."""
import logging
import os
import time

from celery import Celery

from backend.app.async_tasks.service import connect

logger = logging.getLogger(__name__)


def publish_once(client):
    with connect() as db:
        row = db.execute('''SELECT task_id FROM task_outbox WHERE published_at IS NULL
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1''').fetchone()
        if not row:
            return False
        task_id = str(row['task_id'])
        client.send_task('labmate.process_material', args=[task_id], task_id=task_id, queue='materials',
                         retry=False, ignore_result=True)
        db.execute('UPDATE task_outbox SET published_at=now() WHERE task_id=%s', (task_id,))
        logger.info('published task_id=%s', task_id)
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    client = Celery('labmate-publisher', broker=os.environ['CELERY_BROKER_URL'])
    client.conf.update(broker_connection_timeout=10, broker_transport_options={'socket_timeout': 10,
                       'socket_connect_timeout': 10}, task_serializer='json', accept_content=['json'])
    while True:
        try:
            if not publish_once(client):
                time.sleep(1)
        except Exception as exc:
            # Do not log broker URLs, tokens or document content.
            logger.warning('publish_failed error_type=%s', type(exc).__name__)
            time.sleep(3)


if __name__ == '__main__':
    main()
