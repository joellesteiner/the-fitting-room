import sqlite3
import unittest

import storage

INJECTION = "x' OR '1'='1"


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
        for table in ('shoppers', 'owned_pairs', 'fit_reports'):
            columns |= {row['name'] for row in self.conn.execute(f'PRAGMA table_info({table})')}
        for banned in ('height', 'weight', 'waist_cm', 'hip_cm', 'name', 'email', 'age'):
            self.assertNotIn(banned, columns)

    # Delete
    def test_delete_removes_shopper_pairs_and_reports(self):
        s = storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, s, '501', 28, 0)
        storage.add_fit_report(self.conn, s, '501', 29, 'right')
        removed = storage.delete_shopper(self.conn, s)
        self.assertEqual(removed, {'shoppers': 1, 'owned_pairs': 1, 'fit_reports': 1})
        self.assertFalse(storage.shopper_exists(self.conn, s))
        for table in ('owned_pairs', 'fit_reports'):
            count = self.conn.execute(f'SELECT COUNT(*) FROM {table} WHERE shopper_id = ?', (s,)).fetchone()[0]
            self.assertEqual(count, 0)

    def test_delete_leaves_other_shoppers_alone(self):
        a, b = storage.create_shopper(self.conn), storage.create_shopper(self.conn)
        storage.add_owned_pair(self.conn, b, '501', 30, 0)
        storage.delete_shopper(self.conn, a)
        self.assertEqual(len(storage.list_wardrobe(self.conn, b)), 1)

    def test_delete_unknown_shopper_removes_nothing(self):
        self.assertEqual(storage.delete_shopper(self.conn, 'nobody'), {'shoppers': 0, 'owned_pairs': 0, 'fit_reports': 0})

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
