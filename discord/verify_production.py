#!/usr/bin/env python3
"""Production browser check for a provisioned synthetic account, never members.

No screenshots, trace, HAR, storage-state export, private responses, or raw errors
are written. The signed URL is consumed in memory and never navigated to.
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urljoin
from verification import SITE, CHECKS, EXTENDED_CHECKS, payload_hash, validate_target
from render_update import validate_payload


class VerificationStopped(Exception):
    pass

VIDEO = 'https://video-window.honotoku.chatgpt.site'


def allowed_public_request(url, method, headers, member):
    """Read only public release surfaces; never register, buy or create videos."""
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.scheme != 'https' or 'token' in query:
        return False
    if parsed.netloc == urlsplit(VIDEO).netloc:
        # No support authentication header may ever reach the video origin.
        if {'x-affiliate-id', 'x-activity-token'} & headers.keys():
            return False
        if parsed.path.startswith('/cdn-cgi/challenge-platform/'):
            return allowed_request(SITE + parsed.path + ('?' + parsed.query if parsed.query else ''), method, headers, member)
        if method != 'GET':
            return False
        if parsed.path == '/admin':
            return query == {'mode': ['browser'], 'ref': [member], 'support_ref': [member]}
        if parsed.path == '/api/member/me':
            return not query and headers.get('x-video-mode') == 'browser'
        if parsed.path in ('/assets/id-choice.css', '/assets/id-choice.js', '/assets/admin.js'):
            return query == {'v': ['20261020-id-switch']}
        return not query and parsed.path in ('/favicon.svg', '/assets/style.css', '/assets/theme.css', '/assets/admin.css')
    if parsed.netloc != urlsplit(SITE).netloc or method != 'GET':
        return False
    if parsed.path == '/':
        return query in ({}, {'ref': [member]})
    if parsed.path == '/lp-share':
        return (query.get('ref') == [member] and not set(query) - {'ref', 'coupon', 'product'} and
                query.get('product', ['anoa-advance-cream']) == ['anoa-advance-cream'] and
                query.get('coupon', ['TESTONLY']) == ['TESTONLY'])
    if parsed.path in ('/go/anoa-advance-cream', '/lp/anoa-advance-cream'):
        return (query.get('id') == [member] and query.get('preview') == ['1'] and
                not set(query) - {'id', 'preview', 'coupon'} and query.get('coupon', ['TESTONLY']) == ['TESTONLY'])
    return not query and parsed.path.startswith(('/lp-assets/', '/images/'))


def excluded_public_request(url, method, resource_type):
    """Abort analytics and one unrelated catalog thumbnail, with no traffic."""
    parsed = urlsplit(url)
    if (parsed.scheme == 'https' and parsed.netloc == urlsplit(SITE).netloc and
            parsed.path == '/api/page-view' and not parsed.query and not parsed.fragment):
        return method == 'POST' and resource_type == 'fetch'
    return (url == 'https://estlela-ultima-treatment.honotoku.chatgpt.site/assets/product-original.png' and
            method == 'GET' and resource_type == 'image')


async def verify_public_surfaces(page, api, member, checks):
    await page.goto(SITE + '/', wait_until='networkidle')
    await page.get_by_role('heading', level=1).wait_for(state='visible')
    nav = page.get_by_role('navigation', name='サポートメニュー')
    if await nav.locator('a').count() != 9 or not await page.get_by_text('紹介者が運営するサポートサイトです。', exact=False).is_visible():
        raise VerificationStopped('public_landing_mismatch')
    canonical = await page.locator('link[rel="canonical"]').get_attribute('href')
    if canonical.rstrip('/') != SITE:
        raise VerificationStopped('public_canonical_mismatch')
    await page.goto(SITE + '/?' + urlencode({'ref': member}), wait_until='networkidle')
    video = page.get_by_role('link', name=re.compile('動画を送る'))
    video_url = await video.get_attribute('href')
    if not video_url or not allowed_public_request(video_url, 'GET', {}, member):
        raise VerificationStopped('video_entry_link_mismatch')
    await page.get_by_role('link', name=re.compile('商品を紹介する')).click()
    await page.get_by_role('link', name='ANOA アドバンスクリームの紹介メニューを開く', exact=True).click()
    preview = page.get_by_role('link', name='商品LPを別画面で開く', exact=True)
    await preview.wait_for(state='visible')
    preview_url = urljoin(SITE, await preview.get_attribute('href'))
    if not allowed_public_request(preview_url, 'GET', {}, member):
        raise VerificationStopped('cream_referral_link_mismatch')
    checks['public-referral'] = True
    await page.goto(preview_url, wait_until='networkidle')
    await page.get_by_role('heading', name='うるおいを守る、 仕上げのひと手間。', level=1).wait_for(state='visible')
    for name, destination, expected in (
            ('無料カスタマー登録へ', 'register', 'https://member.estlela.jp/U' + member),
            ('公式サイトで確認する', 'shop', 'https://estlela.jp/U' + member + '/')):
        href = await page.get_by_role('link', name=name, exact=True).get_attribute('href')
        parsed = urlsplit(urljoin(SITE, href))
        if (parsed.scheme != 'https' or parsed.netloc != urlsplit(SITE).netloc or
                parsed.path != '/official/anoa-advance-cream' or
                parse_qs(parsed.query) != {'id': [member], 'target': [destination], 'preview': ['1']}):
            raise VerificationStopped('cream_official_link_mismatch')
        response = await api.get(urljoin(SITE, href), max_redirects=0)
        if response.status not in (302, 303, 307, 308) or response.headers.get('location') != expected:
            raise VerificationStopped('cream_official_redirect_mismatch')
    # The preview never counts LP views or purchase/registration clicks; redirects
    # are inspected without following them to either external destination.
    hero = page.get_by_role('img', name='やわらかな光の中の女性と、ゴールドの蓋のANOAアドバンスクリーム')
    if not await hero.evaluate('(image) => image.complete && image.naturalWidth > 0'):
        raise VerificationStopped('cream_image_failed')
    checks['cream-lp'] = True
    await page.goto(video_url, wait_until='networkidle')
    await page.get_by_role('heading', name='動画に使うIDを選ぶ', exact=True).wait_for(state='visible')
    own = page.locator('#id-source-support')
    field = page.get_by_label('使用する紹介者ID（2〜6桁）', exact=True)
    if not await own.is_checked() or await field.input_value() != member or not await field.evaluate('(input) => input.readOnly'):
        raise VerificationStopped('video_support_id_mismatch')
    await page.locator('#id-source-other').check()
    await field.fill('1')
    if await field.evaluate('(input) => input.checkValidity()'):
        raise VerificationStopped('video_invalid_id_accepted')
    await field.fill(member)
    if not await field.evaluate('(input) => input.checkValidity()'):
        raise VerificationStopped('video_valid_id_rejected')
    if not await page.get_by_role('button', name='このIDで動画を作成する', exact=True).is_enabled():
        raise VerificationStopped('video_id_selection_unavailable')
    # Do not submit: fresh browser memberships would inflate usage counts.
    # The actual 999999 selection/dashboard/history was verified separately.
    checks['video-id-entry'] = True


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
    if parsed.path.startswith('/cdn-cgi/challenge-platform/'):
        # Run the site's normal Cloudflare browser check only after an explicit
        # per-run opt-in. Do not forward application credentials in this path.
        return (os.environ.get('ESTLELA_ALLOW_CLOUDFLARE_JSD') == '1' and
                method in ('GET', 'POST') and not query and
                not {'x-affiliate-id', 'x-activity-token'} & headers.keys() and
                '..' not in parsed.path.split('/') and
                re.fullmatch(r"/cdn-cgi/challenge-platform/[A-Za-z0-9_./:~!$&'()*+,;=@-]+", parsed.path) is not None)
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
    # Chromium can fetch the public icons declared by the management manifest.
    return method == 'GET' and not query and (parsed.path.startswith('/assets/') or parsed.path.startswith('/_next/') or parsed.path in (
        '/favicon.svg', '/estlela-management.webmanifest',
        '/apple-touch-icon-estlela-management-180.png',
        '/estlela-management-192.png', '/estlela-management-512.png'))


def hosting_widget_request(url, method, resource_type):
    """The hosting editor widget is not part of the app and must stay blocked."""
    parsed = urlsplit(url)
    return (method == 'GET' and resource_type == 'script' and
            parsed.scheme == 'https' and parsed.netloc in (urlsplit(SITE).netloc, urlsplit(VIDEO).netloc) and
            parsed.path == '/_sites/dispatch-assets/sites-widget.js' and
            not parsed.query and not parsed.fragment)


def blocked_request_code(url, resource_type):
    """Identify blocked resources without storing URLs or query values."""
    parsed = urlsplit(url)
    kind = resource_type if resource_type in ('document', 'stylesheet', 'image', 'media', 'font', 'script', 'xhr', 'fetch', 'manifest', 'websocket', 'eventsource') else 'other'
    origin = 'same_origin' if parsed.scheme == 'https' and parsed.netloc == urlsplit(SITE).netloc else 'external'
    area = next((label for prefix, label in (('/_sites/', 'hosting'), ('/assets/', 'assets'), ('/_next/', 'next'), ('/cdn-cgi/', 'cdn_cgi'), ('/api/', 'api')) if parsed.path.startswith(prefix)), 'other')
    # The hash excludes the entire query string and fragment, including IDs and
    # tokens. Compare it only with known public resource paths during diagnosis.
    fingerprint = hashlib.sha256((parsed.scheme + '://' + parsed.netloc + parsed.path).encode()).hexdigest()[:16]
    return ':'.join((kind, origin, area, 'query' if parsed.query else 'no_query', fingerprint))


async def run_browser(payload, raw_url):
    from playwright.async_api import async_playwright
    member, token = credentials(raw_url)
    target = validate_target(payload)
    extended = payload['verification_requirements'] == list(EXTENDED_CHECKS)
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
                # Sites injects this optional editor/composer loader into the
                # document. Do not execute it or permit its external traffic.
                # Its exact, query-free script GET is intentionally aborted.
                if hosting_widget_request(request.url, request.method, request.resource_type):
                    await route.abort()
                    return
                if extended and excluded_public_request(request.url, request.method, request.resource_type):
                    await route.abort()
                    return
                if (allowed_request(request.url, request.method, request.headers, member) or
                        extended and allowed_public_request(request.url, request.method, request.headers, member)):
                    await route.continue_()
                else:
                    # Retain only categories and a query-free resource hash.
                    # Never retain a URL, query values, headers, or private body.
                    blocked.append(blocked_request_code(request.url, request.resource_type))
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
            if extended:
                notification = page.get_by_role('button', name='通知を受け取る（準備中）', exact=True)
                if not await notification.is_visible() or not await notification.is_disabled():
                    raise VerificationStopped('notification_readiness_mismatch')
                checks['notification-not-ready'] = True
            changed = True  # Even an ambiguous write must be restored before success.
            async with page.expect_response(lambda r: urlsplit(r.url).path == '/api/monthly-tasks' and r.request.method == 'PATCH') as pending:
                # The controlled checkbox updates only after the PATCH completes.
                # Click once; the response and reload assertions below verify persistence.
                await checkbox.click()
            if (await pending.value).status != 200:
                raise VerificationStopped('monthly_write_failed')
            await page.reload(wait_until='networkidle')
            checkbox = page.get_by_role('checkbox', name='アーカイブを確認しました')
            await checkbox.wait_for(state='visible')
            updated = await state()
            if updated != {**original, 'archiveDone': not original['archiveDone']} or await checkbox.is_checked() == original['archiveDone']:
                raise VerificationStopped('monthly_persistence_failed')
            if extended:
                await verify_public_surfaces(page, api, member, checks)
            if blocked:
                raise VerificationStopped('unexpected_network_request_blocked:' + ','.join(sorted(set(blocked))))
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
        if report['checks'] != {key: True for key in payload['verification_requirements']}:
            raise VerificationStopped('incomplete_browser_verification')
        report['status'] = 'passed'
    except VerificationStopped as error:
        report['reason'] = str(error)  # Only sanitized codes originate above.
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

