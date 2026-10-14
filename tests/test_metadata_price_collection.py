from copy import deepcopy
import contextlib
import hashlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import duckdb

from scripts import metadata_price_collection as c
from scripts import metadata_price_features as m
from scripts import train_baselines as b
from scripts.protocol_manifest import canonical_json,sha256_file
import tests.test_train_baselines as baseline_tests
import tests.test_metadata_price_features as metadata_tests


class StrictCollectionTests(unittest.TestCase):
    def setUp(self):
        fixture=baseline_tests.CollectionAcceptanceTests('test_exact_external_acceptance_accepts_then_missing_or_extra_scope_rejects')
        fixture.setUp();self.addCleanup(fixture.doCleanups);self.fixture=fixture
        self.addCleanup(patch.stopall);patch.object(c,'ROOT',fixture.root).start()

    def test_real_tiny_producer_bundle_passes_exact14_supplement(self):
        result=c.verify_collection_strict(self.fixture.path)
        self.assertEqual(result['phase']['role'],'train')

    def test_fresh_resealed_omitted_QC_consumption_rejected_even_if_legacy_transport_passes(self):
        f=self.fixture;root=f.root
        state_path=f.fixture.directory/'state.json';state=b._read_json(state_path);entry=state['shards'][0]
        approval_path=root/entry['acceptance']['path'];approval=b._read_json(approval_path)
        am=b._read_json(root/entry['anchor']['directory']/'run.json');cm=b._read_json(root/entry['candidate']['directory']/'run.json')
        missing=[am['artifact_refs']['queries'],cm['artifact_refs']['candidates']]
        for name in missing:del approval['fingerprints'][name]
        b._atomic_json(approval_path,approval);entry['acceptance']['sha256']=sha256_file(approval_path)
        manifest_path=root/entry['features']['directory']/'run.json';report_path=manifest_path.parent/'report.json'
        manifest=b._read_json(manifest_path)
        for name in missing:del manifest['identity']['input_hashes'][name]
        manifest['identity']['input_hashes'][entry['acceptance']['path']]=entry['acceptance']['sha256']
        manifest['run_id']=hashlib.sha256(canonical_json(manifest['identity']).encode()).hexdigest()
        b._atomic_json(manifest_path,manifest)
        report=b._read_json(report_path);report['run_id']=manifest['run_id'];b._atomic_json(report_path,report)
        entry['features']['run_id']=manifest['run_id']
        for p in [manifest_path,report_path]:entry['features']['fingerprints'][str(p.relative_to(root))]=sha256_file(p)
        b._atomic_json(state_path,state)
        outer=deepcopy(f.approval)
        for p in [state_path,approval_path,manifest_path,report_path]:outer['fingerprints'][str(p.relative_to(root))]=sha256_file(p)
        b._atomic_json(f.path,outer)
        b.verify_collection(f.path) # demonstrate the prior scope gap, not a hash failure
        with self.assertRaisesRegex(ValueError,'canonical14'):c.verify_collection_strict(f.path)


class FullExportTests(unittest.TestCase):
    def setUp(self):
        fixture=metadata_tests.MetadataGateTests('test_actual_tiny_gate_exports_keys_reference_schema_and_cpu_no_labels_no_fits')
        fixture.setUp();self.addCleanup(fixture.doCleanups);self.fixture=fixture;self.root=fixture.root.resolve()
        self.addCleanup(patch.stopall);patch.object(c,'ROOT',self.root).start()
        b._atomic_json(fixture.acceptance,dict(version=1,approved=True,scope='reviewed_development_collection',collection_id='c'*64))
        candidate_code=self.root/'scripts/candidate_pilot.py';candidate_code.write_text('fixture canonical candidate code')
        source=duckdb.connect(str(fixture.source))
        source.execute("INSERT INTO events VALUES ('2019-10-10 23:59:59',1,11,10,'code','second',9.0)");source.close()
        fixture.collection['pins']={str(p.resolve().relative_to(self.root)):sha256_file(p) for p in
            [fixture.acceptance,fixture.source,self.root/'q.parquet',self.root/'f.parquet',candidate_code]}
        fixture.approve()
        with contextlib.redirect_stdout(io.StringIO()):gate_report=fixture.run_gate()
        gate_directory=self.root/'artifacts/metadata-price'/gate_report['run_id']
        gate_manifest=b._read_json(gate_directory/'run.json')
        pins=dict(gate_manifest['identity']['fingerprints'])
        pins[gate_manifest['gate_approval']['path']]=gate_manifest['gate_approval']['sha256']
        pins.update({a['path']:a['sha256'] for a in gate_manifest['outputs'].values()})
        for p in [gate_directory/'run.json',gate_directory/'report.json']:pins[str(p.relative_to(self.root))]=sha256_file(p)
        self.gate_path=self.root/'gate-source.json'
        b._atomic_json(self.gate_path,dict(version=1,approved=True,scope='reviewed_metadata_price_100q',run_id=gate_report['run_id'],fingerprints=pins))
        self.train_path=self.root/'train.json';self.selection_path=self.root/'selection.json'
        self.train_path.write_text('{}');self.selection_path.write_text('{}')
        self.approval_path=self.root/'export-approval.json'
        fullpins={**pins,'gate-source.json':sha256_file(self.gate_path)}
        for p in [fixture.source,self.root/'q.parquet',self.root/'f.parquet',self.train_path,self.selection_path]:fullpins[str(p.resolve().relative_to(self.root))]=sha256_file(p)
        identity=dict(version=1,role=c.ROLE,limits=deepcopy(c.LIMITS),spec=deepcopy(m.SPEC),fingerprints=fullpins,
            acceptance_refs=dict(train='train.json',selection='selection.json',gate='gate-source.json'),
            collections=dict(train='c'*64,selection='d'*64),gate_run_id=gate_report['run_id'])
        self.plan=dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity)
        self.collections={}
        for role,cid in [('train','c'*64),('selection','d'*64)]:
            self.collections[role]=dict(phase=dict(role=role,range=dict(start='2019-10-10T00:00:00Z',end='2019-10-12T00:00:00Z'),
                budget=dict(max_queries=140,max_candidate_pairs=140)),refs=dict(queries=['q.parquet'],features=['f.parquet']),
                plan=dict(collection_id=cid,execution_inputs=dict(source_path='source.duckdb'),
                    identity=dict(shard_protocols=[dict(source=dict(start='2019-10-01T00:00:00Z',end='2019-11-01T00:00:00Z'))])))
        self.preparer=patch.object(c,'prepare_export_plan',side_effect=lambda *a,**kw:(deepcopy(self.plan),deepcopy(self.collections)))
        self.preparer.start();self.addCleanup(self.preparer.stop)
        b._atomic_json(self.approval_path,dict(version=1,approved=True,scope=c.ROLE,run_id=self.plan['run_id'],fingerprints=fullpins))

    def run_export(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return c.run_export(self.train_path,self.selection_path,self.gate_path,execution_approval=self.approval_path)

    def reports(self):
        return [b._read_json(p) for p in (self.root/'artifacts/metadata-price-development').glob('*/report.json')]

    def accept_export(self,report):
        directory=self.root/'artifacts/metadata-price-development'/report['run_id']
        manifest=b._read_json(directory/'run.json');pins=dict(manifest['identity']['fingerprints'])
        pins[manifest['execution_approval']['path']]=manifest['execution_approval']['sha256']
        for days in manifest['outputs'].values():
            for day in days:pins.update({a['path']:a['sha256'] for a in day['artifacts'].values()})
        for p in [directory/'run.json',directory/'report.json']:pins[str(p.relative_to(self.root))]=sha256_file(p)
        path=self.root/'full-source.json'
        b._atomic_json(path,dict(version=1,approved=True,scope='reviewed_metadata_price_development_export',run_id=report['run_id'],fingerprints=pins))
        return path

    def test_source_gate_exact_scope_and_actual_outputs_unchanged(self):
        value=c.verify_accepted_metadata_gate(self.gate_path)
        self.assertEqual(value['report']['materialization']['pairs'],100)
        a=b._read_json(self.gate_path);a['fingerprints'].pop(next(n for n in a['fingerprints'] if n.endswith('reference.parquet')))
        b._atomic_json(self.gate_path,a)
        with self.assertRaisesRegex(ValueError,'exact required'):c.verify_accepted_metadata_gate(self.gate_path)

    def test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption(self):
        report=self.run_export();self.assertEqual(report['status'],'complete_produced_unreviewed')
        self.assertEqual(report['fit_attempt_count'],0);self.assertFalse(report['labels_loaded'])
        for role in ['train','selection']:
            self.assertEqual(report['phases'][role]['queries'],140);self.assertEqual(report['phases'][role]['pairs'],140)
            self.assertEqual(len(report['phases'][role]['days']),2)
            self.assertEqual([d['model_boundary']['unique_items'] for d in report['phases'][role]['days']],[1,1])
            self.assertEqual([d['model_boundary']['diagnostic_cardinality']['brand'] for d in report['phases'][role]['days']],[1,1])
            self.assertEqual(report['phases'][role]['diagnostic_phase_encoded_cardinality']['brand'],2)
        verified=c.verify_accepted_export(self.accept_export(report))
        self.assertEqual(len(verified['refs']['train']),2)
        with self.assertRaises(FileExistsError):self.run_export()

    def test_wrong_approval_before_source_export_and_partial_failure_preservation(self):
        a=b._read_json(self.approval_path);a['fingerprints'].pop('q.parquet');b._atomic_json(self.approval_path,a)
        with self.assertRaisesRegex(ValueError,'approval'):self.run_export()
        self.assertEqual(self.reports()[0]['status'],'failed')
        self.assertFalse(any((self.root/'artifacts/metadata-price-development').rglob('features.parquet')))

    def test_final_input_mutation_rejects_and_preserves_daily_exports(self):
        original=c.validate_day_arrays
        def altered(*a,**kw):
            result=original(*a,**kw);(self.root/'train.json').write_text('changed');return result
        with patch.object(c,'validate_day_arrays',side_effect=altered),self.assertRaisesRegex(ValueError,'content changed'):self.run_export()
        self.assertTrue(any((self.root/'artifacts/metadata-price-development').rglob('features.parquet')))
        self.assertEqual(self.reports()[0]['status'],'failed')

    def test_close_resource_overrun_fails_final_seal(self):
        actual_connect=duckdb.connect;actual_clock=c.time.monotonic;offset=[0.]
        class Connection:
            def __init__(self,con):self.con=con
            def __getattr__(self,n):return getattr(self.con,n)
            def close(self):self.con.close();offset[0]+=1300
        with patch('duckdb.connect',side_effect=lambda *a,**kw:Connection(actual_connect(*a,**kw)) if kw.get('read_only') else actual_connect(*a,**kw)),patch.object(c.time,'monotonic',side_effect=lambda:actual_clock()+offset[0]),self.assertRaises(TimeoutError):self.run_export()
        self.assertTrue(all(r['status']=='failed' for r in self.reports()))

    def reseal_gate_without(self,name):
        approval=b._read_json(self.gate_path);old=self.root/'artifacts/metadata-price'/approval['run_id']
        manifest=b._read_json(old/'run.json');report=b._read_json(old/'report.json')
        manifest['identity']['fingerprints'].pop(name)
        new_id=hashlib.sha256(canonical_json(manifest['identity']).encode()).hexdigest()
        new=old.parent/new_id;old.rename(new);manifest['run_id']=report['run_id']=new_id
        b._atomic_json(self.fixture.approval,dict(version=1,approved=True,scope=m.GATE_ROLE,run_id=new_id,fingerprints=manifest['identity']['fingerprints']))
        manifest['gate_approval']['sha256']=sha256_file(self.fixture.approval)
        for key,artifact in manifest['outputs'].items():artifact['path']=str((new/(key+'.parquet')).relative_to(self.root))
        report['artifacts']=deepcopy(manifest['outputs'])
        b._atomic_json(new/'run.json',manifest);b._atomic_json(new/'report.json',report)
        pins={**manifest['identity']['fingerprints'],manifest['gate_approval']['path']:manifest['gate_approval']['sha256']}
        pins.update({a['path']:a['sha256'] for a in manifest['outputs'].values()})
        pins.update({str(p.relative_to(self.root)):sha256_file(p) for p in [new/'run.json',new/'report.json']})
        b._atomic_json(self.gate_path,dict(version=1,approved=True,scope='reviewed_metadata_price_100q',run_id=new_id,fingerprints=pins))

    def test_fresh_resealed100_without_source_is_rejected(self):
        self.reseal_gate_without('source.duckdb')
        with self.assertRaisesRegex(ValueError,'complete actual'):c.verify_accepted_metadata_gate(self.gate_path)

    def test_fresh_resealed100_without_candidate_code_is_rejected(self):
        self.reseal_gate_without('scripts/candidate_pilot.py')
        with self.assertRaisesRegex(ValueError,'complete actual'):c.verify_accepted_metadata_gate(self.gate_path)

    def test_fresh_resealed100_without_specfile_is_rejected(self):
        self.reseal_gate_without('configs/features/metadata-price.json')
        with self.assertRaisesRegex(ValueError,'actual accepted train and spec'):c.verify_accepted_metadata_gate(self.gate_path)

    def reseal_physical(self,report,name,transform):
        directory=self.root/'artifacts/metadata-price-development'/report['run_id']
        manifest=b._read_json(directory/'run.json');day=manifest['outputs']['train'][0];artifact=day['artifacts'][name]
        path=self.root/artifact['path'];con=duckdb.connect(':memory:')
        try:
            con.execute('CREATE TABLE changed AS SELECT * FROM read_parquet(?)',[str(path)])
            transform(con)
            path.unlink();con.execute('COPY changed TO ? (FORMAT PARQUET)',[str(path)])
            artifact.update(sha256=sha256_file(path),bytes=path.stat().st_size,
                rows=con.execute('SELECT count(*) FROM changed').fetchone()[0],
                schema=[list(r[:2]) for r in con.execute('DESCRIBE changed').fetchall()])
        finally:con.close()
        report['phases']['train']['days']=deepcopy(manifest['outputs']['train'])
        b._atomic_json(directory/'run.json',manifest);b._atomic_json(directory/'report.json',report)
        return self.accept_export(report)

    def test_fresh_resealed_physical_wrong_query_is_rejected(self):
        report=self.run_export()
        path=self.reseal_physical(report,'queries',lambda con:con.execute("UPDATE changed SET query_id='wrong' WHERE query_id=(SELECT min(query_id) FROM changed)"))
        with self.assertRaisesRegex(ValueError,'Physical query rows'):c.verify_accepted_export(path)

    def test_fresh_resealed_physical_missing_nominal_column_is_rejected(self):
        report=self.run_export()
        path=self.reseal_physical(report,'features',lambda con:con.execute('ALTER TABLE changed DROP COLUMN brand'))
        with self.assertRaisesRegex(ValueError,'schema'):c.verify_accepted_export(path)

    def test_fresh_resealed_physical_missing_pair_is_rejected(self):
        report=self.run_export()
        path=self.reseal_physical(report,'features',lambda con:con.execute('DELETE FROM changed WHERE query_id=(SELECT min(query_id) FROM changed)'))
        with self.assertRaisesRegex(ValueError,'key cover'):c.verify_accepted_export(path)

    def test_fresh_resealed_physical_reference_membership_is_rejected(self):
        report=self.run_export()
        path=self.reseal_physical(report,'reference',lambda con:con.execute('DELETE FROM changed WHERE product_id=1'))
        with self.assertRaisesRegex(ValueError,'membership'):c.verify_accepted_export(path)

    def test_fresh_resealed_complete_report_cannot_override_known_failed_receipt(self):
        report=self.run_export();acceptance=self.accept_export(report)
        directory=self.root/'artifacts/metadata-price-development'/report['run_id']
        b._atomic_json(directory/'report.failed.json',dict(status='failed',error='final receipt writer failed'))
        with self.assertRaisesRegex(ValueError,'Known failed'):c.verify_accepted_export(acceptance)


class DailyBoundaryTests(unittest.TestCase):
    def setUp(self):
        fixture=metadata_tests.MetadataPriceTests('test_all_pairs_match_direct_list_oracle_and_fixed_schema')
        fixture.setUp();self.addCleanup(fixture.tearDown);fixture.create();self.con=fixture.con

    def test_every_unique_item_projection_validates_and_cross_query_variation_rejects(self):
        expected=c.validate_day_arrays(self.con);self.assertEqual(expected['unique_items'],len(metadata_tests.ITEMS))
        self.con.execute("INSERT INTO metadata_price_features SELECT 'other',*EXCLUDE(query_id) FROM metadata_price_features")
        self.assertEqual(c.validate_day_arrays(self.con)['unique_items'],len(metadata_tests.ITEMS))
        self.con.execute("UPDATE metadata_price_features SET brand='value:changed' WHERE query_id='other' AND product_id=1")
        with self.assertRaisesRegex(ValueError,'differ across Q'):c.validate_day_arrays(self.con)

    def test_unique_item_cap_is_before_python_array_allocation(self):
        self.con.execute('''CREATE OR REPLACE TEMP TABLE metadata_price_features AS
            SELECT 'q' query_id,r.id::BIGINT product_id,f.*EXCLUDE(query_id,product_id)
            FROM (SELECT * FROM metadata_price_features WHERE product_id=1) f CROSS JOIN range(22001) r(id)''')
        with patch.object(m,'model_arrays',side_effect=AssertionError('should not allocate')),self.assertRaisesRegex(ValueError,'22000'):c.validate_day_arrays(self.con)


class ExecutionAuditTests(unittest.TestCase):
    def setUp(self):
        from tempfile import TemporaryDirectory
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.output=Path(temporary.name)/'artifacts/exports'

    def reports(self):return [b._read_json(p) for p in self.output.glob('*/report.json')]

    def test_terminal_cpu_cap_and_counter_failure_preserve_failed_audit(self):
        clock=[0.]
        with patch.object(c,'cpu_time',side_effect=lambda:clock[0]),self.assertRaisesRegex(TimeoutError,'processCPU'):
            with c.ExecutionAudit(self.output,seconds=10,scope='unit',cpu_seconds=1) as audit:
                audit.report['status']='complete_produced_unreviewed';clock[0]=2.
        self.assertEqual(self.reports()[0]['status'],'failed')
        with patch.object(c,'cpu_time',side_effect=OSError('CPU unavailable')),self.assertRaisesRegex(OSError,'CPU unavailable'):
            c.ExecutionAudit(self.output,seconds=10,scope='unit')
        self.assertTrue(all(r['status']=='failed' for r in self.reports()))

    def test_primary_error_kept_when_terminal_close_also_fails(self):
        class Broken:
            def close(self):raise OSError('secondary close')
        with self.assertRaisesRegex(ValueError,'primary export'):
            with c.ExecutionAudit(self.output,seconds=10,scope='unit') as audit:
                audit.connection=Broken();raise ValueError('primary export')
        report=self.reports()[0]
        self.assertEqual(report['error'],'primary export')
        self.assertEqual(report['terminal_errors'][0]['error'],'secondary close')

    def test_stage_primary_preserved_when_cpu_measurement_also_fails(self):
        failed=[False]
        def counter():
            if failed[0]:raise OSError('secondary CPU counter')
            return 0.
        def operation():failed[0]=True;raise ValueError('primary operation')
        with patch.object(c,'cpu_time',side_effect=counter),self.assertRaisesRegex(ValueError,'primary operation'):
            with c.ExecutionAudit(self.output,seconds=10,scope='unit') as audit:audit.stage('fault',operation)
        report=self.reports()[0]
        self.assertEqual(report['error'],'primary operation');self.assertIsNone(report['process_cpu_user_system_seconds'])
        self.assertTrue(any('CPU counter' in e['error'] for e in report['secondary_errors']))

    def test_terminal_measurement_and_writer_failure_preserve_primary_and_failed_evidence(self):
        original=c._atomic_json;failed=[False]
        def writer(path,value):
            if failed[0] and path.name=='report.json':raise OSError('secondary report writer')
            return original(path,value)
        def rss():
            if failed[0]:raise OSError('secondary RSS')
            return 0
        with patch.object(c,'_atomic_json',side_effect=writer),patch.object(c,'peak_rss_bytes',side_effect=rss),self.assertRaisesRegex(ValueError,'primary export'):
            with c.ExecutionAudit(self.output,seconds=10,scope='unit') as audit:
                failed[0]=True;raise ValueError('primary export')
        fallback=b._read_json(next(self.output.glob('*/report.failed.json')))
        self.assertEqual(fallback['status'],'failed');self.assertEqual(fallback['error'],'primary export')
        self.assertIsNone(fallback['process_peak_rss_bytes'])
        self.assertTrue(any(e['location']=='report_write' for e in fallback['terminal_errors']))

    def test_manifest_and_first_summary_cpu_are_accounted_before_final_receipt(self):
        original=c._atomic_json;clock=[0.];charged=[False]
        def writer(path,value):
            if path.name=='run.json':clock[0]+=7.
            if path.name=='report.json' and value.get('status')=='finalizing' and not charged[0]:
                clock[0]+=3.;charged[0]=True
            return original(path,value)
        with patch.object(c,'_atomic_json',side_effect=writer),patch.object(c,'cpu_time',side_effect=lambda:clock[0]):
            with c.ExecutionAudit(self.output,seconds=10,scope='unit') as audit:
                audit.manifest={'synthetic':True};audit.report['status']='complete_produced_unreviewed'
        report=self.reports()[0]
        self.assertEqual(report['process_cpu_user_system_seconds'],10.)
        self.assertIn('before_final_receipt',report['cpu_accounting_boundary'])

    def test_failed_final_receipt_leaves_finalizing_summary_and_failed_marker(self):
        original=c._atomic_json
        def writer(path,value):
            if path.name=='report.json' and value.get('status')=='complete_produced_unreviewed':
                raise OSError('final complete receipt failed')
            return original(path,value)
        with patch.object(c,'_atomic_json',side_effect=writer),self.assertRaisesRegex(OSError,'final complete'):
            with c.ExecutionAudit(self.output,seconds=10,scope='unit') as audit:audit.report['status']='complete_produced_unreviewed'
        self.assertEqual(self.reports()[0]['status'],'finalizing')
        self.assertEqual(b._read_json(next(self.output.glob('*/report.failed.json')))['status'],'failed')


if __name__=='__main__':unittest.main()
