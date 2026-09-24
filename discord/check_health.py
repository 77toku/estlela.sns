"""Check generator evidence independently of whether an announcement was needed."""
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def check_health(now=None, root=ROOT):
    now = now or datetime.now(ZoneInfo('Asia/Tokyo'))
    now = now.astimezone(ZoneInfo('Asia/Tokyo'))
    # The 07:00 generator has until 07:45 to finish. Before then inspect yesterday.
    day = now.date() if now.time() >= time(7, 45) else now.date() - timedelta(days=1)
    path = root / 'checks' / f'{day.isoformat()}.json'
    if not path.exists():
        raise RuntimeError(f'Missing generator record: {path.name}; no-update is not proven')
    record = json.loads(path.read_text())
    checked = datetime.fromisoformat(record['checked_at'])
    cutoff = datetime.fromisoformat(record['cutoff_jst'])
    if checked.tzinfo is None or cutoff.tzinfo is None:
        raise ValueError('Generator timestamps must include timezone')
    if (cutoff.astimezone(ZoneInfo('Asia/Tokyo')).date() != day
            or cutoff.astimezone(ZoneInfo('Asia/Tokyo')).time() != time(7)
            or checked < cutoff or checked > now):
        raise ValueError('Invalid generator timestamps')
    status = record.get('status')
    if status not in ('no_update', 'queued', 'delivered'):
        raise RuntimeError('Generator failed or has no conclusive result')
    if not record.get('evidence'):
        raise ValueError('Missing public-update verification evidence')
    releases = record.get('release_ids')
    if not isinstance(releases, list) or (status == 'no_update' and releases):
        raise ValueError('Invalid release_ids')
    if status != 'no_update' and not releases:
        raise ValueError('No releases recorded for queued/delivered status')
    for rid in releases:
        import re
        if not isinstance(rid, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', rid):
            raise ValueError('Invalid release ID')
        if not (root / 'sent' / f'{rid}.json').exists():
            raise RuntimeError(f'Missing delivery receipt: {rid}')
    print(f'Generator verified: {day} ({status})')


if __name__ == '__main__':
    check_health()
