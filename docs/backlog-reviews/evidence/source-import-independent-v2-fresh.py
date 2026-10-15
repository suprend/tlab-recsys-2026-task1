"""Seven new canonical-spool probes on <=2 artificial rows, no actual source."""
import ast,csv,gzip,hashlib,io,json,os,stat,sys,tempfile,unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import duckdb
from scripts import source_import as m
ROOT=Path(__file__).resolve().parents[3];FREEZE=Path('source-import-freeze-v2.json')
BASE=['2019-10-01 00:00:00 UTC','view','1','2','category','brand','0','3','session']
def body(rows):
 stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(m.FIELDS);writer.writerows(rows);return stream.getvalue().encode()
def freeze():
 result={}
 for path,wanted in json.loads(FREEZE.read_text())['files'].items():
  raw=(ROOT/path).read_bytes();got=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw));assert got==wanted;result[path]=got
 return result
class CanonicalFresh(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='canonical typed9 ');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.archive=self.root/'local.gz';self.work=self.root/'new import'
 def fixture(self,raw,rows=1):
  self.raw=raw;compressed=gzip.compress(raw,mtime=0);self.archive.write_bytes(compressed);self.profile=deepcopy(m.PRODUCTION_PROFILE);self.profile.update(scope='synthetic_typed9_import_fixture',compressed_sha256=hashlib.sha256(compressed).hexdigest(),compressed_bytes=len(compressed),uncompressed_bytes=len(raw),expected_rows=rows)
 def run_import(self):return m.import_archive(self.archive,self.work,self.profile,check=lambda:None)
 def test_three_text_fields_original_ambiguous_tokens_and_native_path(self):
  row=BASE.copy();row[4]=' "category" ';row[5]=' "brand" ';row[8]=' "session" ';raw=(','.join(m.FIELDS)+'\n'+','.join(row)+'\n').encode();self.fixture(raw);original=duckdb.connect;reads=[]
  class Wrapped:
   def __init__(inner,*args,**kwargs):inner.real=original(*args,**kwargs)
   def execute(inner,query,*args,**kwargs):
    if 'FROM read_csv(' in query:reads.extend(args[0])
    return inner.real.execute(query,*args,**kwargs)
   def close(inner):inner.real.close()
  with patch.object(duckdb,'connect',Wrapped):result=self.run_import()
  self.assertEqual(reads,[str(self.work/'validated.csv')]);con=original(result['database']['path'],read_only=True)
  try:self.assertEqual(con.execute('SELECT category_code,brand,user_session FROM events').fetchone(),tuple(row[i] for i in [4,5,8]))
  finally:con.close()
 def test_raw_and_canonical_original_witnesses_and_paid_hash_passes(self):
  row=BASE.copy();row[4]='';row[5]='quote "\r\n汉字';row[8]='NULL';raw=body([row]);self.fixture(raw);original=m.file_hash;reads=[]
  def track(path,check):reads.append(Path(path).name);return original(path,check)
  with patch.object(m,'file_hash',track):result=self.run_import()
  canonical=io.StringIO(newline='');writer=csv.writer(canonical,quoting=csv.QUOTE_ALL,lineterminator='\n');writer.writerow(m.FIELDS);writer.writerow(row);expected=canonical.getvalue().encode()
  self.assertEqual((self.work/'source.csv').read_bytes(),raw);self.assertEqual((self.work/'validated.csv').read_bytes(),expected)
  self.assertEqual(result['csv']['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(result['validated_csv']['sha256'],hashlib.sha256(expected).hexdigest());self.assertEqual(result['validated_csv']['bytes'],len(expected));self.assertNotEqual(result['csv']['sha256'],result['validated_csv']['sha256'])
  self.assertEqual(Counter(reads),Counter({'validated.csv':3,'local.gz':2,'source.csv.gz':2,'source.csv':2,'events.duckdb':2,'import-evidence.json':1}))
  self.assertEqual(stat.S_IMODE(self.work.stat().st_mode),0o700)
  for name in ['source.csv.gz','source.csv','validated.csv']:self.assertEqual(stat.S_IMODE((self.work/name).stat().st_mode),0o600)
 def test_canonical_fsync_failure_stops_before_DB_preserves_consumption_and_primary(self):
  self.fixture(body([BASE]));original=os.fsync;seen=[]
  def fail_canonical(fd):
   path=self.work/'validated.csv'
   if path.exists() and os.fstat(fd).st_ino==path.stat().st_ino:seen.append(True);raise OSError('canonical fsync failed')
   return original(fd)
  prior=csv.field_size_limit()
  with patch.object(os,'fsync',fail_canonical),self.assertRaisesRegex(OSError,'canonical fsync failed'):self.run_import()
  self.assertEqual(seen,[True]);self.assertEqual(csv.field_size_limit(),prior);self.assertTrue((self.work/'validated.csv').exists());self.assertTrue((self.work/'import.consumed.json').exists());self.assertTrue((self.work/'report.failed.json').exists());self.assertFalse((self.work/'events.duckdb').exists());self.assertFalse((self.work/'import-evidence.json').exists())
  with self.assertRaisesRegex(ValueError,'exclusive import'):self.run_import()
 def test_parse_failure_retains_only_canonical_valid_prefix_and_no_DB(self):
  row=BASE.copy();row[2]='not-an-int';self.fixture(body([BASE,row]),rows=2);prior=csv.field_size_limit()
  with self.assertRaisesRegex(ValueError,'integer token'):self.run_import()
  self.assertEqual(csv.field_size_limit(),prior);self.assertTrue((self.work/'report.failed.json').exists());self.assertFalse((self.work/'events.duckdb').exists())
  with (self.work/'validated.csv').open(newline='') as stream:self.assertEqual(list(csv.reader(stream,strict=True)),[list(m.FIELDS),BASE])
 def test_existing_explicit_canonical_destination_is_never_overwritten(self):
  raw=body([BASE]);source=self.root/'raw.csv';source.write_bytes(raw);canonical=self.root/'existing.csv';canonical.write_bytes(b'caller-owned original');self.fixture(raw);prior=csv.field_size_limit()
  with self.assertRaises(FileExistsError):m.validate_csv(source,self.profile,lambda:None,canonical_path=canonical)
  self.assertEqual(canonical.read_bytes(),b'caller-owned original');self.assertEqual(source.read_bytes(),raw);self.assertEqual(csv.field_size_limit(),prior)
 def test_canonical_substitution_after_witness_before_native_cannot_return_success(self):
  self.fixture(body([BASE]));original=duckdb.connect;changed=[]
  def change_then_connect(*args,**kwargs):
   p=self.work/'validated.csv';raw=p.read_bytes();self.assertIn(b'"brand"',raw);p.write_bytes(raw.replace(b'"brand"',b'"other"'));changed.append(True);return original(*args,**kwargs)
  with patch.object(duckdb,'connect',change_then_connect),self.assertRaisesRegex(ValueError,'Canonical validated CSV changed'):self.run_import()
  self.assertEqual(changed,[True]);self.assertTrue((self.work/'events.duckdb').exists());self.assertTrue((self.work/'report.failed.json').exists());self.assertFalse((self.work/'import-evidence.json').exists())
 def test_wrong_total_count_does_not_promote_complete_canonical_prefix(self):
  self.fixture(body([BASE]),rows=2)
  with self.assertRaisesRegex(ValueError,'raw-bag row count'):self.run_import()
  self.assertTrue((self.work/'validated.csv').exists());self.assertFalse((self.work/'events.duckdb').exists());self.assertFalse((self.work/'import-evidence.json').exists());self.assertTrue((self.work/'report.failed.json').exists())
if __name__=='__main__':
 freeze();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CanonicalFresh));post=freeze();Path('tlab-source-import-independent-v2-fresh-post-hashes.json').write_text(json.dumps(post,indent=2)+'\n');sys.exit(not result.wasSuccessful())
