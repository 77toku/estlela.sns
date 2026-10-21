import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import publish_updates as publisher
from prepare_update import prepare
from verification import CHECKS, SITE, payload_hash, validate_report
from verify_production import allowed_request, blocked_request_code, credentials, hosting_widget_request, VerificationStopped


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.payload = json.loads((publisher.ROOT / 'outbox/estlela-v131.json').read_text())
        self.payload.update(release_id='estlela-v138', source_versions=[132, 133, 134, 135, 136, 137, 138],
                            verification_requirements=list(CHECKS), verification_target={
                                'source_commit': 'a' * 40, 'source_fingerprint': 'b' * 64,
                                'deployment_id': 'appgdep_LOCALTEST', 'public_version': 138})
        self.report = {'schema_version': 1, 'status': 'passed', 'payload_hash': payload_hash(self.payload),
                       'target': self.payload['verification_target'], 'checks': {key: True for key in CHECKS},
                       'checked_at': datetime.now(timezone.utc).isoformat()}
        self.patches = [patch.object(publisher, 'ROOT', self.root)] + [
            patch.object(publisher, name.upper(), self.root / name) for name in ('outbox', 'sent', 'attempts')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def test_exact_source_payload_and_fresh_success_required(self):
        validate_report(self.payload, self.report)
        for update in ({'status': 'blocked'}, {'status': 'error'}, {'checks': {}}, {'target': {}},
                       {'payload_hash': '0' * 64}, {'checked_at': '2000-01-01T00:00:00+00:00'},
                       {'checked_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_report(self.payload, {**self.report, **update})
        altered = {**self.payload, 'headline': 'Different announcement'}
        with self.assertRaises(ValueError):
            validate_report(altered, self.report)

    def test_unverified_generation_and_delivery_are_blocked(self):
        with self.assertRaises(ValueError):
            prepare(self.payload, {**self.report, 'status': 'blocked'}, self.root)
        self.assertFalse((self.root / 'outbox').exists())
        (self.root / 'outbox').mkdir()
        (self.root / 'outbox/estlela-v138.json').write_text(json.dumps(self.payload))
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/LOCAL_TEST'}), \
                patch.object(publisher, 'send_to_discord') as send, \
                patch.object(publisher, 'checkpoint') as checkpoint:
            with self.assertRaises(ValueError):
                publisher.publish_all()
            send.assert_not_called()
            checkpoint.assert_not_called()

    def test_verified_generation_render_delivery_receipt_and_duplicate_skip(self):
        prepare(self.payload, self.report, self.root)
        self.assertEqual(len(publisher.check_queue()), 1)
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/LOCAL_TEST'}), \
                patch.object(publisher, 'send_to_discord', return_value='LOCAL_TEST_MESSAGE_ID') as send, \
                patch.object(publisher, 'checkpoint') as checkpoint:
            publisher.publish_all()  # Real PNG renderer; only network/Git are mocked.
            self.assertEqual(send.call_count, 1)
            self.assertEqual(checkpoint.call_count, 2)
            publisher.publish_all()
            self.assertEqual(send.call_count, 1)
        receipt = json.loads((self.root / 'sent/estlela-v138.json').read_text())
        self.assertEqual(receipt['content_hash'], payload_hash(self.payload))
        with self.assertRaises(ValueError):
            prepare(self.payload, self.report, self.root)

    def test_unknown_or_orphaned_attempt_blocks_every_new_release(self):
        (self.root / 'attempts').mkdir()
        (self.root / 'attempts/orphan.json').write_text('{}')
        with self.assertRaises(RuntimeError):
            prepare(self.payload, self.report, self.root)
        with self.assertRaises(RuntimeError):
            publisher.check_queue()

    def test_timeouts_preserve_intent_and_are_not_retried(self):
        prepare(self.payload, self.report, self.root)
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/LOCAL_TEST'}), \
                patch.object(publisher, 'render_update'), patch.object(publisher, 'checkpoint'), \
                patch.object(publisher, 'send_to_discord', side_effect=RuntimeError('uncertain')) as send:
            with self.assertRaises(RuntimeError):
                publisher.publish_all()
            with self.assertRaises(RuntimeError):
                publisher.publish_all()
            self.assertEqual(send.call_count, 1)
        self.assertTrue((self.root / 'attempts/estlela-v138.json').exists())
        self.assertFalse((self.root / 'sent/estlela-v138.json').exists())

    def test_existing_delivered_records_need_no_retroactive_evidence(self):
        (self.root / 'outbox').mkdir()
        old = {k: v for k, v in self.payload.items() if not k.startswith('verification_')}
        (self.root / 'outbox/estlela-v138.json').write_text(json.dumps(old))
        publisher.write_marker(old, 'EXISTING_MESSAGE')
        self.assertEqual(publisher.check_queue(), [])

    def test_secrets_are_restricted_to_exact_origin_and_never_in_errors(self):
        secret = 'c' * 64
        self.assertEqual(credentials(SITE + '/affiliate-activity?ref=991122&token=' + secret), ('991122', secret))
        for url in ('', 'https://evil.example/affiliate-activity?ref=991122&token=' + secret,
                    SITE + '.evil.example/affiliate-activity?ref=991122&token=' + secret,
                    SITE + '/affiliate-activity?ref=991122&ref=22&token=' + secret,
                    SITE + '/affiliate-activity?ref=991122&token=' + secret + '#extra'):
            with self.assertRaises(VerificationStopped) as error:
                credentials(url)
            self.assertNotIn(secret, str(error.exception))

    def test_browser_blocks_other_id_external_requests_notifications_and_tokens(self):
        member = '991122'
        for url, method, headers in (
            (SITE + '/api/affiliate-admin', 'GET', {}),
            (SITE + '/api/affiliate-activity?ref=22&session=mt', 'GET', {}),
            (SITE + '/api/mt-subscription', 'POST', {'x-affiliate-id': member}),
            (SITE + '/api/video-ticket', 'POST', {}),
            ('https://discord.com/api/webhooks/test', 'POST', {}),
            (SITE + '/affiliate-activity?ref=991122&token=' + 'c' * 64, 'GET', {}),
            (SITE + '/api/monthly-tasks', 'PATCH', {'x-affiliate-id': '22'}),
        ):
            self.assertFalse(allowed_request(url, method, headers, member))
        self.assertTrue(allowed_request(SITE + '/api/monthly-tasks', 'PATCH', {'x-affiliate-id': member}, member))
        self.assertTrue(allowed_request(SITE + '/affiliate-activity?ref=991122&session=mt', 'GET', {}, member))

    def test_management_manifest_icons_are_public_read_only_resources(self):
        member = '991122'
        for path in ('/estlela-management-192.png', '/estlela-management-512.png'):
            with self.subTest(path=path):
                self.assertTrue(allowed_request(SITE + path, 'GET', {}, member))
                self.assertFalse(allowed_request(SITE + path, 'POST', {}, member))
                self.assertFalse(allowed_request(SITE + path + '?ref=22', 'GET', {}, member))
                self.assertFalse(allowed_request(SITE + path + '?token=' + 'c' * 64, 'GET', {}, member))
                self.assertFalse(allowed_request('https://example.org' + path, 'GET', {}, member))

    def test_only_exact_hosting_editor_script_is_intentionally_aborted(self):
        widget = SITE + '/_sites/dispatch-assets/sites-widget.js'
        self.assertFalse(allowed_request(widget, 'GET', {}, '991122'))
        self.assertTrue(hosting_widget_request(widget, 'GET', 'script'))
        for url, method, kind in (
            (widget, 'POST', 'script'),
            (widget, 'GET', 'fetch'),
            (widget + '?ref=22', 'GET', 'script'),
            (widget + '?token=' + 'c' * 64, 'GET', 'script'),
            (widget + '#extra', 'GET', 'script'),
            ('https://example.org/_sites/dispatch-assets/sites-widget.js', 'GET', 'script'),
            (SITE + '/api/video-ticket', 'GET', 'script'),
            (SITE + '/_sites/dispatch-assets/other.js', 'GET', 'script'),
        ):
            with self.subTest(url=url, method=method, kind=kind):
                self.assertFalse(hosting_widget_request(url, method, kind))

    def test_blocked_resource_diagnostics_exclude_all_query_values(self):
        base = SITE + '/_sites/dispatch-assets/sites-widget.js'
        code = blocked_request_code(base + '?ref=991122&token=' + 'c' * 64, 'script')
        self.assertEqual(code, blocked_request_code(base + '?ref=22&token=' + 'd' * 64, 'script'))
        for value in (SITE, '/_sites/', '991122', 'c' * 64, 'token=', 'ref='):
            self.assertNotIn(value, code)
        self.assertRegex(code, r'^script:same_origin:hosting:query:[a-f0-9]{16}$')

    def test_cloudflare_browser_check_requires_explicit_opt_in_and_no_app_credentials(self):
        path = '/cdn-cgi/challenge-platform/scripts/jsd/main.js'
        with patch.dict(os.environ, {'ESTLELA_ALLOW_CLOUDFLARE_JSD': '0'}):
            self.assertFalse(allowed_request(SITE + path, 'GET', {}, '991122'))
        with patch.dict(os.environ, {'ESTLELA_ALLOW_CLOUDFLARE_JSD': '1'}):
            self.assertTrue(allowed_request(SITE + path, 'GET', {}, '991122'))
            self.assertTrue(allowed_request(SITE + '/cdn-cgi/challenge-platform/h/g/jsd/verification', 'POST', {}, '991122'))
            for url, method, headers in (
                (SITE + path, 'DELETE', {}),
                (SITE + path + '?ref=22', 'GET', {}),
                (SITE + path + '?token=' + 'c' * 64, 'GET', {}),
                (SITE + path, 'GET', {'x-affiliate-id': '991122'}),
                (SITE + path, 'GET', {'x-activity-token': 'c' * 64}),
                ('https://example.org' + path, 'GET', {}),
                (SITE + '/cdn-cgi/trace', 'GET', {}),
                (SITE + '/cdn-cgi/challenge-platform/../api/private', 'GET', {}),
            ):
                with self.subTest(url=url, method=method):
                    self.assertFalse(allowed_request(url, method, headers, '991122'))

