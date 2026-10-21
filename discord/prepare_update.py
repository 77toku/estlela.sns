#!/usr/bin/env python3
"""Prepare an immutable outbox + its exact passing report. This never sends."""
import argparse
import json
from pathlib import Path
from render_update import validate_payload
from verification import validate_report

ROOT = Path(__file__).resolve().parent


def prepare(payload, report, root=ROOT):
    validate_payload(payload)
    validate_report(payload, report)
    rid = payload['release_id']
    for folder in ('outbox', 'sent', 'attempts', 'verifications'):
        if (root / folder / f'{rid}.json').exists():
            raise ValueError('Existing release state must be reconciled, never overwritten: ' + rid)
    # An orphaned/ambiguous attempt blocks any new announcement, too.
    for attempt in (root / 'attempts').glob('*.json'):
        if not (root / 'sent' / attempt.name).exists():
            raise RuntimeError('Unresolved delivery attempt; reconcile before queueing')
    for path in (root / 'outbox').glob('*.json'):
        previous = json.loads(path.read_text(encoding='utf-8'))
        if set(previous.get('source_versions', [])) & set(payload['source_versions']):
            raise ValueError('Source versions were already queued')
        if all(previous.get(k) == payload.get(k) for k in ('headline', 'changes', 'message', 'site_url')):
            raise ValueError('Announcement content was already queued')
    # Save proof first. If interrupted, no unverified sendable payload exists.
    for folder, content in (('verifications', report), ('outbox', payload)):
        (root / folder).mkdir(parents=True, exist_ok=True)
        with (root / folder / f'{rid}.json').open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(content, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    prepare(json.loads(args.candidate.read_text()), json.loads(args.report.read_text()))
    print('Prepared verified outbox and evidence; no Discord message sent.')
