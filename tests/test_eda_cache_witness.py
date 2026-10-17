"""Legacy EDA cache controls: temporary two-event gzip only; no models or real data."""
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import duckdb

from scripts import eda as m


CSV = (
    'event_time,event_type,product_id,category_id,category_code,brand,price,user_id,user_session\n'
    '2019-10-01 00:00:00 UTC,view,1,9,electronics.phone,acme,1.00,7,s\n'
    '2019-10-02 00:00:00 UTC,purchase,2,9,electronics.phone,acme,2.00,8,t\n'
)


class EDACacheWitness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'two-events.csv.gz'
        self.db = self.root / 'processed' / 'events.duckdb'
        self.manifest = self.source.with_name('two-events.download.json')
        self.write_source(CSV)

    def write_source(self, csv):
        body = gzip.compress(csv.encode('utf-8'), mtime=0)
        self.source.write_bytes(body)
        self.manifest.write_text(json.dumps({
            'sha256': hashlib.sha256(body).hexdigest(), 'compressed_bytes': len(body),
        }), encoding='utf-8')

    def fresh(self):
        result = m.ingest(self.source, self.db)
        self.assertEqual(result['rows'], 2)
        self.assertTrue(m.cache_witness_path(self.db).is_file())
        return result

    def mutate(self, sql, expected_rows):
        con = duckdb.connect(str(self.db))
        try:
            con.execute(sql)
            self.assertEqual(con.execute('SELECT count(*) FROM events').fetchone()[0], expected_rows)
            con.execute('CHECKPOINT')
        finally:
            con.close()
        self.assertFalse(self.db.with_name(self.db.name + '.wal').exists())

    def reject_without_native_open(self, message):
        before = self.db.read_bytes()
        with patch.object(m.duckdb, 'connect', side_effect=AssertionError('must reject before native open')):
            with self.assertRaisesRegex(ValueError, message):
                m.ingest(self.source, self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_fresh_then_unchanged_reuse_preserves_bytes_and_opens_read_only(self):
        first = self.fresh()
        before = self.db.read_bytes()
        proof = m.cache_witness_path(self.db).read_bytes()
        with patch.object(m, 'connect', wraps=m.connect) as opening:
            self.assertEqual(m.ingest(self.source, self.db), first)
        self.assertTrue(opening.call_args.kwargs['read_only'])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(m.cache_witness_path(self.db).read_bytes(), proof)
        witness = json.loads(proof)
        self.assertEqual(witness['database_sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(witness['database_bytes'], len(before))

    def test_duplicate_append_with_unchanged_source_metadata_rejects(self):
        self.fresh()
        proof = m.cache_witness_path(self.db).read_bytes()
        self.mutate('INSERT INTO events SELECT * FROM events', 4)
        self.reject_without_native_open('recorded content witness')
        self.assertEqual(m.cache_witness_path(self.db).read_bytes(), proof)

    def test_same_count_value_edit_with_unchanged_source_metadata_rejects(self):
        self.fresh()
        self.mutate("UPDATE events SET brand='changed' WHERE product_id=1", 2)
        self.reject_without_native_open('recorded content witness')

    def test_missing_legacy_witness_rejects_and_preserves_database(self):
        self.fresh()
        m.cache_witness_path(self.db).unlink()
        self.reject_without_native_open('choose a new --db path or independently verify')
        self.assertFalse(m.cache_witness_path(self.db).exists())

    def test_bad_archive_manifest_hash_still_rejects_before_database_open(self):
        self.fresh()
        self.manifest.write_text(json.dumps({
            'sha256': '0' * 64, 'compressed_bytes': self.source.stat().st_size,
        }), encoding='utf-8')
        self.reject_without_native_open('verified download manifest')

    def test_witness_source_sha_mismatch_rejects(self):
        self.fresh()
        self.write_source(CSV.replace('acme', 'other'))
        self.reject_without_native_open('belongs to another source')

    def test_unexpected_even_empty_WAL_rejects_without_recovery(self):
        self.fresh()
        wal = self.db.with_name(self.db.name + '.wal')
        wal.write_bytes(b'')
        self.reject_without_native_open('unexpected WAL')
        self.assertEqual(wal.read_bytes(), b'')

    def test_invalid_witness_is_not_automatically_refreshed(self):
        self.fresh()
        path = m.cache_witness_path(self.db)
        for value in [[], {'format': 'old'}, {'format': m.CACHE_WITNESS_FORMAT,
                      'source_sha256': '0' * 64, 'database_sha256': '0' * 64,
                      'database_bytes': True}]:
            with self.subTest(witness=value):
                proof = json.dumps(value).encode('utf-8')
                path.write_bytes(proof)
                self.reject_without_native_open('invalid content witness')
                self.assertEqual(path.read_bytes(), proof)

    def test_direct_read_only_open_also_rejects_database_drift(self):
        self.fresh()
        self.mutate("UPDATE events SET price=3.00 WHERE product_id=1", 2)
        with patch.object(m.duckdb, 'connect', side_effect=AssertionError('must reject before native open')):
            with self.assertRaisesRegex(ValueError, 'recorded content witness'):
                m.connect(self.db, read_only=True)

    def test_writable_helper_does_not_adopt_an_existing_database(self):
        self.fresh()
        before = self.db.read_bytes()
        with patch.object(m.duckdb, 'connect', side_effect=AssertionError('must reject before native open')):
            with self.assertRaisesRegex(ValueError, 'fresh path for writable ingest'):
                m.connect(self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_mutation_between_precheck_and_native_open_rejects_before_query(self):
        self.fresh()
        actual_connect = duckdb.connect
        opened = []

        def opening(*args, **kwargs):
            con = actual_connect(str(self.db))
            try:
                con.execute("UPDATE events SET brand='late change' WHERE product_id=1")
                self.assertEqual(con.execute('SELECT count(*) FROM events').fetchone()[0], 2)
                con.execute('CHECKPOINT')
            finally:
                con.close()
            connection = Mock(wraps=actual_connect(*args, **kwargs))
            connection.execute.side_effect = AssertionError('must reject before any query')
            opened.append(connection)
            return connection

        with patch.object(m.duckdb, 'connect', side_effect=opening):
            with self.assertRaisesRegex(ValueError, 'recorded content witness'):
                m.connect(self.db, read_only=True)
        self.assertEqual(len(opened), 1)
        opened[0].execute.assert_not_called()
        opened[0].close.assert_called_once()

    def test_fresh_strict_parser_failure_does_not_seal_or_adopt_partial_database(self):
        self.write_source(CSV.replace('1.00', 'not-a-decimal', 1))
        with self.assertRaises(duckdb.Error):
            m.ingest(self.source, self.db)
        self.assertTrue(self.db.is_file())
        self.assertFalse(m.cache_witness_path(self.db).exists())
        self.reject_without_native_open('no readable content witness')

    def test_orphan_witness_does_not_allow_fresh_adoption(self):
        self.db.parent.mkdir()
        path = m.cache_witness_path(self.db)
        path.write_text('{}', encoding='utf-8')
        with patch.object(m.duckdb, 'connect', side_effect=AssertionError('must not create database')):
            with self.assertRaisesRegex(ValueError, 'orphaned witness or WAL'):
                m.ingest(self.source, self.db)
        self.assertFalse(self.db.exists())
        self.assertEqual(path.read_text(encoding='utf-8'), '{}')


if __name__ == '__main__':
    unittest.main()
