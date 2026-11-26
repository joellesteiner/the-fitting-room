"""Storage for the wardrobe and fit history, using SQLite from the Python standard library.

What is stored, and nothing more:
* shoppers: a random pseudonymous ID and the date it was created. No name, email or body data.
* owned_pairs: the jeans a shopper says they own (product, size, how it feels).
* recommendations: the belief over sizes the server worked out, kept so a later fit report is
  applied to the server's own copy and never to probabilities sent by the browser.
* fit_reports: what a shopper said about a pair after delivery (product, size worn, report),
  at most one per recommendation.

Recommendations are deleted after RECOMMENDATION_KEEP_DAYS. Everything a shopper owns is deleted
with delete_shopper, and secure_delete makes sure the deleted bytes do not linger in the file.

Every query uses ? placeholders, so values are always sent to SQLite as data and are never
pasted into the SQL text. That is what stops SQL injection (OWASP A03). The CHECK constraints
in the schema are a second line of defence if a bad value ever gets past the server's checks.
"""
import json
import secrets
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / 'data' / 'fitting_room.db'

# A recommendation is only needed until the shopper can report how the pair fitted.
# Delivery plus the 14 day cancellation period under the Consumer Contracts Regulations fits well inside 30 days.
# A fit report outlives its recommendation: deleting the recommendation only clears the link to it.
RECOMMENDATION_KEEP_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS shoppers (
    id          TEXT PRIMARY KEY,
    created_on  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owned_pairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shopper_id  TEXT NOT NULL REFERENCES shoppers(id) ON DELETE CASCADE,
    product_id  TEXT NOT NULL,
    size        INTEGER NOT NULL CHECK (size BETWEEN 24 AND 34),
    feel        INTEGER NOT NULL CHECK (feel IN (-2, 0, 2)),
    created_on  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendations (
    id          TEXT PRIMARY KEY,
    shopper_id  TEXT REFERENCES shoppers(id) ON DELETE CASCADE,
    product_id  TEXT NOT NULL,
    belief      TEXT NOT NULL,
    created_on  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fit_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    shopper_id          TEXT NOT NULL REFERENCES shoppers(id) ON DELETE CASCADE,
    product_id          TEXT NOT NULL,
    worn_size           INTEGER NOT NULL CHECK (worn_size BETWEEN 24 AND 34),
    report              TEXT NOT NULL CHECK (report IN ('tight', 'right', 'loose')),
    created_on          TEXT NOT NULL,
    recommendation_id   TEXT REFERENCES recommendations(id) ON DELETE SET NULL
);
"""

# Created after _upgrade, because a database made before recommendations were stored
# does not have the recommendation_id column until _upgrade adds it.
# SQLite treats NULLs as distinct, so older reports with no recommendation never clash.
ONE_REPORT_PER_RECOMMENDATION = """
CREATE UNIQUE INDEX IF NOT EXISTS fit_reports_one_per_recommendation
    ON fit_reports (recommendation_id)
"""


def connect(path=DEFAULT_DB):
    """Open the database, create the tables if needed and switch on foreign keys.

    The server opens one connection per request, because a SQLite connection
    should not be shared between the threads of ThreadingHTTPServer.
    """
    if str(path) != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # SQLite ignores REFERENCES unless this is on, so ON DELETE CASCADE would silently do nothing.
    conn.execute('PRAGMA foreign_keys = ON')
    # Without this SQLite only marks deleted rows as free space, and their bytes stay readable in the
    # file until something overwrites them. With it, deleted content is overwritten with zeros.
    conn.execute('PRAGMA secure_delete = ON')
    conn.executescript(SCHEMA)
    _upgrade(conn)
    conn.execute(ONE_REPORT_PER_RECOMMENDATION)
    return conn


def _upgrade(conn):
    """Bring a database made by an earlier version up to date, keeping its rows.

    CREATE TABLE IF NOT EXISTS skips a table that already exists, so a new column has to be added here.
    """
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(fit_reports)')}
    if 'recommendation_id' not in columns:
        with conn:
            conn.execute('ALTER TABLE fit_reports ADD COLUMN recommendation_id TEXT '
                         'REFERENCES recommendations(id) ON DELETE SET NULL')


def _today():
    # Only the date is kept, not the time: enough to apply a retention period, less to profile.
    return date.today().isoformat()


def create_shopper(conn):
    """Create a shopper with a random, unguessable ID and return the ID."""
    shopper_id = secrets.token_urlsafe(16)
    with conn:
        conn.execute('INSERT INTO shoppers (id, created_on) VALUES (?, ?)', (shopper_id, _today()))
    return shopper_id


def shopper_exists(conn, shopper_id):
    row = conn.execute('SELECT 1 FROM shoppers WHERE id = ?', (shopper_id,)).fetchone()
    return row is not None


def add_owned_pair(conn, shopper_id, product_id, size, feel):
    with conn:
        cur = conn.execute(
            'INSERT INTO owned_pairs (shopper_id, product_id, size, feel, created_on) VALUES (?, ?, ?, ?, ?)',
            (shopper_id, product_id, size, feel, _today()))
    return cur.lastrowid


def list_wardrobe(conn, shopper_id):
    rows = conn.execute(
        'SELECT id, product_id, size, feel, created_on FROM owned_pairs WHERE shopper_id = ? ORDER BY id',
        (shopper_id,)).fetchall()
    return [dict(r) for r in rows]


def save_recommendation(conn, shopper_id, product_id, belief):
    """Keep the server's belief for one recommendation and return a random ID for it.

    shopper_id may be None when the shopper has not saved a wardrobe.
    The belief is stored as JSON text, for example {"28": 0.15, "29": 0.56, ...}.
    """
    recommendation_id = secrets.token_urlsafe(16)
    with conn:
        conn.execute(
            'INSERT INTO recommendations (id, shopper_id, product_id, belief, created_on) VALUES (?, ?, ?, ?, ?)',
            (recommendation_id, shopper_id, product_id, json.dumps(belief, sort_keys=True), _today()))
    return recommendation_id


def get_recommendation(conn, recommendation_id):
    """Return the stored recommendation with its belief as a dict, or None if there is no such ID."""
    row = conn.execute(
        'SELECT id, shopper_id, product_id, belief, created_on FROM recommendations WHERE id = ?',
        (recommendation_id,)).fetchone()
    if row is None:
        return None
    found = dict(row)
    found['belief'] = json.loads(found['belief'])
    return found


def add_fit_report(conn, shopper_id, product_id, worn_size, report, recommendation_id=None):
    """Store a fit report. A second report for the same recommendation replaces the first.

    Replacing rather than adding means one purchase can only ever count once, so repeating
    a request cannot flood the data the sensor model is relearned from.
    """
    with conn:
        cur = conn.execute(
            'INSERT INTO fit_reports (shopper_id, product_id, worn_size, report, created_on, recommendation_id) '
            'VALUES (?, ?, ?, ?, ?, ?) '
            'ON CONFLICT (recommendation_id) DO UPDATE SET '
            'worn_size = excluded.worn_size, report = excluded.report, created_on = excluded.created_on',
            (shopper_id, product_id, worn_size, report, _today(), recommendation_id))
    return cur.lastrowid


def list_fit_reports(conn, shopper_id):
    rows = conn.execute(
        'SELECT id, product_id, worn_size, report, created_on FROM fit_reports WHERE shopper_id = ? ORDER BY id',
        (shopper_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_shopper(conn, shopper_id):
    """Delete a shopper and, through ON DELETE CASCADE, every pair, report and recommendation they own.

    Returns how many rows were removed from each table, so the caller can prove it worked.
    The counts and the delete run in one transaction, so a row added in between cannot be missed.
    """
    tables = ('owned_pairs', 'fit_reports', 'recommendations')
    with conn:
        # The table names come from the fixed tuple above, never from the request, so the f string is safe.
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t} WHERE shopper_id = ?', (shopper_id,)).fetchone()[0]
                  for t in tables}
        cur = conn.execute('DELETE FROM shoppers WHERE id = ?', (shopper_id,))
    if cur.rowcount == 0:
        return {'shoppers': 0, 'owned_pairs': 0, 'fit_reports': 0, 'recommendations': 0}
    return {'shoppers': cur.rowcount, **counts}


def purge_old_recommendations(conn, today=None, keep_days=RECOMMENDATION_KEEP_DAYS):
    """Delete recommendations older than keep_days and return how many went.

    Applies to every recommendation, with or without a shopper. A fit report that pointed at a
    deleted recommendation keeps its product, size and fit; ON DELETE SET NULL clears only the link.
    created_on is an ISO date (YYYY-MM-DD), so comparing the text compares the dates.
    """
    cutoff = ((today or date.today()) - timedelta(days=keep_days)).isoformat()
    with conn:
        cur = conn.execute('DELETE FROM recommendations WHERE created_on < ?', (cutoff,))
    return cur.rowcount
