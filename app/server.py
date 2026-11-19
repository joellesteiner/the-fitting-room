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
# IDs made by storage.create_shopper are URL safe base64. Anything else is refused before it reaches the database.
SHOPPER_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{16,64}$')


class UnknownShopper(Exception):
    pass


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
        if not SHOPPER_ID_PATTERN.fullmatch(value):
            raise ValueError('Invalid shopper ID')
        return value

    def handle_api(self, action):
        """Run one API action and turn its outcome or error into a JSON reply."""
        try:
            return self.reply(200, action())
        except UnknownShopper:
            return self.reply(404, {'error': 'Unknown shopper ID'})
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
        return recommend(data.get('owned_size'), data.get('feel'), data.get('intent'), data.get('query'))

    def post_report(self):
        data = self.read_json()
        shopper = self.shopper_id(required=False)
        result = report(data.get('belief') or {}, data.get('worn'), data.get('report'))
        # The belief update works without an account. A report is only stored when the shopper has saved a wardrobe.
        if shopper is not None:
            product_id = data.get('product_id')
            if product_id not in PRODUCT_IDS:
                raise ValueError('Unknown product')
            with closing(storage.connect(self.db_path)) as conn:
                if not storage.shopper_exists(conn, shopper):
                    raise UnknownShopper()
                storage.add_fit_report(conn, shopper, product_id, result['worn'], result['report'])
            result['stored'] = True
        return result

    def post_wardrobe(self):
        data = self.read_json()
        shopper = self.shopper_id(required=False)
        product_id, size, feel = data.get('product_id'), data.get('size'), data.get('feel')
        # Check every value here, at the edge of the system, before anything touches the database.
        if product_id not in PRODUCT_IDS:
            raise ValueError('Unknown product')
        if not isinstance(size, int) or size not in WAIST:
            raise ValueError('This size is outside the published chart range')
        if not isinstance(feel, int) or feel not in (-2, 0, 2):
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
