"""Phase boundaries, original v1 shard caps and reserved confirmation guard."""
from copy import deepcopy
from pathlib import Path
import unittest

from scripts.development_collection import (authorize_phase_execution,build_collection_plan,
    load_phase,shard_protocols,validate_phase,validate_phase_set)
from scripts.protocol_manifest import load_protocol,validate_protocol

ROOT=Path(__file__).resolve().parents[1]


class DevelopmentCollectionTests(unittest.TestCase):
    def setUp(self):
        self.base=load_protocol(ROOT/'configs/protocols/clock-48h.json')
        self.phases={r:load_phase(ROOT/('configs/development/'+r+'.json'),self.base)
                     for r in ['train','selection','confirmation']}

    def test_calendar_and_five_shards_cover13_train_days_without_changing_v1_semantics(self):
        roles=validate_phase_set(list(self.phases.values()),self.base)
        self.assertEqual(set(roles),{'train','selection','confirmation'})
        shards=shard_protocols(self.phases['train'],self.base)
        self.assertEqual(len(shards),5)
        self.assertEqual([s['budget']['max_anchors'] for s in shards],[6000,6000,6000,6000,2000])
        self.assertEqual(sum(s['budget']['max_candidate_pairs'] for s in shards),5720000)
        self.assertEqual(shards[0]['pilot']['start'],'2019-10-08T00:00:00Z')
        self.assertEqual(shards[-1]['pilot']['end'],'2019-10-21T00:00:00Z')
        for left,right in zip(shards,shards[1:]):self.assertEqual(left['pilot']['end'],right['pilot']['start'])
        for shard in shards:
            self.assertEqual(validate_protocol(shard),shard)
            for key in ['source','query','target','candidates','history']:
                self.assertEqual(shard[key],self.base[key])

    def test_phase_does_not_turn_output_model_into_early_training_feature(self):
        train=self.phases['train']
        self.assertGreater(train['model_timing']['available_at'],train['range']['start'])
        self.assertEqual(validate_phase(train,self.base),train)
        late=deepcopy(self.phases['selection'])
        late['model_timing']['available_at']='2019-10-22T00:00:01Z'
        with self.assertRaisesRegex(ValueError,'unavailable'):
            validate_phase(late,self.base)

    def test_train_label_cutoff_and_positive_fit_gap_are_enforced(self):
        for update in [{'fit_data_cutoff':'2019-10-20T00:00:00Z'},
                       {'available_at':'2019-10-21T00:00:00Z'}]:
            phase=deepcopy(self.phases['train']);phase['model_timing'].update(update)
            with self.assertRaises(ValueError):validate_phase(phase,self.base)
        phase=deepcopy(self.phases['train'])
        phase['label_available_before']='2019-10-20T00:00:00Z'
        with self.assertRaises(ValueError):validate_phase(phase,self.base)

    def test_right_closed_label_needs_strictly_later_availability(self):
        base=deepcopy(self.base);base['target']['include_end']=True
        with self.assertRaisesRegex(ValueError,'not matured'):
            validate_phase(self.phases['train'],base)

    def test_final_holdout_and_confirmation_cannot_be_silently_opened(self):
        with self.assertRaises(ValueError):authorize_phase_execution(self.phases['confirmation'],self.base)
        phase=deepcopy(self.phases['confirmation']);phase['lock_required']=False
        with self.assertRaises(ValueError):validate_phase(phase,self.base)
        phase=deepcopy(self.phases['selection']);phase['range']['end']='2019-10-27T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'holdout'):validate_phase(phase,self.base)
        phase=deepcopy(self.phases['selection']);phase['role']='test'
        with self.assertRaisesRegex(ValueError,'not final test'):validate_phase(phase,self.base)

    def test_confirmation_lock_requires_strong_control_selected_branch_and_timely_freeze(self):
        phase=self.phases['confirmation']
        lock=dict(version=1,approved=True,frozen_before='2019-10-24T00:00:00Z',
                  strong_baseline_sha256='a'*64,selected_branch_sha256='b'*64)
        authorize_phase_execution(phase,self.base,lock)
        for change in [{'approved':False},{'frozen_before':'2019-10-24T00:00:01Z'},
                       {'frozen_before':'2019-10-20T00:00:00Z'},
                       {'strong_baseline_sha256':'not-a-hash'}]:
            invalid={**lock,**change}
            with self.assertRaises(ValueError):authorize_phase_execution(phase,self.base,invalid)
        with self.assertRaises(ValueError):authorize_phase_execution(self.phases['selection'],self.base,lock)

    def test_phase_set_rejects_changed_semantics_duplicate_roles_and_label_overlap(self):
        for mutate in [lambda p:p[2].update(feature_registry='configs/other.json'),
                       lambda p:p[2].update(role='selection',lock_required=False),
                       lambda p:p[1].update(label_available_before='2019-10-25T00:00:00Z')]:
            phases=deepcopy(list(self.phases.values()));mutate(phases)
            with self.assertRaises(ValueError):validate_phase_set(phases,self.base)

    def test_unknown_fields_boolean_caps_bad_timestamps_and_oversized_shards_reject(self):
        for change in [{'surprise':True},{'shard_days':4},{'shard_days':True}]:
            phase={**self.phases['train'],**change}
            with self.assertRaises(ValueError):validate_phase(phase,self.base)
        for timestamp in ['2019-10-08T00:00:00','2019-10-08T01:00:00Z','2019-10-8T00:00:00Z']:
            phase=deepcopy(self.phases['train']);phase['range']['start']=timestamp
            with self.assertRaises(ValueError):validate_phase(phase,self.base)
        phase=deepcopy(self.phases['train']);phase['budget']['max_queries']=26001
        with self.assertRaises(ValueError):validate_phase(phase,self.base)

    def test_planned_identity_is_stable_and_does_not_claim_execution(self):
        kwargs=dict(registry_sha256='a'*64,source_sha256='b'*64,
                    code_hashes={'uv.lock':'c'*64,'scripts/development_collection.py':'d'*64})
        first=build_collection_plan(self.phases['train'],self.base,**kwargs)
        self.assertEqual(first,build_collection_plan(self.phases['train'],self.base,**kwargs))
        self.assertEqual(first['identity']['status'],'planned_not_executed')
        other=build_collection_plan(self.phases['train'],self.base,**{**kwargs,'registry_sha256':'e'*64})
        self.assertNotEqual(first['collection_id'],other['collection_id'])
        self.assertNotIn('measured_queries',first)


class DevelopmentRuntimeTests(unittest.TestCase):
    """Actual tiny Q/Y/C/F producers and simulated independent approvals."""
    def setUp(self):
        import contextlib
        import tempfile
        import shutil
        import duckdb
        from unittest.mock import patch
        from scripts import development_collection as d, anchor_pilot as a, candidate_pilot as c
        from scripts import manual_features as m, heuristic_baselines as h
        self.d, self.a, self.c = d, a, c
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for name in [*d.PRODUCER_CODE, 'pyproject.toml', 'configs/features/manual-18.json']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, path)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for module in [d, a, c, m, h]:
            self.stack.enter_context(patch.object(module, 'ROOT', self.root))
        base = load_protocol(ROOT / 'configs/protocols/clock-48h.json')
        base['query']['max_users_per_day'] = 2
        base['candidates'].update(popular_limit=3, recent_limit=3, max_unique=6)
        base['budget'] = dict(max_anchors=6, max_candidate_pairs=36)
        self.base = base
        self.phase = load_phase(ROOT / 'configs/development/train.json', load_protocol(ROOT / 'configs/protocols/clock-48h.json'))
        self.phase.update(range=dict(start='2019-10-08T00:00:00Z', end='2019-10-10T00:00:00Z'),
                          label_available_before='2019-10-10T00:00:00Z', shard_days=1,
                          model_timing=dict(fit_data_cutoff='2019-10-10T00:00:00Z', available_at='2019-10-11T00:00:00Z'),
                          budget=dict(max_queries=4, max_candidate_pairs=24, wall_seconds=60))
        self.phase_path = self.root / 'configs/development/train.json'
        self.phase_path.parent.mkdir(parents=True)
        d._atomic_json(self.phase_path, self.phase)
        basepath = self.root / self.phase['base_protocol']
        basepath.parent.mkdir(parents=True, exist_ok=True)
        d._atomic_json(basepath, base)
        self.db = self.root / 'data/tiny.duckdb'
        self.db.parent.mkdir()
        con = duckdb.connect(str(self.db))
        try:
            con.execute('CREATE TABLE ingest_metadata(note VARCHAR)')
            con.execute("INSERT INTO ingest_metadata VALUES ('tiny synthetic source')")
            con.execute('''CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,
                          user_id BIGINT,category_id BIGINT,category_code VARCHAR)''')
            con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)', [
                ('2019-10-07 18:00:00', 'view', 10, 1, 100, 'a'),
                ('2019-10-07 20:00:00', 'purchase', 20, 2, 200, 'b'),
                ('2019-10-08 00:00:00', 'purchase', 10, 1, 100, 'a'),
                ('2019-10-08 12:00:00', 'view', 30, 2, 300, None),
                ('2019-10-09 00:00:00', 'purchase', 30, 2, 300, None)])
        finally:
            con.close()
        self.plan = d.prepare_execution_plan(self.phase_path, self.db)
        self.producer = self.root / 'artifacts/acceptance/producer.json'
        self.producer.parent.mkdir(parents=True)
        d._atomic_json(self.producer, dict(version=1, approved=True, scope='reviewed_producers_and_phase_plan',
            collection_id=self.plan['collection_id'], fingerprints=self.plan['execution_inputs']['fingerprints']))
        self.output = self.root / 'artifacts/development'
        self.acceptances = self.root / 'artifacts/acceptance/shards'
        self.directory = self.output / self.plan['collection_id']

    def execute(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return self.d.run_phase(self.phase_path, self.db, self.output,
                producer_approval_path=self.producer, shard_acceptance_dir=self.acceptances)

    def read_state(self):
        return self.d._read_json(self.directory / 'state.json')

    def approve_shards(self):
        """Test fixture simulates an external reviewer, never production logic."""
        from scripts.protocol_manifest import load_run_manifest, sha256_file
        self.acceptances.mkdir(parents=True, exist_ok=True)
        for entry in self.read_state()['shards']:
            pins = {}
            for kind in ['anchor', 'candidate']:
                seal = entry[kind]
                manifest = load_run_manifest(self.root / seal['directory'] / 'run.json')
                pins.update(seal['fingerprints'])
                pins.update(manifest['identity']['code_hashes'])
                pins.update(manifest['identity']['input_hashes'])
            self.d._atomic_json(self.acceptances / (entry['candidate']['run_id'] + '.json'),
                dict(version=1, approved=True, anchor_run_id=entry['anchor']['run_id'],
                     candidate_run_id=entry['candidate']['run_id'], fingerprints=pins))

    def test_actual_producers_wait_for_external_review_then_resume_full_features_and_cache(self):
        first = self.execute()
        self.assertEqual(first['status'], 'waiting_for_shard_review')
        self.assertEqual(len(first['pending']), 2)
        self.assertTrue(all('features' not in e for e in self.read_state()['shards']))
        first_cost = self.read_state()['compute_seconds']
        self.approve_shards()
        complete = self.execute()
        self.assertEqual(complete['status'], 'complete_produced_unreviewed')
        counts = complete['collection']['counts']
        self.assertEqual(counts['queries'], 4)
        self.assertEqual(counts['labels'], 2)
        self.assertEqual(counts['candidates'], counts['features'])
        self.assertEqual(complete['prior_compute_seconds'], first_cost)
        self.assertAlmostEqual(self.read_state()['compute_seconds'], first_cost + complete['seconds'])
        state = self.read_state()
        cached = self.execute()
        self.assertEqual(cached['collection'], complete['collection'])
        self.assertEqual(self.read_state()['shards'], state['shards'])
        self.assertEqual(len(self.read_state()['attempts']), 3)
        self.assertGreater(self.read_state()['compute_seconds'], state['compute_seconds'])

    def test_approval_is_not_inferred_from_fresh_current_hashes_or_scope(self):
        approval = self.d._read_json(self.producer)
        approval['approved'] = False
        self.d._atomic_json(self.producer, approval)
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.execute()
        self.assertFalse((self.directory / 'state.json').exists())
        reports = list(self.output.glob('attempt-*/report.json'))
        self.assertEqual(self.d._read_json(reports[0])['status'], 'failed')
        approval.update(approved=True, scope='output_acceptance')
        self.d._atomic_json(self.producer, approval)
        with self.assertRaisesRegex(ValueError, 'masquerade'):
            self.execute()

    def test_modified_source_code_or_phase_cannot_reuse_reviewed_producer_bundle(self):
        for path in [self.db, self.root / 'scripts/candidate_pilot.py', self.phase_path]:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b'\n')
                try:
                    with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
                        self.execute()
                finally:
                    path.write_bytes(original)

    def test_cached_complete_output_tamper_fails_before_features_even_with_shard_approval(self):
        self.execute()
        self.approve_shards()
        entry = self.read_state()['shards'][0]
        report = self.root / entry['candidate']['directory'] / 'report.json'
        report.write_bytes(report.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Cached output changed'):
            self.execute()
        self.assertEqual(self.read_state()['status'], 'failed')
        self.assertTrue(all('features' not in e for e in self.read_state()['shards']))

    def test_failed_child_preserves_partial_cost_and_never_claims_collection_complete(self):
        from unittest.mock import patch
        with patch.object(self.c, 'run', side_effect=TimeoutError('synthetic candidate timeout')):
            with self.assertRaisesRegex(TimeoutError, 'synthetic candidate timeout'):
                self.execute()
        state = self.read_state()
        self.assertEqual(state['status'], 'failed')
        self.assertGreater(state['compute_seconds'], 0)
        self.assertIn('anchor', state['shards'][0])
        self.assertNotIn('candidate', state['shards'][0])
        audit = self.d._read_json(self.root / state['attempts'][0])
        self.assertEqual(audit['error_type'], 'TimeoutError')
        self.assertTrue(any(s['status'] == 'failed' for s in audit['stages']))

    def test_exhausted_cumulative_budget_and_crash_lock_are_not_silently_reset(self):
        self.execute()
        state = self.read_state()
        state['compute_seconds'] = self.phase['budget']['wall_seconds']
        self.d._atomic_json(self.directory / 'state.json', state)
        with self.assertRaisesRegex(TimeoutError, 'Cumulative'):
            self.execute()
        self.assertEqual(self.read_state(), state)
        lock = self.directory / '.runtime.lock'
        lock.touch()
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertTrue(lock.exists())

    def test_identified_feature_failure_is_preserved_and_normal_resume_completes(self):
        from unittest.mock import patch
        from scripts import manual_features
        self.execute()
        self.approve_shards()
        with patch.object(manual_features, 'create_manual_features', side_effect=TimeoutError('identified F failure')):
            with self.assertRaisesRegex(TimeoutError, 'identified F failure'):
                self.execute()
        state = self.read_state()
        attempt = [a for a in state['shards'][0]['producer_attempts'] if a['kind'] == 'features'][0]
        partial_reports = list((self.root / attempt['output_root']).glob('*/report.json'))
        self.assertEqual(len(partial_reports), 1)
        self.assertEqual(self.d._read_json(partial_reports[0])['status'], 'failed')
        original = partial_reports[0].read_bytes()
        failed_cost = state['compute_seconds']
        complete = self.execute()
        self.assertEqual(complete['status'], 'complete_produced_unreviewed')
        self.assertGreater(self.read_state()['compute_seconds'], failed_cost)
        self.assertEqual(partial_reports[0].read_bytes(), original)
        roots = [a['output_root'] for a in self.read_state()['shards'][0]['producer_attempts'] if a['kind'] == 'features']
        self.assertEqual(len(roots), 2)
        self.assertEqual(len(set(roots)), 2)

    def test_identified_candidate_failure_is_preserved_and_normal_resume_reaches_review(self):
        from unittest.mock import patch
        with patch.object(self.c, 'build_candidates', side_effect=TimeoutError('identified C failure')):
            with self.assertRaisesRegex(TimeoutError, 'identified C failure'):
                self.execute()
        state = self.read_state()
        attempt = [a for a in state['shards'][0]['producer_attempts'] if a['kind'] == 'candidate'][0]
        reports = list((self.root / attempt['output_root']).glob('*/report.json'))
        self.assertEqual(self.d._read_json(reports[0])['status'], 'failed')
        original = reports[0].read_bytes()
        self.assertEqual(self.execute()['status'], 'waiting_for_shard_review')
        self.assertEqual(reports[0].read_bytes(), original)

    def test_identified_anchor_failure_is_preserved_and_normal_resume_reaches_review(self):
        from unittest.mock import patch
        with patch.object(self.a, 'build_pilot', side_effect=TimeoutError('identified QY failure')):
            with self.assertRaisesRegex(TimeoutError, 'identified QY failure'):
                self.execute()
        state = self.read_state()
        attempt = state['shards'][0]['producer_attempts'][0]
        self.assertEqual(attempt['kind'], 'anchor')
        reports = list((self.root / attempt['output_root']).glob('*/report.json'))
        self.assertEqual(self.d._read_json(reports[0])['status'], 'failed')
        original = reports[0].read_bytes()
        self.assertEqual(self.execute()['status'], 'waiting_for_shard_review')
        self.assertEqual(reports[0].read_bytes(), original)

    def test_incomplete_or_duplicated_shards_never_aggregate_as_complete(self):
        self.execute()
        self.approve_shards()
        self.execute()
        state = self.read_state()
        for shards in [state['shards'][:1], [state['shards'][0], state['shards'][0]]]:
            with self.subTest(shards=len(shards)), self.assertRaisesRegex(ValueError, 'shard cover'):
                self.d.aggregate_collection(self.plan, {**state, 'shards': shards})

    def test_confirmation_runtime_refuses_even_valid_schema_lock_before_source_read(self):
        from unittest.mock import patch
        phase = deepcopy(self.phase)
        phase.update(role='confirmation', lock_required=True,
                     model_timing=dict(fit_data_cutoff='2019-10-06T00:00:00Z', available_at='2019-10-07T00:00:00Z'))
        self.d._atomic_json(self.phase_path, phase)
        with patch.object(self.d, '_digest', side_effect=AssertionError('source must stay unread')):
            with self.assertRaisesRegex(ValueError, 'Confirmation runtime'):
                self.execute()


if __name__=='__main__':unittest.main()
