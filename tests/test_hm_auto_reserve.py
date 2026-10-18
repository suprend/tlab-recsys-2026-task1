"""Only tiny synthetic DuckDBs/cohorts; never open the real H&M source."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from scripts import hm_auto_reserve as reserve


def customer(i):
    return hashlib.sha256(f'fixture-user-{i}'.encode()).hexdigest()


def ordered(values, salt):
    return sorted(values, key=lambda value: (hashlib.sha256((value+':'+salt).encode()).hexdigest(), value))


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hm-auto-reserve-fixture-')
        self.root = Path(self.temp.name)
        self.con = duckdb.connect()
        self.con.execute('SET threads=2')
        self.con.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR)')
        self.old_count = 3
        self.new_count = 4
        self.ids = [customer(i) for i in range(20)]
        self.rows = [('2020-08-01', c) for c in self.ids]
        self.rows += [('2020-09-16', customer(901)), ('2020-09-22', customer(902))]
        self.con.executemany('INSERT INTO transactions VALUES (?,?)', self.rows)
        self.cache_paths = self.write_caches(self.con, self.root/'old-users')

    def tearDown(self):
        self.con.close()
        self.temp.cleanup()

    def write_caches(self, con, root):
        result = {}
        for anchor in reserve.CACHE_ANCHORS:
            cutoff = date.fromisoformat(anchor)
            users = {c for day,c in self.rows if cutoff-timedelta(days=90) <= date.fromisoformat(day) < cutoff}
            selected = ordered(users, '2026')[:self.old_count]
            path = root/anchor/'users.parquet'
            path.parent.mkdir(parents=True)
            con.execute('CREATE OR REPLACE TEMP TABLE fixture_users(customer_id VARCHAR)')
            con.executemany('INSERT INTO fixture_users VALUES (?)', [(c,) for c in selected])
            con.execute('COPY fixture_users TO ? (FORMAT PARQUET)', [str(path)])
            result[anchor] = path
        # These corrupt files prove no target/frame reads are needed.
        (root/'targets.parquet').write_text('not a parquet', encoding='utf-8')
        (root/'frame.parquet').write_text('not a parquet', encoding='utf-8')
        return result

    def build(self, con=None, paths=None):
        return reserve.construct_reservation(con or self.con, paths or self.cache_paths,
                                             old_users=self.old_count, new_users=self.new_count)

    def reserved(self, con=None):
        return (con or self.con).execute('SELECT customer_id,cohort_hash,reservation_rank '
                                        'FROM hm_auto_reserved ORDER BY reservation_rank').fetchall()

    def test_exact_hash_order_exclusion_and_repeatability(self):
        report = self.build()
        excluded = set(ordered(self.ids, '2026')[:3])
        expected = ordered(set(self.ids)-excluded, reserve.SALT)[:4]
        self.assertEqual([row[0] for row in self.reserved()], expected)
        self.assertEqual([row[2] for row in self.reserved()], [1,2,3,4])
        self.assertEqual(report['excluded_users'], 3)
        self.assertEqual(report['remaining_history_eligible_users'], 17)
        self.assertEqual(report['overlap_users'], 0)
        self.assertEqual(len(report['actual_old_cohorts']), 6)
        self.assertTrue(all(entry['covered_by_reconstruction'] for entry in report['actual_old_cohorts']))
        second = duckdb.connect()
        try:
            second.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR)')
            second.executemany('INSERT INTO transactions VALUES (?,?)', list(reversed(self.rows)))
            other = self.build(second)
            self.assertEqual(self.reserved(), self.reserved(second))
            self.assertEqual(report['reserved_ordered_ids_sha256'], other['reserved_ordered_ids_sha256'])
            self.assertEqual(report['excluded_ordered_ids_sha256'], other['excluded_ordered_ids_sha256'])
        finally:
            second.close()

    def test_future_transactions_and_outcomes_cannot_affect_reserved_ids(self):
        self.build()
        first = self.reserved()
        future = duckdb.connect()
        try:
            # Future-only transactions include existing and novel users; labels
            # are arbitrary/unrelated and are not part of the source projection.
            future.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,label BOOLEAN)')
            future.executemany('INSERT INTO transactions VALUES (?,?,?)',
                               [(day,c,True) for day,c in self.rows if day < '2020-09-16']
                               + [('2020-09-16', c,False) for c in self.ids]
                               + [('2020-09-17',customer(i),True) for i in range(100,130)])
            self.build(future)
            self.assertEqual(first, self.reserved(future))
            self.assertEqual(future.execute('SELECT max(t_dat) FROM hm_auto_history').fetchone()[0], date(2020,8,1))
        finally:
            future.close()

    def test_exact_window_boundaries_and_aug05_pilot_exclusion(self):
        # A user seen only on the earliest included day belongs to Aug05 old Q,
        # and remains excluded even if absent from Sep16 eligibility.
        self.con.execute('DELETE FROM transactions')
        early = ordered([customer(i) for i in range(50,90)], '2026')[:3]
        self.con.executemany('INSERT INTO transactions VALUES (?,?)',
                             [('2020-05-07',c) for c in early]
                             + [('2020-05-06',customer(900))]
                             + [('2020-08-10',c) for c in self.ids])
        # Reconstruct synthetic cache rows per anchor independently in Python.
        self.rows = [('2020-05-07',c) for c in early] + [('2020-08-10',c) for c in self.ids]
        paths = self.write_caches(self.con, self.root/'boundary-old-users')
        self.build(paths=paths)
        actual = {row[0] for row in self.con.execute('SELECT customer_id FROM hm_auto_excluded').fetchall()}
        self.assertTrue(set(early) <= actual)
        self.assertNotIn(customer(900), actual)
        self.assertTrue(all(row[0] not in set(early) for row in self.reserved()))

    def test_actual_old_queries_outside_union_fail_closed(self):
        path = self.cache_paths[reserve.CACHE_ANCHORS[0]]
        self.con.execute('CREATE OR REPLACE TEMP TABLE invalid_users(customer_id VARCHAR)')
        self.con.executemany('INSERT INTO invalid_users VALUES (?)', [(customer(700+i),) for i in range(3)])
        self.con.execute('COPY invalid_users TO ? (FORMAT PARQUET)', [str(path)])
        with self.assertRaisesRegex(ValueError, 'not covered'):
            self.build()

    def test_duplicate_cached_queries_and_non_users_file_rejected(self):
        path = self.cache_paths[reserve.CACHE_ANCHORS[0]]
        self.con.execute('CREATE OR REPLACE TEMP TABLE duplicate_users AS SELECT ?::VARCHAR customer_id', [self.ids[0]])
        self.con.execute('COPY (SELECT * FROM duplicate_users CROSS JOIN range(3)) TO ? (FORMAT PARQUET)', [str(path)])
        with self.assertRaisesRegex(ValueError, 'duplicates'):
            self.build()
        paths = dict(self.cache_paths)
        paths[reserve.CACHE_ANCHORS[0]] = self.root/'frame.parquet'
        other = duckdb.connect()
        try:
            other.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR)')
            other.executemany('INSERT INTO transactions VALUES (?,?)', self.rows)
            with self.assertRaisesRegex(ValueError, 'Only old users'):
                self.build(other, paths)
        finally:
            other.close()

    def test_insufficient_unused_population_is_error(self):
        with self.assertRaisesRegex(ValueError, 'Insufficient unused'):
            reserve.construct_reservation(self.con, self.cache_paths, old_users=3, new_users=18)

    def test_production_config_bytes_are_pinned(self):
        original = reserve.ROOT/'configs'/'datasets'/'hm-auto-v2.json'
        reserve.load_config(original)
        altered = self.root/'changed-config.json'
        altered.write_bytes(original.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError, 'frozen v2 config'):
            reserve.load_config(altered)

    def test_production_entrypoint_tiny_db_export_and_output_exclusivity(self):
        database = self.root/'tiny.duckdb'
        disk = duckdb.connect(str(database))
        disk.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR)')
        disk.executemany('INSERT INTO transactions VALUES (?,?)', self.rows)
        disk.close()
        output = self.root/'artifacts'/'hm-auto-v2'/'reservation'
        config = reserve.ROOT/'configs'/'datasets'/'hm-auto-v2.json'
        with patch.object(reserve, 'ROOT', self.root), \
             patch.object(reserve, 'DATABASE_BYTES', database.stat().st_size), \
             patch.object(reserve, 'DATABASE_SHA256', reserve.sha256_file(database)), \
             patch.object(reserve, 'OLD_USERS', 3), patch.object(reserve, 'NEW_USERS', 4), \
             patch.object(reserve, 'cached_user_paths', return_value=self.cache_paths):
            report = reserve.reserve(database, output, config=config, wall_seconds=30)
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(report['counts_history_only']['reserved_users'], 4)
            self.assertTrue(report['database']['opened_read_only'])
            self.assertTrue(report['no_test_targets_or_features'])
            self.assertEqual(set(report['files']), {'reserved-users.parquet','excluded-users.parquet'})
            for name, info in report['files'].items():
                self.assertEqual(reserve.sha256_file(output/name), info['sha256'])
            manifest_bytes = (output/'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError):
                reserve.reserve(database, output, config=config)
            self.assertEqual((output/'manifest.json').read_bytes(), manifest_bytes)
            with self.assertRaisesRegex(ValueError, 'new child'):
                reserve.reserve(database, self.root/'outside', config=config)
            self.assertFalse((self.root/'outside').exists())

    def test_production_database_pin_rejects_before_output_creation(self):
        fake = self.root/'wrong.duckdb'
        fake.write_bytes(b'not the original database')
        output = self.root/'artifacts'/'hm-auto-v2'/'bad-source'
        config = reserve.ROOT/'configs'/'datasets'/'hm-auto-v2.json'
        with patch.object(reserve, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'pinned typed database'):
                reserve.reserve(fake, output, config=config)
        self.assertFalse(output.exists())

    def test_deadline_and_disk_preflight_fail_closed(self):
        for value in (0, -1, 1801):
            with self.assertRaises(ValueError):
                reserve.Deadline(value)
        deadline = reserve.Deadline(10)
        deadline.expires = 0
        with self.assertRaises(TimeoutError):
            deadline.check()
        database = self.root/'disk-check.duckdb'
        database.write_bytes(b'fixture')
        config = reserve.ROOT/'configs'/'datasets'/'hm-auto-v2.json'
        output = self.root/'artifacts'/'hm-auto-v2'/'low-space'
        with patch.object(reserve, 'ROOT', self.root), \
             patch.object(reserve, 'DATABASE_BYTES', 7), \
             patch.object(reserve, 'DATABASE_SHA256', reserve.sha256_file(database)), \
             patch.object(reserve.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 1})()):
            with self.assertRaisesRegex(OSError, '10GiB'):
                reserve.reserve(database, output, config=config)
        failure = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(failure['status'], 'failed')
        self.assertFalse((output/'reserved-users.parquet').exists())


if __name__ == '__main__':
    unittest.main()
