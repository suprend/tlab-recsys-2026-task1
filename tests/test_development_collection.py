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


if __name__=='__main__':unittest.main()
