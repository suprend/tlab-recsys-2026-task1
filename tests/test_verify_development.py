"""Independent verifier seam: accepted synthetic inputs, semantic corruption."""
import unittest
from pathlib import Path
import tests.test_development_collection as fixture_tests
from scripts.verify_development import verify


class VerificationTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        from unittest.mock import patch
        real_connect=duckdb.connect
        def limited_connect(*args,**kwargs):
            connection=real_connect(*args,**kwargs)
            connection.execute('SET threads=2')
            return connection
        connections=patch('duckdb.connect',side_effect=limited_connect)
        connections.start();self.addCleanup(connections.stop)
        self.build()

    def build(self, rows=None):
        import json
        from scripts.protocol_manifest import canonical_json, load_run_manifest, sha256_file
        fixture = fixture_tests.DevelopmentRuntimeTests('test_actual_producers_wait_for_external_review_then_resume_full_features_and_cache')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.root = fixture, fixture.root
        if rows is not None:
            import duckdb
            con=duckdb.connect(str(fixture.db))
            try:
                con.execute('DELETE FROM events')
                if rows:con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',rows)
            finally:con.close()
            fixture.plan=fixture.d.prepare_execution_plan(fixture.phase_path,fixture.db)
            fixture.directory=fixture.output/fixture.plan['collection_id']
            fixture.d._atomic_json(fixture.producer,dict(version=1,approved=True,scope='reviewed_producers_and_phase_plan',
                collection_id=fixture.plan['collection_id'],fingerprints=fixture.plan['execution_inputs']['fingerprints']))
        fixture.execute();fixture.approve_shards();fixture.execute()
        state=fixture.read_state();plan=fixture.plan
        names={str(fixture.directory.relative_to(self.root))+'/state.json',
            str(fixture.directory.relative_to(self.root))+'/plan.json',state['attempts'][-1]}
        names.update(plan['execution_inputs']['fingerprints'])
        for entry in state['shards']:
            names.add(entry['acceptance']['path'])
            for kind in ['anchor','candidate','features']:
                names.update(entry[kind]['fingerprints'])
                m=load_run_manifest(self.root/entry[kind]['directory']/'run.json')
                names.update(m['identity']['code_hashes']);names.update(m['identity']['input_hashes'])
        self.expected=self.root/'artifacts/acceptance/collection.json'
        self.expected.write_text(canonical_json(dict(version=1,approved=True,scope='reviewed_development_collection',
            collection_id=plan['collection_id'],complete_attempt_report=state['attempts'][-1],
            fingerprints={n:sha256_file(self.root/n) for n in sorted(names)})))

    def test_complete_tiny_collection_has_exhaustive_QYC_and_explicit_sampled_F_scope(self):
        result = verify(self.root, self.expected)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['counts'], {'queries': 4, 'labels': 2, 'candidates': 8, 'features': 8})
        self.assertEqual(result['scope']['QYC'], 'exhaustive_source_relations')
        self.assertEqual(result['scope']['F_values'], 'deterministic_sample_only')
        self.assertEqual(result['formula_checks'], result['sample_pairs'] * 18)
        self.assertEqual(result['fits'], 0)

    def test_fresh_resealed_wrong_aggregate_counts_are_not_verified(self):
        import json
        from scripts.protocol_manifest import canonical_json, sha256_file
        approval = json.loads(self.expected.read_text())
        name = approval['complete_attempt_report']
        report = json.loads((self.root/name).read_text())
        report['collection']['counts']['queries'] += 1
        (self.root/name).write_text(canonical_json(report))
        approval['fingerprints'][name] = sha256_file(self.root/name)
        self.expected.write_text(canonical_json(approval))
        with self.assertRaisesRegex(ValueError, 'collection.report_counts'):
            verify(self.root, self.expected)

    def rewrite_output(self, label, statement):
        """Corrupt tiny fixture data, then refresh its complete synthetic lineage."""
        import json
        import duckdb
        from scripts.protocol_manifest import canonical_json, sha256_file
        state_path = self.fixture.directory/'state.json'
        state = json.loads(state_path.read_text())
        kind = {'queries':'anchor','labels':'anchor','candidates':'candidate','features':'features'}[label]
        entry = state['shards'][0]
        manifest = json.loads((self.root/entry[kind]['directory']/'run.json').read_text())
        path = self.root/manifest['artifact_refs'][label]
        con = duckdb.connect(':memory:')
        try:
            con.execute('SET threads=2')
            con.execute("SET memory_limit='128MB'")
            con.read_parquet(str(path)).create_view('input')
            con.execute('CREATE TABLE changed AS '+statement)
            temporary = path.with_suffix('.new.parquet')
            con.execute('COPY changed TO ? (FORMAT PARQUET)',[str(temporary)])
            temporary.replace(path)
        finally:
            con.close()
        self.reseal_lineage()

    def reseal_lineage(self):
        """Refresh synthetic bytes after corruption; never repair semantic fields."""
        import json
        from scripts.protocol_manifest import canonical_json, sha256_file
        state_path = self.fixture.directory/'state.json'
        state = json.loads(state_path.read_text())
        def read(name):return json.loads((self.root/name).read_text())
        def write(name,value):(self.root/name).write_text(canonical_json(value)+'\n')
        def refreshed(pins):return {name:sha256_file(self.root/name) for name in pins}
        import hashlib
        for entry in state['shards']:
            previous_candidate_id=entry['candidate']['run_id']
            am = read(entry['anchor']['directory']+'/run.json')
            cm_name = entry['candidate']['directory']+'/run.json'
            cm = read(cm_name)
            cm['identity']['input_hashes'] = refreshed(cm['identity']['input_hashes'])
            cm['run_id'] = hashlib.sha256(canonical_json(cm['identity']).encode()).hexdigest()
            write(cm_name,cm)
            cr_name = entry['candidate']['directory']+'/report.json'
            cr = read(cr_name);cr['run_id']=cm['run_id'];write(cr_name,cr)
            entry['candidate']['run_id']=cm['run_id']
            ap_name=entry['acceptance']['path'];ap=read(ap_name)
            ap.update(anchor_run_id=am['run_id'],candidate_run_id=cm['run_id'],fingerprints=refreshed(ap['fingerprints']))
            write(ap_name,ap);entry['acceptance']['sha256']=sha256_file(self.root/ap_name)
            fm_name=entry['features']['directory']+'/run.json';fm=read(fm_name)
            fr_name=entry['features']['directory']+'/report.json';fr=read(fr_name)
            selections=[n for n in fm['identity']['input_hashes'] if '/selections/' in n]
            selection=read(selections[0]);selection['source_candidate_run']=cm['run_id'];write(selections[0],selection)
            fm['identity']['input_hashes']=refreshed(fm['identity']['input_hashes'])
            fm['run_id']=hashlib.sha256(canonical_json(fm['identity']).encode()).hexdigest();write(fm_name,fm)
            if fr.get('candidate_run_id')==previous_candidate_id:fr['candidate_run_id']=cm['run_id']
            fr.update(run_id=fm['run_id'],selection=selection,
                      output_sha256=sha256_file(self.root/fm['artifact_refs']['features']))
            write(fr_name,fr);entry['features']['run_id']=fm['run_id']
            for kind in ['anchor','candidate','features']:
                entry[kind]['fingerprints']=refreshed(entry[kind]['fingerprints'])
        write(str(state_path.relative_to(self.root)),state)
        approval=json.loads(self.expected.read_text());approval['fingerprints']=refreshed(approval['fingerprints'])
        self.expected.write_text(canonical_json(approval)+'\n')

    def test_fresh_resealed_shard_approval_cannot_choose_its_own_input_scope(self):
        import json
        from scripts.protocol_manifest import canonical_json
        for case in ['queries','candidates','query_coverage','code','source','extra','queries_and_candidates']:
            with self.subTest(case=case):
                if case!='queries':self.build()
                entry=self.fixture.read_state()['shards'][0]
                def read(name):return json.loads((self.root/name).read_text())
                def write(name,value):(self.root/name).write_text(canonical_json(value)+'\n')
                am=read(entry['anchor']['directory']+'/run.json')
                cm=read(entry['candidate']['directory']+'/run.json')
                ap=read(entry['acceptance']['path'])
                fn=entry['features']['directory']+'/run.json';fm=read(fn)
                if case=='extra':
                    name='pyproject.toml'
                    from scripts.protocol_manifest import sha256_file
                    ap['fingerprints'][name]=sha256_file(self.root/name)
                    fm['identity']['input_hashes'][name]=ap['fingerprints'][name]
                else:
                    names=([am['artifact_refs']['queries'],cm['artifact_refs']['candidates']] if case=='queries_and_candidates' else
                        [am['artifact_refs']['queries']] if case=='queries' else
                        [cm['artifact_refs'][case]] if case in ['candidates','query_coverage'] else
                        ['scripts/anchor_pilot.py'] if case=='code' else list(am['identity']['input_hashes']))
                    for name in names:
                        del ap['fingerprints'][name]
                        del fm['identity']['input_hashes'][name]
                write(entry['acceptance']['path'],ap);write(fn,fm)
                self.reseal_lineage()
                with self.assertRaisesRegex(ValueError,'lineage.shard_approval_scope|lineage.child_source'):
                    verify(self.root,self.expected)

    def corrupt_report_link(self,kind,field):
        import json
        from scripts.protocol_manifest import canonical_json
        entry=self.fixture.read_state()['shards'][0]
        name=entry[kind]['directory']+'/report.json'
        report=json.loads((self.root/name).read_text());report[field]='a'*64
        (self.root/name).write_text(canonical_json(report)+'\n')
        self.reseal_lineage()

    def test_fresh_resealed_candidate_report_requires_actual_anchor_id(self):
        self.corrupt_report_link('candidate','anchor_run_id')
        with self.assertRaisesRegex(ValueError,'lineage.candidate_report_ids'):
            verify(self.root,self.expected)

    def test_fresh_resealed_feature_report_requires_actual_anchor_id(self):
        self.corrupt_report_link('features','anchor_run_id')
        with self.assertRaisesRegex(ValueError,'lineage.feature_report_ids'):
            verify(self.root,self.expected)

    def test_fresh_resealed_feature_report_requires_actual_candidate_id(self):
        self.corrupt_report_link('features','candidate_run_id')
        with self.assertRaisesRegex(ValueError,'lineage.feature_report_ids'):
            verify(self.root,self.expected)

    def test_fresh_resealed_feature_value_is_rejected_by_source_formula(self):
        self.rewrite_output('features','SELECT * REPLACE(user_view_7d+1 AS user_view_7d) FROM input')
        with self.assertRaisesRegex(ValueError,'F.formula.user_view_7d'):
            verify(self.root,self.expected)

    def test_fresh_resealed_fullY_cannot_be_dropped(self):
        self.rewrite_output('labels','SELECT * FROM input WHERE false')
        with self.assertRaisesRegex(ValueError,'Y.source_relation'):
            verify(self.root,self.expected)

    def test_fresh_resealed_zero_purchase_query_cannot_be_dropped(self):
        self.rewrite_output('queries','SELECT * FROM input ORDER BY user_id LIMIT 1')
        with self.assertRaisesRegex(ValueError,'orphan|Q.source_relation'):
            verify(self.root,self.expected)

    def test_fresh_resealed_candidate_tie_rank_cannot_change(self):
        self.rewrite_output('candidates','SELECT * REPLACE(popular_source_rank+1 AS popular_source_rank) FROM input')
        with self.assertRaisesRegex(ValueError,'C.source_relation'):
            verify(self.root,self.expected)

    def test_fresh_resealed_missing_flag_is_rejected(self):
        self.rewrite_output('features','SELECT * REPLACE(NOT pair_view_recency_seconds_missing AS pair_view_recency_seconds_missing) FROM input')
        with self.assertRaisesRegex(ValueError,'F.range_null.pair_view_recency_seconds'):
            verify(self.root,self.expected)

    def test_duplicate_feature_keys_fail_before_formula_sample(self):
        self.rewrite_output('features','SELECT * FROM input UNION ALL SELECT * FROM input LIMIT 5')
        with self.assertRaisesRegex(ValueError,'f.unique'):
            verify(self.root,self.expected)

    def test_default_CLI_is_readonly_and_explicit_evidence_is_exclusive(self):
        import contextlib,io,json
        from scripts.verify_development import main
        from scripts.protocol_manifest import sha256_file
        before={str(p.relative_to(self.root)):sha256_file(p) for p in self.root.rglob('*') if p.is_file()}
        args=['--project-root',str(self.root),'--expectations',str(self.expected.relative_to(self.root))]
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(main(args),0)
        after={str(p.relative_to(self.root)):sha256_file(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(json.loads(output.getvalue())['status'],'verified')
        evidence=self.root/'artifacts/evidence.json'
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main(args+['--evidence-out','artifacts/evidence.json']),0)
        old=evidence.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main(args+['--evidence-out','artifacts/evidence.json']),1)
        self.assertEqual(evidence.read_bytes(),old)

    def test_deadline_failure_has_partial_evidence_without_success_or_writes(self):
        from scripts.verify_development import VerificationError
        with self.assertRaises(VerificationError) as failure:
            verify(self.root,self.expected,seconds=1e-9)
        result=failure.exception.evidence
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['completed'],[])
        self.assertEqual(result['failure_gate'],'budget.deadline')
        self.assertIn('resources',result)
        self.assertNotIn('acceptance_written',result)

    def test_rss_failure_is_an_explicit_resource_gate(self):
        from scripts.verify_development import VerificationError
        with self.assertRaises(VerificationError) as failure:
            verify(self.root,self.expected,rss_bytes=1)
        self.assertEqual(failure.exception.evidence['failure_gate'],'budget.rss')

    def test_paths_cannot_escape_project_by_traversal_or_symlink(self):
        import tempfile
        with tempfile.TemporaryDirectory() as outside:
            path=Path(outside)/'expectations.json';path.write_bytes(self.expected.read_bytes())
            link=self.root/'escape.json';link.symlink_to(path)
            for bad in ['../escape.json','escape.json',str(path)]:
                with self.subTest(path=bad),self.assertRaises(ValueError):verify(self.root,bad)

    def test_exact_physical_F_type_is_checked_before_values(self):
        self.rewrite_output('features','SELECT * REPLACE(user_view_7d::DOUBLE AS user_view_7d) FROM input')
        with self.assertRaisesRegex(ValueError,'schema.f'):
            verify(self.root,self.expected)

    @staticmethod
    def complex_rows():
        return [
            ('2019-10-01 00:00:00','view',40,1,100,'old'),
            ('2019-10-01 00:00:00','view',10,1,100,'old'),
            ('2019-10-07 18:00:00','view',10,1,100,'old'),
            ('2019-10-07 18:00:00','view',10,None,None,None),
            ('2019-10-07 19:00:00','purchase',20,2,200,'two'),
            ('2019-10-07 19:00:00','purchase',40,2,200,'two'),
            ('2019-10-07 22:00:00','view',50,2,None,None),
            ('2019-10-07 23:00:00','view',777,None,200,'two'),
            ('2019-10-08 00:00:00','purchase',10,1,999,'new'),
            ('2019-10-08 01:00:00','purchase',999,1,999,'new'),
            ('2019-10-08 12:00:00','view',30,2,300,None),
            ('2019-10-09 00:00:00','purchase',30,2,300,None)]

    def test_global_peers_historical_categories_expiry_fullprefix_and_coldY(self):
        self.build(self.complex_rows())
        result=verify(self.root,self.expected)
        self.assertEqual(result['counts']['queries'],4)
        self.assertEqual(result['counts']['labels'],3)
        self.assertEqual(result['population'],dict(mature_empty_Y_queries=2,empty_C_queries=0,fullY_outside_C=1))
        self.assertGreater(result['sampling'][0]['strata']['category_ambiguous']['available_pairs'],0)
        self.assertGreater(result['sampling'][0]['strata']['category_missing']['available_pairs'],0)

    def test_cold_fullY_target_outside_C_is_required_even_with_fresh_seals(self):
        self.build(self.complex_rows())
        self.rewrite_output('labels','SELECT * FROM input WHERE product_id<>999')
        with self.assertRaisesRegex(ValueError,'Y.source_relation'):
            verify(self.root,self.expected)

    def test_category_denominator_cannot_be_restricted_to_C(self):
        self.build(self.complex_rows())
        # Only off-C product777 contributes category200 view denominator.
        self.rewrite_output('features','SELECT * REPLACE(CASE WHEN category_view_7d IS NULL THEN NULL ELSE 0::BIGINT END AS category_view_7d) FROM input')
        with self.assertRaisesRegex(ValueError,'F.formula.category_view_7d'):
            verify(self.root,self.expected)

    def test_zero_target_and_empty_C_queries_are_retained_in_population(self):
        self.build([('2019-10-07 18:00:00','view',10,1,100,'one'),
                    ('2019-10-07 18:00:00','cart',None,2,None,None)])
        result=verify(self.root,self.expected)
        self.assertEqual(result['counts'],dict(queries=4,labels=0,candidates=2,features=2))
        self.assertEqual(result['population'],dict(mature_empty_Y_queries=4,empty_C_queries=2,fullY_outside_C=0))

    def test_failed_aggregation_attempt_cannot_be_verified_complete(self):
        import json
        from unittest.mock import patch
        from scripts import development_collection
        from scripts.protocol_manifest import canonical_json,sha256_file
        from scripts.verify_development import VerificationError
        with patch.object(development_collection,'aggregate_collection',
                          side_effect=ValueError('synthetic aggregation failure')) as aggregate:
            with self.assertRaisesRegex(ValueError,'synthetic aggregation failure'):
                self.build([])
        aggregate.assert_called_once()
        fixture=self.fixture;state=fixture.read_state()
        self.assertEqual(state['status'],'failed')
        names={str(fixture.directory.relative_to(self.root))+'/state.json',
               str(fixture.directory.relative_to(self.root))+'/plan.json',state['attempts'][-1]}
        names.update(fixture.plan['execution_inputs']['fingerprints'])
        expected=self.root/'artifacts/acceptance/failed-collection.json'
        expected.write_text(canonical_json(dict(version=1,approved=True,scope='reviewed_development_collection',
            collection_id=fixture.plan['collection_id'],complete_attempt_report=state['attempts'][-1],
            fingerprints={n:sha256_file(self.root/n) for n in names})))
        with self.assertRaises(VerificationError) as failure:verify(self.root,expected)
        self.assertEqual(failure.exception.evidence['failure_gate'],'lineage.complete_attempt')
        self.assertEqual(failure.exception.evidence['status'],'failed')
        self.assertNotIn('counts',failure.exception.evidence)

    def test_all_empty_source_is_verified_with_typed_empty_QYCF_and_zero_population(self):
        self.build([])
        result=verify(self.root,self.expected)
        self.assertEqual(result['status'],'verified')
        self.assertEqual(result['counts'],dict(queries=0,labels=0,candidates=0,features=0))
        self.assertEqual(result['population'],dict(mature_empty_Y_queries=0,empty_C_queries=0,fullY_outside_C=0))
        self.assertEqual(result['completed'],[
            'lineage','shard_0_QYC','shard_0_F','shard_1_QYC','shard_1_F'])
        self.assertEqual(result['sample_pairs'],0)
        self.assertEqual(result['formula_checks'],0)
        self.assertEqual(result['fits'],0)

    def test_reordered_peers_and_future_suffix_do_not_change_verified_relations(self):
        rows=self.complex_rows();self.build(rows)
        first=verify(self.root,self.expected)
        future=[('2019-10-10 00:00:00','purchase',888,1,None,None),
                ('2019-10-10 00:00:00','view',10,None,777,'future')]
        self.build(list(reversed(rows))+future)
        second=verify(self.root,self.expected)
        self.assertEqual(first['counts'],second['counts'])
        self.assertEqual(first['population'],second['population'])
        self.assertEqual(first['sample_pairs'],second['sample_pairs'])

    def test_fresh_project_location_with_spaces_has_no_machine_root_dependency(self):
        import tempfile,shutil
        with tempfile.TemporaryDirectory() as parent:
            clone=Path(parent)/'fresh project with spaces'
            shutil.copytree(self.root,clone)
            result=verify(clone,self.expected.relative_to(self.root))
        self.assertEqual(result['counts'],dict(queries=4,labels=2,candidates=8,features=8))

    def test_engine_open_failure_preserves_failed_evidence_after_lineage(self):
        from unittest.mock import patch
        from scripts.verify_development import VerificationError
        with patch('duckdb.connect',side_effect=OSError('synthetic engine open failure')):
            with self.assertRaises(VerificationError) as failure:verify(self.root,self.expected)
        self.assertEqual(failure.exception.evidence['status'],'failed')
        self.assertEqual(failure.exception.evidence['completed'],['lineage'])
        self.assertEqual(failure.exception.evidence['failure_gate'],'verification.input_or_engine_error')

    def test_runtime_version_must_match_pinned_lock_before_engine_use(self):
        from unittest.mock import patch
        from scripts.verify_development import VerificationError
        with patch('duckdb.__version__','0.0.0'):
            with self.assertRaises(VerificationError) as failure:verify(self.root,self.expected)
        self.assertEqual(failure.exception.evidence['failure_gate'],'runtime.duckdb_version')

    def test_fresh_resealed_plan_cannot_change_binding_scope_or_typed_registry(self):
        import json,hashlib
        from copy import deepcopy
        from scripts.protocol_manifest import canonical_json,sha256_file
        from scripts.verify_development import VerificationError
        original=json.loads(self.expected.read_text())
        directory=self.fixture.directory
        plan0=json.loads((directory/'plan.json').read_text());state0=json.loads((directory/'state.json').read_text())
        report0=json.loads((self.root/original['complete_attempt_report']).read_text())
        registry=self.root/plan0['identity']['phase']['feature_registry'];registry_bytes=registry.read_bytes()
        for case in ['source','registry','code','phase','extra','typed_registry']:
            with self.subTest(case=case):
                plan,state,report,expect=[deepcopy(x) for x in [plan0,state0,report0,original]]
                if case in ['source','registry']:plan['identity'][case+'_sha256']='a'*64
                elif case=='code':plan['identity']['code_hashes']['scripts/manual_features.py']='b'*64
                elif case=='phase':plan['identity']['phase']['name']='different-phase-body'
                elif case=='extra':
                    extra=self.root/'extra.txt';extra.write_text('tiny extra input')
                    plan['execution_inputs']['fingerprints']['extra.txt']=sha256_file(extra)
                    expect['fingerprints']['extra.txt']=sha256_file(extra)
                else:
                    spec=json.loads(registry_bytes);spec['version']=True;registry.write_text(canonical_json(spec))
                    name=str(registry.relative_to(self.root));digest=sha256_file(registry)
                    plan['identity']['registry_sha256']=digest
                    plan['execution_inputs']['fingerprints'][name]=digest;expect['fingerprints'][name]=digest
                cid=hashlib.sha256(canonical_json(plan['identity']).encode()).hexdigest()
                plan['collection_id']=state['collection_id']=report['collection_id']=cid
                target=directory.parent/cid;target.mkdir(exist_ok=True)
                report_name='artifacts/fault-'+case+'.json';state['attempts'][-1]=report_name
                for path,value in [(target/'plan.json',plan),(target/'state.json',state),(self.root/report_name,report)]:
                    path.write_text(canonical_json(value))
                for old in [str(directory.relative_to(self.root))+'/plan.json',str(directory.relative_to(self.root))+'/state.json',original['complete_attempt_report']]:
                    expect['fingerprints'].pop(old)
                for path in [target/'plan.json',target/'state.json',self.root/report_name]:
                    expect['fingerprints'][str(path.relative_to(self.root))]=sha256_file(path)
                expect.update(collection_id=cid,complete_attempt_report=report_name)
                self.expected.write_text(canonical_json(expect))
                try:
                    with self.assertRaises(VerificationError) as failure:verify(self.root,self.expected)
                    expected_gate={'phase':'lineage.phase_body','extra':'lineage.execution_scope',
                        'typed_registry':'unsupported.registry_manual18'}.get(case,'lineage.identity_binding')
                    self.assertEqual(failure.exception.evidence['failure_gate'],expected_gate)
                finally:registry.write_bytes(registry_bytes)

    def test_cleanup_resource_overrun_cannot_return_verified(self):
        import duckdb, time, resource, sys
        from unittest.mock import patch
        from scripts.verify_development import VerificationError
        real_connect,real_wall,real_cpu,real_usage=duckdb.connect,time.monotonic,time.process_time,resource.getrusage
        for case in ['wall','cpu','rss']:
            changed=[False]
            class Connection:
                def __init__(self,*args,**kwargs):self.actual=real_connect(*args,**kwargs)
                def __getattr__(self,name):return getattr(self.actual,name)
                def close(self):self.actual.close();changed[0]=True
            def usage(which):
                value=real_usage(which)
                if changed[0] and case=='rss':
                    fields=list(value);fields[2]=(512*2**20+1) if sys.platform=='darwin' else 512*1024+1
                    return resource.struct_rusage(fields)
                return value
            with self.subTest(case=case),patch('duckdb.connect',side_effect=Connection), \
                 patch('time.monotonic',side_effect=lambda:real_wall()+(700 if changed[0] and case=='wall' else 0)), \
                 patch('time.process_time',side_effect=lambda:real_cpu()+(700 if changed[0] and case=='cpu' else 0)), \
                 patch('resource.getrusage',side_effect=usage):
                with self.assertRaises(VerificationError) as failure:verify(self.root,self.expected)
                self.assertEqual(failure.exception.evidence['status'],'failed')
                self.assertEqual(failure.exception.evidence['failure_gate'],'budget.rss' if case=='rss' else 'budget.deadline')

    def test_close_failure_and_unavailable_final_counters_preserve_failed_evidence(self):
        import duckdb,resource
        from unittest.mock import patch
        from scripts.verify_development import VerificationError
        real_connect,real_usage=duckdb.connect,resource.getrusage
        for case in ['close','summary']:
            changed=[False];post_close_reads=[0]
            class Connection:
                def __init__(self,*args,**kwargs):self.actual=real_connect(*args,**kwargs)
                def __getattr__(self,name):return getattr(self.actual,name)
                def close(self):
                    self.actual.close();changed[0]=True
                    if case=='close':raise OSError('synthetic close failure')
            def usage(which):
                if changed[0] and case=='summary':
                    post_close_reads[0]+=1
                    if post_close_reads[0]>=2:raise OSError('synthetic final counters unavailable')
                return real_usage(which)
            with self.subTest(case=case),patch('duckdb.connect',side_effect=Connection),patch('resource.getrusage',side_effect=usage):
                with self.assertRaises(VerificationError) as failure:verify(self.root,self.expected)
                result=failure.exception.evidence
                self.assertEqual(result['status'],'failed')
                self.assertIn('lineage',result['completed'])
                self.assertIn('resources',result)
                self.assertEqual(result['failure_gate'],'cleanup.close' if case=='close' else 'resources.summary')
