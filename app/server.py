from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
from recommendation_engine import recommend, report, CATALOG, CHART

ROOT = Path(__file__).parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_GET(self):
        if self.path == '/api/health':
            return self.reply(200, {'ok': True, 'catalogue_count': len(CATALOG)})
        if self.path == '/api/catalogue':
            return self.reply(200, {'items': CATALOG, 'chart': CHART})
        return super().do_GET()

    def reply(self, status, obj):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path not in ('/api/recommend', '/api/report'):
            return self.reply(404, {'error': 'Unknown endpoint'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if n > 10000:
                raise ValueError('Request too large')
            data = json.loads(self.rfile.read(n))
            if self.path == '/api/recommend':
                return self.reply(200, recommend(data.get('owned_size'), data.get('feel'), data.get('intent'), data.get('query')))
            return self.reply(200, report(data.get('belief') or {}, data.get('worn'), data.get('report')))
        except Exception as e:
            return self.reply(400, {'error': str(e)})


if __name__ == '__main__':
    print('The Fitting Room: http://127.0.0.1:8799', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8799), Handler).serve_forever()
