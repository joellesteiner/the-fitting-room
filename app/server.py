from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from contextlib import closing
from pathlib import Path
import json
import os
import re
import sqlite3

import storage
from recommendation_engine import recommend, report, CATALOG, CHART, WAIST

ROOT = Path(__file__).parent
PRODUCT_IDS = {p['id'] for p in CATALOG}
# The shopper ID is sent in a header, not the URL, so it does not end up in browser history or access logs.
SHOPPER_HEADER = 'X-Shopper-Id'
# IDs made by storage.create_shopper and storage.save_recommendation are URL safe base64.
# Anything else is refused before it reaches the database.
ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
# The only fields a fit report may carry. The belief is deliberately not one of them:
# the server applies the report to its own stored copy, so the browser cannot choose the probabilities.
REPORT_FIELDS = {'recommendation_id', 'worn', 'report'}


class UnknownShopper(Exception):
    pass


class UnknownRecommendation(Exception):
    pass


def is_whole_number(value):
    # In Python True and False count as int (True == 1), so they are ruled out explicitly.
    return isinstance(value, int) and not isinstance(value, bool)


class Handler(SimpleHTTPRequestHandler):
    db_path = storage.DEFAULT_DB

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def reply(self, status, obj):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def shopper_id(self, required):
        """Read and check the shopper ID header. Returns None if it is absent and not required."""
        value = self.headers.get(SHOPPER_HEADER)
        if value is None:
            if required:
                raise ValueError('Missing shopper ID')
            return None
        if not ID_PATTERN.fullmatch(value):
            raise ValueError('Invalid shopper ID')
        return value

    def handle_api(self, action):
        """Run one API action and turn its outcome or error into a JSON reply."""
        try:
            return self.reply(200, action())
        except UnknownShopper:
            return self.reply(404, {'error': 'Unknown shopper ID'})
        except UnknownRecommendation:
            return self.reply(404, {'error': 'Unknown recommendation'})
        except sqlite3.Error:
            # Never send database error text to the browser: it can reveal table and column names.
            return self.reply(500, {'error': 'Storage error'})
        except Exception as e:
            return self.reply(400, {'error': str(e)})

    def read_json(self):
        n = int(self.headers.get('Content-Length', '0'))
        if n > 10000:
            raise ValueError('Request too large')
        data = json.loads(self.rfile.read(n))
        if not isinstance(data, dict):
            raise ValueError('Request body must be a JSON object')
        return data

    def do_GET(self):
        if self.path == '/api/health':
            return self.reply(200, {'ok': True, 'catalogue_count': len(CATALOG)})
        if self.path == '/api/catalogue':
            return self.reply(200, {'items': CATALOG, 'chart': CHART})
        if self.path == '/api/wardrobe':
            return self.handle_api(self.get_wardrobe)
        return super().do_GET()

    def do_POST(self):
        actions = {'/api/recommend': self.post_recommend, '/api/report': self.post_report,
                   '/api/wardrobe': self.post_wardrobe}
        if self.path not in actions:
            return self.reply(404, {'error': 'Unknown endpoint'})
        return self.handle_api(actions[self.path])

    # ---- API actions ----

    def post_recommend(self):
        data = self.read_json()
        shopper = self.shopper_id(required=False)
        result = recommend(data.get('owned_size'), data.get('feel'), data.get('intent'), data.get('query'))
        # Keep the server's own copy of the belief. The browser gets an ID to refer to it, and a copy to draw.
        with closing(storage.connect(self.db_path)) as conn:
            if shopper is not None and not storage.shopper_exists(conn, shopper):
                raise UnknownShopper()
            result['recommendation_id'] = storage.save_recommendation(conn, shopper, result['product_id'],
                                                                      result['belief'])
        return result

    def post_report(self):
        data = self.read_json()
        unexpected = set(data) - REPORT_FIELDS
        if unexpected:
            raise ValueError('Unexpected field: ' + ', '.join(sorted(unexpected)))
        recommendation_id, worn, report_value = data.get('recommendation_id'), data.get('worn'), data.get('report')
        if not isinstance(recommendation_id, str) or not ID_PATTERN.fullmatch(recommendation_id):
            raise ValueError('Invalid recommendation ID')
        if not is_whole_number(worn) or worn not in WAIST:
            raise ValueError('Worn size is outside the published chart range')
        if report_value not in ('tight', 'right', 'loose'):
            raise ValueError('Report must be tight, right or loose')
        shopper = self.shopper_id(required=False)
        with closing(storage.connect(self.db_path)) as conn:
            found = storage.get_recommendation(conn, recommendation_id)
            # A recommendation made for one shopper can only be reported on by that shopper.
            # A wrong owner gets the same reply as a missing ID, so the reply does not reveal that the ID exists.
            if found is None or found['shopper_id'] != shopper:
                raise UnknownRecommendation()
            # Always start from the stored belief, never from the last update, so repeating a report cannot
            # push the belief further and further. The posterior is returned, not saved over the prior.
            result = report(found['belief'], worn, report_value)
            if shopper is not None:
                storage.add_fit_report(conn, shopper, found['product_id'], worn, report_value, recommendation_id)
                result['stored'] = True
        result['recommendation_id'] = recommendation_id
        return result

    def post_wardrobe(self):
        data = self.read_json()
        shopper = self.shopper_id(required=False)
        product_id, size, feel = data.get('product_id'), data.get('size'), data.get('feel')
        # Check every value here, at the edge of the system, before anything touches the database.
        if product_id not in PRODUCT_IDS:
            raise ValueError('Unknown product')
        if not is_whole_number(size) or size not in WAIST:
            raise ValueError('This size is outside the published chart range')
        if not is_whole_number(feel) or feel not in (-2, 0, 2):
            raise ValueError('Invalid saved fit feedback')
        with closing(storage.connect(self.db_path)) as conn:
            if shopper is None:
                shopper = storage.create_shopper(conn)
            elif not storage.shopper_exists(conn, shopper):
                raise UnknownShopper()
            storage.add_owned_pair(conn, shopper, product_id, size, feel)
            return {'shopper_id': shopper, 'pairs': storage.list_wardrobe(conn, shopper)}

    def get_wardrobe(self):
        shopper = self.shopper_id(required=True)
        with closing(storage.connect(self.db_path)) as conn:
            if not storage.shopper_exists(conn, shopper):
                raise UnknownShopper()
            return {'shopper_id': shopper, 'pairs': storage.list_wardrobe(conn, shopper),
                    'fit_reports': storage.list_fit_reports(conn, shopper)}


if __name__ == '__main__':
    Handler.db_path = Path(os.environ.get('FITTING_ROOM_DB', storage.DEFAULT_DB))
    print('The Fitting Room: http://127.0.0.1:8799', flush=True)
    print(f'Database: {Handler.db_path}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8799), Handler).serve_forever()
