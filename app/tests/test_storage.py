import sqlite3
import tempfile
import unittest
from pathlib import Path

import storage

INJECTION = "x' OR '1'='1"
BELIEF = {'28': 0.2, '29': 0.5, '30': 0.3}


class Storage(unittest.TestCase):
    def setUp(self):
        # A fresh in memory database for every test, so tests never share data.
        self.conn = storage.connect(':memory:')

    def tearDown(self):
        self.conn.close()

    # Create and read
    def test_shopper_id_is_random_and_long(self):
        a, b = storage.create_shopper(self.conn), storage.create_shopper(self.conn)
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 22)
        self.assertTrue(storage.shopper_exists(self.conn, a))

    def test_add_and_list_wardrobe(self):
        s = storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, s, '501', 28, -2)
        pairs = storage.list_wardrobe(self.conn, s)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]['product_id'], pairs[0]['size'], pairs[0]['feel']), ('501', 28, -2))

    def test_add_and_list_fit_reports(self):
        s = storage.create_shopper(self.conn)
        storage.add_fit_report(self.conn, s, '501', 29, 'tight')
        reports = storage.list_fit_reports(self.conn, s)
        self.assertEqual([(r['product_id'], r['worn_size'], r['report']) for r in reports], [('501', 29, 'tight')])

    def test_shoppers_only_see_their_own_wardrobe(self):
        a, b = storage.create_shopper(self.conn), storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, a, '501', 28, 0)
        self.assertEqual(storage.list_wardrobe(self.conn, b), [])

    def test_only_date_is_stored_not_time(self):
        s = storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, s, '501', 28, 0)
        self.assertRegex(storage.list_wardrobe(self.conn, s)[0]['created_on'], r'^\d{4}-\d{2}-\d{2}$')

    def test_no_body_data_columns(self):
        columns = set()
        for table in ('shoppers', 'owned_pairs', 'fit_reports', 'recommendations'):
            columns |= {row['name'] for row in self.conn.execute(f'PRAGMA table_info({table})')}
        for banned in ('height', 'weight', 'waist_cm', 'hip_cm', 'name', 'email', 'age'):
            self.assertNotIn(banned, columns)

    # Delete
    def test_delete_removes_shopper_pairs_and_reports(self):
        s = storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, s, '501', 28, 0)
        rec = storage.save_recommendation(self.conn, s, '501', BELIEF)
        storage.add_fit_report(self.conn, s, '501', 29, 'right', rec)
        removed = storage.delete_shopper(self.conn, s)
        self.assertEqual(removed, {'shoppers': 1, 'owned_pairs': 1, 'fit_reports': 1, 'recommendations': 1})
        self.assertFalse(storage.shopper_exists(self.conn, s))
        self.assertIsNone(storage.get_recommendation(self.conn, rec))
        for table in ('owned_pairs', 'fit_reports', 'recommendations'):
            count = self.conn.execute(f'SELECT COUNT(*) FROM {table} WHERE shopper_id = ?', (s,)).fetchone()[0]
            self.assertEqual(count, 0)

    def test_delete_leaves_other_shoppers_alone(self):
        a, b = storage.create_shopper(self.conn), storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, b, '501', 30, 0)
        storage.delete_shopper(self.conn, a)
        self.assertEqual(len(storage.list_wardrobe(self.conn, b)), 1)

    def test_delete_unknown_shopper_removes_nothing(self):
        self.assertEqual(storage.delete_shopper(self.conn, 'nobody'), {'shoppers': 0, 'owned_pairs': 0, 'fit_reports': 0,
                                                                       'recommendations': 0})

    # Recommendations: the server keeps its own copy of the belief
    def test_recommendation_round_trip(self):
        rec = storage.save_recommendation(self.conn, None, '501', BELIEF)
        found = storage.get_recommendation(self.conn, rec)
        self.assertEqual((found['shopper_id'], found['product_id'], found['belief']), (None, '501', BELIEF))

    def test_recommendation_id_is_random_and_long(self):
        a = storage.save_recommendation(self.conn, None, '501', BELIEF)
        b = storage.save_recommendation(self.conn, None, '501', BELIEF)
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 22)

    def test_unknown_recommendation_is_none(self):
        self.assertIsNone(storage.get_recommendation(self.conn, 'nobody'))
        self.assertIsNone(storage.get_recommendation(self.conn, INJECTION))

    def test_recommendation_for_unknown_shopper_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            storage.save_recommendation(self.conn, 'nobody', '501', BELIEF)

    def test_second_report_for_a_recommendation_replaces_the_first(self):
        s = storage.create_shopper(self.conn)
        rec = storage.save_recommendation(self.conn, s, '501', BELIEF)
        for _ in range(3):
            storage.add_fit_report(self.conn, s, '501', 29, 'tight', rec)
        storage.add_fit_report(self.conn, s, '501', 30, 'right', rec)
        reports = storage.list_fit_reports(self.conn, s)
        self.assertEqual([(r['worn_size'], r['report']) for r in reports], [(30, 'right')])

    def test_reports_for_different_recommendations_are_kept_apart(self):
        s = storage.create_shopper(self.conn)
        for _ in range(2):
            rec = storage.save_recommendation(self.conn, s, '501', BELIEF)
            storage.add_fit_report(self.conn, s, '501', 29, 'tight', rec)
        self.assertEqual(len(storage.list_fit_reports(self.conn, s)), 2)

    def test_database_from_before_recommendations_is_upgraded(self):
        # Build a database with the earlier fit_reports table, then open it with the current code.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'old.db'
            old = sqlite3.connect(str(path))
            old.executescript("""
                CREATE TABLE shoppers (id TEXT PRIMARY KEY, created_on TEXT NOT NULL);
                CREATE TABLE fit_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, shopper_id TEXT NOT NULL,
                    product_id TEXT NOT NULL, worn_size INTEGER NOT NULL, report TEXT NOT NULL, created_on TEXT NOT NULL);
                INSERT INTO shoppers VALUES ('old', '2026-11-19');
                INSERT INTO fit_reports (shopper_id, product_id, worn_size, report, created_on)
                    VALUES ('old', '501', 29, 'tight', '2026-11-19');
            """)
            old.close()
            conn = storage.connect(path)
            try:
                self.assertEqual(len(storage.list_fit_reports(conn, 'old')), 1)    # existing row kept
                rec = storage.save_recommendation(conn, 'old', '501', BELIEF)
                storage.add_fit_report(conn, 'old', '501', 30, 'right', rec)
                storage.add_fit_report(conn, 'old', '501', 30, 'loose', rec)
                self.assertEqual(len(storage.list_fit_reports(conn, 'old')), 2)    # one per recommendation
            finally:
                conn.close()

    # Injection: these would leak or wipe other shoppers' data if SQL were built by pasting strings.
    def test_injection_in_shopper_id_does_not_read_other_wardrobes(self):
        s = storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, s, '501', 28, 0)
        self.assertEqual(storage.list_wardrobe(self.conn, INJECTION), [])

    def test_injection_in_shopper_id_does_not_delete_everyone(self):
        s = storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, s, '501', 28, 0)
        storage.delete_shopper(self.conn, INJECTION)
        self.assertTrue(storage.shopper_exists(self.conn, s))
        self.assertEqual(len(storage.list_wardrobe(self.conn, s)), 1)

    def test_injection_text_is_stored_as_plain_data(self):
        s = storage.create_shopper(self.conn)
        payload = "501'); DROP TABLE owned_pairs; --"
        storage.add_owned_pair(self.conn, s, payload, 28, 0)
        self.assertEqual(storage.list_wardrobe(self.conn, s)[0]['product_id'], payload)   # table still exists

    def test_injection_text_in_belief_is_stored_as_plain_data(self):
        rec = storage.save_recommendation(self.conn, None, '501', {INJECTION: 1.0})
        self.assertEqual(storage.get_recommendation(self.conn, rec)['belief'], {INJECTION: 1.0})

    # Schema constraints are a second line of defence
    def test_schema_rejects_out_of_range_size(self):
        s = storage.create_shopper(self.conn)
        with self.assertRaises(sqlite3.IntegrityError):
            storage.add_owned_pair(self.conn, s, '501', 99, 0)

    def test_schema_rejects_unknown_report(self):
        s = storage.create_shopper(self.conn)
        with self.assertRaises(sqlite3.IntegrityError):
            storage.add_fit_report(self.conn, s, '501', 29, 'massive')

    def test_schema_rejects_pair_for_unknown_shopper(self):
        with self.assertRaises(sqlite3.IntegrityError):
            storage.add_owned_pair(self.conn, 'nobody', '501', 28, 0)


if __name__ == '__main__':
    unittest.main()
