"""Storage for the wardrobe and fit history, using SQLite from the Python standard library.

What is stored, and nothing more:
* shoppers: a random pseudonymous ID and the date it was created. No name, email or body data.
* owned_pairs: the jeans a shopper says they own (product, size, how it feels).
* fit_reports: what a shopper said about a pair after delivery (product, size worn, report).

Every query uses ? placeholders, so values are always sent to SQLite as data and are never
pasted into the SQL text. That is what stops SQL injection (OWASP A03). The CHECK constraints
in the schema are a second line of defence if a bad value ever gets past the server's checks.
"""
import secrets
import sqlite3
from datetime import date
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / 'data' / 'fitting_room.db'

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
CREATE TABLE IF NOT EXISTS fit_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shopper_id  TEXT NOT NULL REFERENCES shoppers(id) ON DELETE CASCADE,
    product_id  TEXT NOT NULL,
    worn_size   INTEGER NOT NULL CHECK (worn_size BETWEEN 24 AND 34),
    report      TEXT NOT NULL CHECK (report IN ('tight', 'right', 'loose')),
    created_on  TEXT NOT NULL
);
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
    conn.executescript(SCHEMA)
    return conn


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


def add_fit_report(conn, shopper_id, product_id, worn_size, report):
    with conn:
        cur = conn.execute(
            'INSERT INTO fit_reports (shopper_id, product_id, worn_size, report, created_on) VALUES (?, ?, ?, ?, ?)',
            (shopper_id, product_id, worn_size, report, _today()))
    return cur.lastrowid


def list_fit_reports(conn, shopper_id):
    rows = conn.execute(
        'SELECT id, product_id, worn_size, report, created_on FROM fit_reports WHERE shopper_id = ? ORDER BY id',
        (shopper_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_shopper(conn, shopper_id):
    """Delete a shopper and, through ON DELETE CASCADE, every pair and report they own.

    Returns how many rows were removed from each table, so the caller can prove it worked.
    """
    pairs = conn.execute('SELECT COUNT(*) FROM owned_pairs WHERE shopper_id = ?', (shopper_id,)).fetchone()[0]
    reports = conn.execute('SELECT COUNT(*) FROM fit_reports WHERE shopper_id = ?', (shopper_id,)).fetchone()[0]
    with conn:
        cur = conn.execute('DELETE FROM shoppers WHERE id = ?', (shopper_id,))
    if cur.rowcount == 0:
        return {'shoppers': 0, 'owned_pairs': 0, 'fit_reports': 0}
    return {'shoppers': cur.rowcount, 'owned_pairs': pairs, 'fit_reports': reports}
