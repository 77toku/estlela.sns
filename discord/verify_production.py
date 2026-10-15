#!/usr/bin/env python3
"""Production browser check for a provisioned synthetic account, never members.

No screenshots, trace, HAR, storage-state export, private responses, or raw errors
are written. The signed URL is consumed in memory and never navigated to.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from verification import SITE, CHECKS, payload_hash, validate_target
from render_update import validate_payload


class VerificationStopped(Exception):
    pass


def credentials(raw):
    try:
        url = urlsplit(raw)
        values = parse_qs(url.query, keep_blank_values=True)
        if (url.scheme != 'https' or url.netloc != urlsplit(SITE).netloc or
                url.path != '/affiliate-activity' or url.fragment or
                set(values) != {'ref', 'token'} or any(len(v) != 1 for v in values.values())):
            raise ValueError()
        member, token = values['ref'][0], values['token'][0]
        if not re.fullmatch(r'\d{2,}', member) or not re.fullmatch(r'[a-f0-9]{64}', token):
            raise ValueError()
        return member, token
    except Exception:
        raise VerificationStopped('credentials_missing_or_invalid') from None


def allowed_request(url, method, headers, member):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != urlsplit(SITE).netloc:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    if 'token' in query:
        return False
    if parsed.path == '/api/affiliate-activity':
        return method == 'GET' and query == {'ref': [member], 'session': ['mt']}
    if parsed.path == '/api/monthly-tasks':
        return method in ('GET', 'PATCH') and not query and headers.get('x-affiliate-id') == member
    if parsed.path == '/api/affiliates/resolve':
        return method == 'GET' and query == {'ref': [member]}
    if parsed.path.startswith('/api/'):
        return False
    if parsed.path == '/affiliate-activity':
        return method == 'GET' and query.get('ref') == [member] and query.get('session') == ['mt'] and not set(query) - {'ref', 'session', 'view'}
    return method == 'GET' and not query and (parsed.path.startswith('/assets/') or parsed.path.startswith('/_next/') or parsed.path in ('/favicon.svg', '/estlela-management.webmanifest', '/apple-touch-icon-estlela-management-180.png'))


async def run_browser(payload, raw_url):
    from playwright.async_api import async_playwright
    member, token = credentials(raw_url)
    target = validate_target(payload)
    checks = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(service_workers='block', viewport={'width': 390, 'height': 844})
        context.set_default_timeout(20000)
        api = context.request
        auth_headers = {'x-affiliate-id': member, 'x-activity-token': token}

        async def preflight():
            result = await api.get(SITE + '/api/production-verification', headers=auth_headers, max_redirects=0)
            if result.status != 200:
                raise VerificationStopped('dedicated_account_preflight_failed')
            body = await result.json()
            if (body.get('contract') != 1 or body.get('accountScope') != 'dedicated-test' or
                    body.get('sourceFingerprint') != target['source_fingerprint']):
                raise VerificationStopped('production_source_mismatch')

        original = None
        changed = False
        restored = False
        try:
            # Reject unapproved accounts before the browser fetches any data.
            await preflight()
            denial = await api.get(SITE + '/api/affiliate-activity?' + urlencode({'ref': member}), max_redirects=0)
            if denial.status != 404:
                raise VerificationStopped('id_only_request_not_denied')
            checks['unauthenticated-denied'] = True
            session = await api.post(SITE + '/api/mt-session', headers={**auth_headers, 'Origin': SITE}, max_redirects=0)
            cookie = session.headers.get('set-cookie', '')
            if session.status != 200 or any(flag not in cookie.lower() for flag in ('httponly', 'secure', 'samesite=strict')):
                raise VerificationStopped('normal_session_bootstrap_failed')
            blocked = []
            async def guard(route):
                request = route.request
                if allowed_request(request.url, request.method, request.headers, member):
                    await route.continue_()
                else:
                    blocked.append(True)  # Never retain a request URL or headers.
                    await route.abort()
            await context.route('**/*', guard)
            page = await context.new_page()
            async def state():
                response = await api.get(SITE + '/api/monthly-tasks', headers={'x-affiliate-id': member}, max_redirects=0)
                if response.status != 200:
                    raise VerificationStopped('monthly_read_failed')
                data = await response.json()
                if (not re.fullmatch(r'\d{4}-\d{2}', data.get('month', '')) or
                        type(data.get('archiveDone')) is not bool or type(data.get('passcodeDone')) is not bool):
                    raise VerificationStopped('monthly_state_invalid')
                return {key: data[key] for key in ('month', 'archiveDone', 'passcodeDone')}
            original = await state()
            url = SITE + '/affiliate-activity?' + urlencode({'ref': member, 'session': 'mt'}) + '#monthly-tasks'
            await page.goto(url, wait_until='networkidle')
            nav = page.get_by_role('navigation', name='個別ページのメニュー')
            await nav.wait_for(state='visible')
            if await nav.locator('a').count() != 9:
                raise VerificationStopped('individual_menu_mismatch')
            admin_link = nav.locator('a[href="https://member.estlela.jp/default.asp"]')
            if await admin_link.count() != 1:
                raise VerificationStopped('individual_menu_link_mismatch')
            checks['individual-menu'] = True
            checkbox = page.get_by_role('checkbox', name='アーカイブを確認しました')
            await checkbox.wait_for(state='visible')
            if await checkbox.is_checked() != original['archiveDone']:
                raise VerificationStopped('monthly_render_mismatch')
            checks['monthly-read'] = True
            changed = True  # Even an ambiguous write must be restored before success.
            async with page.expect_response(lambda r: urlsplit(r.url).path == '/api/monthly-tasks' and r.request.method == 'PATCH') as pending:
                await checkbox.set_checked(not original['archiveDone'])
            if (await pending.value).status != 200:
                raise VerificationStopped('monthly_write_failed')
            await page.reload(wait_until='networkidle')
            checkbox = page.get_by_role('checkbox', name='アーカイブを確認しました')
            await checkbox.wait_for(state='visible')
            updated = await state()
            if updated != {**original, 'archiveDone': not original['archiveDone']} or await checkbox.is_checked() == original['archiveDone']:
                raise VerificationStopped('monthly_persistence_failed')
            if blocked:
                raise VerificationStopped('unexpected_network_request_blocked')
        finally:
            try:
                if changed and original is not None:
                    response = await api.patch(SITE + '/api/monthly-tasks', headers={'x-affiliate-id': member, 'Origin': SITE}, data=original, max_redirects=0)
                    restored = response.status == 200 and await state() == original
                    if not restored:
                        raise VerificationStopped('monthly_restore_failed')
                if changed and restored:
                    checks['monthly-write-restore'] = True
                    await preflight()
                    checks['source-stable'] = True
            finally:
                await context.close()
                await browser.close()
    return checks


def main():
    import asyncio
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'schema_version': 1, 'status': 'blocked', 'checks': {}}
    try:
        payload = json.loads(args.candidate.read_text(encoding='utf-8'))
        validate_payload(payload)
        target = validate_target(payload)
        report.update(payload_hash=payload_hash(payload), target=target)
        credentials(os.environ.get('ESTLELA_VERIFICATION_URL', ''))
        report['checks'] = asyncio.run(run_browser(payload, os.environ['ESTLELA_VERIFICATION_URL']))
        if report['checks'] != {key: True for key in CHECKS}:
            raise VerificationStopped('incomplete_browser_verification')
        report['status'] = 'passed'
    except VerificationStopped as error:
        report['reason'] = str(error)  # Only fixed codes originate above.
    except Exception:
        report['status'] = 'error'
        report['reason'] = 'verification_failed'  # Never print Playwright/HTTP details.
    report['checked_at'] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print('Production verification: ' + report['status'])
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
