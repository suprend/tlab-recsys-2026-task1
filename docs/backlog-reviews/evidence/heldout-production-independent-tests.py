"""Independent tiny transport/clock/attachment probes; fake native/authority."""
import io,sys,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(sys.argv[1]).resolve()));del sys.argv[1]
import numpy as np
from scripts import heldout_reporting_worker as m
from scripts import heldout_execution as x
import tests.test_heldout_reporting_worker as fixtures

class IndependentProductionBoundary(unittest.TestCase):
 def transport(self):
  fixture=fixtures.Transport('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups);return fixture
 def pipeline(self):
  fixture=fixtures.Pipeline('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups);return fixture
 def test_duplicate_NPZ_member_rejected_before_any_array_allocation(self):
  f=self.transport();descriptor=f.save();path=f.root/descriptor['artifact']['path']
  import warnings
  with warnings.catch_warnings():
   warnings.simplefilter('ignore',UserWarning)
   with zipfile.ZipFile(path,'a') as archive:archive.writestr('scores.npy',b'duplicate')
  descriptor['artifact']['sha256']=x.sha(path);f.run.pins[descriptor['artifact']['path']]=descriptor['artifact']['sha256']
  with patch.object(np,'load',side_effect=AssertionError('No allocation')),self.assertRaisesRegex(ValueError,'unique NPZ'):m.read_scores(f.run,descriptor,f.day)
 def test_valid_size_Fortran_header_rejected_before_any_array_allocation(self):
  f=self.transport();descriptor=f.save();path=f.root/descriptor['artifact']['path']
  with zipfile.ZipFile(path) as archive:members={name:archive.read(name) for name in archive.namelist()}
  raw=io.BytesIO();np.lib.format.write_array_header_1_0(raw,dict(descr='<i8',fortran_order=True,shape=(1,)));raw.write((1).to_bytes(8,'little'));members['items.npy']=raw.getvalue()
  with zipfile.ZipFile(path,'w') as archive:
   for name,data in members.items():archive.writestr(name,data)
  descriptor['artifact']['sha256']=x.sha(path);f.run.pins[descriptor['artifact']['path']]=descriptor['artifact']['sha256']
  with patch.object(np,'load',side_effect=AssertionError('No allocation')),self.assertRaisesRegex(ValueError,'before allocation'):m.read_scores(f.run,descriptor,f.day)
 def test_same_second_seal_waits_for_real_next_observed_tick_under_guard(self):
  f=self.pipeline();f.source();f.predictions();f.target_inputs();calls=[]
  ticks=iter(['2026-10-15T12:02:30Z','2026-10-15T12:02:31Z'])
  def tick():return next(ticks,'2026-10-15T12:02:31Z')
  with patch.object(m,'utc_now',side_effect=tick),patch.object(m.time,'sleep',side_effect=lambda seconds:calls.append((seconds,f.run.budget.calls))):
   _,ref,_,_=m.targets_role(f.run,f.environment)
  body,_=x.read(f.root/ref['path']);self.assertEqual(body['target_stage_opened_at'],'2026-10-15T12:02:31Z');self.assertEqual(len(calls),1);self.assertGreater(calls[0][1],0)
  self.assertGreaterEqual(body['fullY_started_monotonic'],body['target_stage_started_monotonic'])
 def test_source_attachment_is_actually_read_only_on_synthetic_database(self):
  f=self.pipeline()
  with m.connection(f.run,source=f.raw) as con:
   self.assertEqual(con.execute("SELECT current_setting('threads')").fetchone()[0],2)
   with self.assertRaisesRegex(Exception,'read-only'):con.execute('DELETE FROM reserved_input.main.events')

if __name__=='__main__':unittest.main(verbosity=2)
