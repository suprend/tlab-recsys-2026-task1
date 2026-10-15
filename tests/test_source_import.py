"""Typed9 import kernel only, synthetic<=4-row CSV variants; no actual archive."""
from copy import deepcopy
import csv,gzip,hashlib,io,json,tempfile,unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import duckdb
from scripts import source_import as m

BIG=2**60
ROWS=[['2019-10-01 00:00:00 UTC','view',str(BIG),'9','electronics.phone','acme, labs','0',str(BIG),''],
      ['2019-10-01 00:00:00 UTC','view',str(BIG),'9','electronics.phone','acme, labs','0',str(BIG),''],
      ['2019-10-01 00:00:00 UTC','cart',str(BIG+1),'','','NULL','9999999999.99',str(BIG),'s'],
      ['2019-10-31 23:59:59 UTC','purchase','','0','electronics.phone',' spaced ','-1.20','','']]


def csv_bytes(rows,header=None):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(list(m.FIELDS) if header is None else header);writer.writerows(rows);return stream.getvalue().encode('utf-8')


class ImportKernel(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.archive=self.root/'local source.csv.gz';self.work=self.root/'new import';self.calls=0
        self.fixture(csv_bytes(ROWS),rows=4)
    def fixture(self,raw,*,rows,compressed=None):
        body=gzip.compress(raw,mtime=0) if compressed is None else compressed;self.archive.write_bytes(body)
        self.profile=deepcopy(m.PRODUCTION_PROFILE);self.profile.update(scope='synthetic_typed9_import_fixture',compressed_sha256=hashlib.sha256(body).hexdigest(),compressed_bytes=len(body),uncompressed_bytes=len(raw),expected_rows=rows)
    def check(self):self.calls+=1
    def run_import(self,check=None):return m.import_archive(self.archive,self.work,self.profile,check=self.check if check is None else check)
    def failed_before_native(self):
        self.assertTrue((self.work/'import.consumed.json').exists());self.assertTrue((self.work/'report.failed.json').exists());self.assertFalse((self.work/'events.duckdb').exists())
    def test_exact_typed9_bigint_decimal_NULL_quoted_comma_peers_and_raw_duplicates(self):
        result=self.run_import();self.assertEqual(result['summary']['rows'],4);self.assertEqual(result['summary']['actions'],dict(view=2,cart=1,purchase=1))
        self.assertEqual(result['summary']['nulls']['user_session'],3);self.assertTrue(result['csv']['all_gzip_members_EOF_CRC_ISIZE_checked']);self.assertFalse(result['labels_created'])
        con=duckdb.connect(result['database']['path'],read_only=True)
        try:
            self.assertEqual([tuple(r[:2]) for r in con.execute('DESCRIBE events').fetchall()],list(zip(m.FIELDS,m.TYPES)))
            rows=con.execute('SELECT product_id,brand,price FROM events ORDER BY product_id NULLS LAST').fetchall()
            self.assertEqual(rows,[(BIG,'acme, labs',Decimal('0.00')),(BIG,'acme, labs',Decimal('0.00')),(BIG+1,'NULL',Decimal('9999999999.99')),(None,' spaced ',Decimal('-1.20'))])
        finally:con.close()
        self.assertEqual(m.file_hash(self.work/'events.duckdb',self.check),(result['database']['sha256'],result['database']['bytes']));self.assertGreater(self.calls,10)
        self.assertTrue(result['external_lifetime_acceptance_required'])
    def test_header_only_empty_source_keeps_exact_types_and_zero_counts(self):
        self.fixture(csv_bytes([]),rows=0);result=self.run_import();self.assertEqual(result['summary']['rows'],0);self.assertIsNone(result['summary']['minimum_time'])
    def test_wrong_compressed_sha_stops_before_DB(self):
        self.profile['compressed_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'compressed SHA/size'):self.run_import()
        self.failed_before_native()
    def test_wrong_full_uncompressed_size_is_not_trailer_size_shortcut(self):
        self.profile['uncompressed_bytes']+=2**32
        with self.assertRaisesRegex(ValueError,'Full uncompressed stream'):self.run_import()
        self.failed_before_native()
    def test_bad_CRC_with_matching_synthetic_digest_reaches_integrity_gate(self):
        raw=csv_bytes(ROWS);body=bytearray(gzip.compress(raw,mtime=0));body[-8]^=1;self.fixture(raw,rows=4,compressed=bytes(body))
        with self.assertRaises(gzip.BadGzipFile):self.run_import()
        self.failed_before_native()
    def test_truncated_gzip_with_matching_fixture_digest_rejects(self):
        raw=csv_bytes(ROWS);self.fixture(raw,rows=4,compressed=gzip.compress(raw,mtime=0)[:-3])
        with self.assertRaises(EOFError):self.run_import()
        self.failed_before_native()
    def test_reordered_same_type_ID_header_rejects_before_DB(self):
        header=list(m.FIELDS);header[2],header[7]=header[7],header[2];self.fixture(csv_bytes(ROWS,header),rows=4)
        with self.assertRaisesRegex(ValueError,'ordered CSV header'):self.run_import()
        self.failed_before_native()
    def test_row_padding_or_extra_fields_are_not_silently_accepted(self):
        rows=deepcopy(ROWS);rows[0].pop();self.fixture(csv_bytes(rows),rows=4)
        with self.assertRaisesRegex(ValueError,'nine CSV fields'):self.run_import()
        self.failed_before_native()
    def test_fractional_exponent_overflow_ID_and_price_rounding_reject(self):
        for field,token in [(2,'1.0'),(2,'1e3'),(2,str(2**63)),(6,'1.001'),(6,'1e2'),(6,'10000000000.00')]:
            row=list(ROWS[0]);row[field]=token
            with self.subTest(field=field,token=token),self.assertRaises(ValueError):m.parse_row(row,self.profile)
    def test_literal_UTC_calendar_end_unknown_action_and_required_NULL_reject(self):
        for field,token in [(0,'2019-10-01T00:00:00Z'),(0,'2019-10-01 00:00:00.5 UTC'),(0,'2019-11-01 00:00:00 UTC'),(0,'2019-02-30 00:00:00 UTC'),(1,'remove_cart'),(1,'')]:
            row=list(ROWS[0]);row[field]=token
            with self.subTest(field=field,token=token),self.assertRaises(ValueError):m.parse_row(row,self.profile)
    def test_nullable_keys_remain_NULL_and_zero_price_remains_zero(self):
        row=list(ROWS[0]);row[2]=row[3]=row[7]='';parsed=m.parse_row(row,self.profile)
        self.assertIsNone(parsed[2]);self.assertIsNone(parsed[3]);self.assertIsNone(parsed[7]);self.assertEqual(parsed[6],Decimal(0))
    def test_existing_work_DB_with_plausible_metadata_is_never_reused(self):
        self.work.mkdir();database=self.work/'events.duckdb';database.write_bytes(b'changed events old metadata')
        with self.assertRaisesRegex(ValueError,'exclusive import'):self.run_import()
        self.assertEqual(database.read_bytes(),b'changed events old metadata');self.assertFalse((self.work/'import.consumed.json').exists())
    def test_changed_original_archive_after_snapshot_preserves_failure_and_partial_DB(self):
        changed=False
        def check():
            nonlocal changed
            self.check()
            if (self.work/'source.csv').exists() and not changed:self.archive.write_bytes(b'changed source');changed=True
        with self.assertRaisesRegex(ValueError,'archive/owned snapshot'):self.run_import(check)
        self.assertTrue(changed);self.assertTrue((self.work/'report.failed.json').exists())
    def test_cleanup_failure_preserves_primary_native_error(self):
        class Broken:
            def execute(self,*args):raise RuntimeError('primary native failure')
            def close(self):raise OSError('secondary close failure')
        with patch.object(duckdb,'connect',return_value=Broken()),self.assertRaisesRegex(RuntimeError,'primary native failure') as caught:self.run_import()
        self.assertIn('OSError',str(caught.exception.__notes__));self.assertTrue((self.work/'report.failed.json').exists())
    def test_post_persistence_DB_change_cannot_return_success(self):
        changed=False
        def check():
            nonlocal changed
            self.check()
            if (self.work/'import-evidence.json').exists() and not changed:
                with (self.work/'events.duckdb').open('ab') as stream:stream.write(b'late mutation')
                changed=True
        with self.assertRaisesRegex(ValueError,'DB changed during evidence'):self.run_import(check)
        self.assertTrue(changed);self.assertTrue((self.work/'report.failed.json').exists())
    def test_wrong_raw_bag_row_count_rejects_before_DB(self):
        self.profile['expected_rows']=3
        with self.assertRaisesRegex(ValueError,'raw-bag row count'):self.run_import()
        self.failed_before_native()
    def test_production_profile_cannot_reseal_synthetic_source_or_bool_counts(self):
        altered=deepcopy(m.PRODUCTION_PROFILE);altered['compressed_sha256']=self.profile['compressed_sha256']
        with self.assertRaisesRegex(ValueError,'may not be resealed'):m.validate_profile(altered)
        altered=deepcopy(self.profile);altered['expected_rows']=True
        with self.assertRaises(ValueError):m.validate_profile(altered)
    def test_wrong_compressed_byte_count_stops_before_DB(self):
        self.profile['compressed_bytes']+=1
        with self.assertRaisesRegex(ValueError,'compressed SHA/size'):self.run_import()
        self.failed_before_native()
    def test_invalid_UTF8_rejects_before_native_import(self):
        self.fixture(csv_bytes(ROWS).replace(b'acme, labs',b'\xff',1),rows=4)
        with self.assertRaises(UnicodeDecodeError):self.run_import()
        self.failed_before_native()
    def test_duplicate_header_rejects_before_DB(self):
        header=list(m.FIELDS);header[7]=header[2];self.fixture(csv_bytes(ROWS,header),rows=4)
        with self.assertRaisesRegex(ValueError,'ordered CSV header'):self.run_import()
        self.failed_before_native()
    def test_unclosed_quote_and_oversized_field_reject_without_padding(self):
        self.fixture((','.join(m.FIELDS)+'\n"unclosed').encode(),rows=1)
        with self.assertRaises(csv.Error):self.run_import()
        self.failed_before_native()
        row=list(ROWS[0]);row[5]='a'*65537
        with self.assertRaisesRegex(ValueError,'Bounded UTF8'):m.parse_row(row,self.profile)
    def test_quoted_empty_NULLs_and_nonempty_NULL_string_have_explicit_policy(self):
        stream=io.StringIO(newline='');writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\n');writer.writerow(m.FIELDS)
        row=list(ROWS[0]);row[4]=row[8]='';row[5]='NULL';writer.writerow(row);self.fixture(stream.getvalue().encode(),rows=1)
        result=self.run_import();self.assertEqual(result['summary']['nulls']['category_code'],1);self.assertEqual(result['summary']['nulls']['brand'],0)
        con=duckdb.connect(result['database']['path'],read_only=True)
        try:self.assertEqual(con.execute('SELECT category_code,brand,user_session FROM events').fetchone(),(None,'NULL',None))
        finally:con.close()
    def test_original_ambiguous_space_quote_brand_is_preserved_exactly(self):
        row=list(ROWS[0]);row[5]=' "x" '
        raw=(','.join(m.FIELDS)+'\n'+','.join(row)+'\n').encode()
        self.fixture(raw,rows=1);result=self.run_import()
        con=duckdb.connect(result['database']['path'],read_only=True)
        try:self.assertEqual(con.execute('SELECT brand FROM events').fetchone()[0],' "x" ')
        finally:con.close()
        self.assertTrue(result['validated_csv']['native_reader_used']);self.assertEqual(result['validated_csv']['quoting'],'all_fields')
        with (self.work/'validated.csv').open(newline='') as stream:
            reader=csv.reader(stream,strict=True);self.assertEqual(next(reader),list(m.FIELDS));self.assertEqual(next(reader)[5],' "x" ')
    def test_canonical_reader_preserves_quotes_newlines_unicode_and_literal_NULLs(self):
        for index,value in enumerate([' leading','line1\r\nline2','quote " inside','汉字é😺','NULL','NA']):
            self.work=self.root/('canonical-'+str(index));row=list(ROWS[0]);row[5]=value;self.fixture(csv_bytes([row]),rows=1)
            result=self.run_import();con=duckdb.connect(result['database']['path'],read_only=True)
            try:self.assertEqual(con.execute('SELECT brand FROM events').fetchone()[0],value)
            finally:con.close()
    def test_late_canonical_stream_mutation_prevents_success(self):
        changed=False
        def check():
            nonlocal changed
            self.check()
            if (self.work/'import-evidence.json').exists() and not changed:
                with (self.work/'validated.csv').open('ab') as stream:stream.write(b'late mutation')
                changed=True
        with self.assertRaisesRegex(ValueError,'inputs changed during evidence'):self.run_import(check)
        self.assertTrue(changed);self.assertTrue((self.work/'report.failed.json').exists())
    def test_guard_failure_after_consumption_is_preserved_and_no_retry(self):
        def check():
            if (self.work/'import.consumed.json').exists():raise TimeoutError('original lifetime stop')
        with self.assertRaisesRegex(TimeoutError,'original lifetime stop'):self.run_import(check)
        self.failed_before_native()
        with self.assertRaisesRegex(ValueError,'exclusive import'):self.run_import()

if __name__=='__main__':unittest.main()
