"""End to end tests: start the real server on a spare port with a temporary database and send HTTP requests."""
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import Handler

RIGID = 'classic straight leg rigid non stretch jeans'
# A belief an attacker might send: every probability on W34, whatever really fits.
FORGED = {str(s): (1.0 if s == 34 else 0.0) for s in range(24, 35)}


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        Handler.db_path = Path(cls.tmp.name) / 'test.db'
        Handler.log_message = lambda *a: None          # keep test output quiet
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)   # port 0 means any free port
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, shopper=None):
        headers = {'Content-Type': 'application/json'}
        if shopper is not None:
            headers['X-Shopper-Id'] = shopper
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def save_pair(self, shopper=None, size=28, feel=-2):
        return self.call('POST', '/api/wardrobe', {'product_id': '501', 'size': size, 'feel': feel}, shopper)

    def get_recommendation(self, shopper=None):
        status, rec = self.call('POST', '/api/recommend', {'owned_size': 28, 'feel': -2, 'intent': 'regular',
                                                            'query': RIGID}, shopper)
        self.assertEqual(status, 200)
        return rec

    def send_report(self, rec_id, worn=29, fit='tight', shopper=None, **extra):
        return self.call('POST', '/api/report', {'recommendation_id': rec_id, 'worn': worn, 'report': fit, **extra},
                         shopper)

    # Normal use
    def test_saving_a_pair_creates_a_shopper_and_stores_it(self):
        status, body = self.save_pair()
        self.assertEqual(status, 200)
        self.assertEqual([(p['product_id'], p['size'], p['feel']) for p in body['pairs']], [('501', 28, -2)])
        status, body2 = self.call('GET', '/api/wardrobe', shopper=body['shopper_id'])
        self.assertEqual((status, len(body2['pairs'])), (200, 1))

    def test_second_pair_goes_to_the_same_shopper(self):
        _, first = self.save_pair()
        _, second = self.save_pair(first['shopper_id'], size=30, feel=0)
        self.assertEqual(second['shopper_id'], first['shopper_id'])
        self.assertEqual([p['size'] for p in second['pairs']], [28, 30])

    def test_fit_report_is_stored_for_a_known_shopper(self):
        _, saved = self.save_pair()
        rec = self.get_recommendation(saved['shopper_id'])
        status, rep = self.send_report(rec['recommendation_id'], shopper=saved['shopper_id'])
        self.assertEqual((status, rep['stored']), (200, True))
        _, wardrobe = self.call('GET', '/api/wardrobe', shopper=saved['shopper_id'])
        self.assertEqual([(r['product_id'], r['worn_size'], r['report']) for r in wardrobe['fit_reports']],
                         [(rec['product_id'], 29, 'tight')])

    def test_fit_report_without_a_shopper_still_updates_but_is_not_stored(self):
        rec = self.get_recommendation()
        status, rep = self.send_report(rec['recommendation_id'], fit='right')
        self.assertEqual(status, 200)
        self.assertNotIn('stored', rep)

    # Server side belief (issue #4)
    def test_recommendation_returns_an_id(self):
        rec = self.get_recommendation()
        self.assertRegex(rec['recommendation_id'], r'^[A-Za-z0-9_-]{22}$')

    def test_report_starts_from_the_server_copy_of_the_belief(self):
        rec = self.get_recommendation()
        _, rep = self.send_report(rec['recommendation_id'])
        # Equal up to rounding: the stored belief is rounded to 4 places and the engine renormalises it.
        self.assertEqual(rep['prior'].keys(), rec['belief'].keys())
        for size, p in rec['belief'].items():
            self.assertAlmostEqual(rep['prior'][size], p, delta=0.0005)

    def test_belief_sent_by_the_browser_is_refused(self):
        rec = self.get_recommendation()
        status, body = self.send_report(rec['recommendation_id'], fit='right', belief=FORGED)
        self.assertEqual((status, body), (400, {'error': 'Unexpected field: belief'}))

    def test_product_sent_by_the_browser_is_refused(self):
        # The product now comes from the stored recommendation, so the browser cannot relabel a report.
        rec = self.get_recommendation()
        status, body = self.send_report(rec['recommendation_id'], product_id='ribcage')
        self.assertEqual((status, body), (400, {'error': 'Unexpected field: product_id'}))

    def test_report_without_an_id_is_refused(self):
        status, body = self.call('POST', '/api/report', {'worn': 29, 'report': 'right'})
        self.assertEqual((status, body), (400, {'error': 'Invalid recommendation ID'}))

    def test_made_up_id_is_refused(self):
        status, body = self.send_report('A' * 22)
        self.assertEqual((status, body), (404, {'error': 'Unknown recommendation'}))

    def test_injection_in_recommendation_id_is_refused(self):
        self.get_recommendation()
        for bad in ("x' OR '1'='1", 12345, ['A' * 22], None):
            status, body = self.send_report(bad)
            self.assertEqual((status, body), (400, {'error': 'Invalid recommendation ID'}), bad)

    def test_tampered_id_is_refused(self):
        rec_id = self.get_recommendation()['recommendation_id']
        tampered = rec_id[:-1] + ('A' if rec_id[-1] != 'A' else 'B')
        self.assertEqual(self.send_report(tampered)[0], 404)

    def test_another_shoppers_recommendation_is_refused(self):
        _, alice = self.save_pair()
        _, bob = self.save_pair()
        rec = self.get_recommendation(alice['shopper_id'])
        self.assertEqual(self.send_report(rec['recommendation_id'], shopper=bob['shopper_id'])[0], 404)
        self.assertEqual(self.send_report(rec['recommendation_id'])[0], 404)      # or with no shopper at all
        _, wardrobe = self.call('GET', '/api/wardrobe', shopper=alice['shopper_id'])
        self.assertEqual(wardrobe['fit_reports'], [])

    def test_repeating_a_report_does_not_push_the_belief_further(self):
        rec = self.get_recommendation()
        replies = [self.send_report(rec['recommendation_id'], fit='tight')[1] for _ in range(3)]
        self.assertEqual(replies[0]['belief'], replies[2]['belief'])
        self.assertEqual(replies[0]['prior'], replies[2]['prior'])

    def test_repeating_a_report_stores_it_once(self):
        _, saved = self.save_pair()
        rec = self.get_recommendation(saved['shopper_id'])
        for _ in range(3):
            self.send_report(rec['recommendation_id'], fit='tight', shopper=saved['shopper_id'])
        self.send_report(rec['recommendation_id'], worn=30, fit='right', shopper=saved['shopper_id'])  # a correction
        _, wardrobe = self.call('GET', '/api/wardrobe', shopper=saved['shopper_id'])
        self.assertEqual([(r['worn_size'], r['report']) for r in wardrobe['fit_reports']], [(30, 'right')])

    def test_worn_size_must_be_a_whole_chart_size(self):
        rec_id = self.get_recommendation()['recommendation_id']
        for bad in (29.9, '29', True, 99, None):
            status, body = self.send_report(rec_id, worn=bad)
            self.assertEqual((status, body), (400, {'error': 'Worn size is outside the published chart range'}), bad)

    def test_report_value_must_be_known(self):
        rec_id = self.get_recommendation()['recommendation_id']
        self.assertEqual(self.send_report(rec_id, fit='massive')[0], 400)

    def test_recommendation_for_unknown_shopper_is_refused(self):
        status, _ = self.call('POST', '/api/recommend', {'owned_size': 28, 'feel': -2, 'intent': 'regular',
                                                         'query': RIGID}, 'A' * 22)
        self.assertEqual(status, 404)

    # Bad and hostile input
    def test_injection_in_shopper_header_is_refused(self):
        self.save_pair()
        status, body = self.call('GET', '/api/wardrobe', shopper="x' OR '1'='1")
        self.assertEqual((status, body), (400, {'error': 'Invalid shopper ID'}))

    def test_injection_in_product_is_refused(self):
        status, body = self.call('POST', '/api/wardrobe', {'product_id': "501'; DROP TABLE owned_pairs; --",
                                                            'size': 28, 'feel': 0})
        self.assertEqual((status, body), (400, {'error': 'Unknown product'}))

    def test_wrong_types_are_refused(self):
        for bad in ({'product_id': '501', 'size': '28 OR 1=1', 'feel': 0},
                    {'product_id': '501', 'size': 28, 'feel': 'tight'},
                    {'product_id': ['501'], 'size': 28, 'feel': 0}):
            self.assertEqual(self.call('POST', '/api/wardrobe', bad)[0], 400)

    def test_unknown_but_well_formed_shopper_gets_404(self):
        status, _ = self.call('GET', '/api/wardrobe', shopper='A' * 22)
        self.assertEqual(status, 404)

    def test_missing_shopper_header_is_refused(self):
        self.assertEqual(self.call('GET', '/api/wardrobe')[0], 400)

    def test_database_errors_are_not_shown_to_the_browser(self):
        # Make the database fail on purpose and check the reply hides the SQLite message.
        failure = sqlite3.OperationalError('no such table: owned_pairs')
        with mock.patch('storage.list_wardrobe', side_effect=failure):
            status, body = self.save_pair()
        self.assertEqual((status, body), (500, {'error': 'Storage error'}))

if __name__ == '__main__':
    unittest.main()
