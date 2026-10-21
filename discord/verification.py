"""Fail-closed publication evidence for new announcements; never rewrite history."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

SITE = 'https://estlela-business-support.honotoku.chatgpt.site'
CHECKS = ('unauthenticated-denied', 'individual-menu', 'monthly-read', 'monthly-write-restore', 'source-stable')
EXTENDED_CHECKS = CHECKS + ('public-referral', 'cream-lp', 'video-id-entry', 'notification-not-ready')


def payload_hash(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_target(payload):
    target = payload.get('verification_target', {})
    if not isinstance(target, dict) or set(target) != {'source_commit', 'source_fingerprint', 'deployment_id', 'public_version'}:
        raise ValueError('Invalid source provenance fields')
    if payload.get('site_url', '').rstrip('/') != SITE:
        raise ValueError('Verification is restricted to the configured production origin')
    for key, length in (('source_commit', 40), ('source_fingerprint', 64)):
        if not re.fullmatch('[a-f0-9]{%d}' % length, str(target.get(key, ''))):
            raise ValueError('Missing verified source provenance: ' + key)
    if not re.fullmatch(r'appgdep_[a-zA-Z0-9]+', str(target.get('deployment_id', ''))):
        raise ValueError('Missing Sites publication provenance')
    versions = payload.get('source_versions')
    if (not isinstance(versions, list) or not versions or
            any(type(v) is not int or v < 1 for v in versions) or len(set(versions)) != len(versions)):
        raise ValueError('Invalid source versions')
    latest = target.get('public_version')
    if type(latest) is not int or latest != max(versions):
        raise ValueError('Target must be the latest included public version')
    if payload.get('release_id') != f'estlela-v{latest}':
        raise ValueError('Release ID must match the verified public version')
    if payload.get('verification_requirements') not in (list(CHECKS), list(EXTENDED_CHECKS)):
        raise ValueError('Unsupported production verification profile')
    return target


def validate_report(payload, report, now=None):
    target = validate_target(payload)
    now = now or datetime.now(timezone.utc)
    if report.get('schema_version') != 1 or report.get('status') != 'passed':
        raise ValueError('Production verification has not passed')
    if report.get('payload_hash') != payload_hash(payload) or report.get('target') != target:
        raise ValueError('Verification does not match this exact announcement/source')
    if report.get('checks') != {key: True for key in payload['verification_requirements']}:
        raise ValueError('Production verification is incomplete')
    checked = datetime.fromisoformat(report.get('checked_at', ''))
    if checked.tzinfo is None or not now - timedelta(hours=24) <= checked <= now:
        raise ValueError('Verification is expired or has an invalid timestamp')
    return report


def check_pending_verification(payload, root):
    path = root / 'verifications' / (payload['release_id'] + '.json')
    if not path.exists():
        raise ValueError('Missing production verification: ' + payload['release_id'])
    validate_report(payload, json.loads(path.read_text(encoding='utf-8')))

