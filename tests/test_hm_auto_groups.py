"""Tiny JSON-only group decisions; no DuckDB, parquet or model calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import hm_auto_groups as groups
from scripts import hm_auto_select as selection

_spec = importlib.util.spec_from_file_location('_hm_prefix_fixture', Path(__file__).with_name('test_hm_auto_select.py'))
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)


class GroupDecisionTests(unittest.TestCase):
    def setUp(self):
        fixture = _fixtures.PrefixMetadataTests(methodName='test_exact_metadata_flow_winner_provenance_and_exclusive_output')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        root_patch = patch.object(groups,'ROOT',self.root)
        root_patch.start();self.addCleanup(root_patch.stop)
        for name,module in [('hm_auto_select.py',selection),('hm_auto_groups.py',groups)]:
            (self.root/'scripts'/name).write_bytes(Path(module.__file__).read_bytes())
        protocol = json.loads((self.root/selection.PROTOCOL).read_text(encoding='utf-8'))
        protocol['group_fallback'] = dict(dimensions=groups.DIMS,step1_fits=10,step2_fits_max=8)
        protocol_sha = _fixtures.write(self.root/selection.PROTOCOL,protocol)
        pin_patch = patch.object(selection,'PROTOCOL_SHA',protocol_sha)
        pin_patch.start();self.addCleanup(pin_patch.stop)
        for fold,point in enumerate((.25,.5)):
            for arm in (2,3,4):
                fixture.change_report(fold,arm,lambda report,p=point: report['validation_metrics'].update(map_at_12_conditional=p))
        self.prefix = selection.prefix_decision(fixture.paths,self.root/'artifacts/hm-auto-v2/decisions/prefix')
        self.manual = fixture.manual
        self.definitions = {}
        offset = 0
        for dimension,width in zip(groups.DIMS,groups.WIDTHS):
            self.definitions[dimension] = sorted(f'g{i}' for i in range(offset,offset+width))
            offset += width
        plan = dict(feature_contract_digest=fixture.feature_digest,
            pool=[dict(name=name,dimension=dimension) for dimension in groups.DIMS for name in self.definitions[dimension]])
        study = dict(format='hm-feature-selection-study-v1',status='prepared',plan=plan,plan_digest=selection.canonical(plan))
        study_sha = _fixtures.write(self.root/'artifacts/hm-campaign/feature-study/manifest.json',study)
        manifest = dict(format='hm-auto-v2-semantic-groups-v1',config_sha256=protocol_sha,
            source_study_sha256=study_sha,manual_names=self.manual['numeric']+self.manual['categorical'],groups={})
        for dimension,width in zip(groups.DIMS,groups.WIDTHS):
            path = f'artifacts/hm-auto-v2/groups/{dimension}_names.json'
            names_sha = _fixtures.write(self.root/path,manifest['manual_names']+self.definitions[dimension])
            manifest['groups'][dimension] = dict(programs=self.definitions[dimension],width=width,names_file=path,names_sha256=names_sha)
        manifest_sha = _fixtures.write(self.root/groups.GROUP_METADATA,manifest)
        group_pin = patch.object(groups,'GROUP_SHA256',manifest_sha)
        group_pin.start();self.addCleanup(group_pin.stop)
        self.first_maps = [[.3125,.375,.5,.5625,.625],[.5625,.625,.75,.5,.4375]]
        self.paths,self.audits,self.reports = self.write_group_audits(1)
        self.output = self.root/'artifacts/hm-auto-v2/decisions/group1'

    def write_group_audits(self,stage,first=None,second_maps=None):
        candidates = groups.DIMS if stage == 1 else [d for d in groups.DIMS if d != first]
        paths,audits,reports = [],[],[]
        previous = [] if stage == 1 else self.definitions[first]
        first_index = groups.DIMS.index(first) if first else None
        for fold,anchor in enumerate(selection.ANCHORS):
            audit = deepcopy(self.fixture.audits[fold])
            audit['fits'] = deepcopy(audit['fits'][:2]) if stage == 1 else [deepcopy(audit['fits'][0])]
            if stage == 2:
                baseline = deepcopy(self.audits[fold]['fits'][2+first_index])
                baseline['arm'] = 1
                audit['fits'].append(baseline)
            report_paths = []
            for offset,dimension in enumerate(candidates):
                template = json.loads(self.fixture.reports[fold][2].read_text(encoding='utf-8'))
                template['features'] = dict(numeric=self.manual['numeric']+previous+self.definitions[dimension],
                    categorical=self.manual['categorical'],contract_digest=self.fixture.feature_digest)
                template['validation_metrics']['map_at_12_conditional'] = self.first_maps[fold][offset] if stage == 1 else second_maps[fold][offset]
                template['fit_identity'] = selection.fit_identity(template)
                directory = (f'artifacts/hm-auto-v2/group1/{dimension}/{anchor}' if stage == 1 else
                             f'artifacts/hm-auto-v2/group2/{first}__{dimension}/{anchor}')
                path = self.root/directory/'report.json'
                report_sha = _fixtures.write(path,template)
                report_paths.append(path)
                audit['fits'].append(dict(arm=offset+2,fit_directory=(self.root/directory).as_posix(),
                    report_sha256=report_sha,fit_identity=template['fit_identity'],metrics=deepcopy(template['validation_metrics']),
                    code={name:dict(recorded_sha256=value,current_source_matches=True) for name,value in self.fixture.report_code.items()}))
                if stage == 2:
                    _fixtures.write(self.root/f'artifacts/hm-auto-v2/group2-names/{first}__{dimension}_names.json',
                                    self.manual['numeric']+self.manual['categorical']+previous+self.definitions[dimension])
            path = self.root/f'artifacts/hm-auto-v2/audits/group{stage}-{anchor}/report.json'
            _fixtures.write(path,audit)
            paths.append(path);audits.append(audit);reports.append(report_paths)
        return paths,audits,reports

    def decide(self):
        return groups.group_decision(self.paths,self.output)

    def change_group_report(self,fold,offset,change):
        path = self.reports[fold][offset]
        report = json.loads(path.read_text(encoding='utf-8'))
        change(report)
        report['fit_identity'] = selection.fit_identity(report)
        sha = _fixtures.write(path,report)
        row = self.audits[fold]['fits'][offset+2]
        row.update(report_sha256=sha,fit_identity=report['fit_identity'],metrics=deepcopy(report['validation_metrics']))
        _fixtures.write(self.paths[fold],self.audits[fold])

    def test_stage1_exact_membership_choice_provenance_and_exclusive_output(self):
        report = self.decide()
        self.assertEqual(report['chosen'],'department_no')
        self.assertEqual(report['selected_groups'],['department_no'])
        self.assertEqual(report['width'],12)
        self.assertEqual(report['selected_names'],self.manual['numeric']+self.manual['categorical']+self.definitions['department_no'])
        self.assertEqual(report['next_action'],'group_step2')
        self.assertFalse(report['run_symmetric_L2'])
        self.assertEqual(len(report['fits']),14)
        self.assertEqual([p['name'] for p in report['stage2_plan']], [d for d in groups.DIMS if d != 'department_no'])
        self.assertIn(groups.PREFIX_DECISION,report['provenance'])
        self.assertIn(groups.GROUP_METADATA,report['provenance'])
        with self.assertRaises(FileExistsError):
            self.decide()

    def test_stage1_no_positive_both_keeps_exact_M_and_untouched_test(self):
        for fold,point in enumerate((.25,.5)):
            for offset in range(5):
                self.change_group_report(fold,offset,lambda report,p=point: report['validation_metrics'].update(map_at_12_conditional=p))
        report = self.decide()
        self.assertIsNone(report['chosen'])
        self.assertEqual(report['width'],0)
        self.assertEqual(report['selected_groups'],[])
        self.assertTrue(report['reuse_exact_M'])
        self.assertFalse(report['run_symmetric_L2'])
        self.assertEqual(report['next_action'],'retain_M_no_test')
        self.assertTrue(report['preserve_untouched_customer_holdout'])

    def test_stage2_strict_marginal_improvement_and_total_width(self):
        first = self.decide()
        maps = [[.625,.75,.5,.4375],[.8125,.875,.75,.9375]]
        paths,_,_ = self.write_group_audits(2,'department_no',maps)
        output = self.root/'artifacts/hm-auto-v2/decisions/group2'
        report = groups.group_decision(paths,output,stage=2)
        self.assertEqual(report['chosen'],'colour_group_code')
        self.assertEqual(report['selected_groups'],['department_no','colour_group_code'])
        self.assertEqual(report['width'],23)
        self.assertEqual(report['baseline']['weekly_maps'],[.5,.75])
        self.assertTrue(report['run_symmetric_L2'])
        self.assertIn(groups.FIRST_DECISION,report['provenance'])
        self.assertEqual(report['selected_programs'],first['selected_programs']+self.definitions['colour_group_code'])

    def test_stage2_no_marginal_gain_retains_first_and_does_not_reset_to_M(self):
        self.decide()
        # Several candidates beat original M but none strictly beats current group on both weeks.
        paths,_,_ = self.write_group_audits(2,'department_no',[[.5,.4375,.5625,.375],[.75,.875,.75,.625]])
        report = groups.group_decision(paths,self.root/'artifacts/hm-auto-v2/decisions/group2',stage=2)
        self.assertIsNone(report['chosen'])
        self.assertEqual(report['selected_groups'],['department_no'])
        self.assertEqual(report['width'],12)
        self.assertFalse(report['reuse_exact_M'])
        self.assertTrue(report['run_symmetric_L2'])

    def test_wrong_audit_order_count_dates_and_source_fail_before_output(self):
        with self.assertRaisesRegex(ValueError,'path/order'):
            groups.group_decision(list(reversed(self.paths)),self.output)
        original = deepcopy(self.audits[0])
        for change in (lambda a:a['fits'].pop(),lambda a:a['collection'].update(anchor='2020-09-16'),
                       lambda a:a.update(checker_sha256='0'*64),lambda a:a.update(status='FAIL')):
            audit = deepcopy(original);change(audit);_fixtures.write(self.paths[0],audit)
            with self.assertRaises(ValueError):self.decide()
            self.assertFalse(self.output.exists())

    def test_reforged_features_recipe_runtime_identity_and_inputs_rejected(self):
        original = self.reports[0][0].read_bytes()
        for change in (lambda r:r['features']['numeric'].reverse(),lambda r:r['hyperparameters'].update(l2_leaf_reg=50),
                       lambda r:r['runtime'].update(threads=2),lambda r:r['inputs'][-1].update(qcy_identity='0'*64)):
            self.reports[0][0].write_bytes(original)
            self.change_group_report(0,0,change)
            with self.assertRaises(ValueError):self.decide()
            self.assertFalse(self.output.exists())

    def test_small_float_roundoff_accepted_but_counts_and_large_drift_rejected(self):
        self.audits[0]['fits'][2]['metrics']['map_at_12_conditional'] += 5e-13
        _fixtures.write(self.paths[0],self.audits[0])
        self.decide()
        for field,value in [('queries',20000.0),('positive_queries',True),('empty_target_queries',18999)]:
            actual = deepcopy(self.audits[0]['fits'][2]['metrics']);actual[field]=value
            with self.assertRaises(ValueError):groups.checked_metrics(actual,self.audits[0]['fits'][2]['metrics'])
        actual = deepcopy(self.audits[0]['fits'][2]['metrics']);actual['map_at_12_conditional'] += 2e-12
        with self.assertRaisesRegex(ValueError,'tolerance'):
            groups.checked_metrics(actual,self.audits[0]['fits'][2]['metrics'])

    def test_rejected_prefix_freshness_membership_and_no_early_output(self):
        prefix_path = self.root/groups.PREFIX_DECISION
        original = prefix_path.read_bytes()
        decision = json.loads(original.decode('utf-8'));decision['chosen']='prefix1'
        _fixtures.write(prefix_path,decision)
        with self.assertRaisesRegex(ValueError,'rejected-prefix'):self.decide()
        prefix_path.write_bytes(original)
        with (self.root/'artifacts/hm-auto-v2/prefix1_names.json').open('a',encoding='utf-8') as stream:stream.write(' ')
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):self.decide()
        self.assertFalse(self.output.exists())

    def test_nonfinite_and_duplicate_json_and_wrong_fit_hash_fail_closed(self):
        original = self.paths[0].read_text(encoding='utf-8')
        for token in ('NaN','Infinity','1e999'):
            self.paths[0].write_text(original.replace('0.3125',token),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Nonfinite'):self.decide()
        self.paths[0].write_text('{"status":"PASS","status":"FAIL"}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.decide()
        self.paths[0].write_text(original,encoding='utf-8')
        self.audits[0]['fits'][2]['report_sha256']='0'*64
        _fixtures.write(self.paths[0],self.audits[0])
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):self.decide()
        self.assertFalse(self.output.exists())

    def test_stage2_tampered_accepted_first_decision_rejected(self):
        self.decide()
        path = self.root/groups.FIRST_DECISION
        report = json.loads(path.read_text(encoding='utf-8'));report['chosen']='index_code'
        _fixtures.write(path,report)
        paths,_,_ = self.write_group_audits(2,'department_no',[[.625]*4,[.875]*4])
        with self.assertRaisesRegex(ValueError,'first-group decision'):
            groups.group_decision(paths,self.root/'artifacts/hm-auto-v2/decisions/group2',stage=2)
        self.assertFalse((self.root/'artifacts/hm-auto-v2/decisions/group2').exists())

    def test_group_membership_and_prefix_provenance_cannot_be_forged(self):
        path = self.root/groups.GROUP_METADATA
        original = path.read_bytes()
        manifest = json.loads(original.decode('utf-8'))
        manifest['groups']['product_type_no']['programs'][0] = 'outside-frozen-pool'
        changed_sha = _fixtures.write(path,manifest)
        with patch.object(groups,'GROUP_SHA256',changed_sha):
            with self.assertRaisesRegex(ValueError,'membership'):self.decide()
        path.write_bytes(original)
        prefix_path = self.root/groups.PREFIX_DECISION
        prefix = json.loads(prefix_path.read_text(encoding='utf-8'))
        prefix['provenance'].pop(selection.PROTOCOL)
        _fixtures.write(prefix_path,prefix)
        with self.assertRaisesRegex(ValueError,'incomplete'):self.decide()
        self.assertFalse(self.output.exists())

    def test_metadata_only_flow_has_no_data_or_model_files_available(self):
        self.assertFalse(list(self.root.rglob('*.parquet')))
        self.assertFalse(list(self.root.rglob('*.cbm')))
        self.assertFalse(list(self.root.rglob('*.duckdb')))
        result = self.decide()
        self.assertTrue(all(Path(name).suffix in ('.json','.py') for name in result['provenance']))

    def test_stage2_is_not_allowed_after_zero_first_group(self):
        for fold,point in enumerate((.25,.5)):
            for offset in range(5):
                self.change_group_report(fold,offset,lambda report,p=point: report['validation_metrics'].update(map_at_12_conditional=p))
        self.decide()
        paths = [self.root/f'artifacts/hm-auto-v2/audits/group2-{anchor}/report.json' for anchor in selection.ANCHORS]
        with self.assertRaisesRegex(ValueError,'accepted first group'):
            groups.group_decision(paths,self.root/'artifacts/hm-auto-v2/decisions/group2',stage=2)
        self.assertFalse((self.root/'artifacts/hm-auto-v2/decisions/group2').exists())

    def test_freshness_after_choice_and_output_containment(self):
        original = selection.choose
        def mutate(candidates,baseline):
            result = original(candidates,baseline)
            if candidates and candidates[0]['name'] in groups.DIMS:
                with self.paths[1].open('a',encoding='utf-8') as stream:stream.write(' ')
            return result
        with patch.object(selection,'choose',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'changed during group'):self.decide()
        self.assertFalse(self.output.exists())
        _fixtures.write(self.paths[1],self.audits[1])
        with self.assertRaisesRegex(ValueError,'New output'):
            groups.group_decision(self.paths,self.root/'outside')
        self.assertFalse((self.root/'outside').exists())


if __name__ == '__main__':
    unittest.main()
