"""Explicit duplicate-message probe, only in a fictional isolated test environment."""
import argparse
import os
import uuid

from celery import Celery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task_id', type=uuid.UUID)
    args = parser.parse_args()
    client = Celery('duplicate-probe', broker=os.environ['CELERY_BROKER_URL'])
    task_id = str(args.task_id)
    client.send_task('labmate.process_material', args=[task_id], task_id=task_id,
                     queue='materials', retry=False, ignore_result=True)
    print('Duplicate message sent for task_id=' + task_id)


if __name__ == '__main__':
    main()
