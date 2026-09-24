import copy
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import urllib.error

import publish_updates as p
from check_health import check_health


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('outbox', 'sent', 'attempts', 'checks'):
            (self.root / name).mkdir()
        self.patches = [patch.object(p, name.upper(), self.root / name) for name in ('outbox', 'sent', 'attempts')]
        for item in self.patches:
            item.start()
        self.payload = json.loads((p.ROOT / 'outbox/estlela-v79.json').read_text())
        self.put(self.payload)

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def put(self, payload):
        (self.root / 'outbox' / (payload['release_id'] + '.json')).write_text(json.dumps(payload))

    def test_sent_skipped_and_mutation_rejected(self):
        p.write_marker(self.payload, '123')
        self.assertEqual(p.check_queue(), [])
        self.payload['headline'] = 'Modified headline'
        self.put(self.payload)
        with self.assertRaises(ValueError):
            p.check_queue()

    def test_duplicate_versions_rejected(self):
        other = dict(self.payload, release_id='duplicate')
        self.put(other)
        with self.assertRaises(ValueError):
            p.check_queue()

    def test_duplicate_content_with_different_date_id_version(self):
        self.put(dict(self.payload, release_id='duplicate', date='2026.09.25', source_versions=[80]))
        with self.assertRaises(ValueError):
            p.check_queue()

    def test_uncertain_attempt_blocks(self):
        (self.root / 'attempts/estlela-v79.json').write_text('{}')
        with self.assertRaises(RuntimeError):
            p.check_queue()

    def test_no_secret_fails(self):
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': ''}):
            with self.assertRaises(RuntimeError):
                p.publish_all()

    def test_network_timeout_not_retried(self):
        image = self.root / 'image.png'
        image.write_bytes(b'png')
        with patch.object(p.urllib.request, 'urlopen', side_effect=TimeoutError) as request:
            with self.assertRaises(RuntimeError):
                p.send_to_discord('https://discord.com/api/webhooks/test', self.payload, image)
            self.assertEqual(request.call_count, 1)

    def test_checkpoint_failure_prevents_send(self):
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test'}), \
             patch.object(p, 'render_update'), \
             patch.object(p, 'checkpoint', side_effect=RuntimeError('push failed')), \
             patch.object(p, 'send_to_discord') as send:
            with self.assertRaises(RuntimeError):
                p.publish_all()
            send.assert_not_called()

    def test_partial_batch_receipt_survives_later_failure(self):
        other = copy.deepcopy(self.payload)
        other.update(release_id='estlela-v80', source_versions=[80], headline='Different update')
        self.put(other)
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test'}), \
             patch.object(p, 'render_update'), patch.object(p, 'checkpoint') as save, \
             patch.object(p, 'send_to_discord', side_effect=['123', RuntimeError('uncertain')]):
            with self.assertRaises(RuntimeError):
                p.publish_all()
            self.assertTrue((self.root / 'sent/estlela-v79.json').exists())
            self.assertEqual(save.call_count, 3)

    def test_missing_and_no_update_health(self):
        now = datetime.fromisoformat('2026-09-25T07:45:00+09:00')
        with self.assertRaises(RuntimeError):
            check_health(now, self.root)
        record = {'checked_at': '2026-09-25T07:05:00+09:00', 'cutoff_jst': '2026-09-25T07:00:00+09:00',
                  'status': 'no_update', 'release_ids': [], 'evidence': 'Verified production version 79'}
        (self.root / 'checks/2026-09-25.json').write_text(json.dumps(record))
        check_health(now, self.root)
        record['status'] = 'error'
        (self.root / 'checks/2026-09-25.json').write_text(json.dumps(record))
        with self.assertRaises(RuntimeError):
            check_health(now, self.root)


if __name__ == '__main__':
    unittest.main()
