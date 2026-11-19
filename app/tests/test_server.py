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
        _, rec = self.call('POST', '/api/recommend', {'owned_size': 28, 'feel': -2, 'intent': 'regular',
                                                       'query': 'classic straight leg rigid non stretch jeans'})
        status, rep = self.call('POST', '/api/report', {'belief': rec['belief'], 'worn': 29, 'report': 'tight',
                                                         'product_id': rec['product_id']}, saved['shopper_id'])
        self.assertEqual((status, rep['stored']), (200, True))
        _, wardrobe = self.call('GET', '/api/wardrobe', shopper=saved['shopper_id'])
        self.assertEqual([(r['worn_size'], r['report']) for r in wardrobe['fit_reports']], [(29, 'tight')])

    def test_fit_report_without_a_shopper_still_updates_but_is_not_stored(self):
        _, rec = self.call('POST', '/api/recommend', {'owned_size': 28, 'feel': -2, 'intent': 'regular',
                                                       'query': 'classic straight leg rigid non stretch jeans'})
        status, rep = self.call('POST', '/api/report', {'belief': rec['belief'], 'worn': 29, 'report': 'right'})
        self.assertEqual(status, 200)
        self.assertNotIn('stored', rep)

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
