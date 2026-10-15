"""Independent frozen-v1 tiny typed9 kernel probes, no actual dataset/model access."""
from copy import deepcopy
import csv,gzip,hashlib,io,json,sys,tempfile,unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import duckdb
from scripts import source_import as m
ROOT=Path(__file__).resolve().parents[3]
FREEZE=Path('source-import-freeze-v1.json')
BASE=['2019-10-01 00:00:00 UTC','view','1','2','category','brand','0','3','session']

def csv_body(rows,*,terminator='\n',quoting=csv.QUOTE_MINIMAL):
 out=io.StringIO(newline='');writer=csv.writer(out,lineterminator=terminator,quoting=quoting);writer.writerow(m.FIELDS);writer.writerows(rows);return out.getvalue().encode('utf-8')

def frozen():
 actual={}
 for name,want in json.loads(FREEZE.read_text())['files'].items():
  raw=(ROOT/name).read_bytes();got=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw));assert got==want,(name,got,want);actual[name]=got
 return actual

class IndependentImport(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='typed9 independent ');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'provided local.gz';self.work=self.root/'new result';self.calls=0
 def fixture(self,raw,*,rows=1,compressed=None):
  body=gzip.compress(raw,mtime=0) if compressed is None else compressed;self.source.write_bytes(body);self.profile=deepcopy(m.PRODUCTION_PROFILE);self.profile.update(scope='synthetic_typed9_import_fixture',compressed_sha256=hashlib.sha256(body).hexdigest(),compressed_bytes=len(body),uncompressed_bytes=len(raw),expected_rows=rows)
 def guard(self):self.calls+=1
 def run_import(self):return m.import_archive(self.source,self.work,self.profile,check=self.guard)
 def rows(self,result):
  con=duckdb.connect(result['database']['path'],read_only=True)
  try:return con.execute('SELECT * FROM events ORDER BY product_id NULLS LAST').fetchall()
  finally:con.close()
 def assert_failed(self,*,db=False):
  self.assertTrue((self.work/'import.consumed.json').exists());self.assertTrue((self.work/'report.failed.json').exists());self.assertEqual((self.work/'events.duckdb').exists(),db)
  self.assertEqual(json.loads((self.work/'report.failed.json').read_text())['source_acceptance_issued'],False)
 def test_validated_literal_space_quote_string_survives_native_import(self):
  # Not a malformed quote: Python's declared strict csv dialect treats the
  # quote after an initial space as literal text in an unquoted field.
  literal=' "x" ';raw=(','.join(m.FIELDS)+'\n'+','.join(BASE[:5]+[literal]+BASE[6:])+'\n').encode()
  lexical=list(csv.reader(io.StringIO(raw.decode(),newline=''),strict=True));self.assertEqual(lexical[1][5],literal)
  self.fixture(raw);result=self.run_import();self.assertEqual(result['summary']['nulls']['brand'],0)
  self.assertEqual(self.rows(result)[0][5],literal,'Native importer silently changed the validated raw string')
 def test_exact_all_nine_values_signed64_decimal_quotes_multiline_and_NULL(self):
  first=['2019-10-01 00:00:00 UTC','view',str(-(2**63)),str(2**63-1),'a,"b"','中文\r\n"quoted"','-9999999999.99','+0','NULL']
  second=['2019-10-31 23:59:59 UTC','purchase',str(2**63-1),'','',' leading and trailing ','+9999999999.99',str(-(2**63)),'']
  self.fixture(csv_body([first,second]),rows=2);result=self.run_import()
  self.assertEqual(self.rows(result),[(datetime(2019,10,1),'view',-(2**63),2**63-1,'a,"b"','中文\r\n"quoted"',Decimal('-9999999999.99'),0,'NULL'),(datetime(2019,10,31,23,59,59),'purchase',2**63-1,None,None,' leading and trailing ',Decimal('9999999999.99'),-(2**63),None)])
 def test_all_members_concatenated_gzip_split_inside_UTF8_and_CSV_record(self):
  row=BASE.copy();row[5]='first\n汉字';raw=csv_body([row]);split=raw.index('汉'.encode())+1;body=gzip.compress(raw[:split],mtime=0)+gzip.compress(raw[split:],mtime=0)
  self.fixture(raw,compressed=body);result=self.run_import();self.assertEqual(result['csv']['bytes'],len(raw));self.assertEqual(self.rows(result)[0][5],row[5]);self.assertTrue(result['csv']['all_gzip_members_EOF_CRC_ISIZE_checked'])
 def test_second_member_bad_CRC_is_not_hidden_by_valid_first_member(self):
  raw=csv_body([BASE]);split=len(raw)//2;second=bytearray(gzip.compress(raw[split:],mtime=0));second[-8]^=1;body=gzip.compress(raw[:split],mtime=0)+bytes(second);self.fixture(raw,compressed=body)
  with self.assertRaises(gzip.BadGzipFile):self.run_import()
  self.assert_failed()
 def test_second_member_truncation_is_not_hidden_by_valid_first_member(self):
  raw=csv_body([BASE]);split=len(raw)//2;body=gzip.compress(raw[:split],mtime=0)+gzip.compress(raw[split:],mtime=0)[:-2];self.fixture(raw,compressed=body)
  with self.assertRaises(EOFError):self.run_import()
  self.assert_failed()
 def test_non_gzip_trailing_payload_is_rejected(self):
  raw=csv_body([BASE]);body=gzip.compress(raw,mtime=0)+b'not a gzip member';self.fixture(raw,compressed=body)
  with self.assertRaises(gzip.BadGzipFile):self.run_import()
  self.assert_failed()
 def test_exact_character_limit_accepts_multibyte_field_without_byte_truncation(self):
  row=BASE.copy();row[5]='汉'*65536;self.fixture(csv_body([row]));result=self.run_import();self.assertEqual(self.rows(result)[0][5],row[5])
 def test_over_character_limit_fails_before_native_and_restores_csv_global_limit(self):
  prior=csv.field_size_limit();row=BASE.copy();row[5]='a'*65537;self.fixture(csv_body([row]))
  with self.assertRaises(csv.Error):self.run_import()
  self.assertEqual(csv.field_size_limit(),prior);self.assert_failed()
 def test_NUL_in_nullable_text_rejects_before_native_import(self):
  row=BASE.copy();row[4]='a\x00b';self.fixture(csv_body([row]))
  with self.assertRaisesRegex(ValueError,'without NUL'):self.run_import()
  self.assert_failed()
 def test_blank_csv_record_is_not_silently_skipped(self):
  raw=csv_body([BASE])+b'\n';self.fixture(raw,rows=2)
  with self.assertRaisesRegex(ValueError,'nine CSV fields'):self.run_import()
  self.assert_failed()
 def test_CRLF_and_quoted_multiline_preserve_all_text_and_raw_bag(self):
  row=BASE.copy();row[4]='a\r\nb';row[5]='c\r\nd';self.fixture(csv_body([row,row],terminator='\r\n',quoting=csv.QUOTE_ALL),rows=2);result=self.run_import();rows=self.rows(result)
  self.assertEqual(len(rows),2);self.assertEqual(rows[0],rows[1]);self.assertEqual(rows[0][4:6],('a\r\nb','c\r\nd'))
 def test_exclusive_marker_is_present_before_first_source_open(self):
  raw=csv_body([BASE]);self.fixture(raw);original=Path.open;seen=[]
  def inspect(path,*args,**kwargs):
   if Path(path)==self.source and args and args[0]=='rb':seen.append((self.work/'import.consumed.json').is_file())
   return original(path,*args,**kwargs)
  with patch.object(Path,'open',inspect):self.run_import()
  self.assertGreaterEqual(len(seen),1);self.assertTrue(all(seen));self.assertEqual(json.loads((self.work/'import.consumed.json').read_text())['profile'],self.profile)
 def test_native_checkpoint_failure_preserves_committed_partial_and_primary_error(self):
  self.fixture(csv_body([BASE]));original=duckdb.connect;closed=[]
  class Wrapped:
   def __init__(inner,*args,**kwargs):inner.real=original(*args,**kwargs)
   def execute(inner,query,*args,**kwargs):
    if query=='CHECKPOINT':raise RuntimeError('independent checkpoint failure')
    return inner.real.execute(query,*args,**kwargs)
   def close(inner):closed.append(True);inner.real.close()
  with patch.object(duckdb,'connect',Wrapped),self.assertRaisesRegex(RuntimeError,'independent checkpoint failure'):self.run_import()
  self.assert_failed(db=True);self.assertEqual(len(closed),1);self.assertFalse((self.work/'import-evidence.json').exists())
  with self.assertRaisesRegex(ValueError,'exclusive import'):self.run_import()
 def test_changed_persisted_evidence_is_rejected_using_original_written_digest(self):
  self.fixture(csv_body([BASE]));original=m.exclusive
  def corrupt(path,body):
   ref=original(path,body)
   if Path(path).name=='import-evidence.json':
    changed=deepcopy(body);changed['labels_created']=True;Path(path).write_text(m.canonical(changed)+'\n')
   return ref
  with patch.object(m,'exclusive',corrupt),self.assertRaisesRegex(ValueError,'Original import evidence changed'):self.run_import()
  self.assert_failed(db=True)
 def test_evidence_persistence_primary_failure_is_not_replaced_by_failure_writer_error(self):
  self.fixture(csv_body([BASE]));original=m.exclusive
  def fail_writers(path,body):
   if Path(path).name=='import-evidence.json':raise OSError('original evidence storage failure')
   if Path(path).name=='report.failed.json':raise PermissionError('secondary failure writer failure')
   return original(path,body)
  with patch.object(m,'exclusive',fail_writers),self.assertRaisesRegex(OSError,'original evidence storage failure') as error:self.run_import()
  self.assertIn('PermissionError',str(error.exception.__notes__));self.assertTrue((self.work/'import.consumed.json').exists());self.assertTrue((self.work/'events.duckdb').exists());self.assertFalse((self.work/'import-evidence.json').exists())
 def test_known_failed_marker_after_evidence_prevents_success(self):
  self.fixture(csv_body([BASE]));original=m.exclusive
  def late_failure(path,body):
   ref=original(path,body)
   if Path(path).name=='import-evidence.json':original(self.work/'report.failed.json',dict(status='known failed'))
   return ref
  with patch.object(m,'exclusive',late_failure),self.assertRaisesRegex(ValueError,'Known failed import'):self.run_import()
  self.assertTrue((self.work/'report.failed.json').exists())
 def test_preconsumption_invalid_profile_does_not_read_source_or_create_work(self):
  self.fixture(csv_body([BASE]));self.profile['expected_rows']=True;original=Path.open;sourceopens=[]
  def inspect(path,*args,**kwargs):
   if Path(path)==self.source:sourceopens.append(True)
   return original(path,*args,**kwargs)
  with patch.object(Path,'open',inspect),self.assertRaises(ValueError):self.run_import()
  self.assertEqual(sourceopens,[]);self.assertFalse(self.work.exists())

if __name__=='__main__':
 frozen();suite=unittest.defaultTestLoader.loadTestsFromTestCase(IndependentImport);result=unittest.TextTestRunner(verbosity=2).run(suite);post=frozen();Path('tlab-source-import-independent-post-hashes.json').write_text(json.dumps(post,indent=2)+'\n');sys.exit(not result.wasSuccessful())
