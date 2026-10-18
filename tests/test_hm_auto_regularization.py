"""JSON-only L2 contracts in D: temporary roots, outside project artifacts."""
from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import hm_auto_regularization as regularization
from scripts import hm_auto_groups as groups
from scripts import hm_auto_select as selection
from tests import test_hm_auto_groups as group_fixtures

SOURCE_ROOT = Path(__file__).resolve().parents[1]
write = group_fixtures._fixtures.write


class TuningTests(unittest.TestCase):
    def test_each_arm_uses_unweighted_weekly_mean_and_ties_choose10(self):
        result = regularization.choose_l2(dict(M={10: [.25, .5], 50: [.375, .375]},
            E={10: [.5, .5], 50: [.375, .625]}))
        self.assertEqual(result['chosen_l2'], dict(M=10, E=10))
        self.assertEqual(result['tuned_weekly_deltas'], [.25, 0])
        self.assertFalse(result['candidate_eligible'])
        self.assertFalse(result['customer_holdout_authorized'])
        independent = regularization.choose_l2(dict(M={10: [.25, .25], 50: [.5, .5]},
            E={10: [.75, .75], 50: [.625, .625]}))
        self.assertEqual(independent['chosen_l2'], dict(M=50, E=10))
        self.assertTrue(independent['candidate_eligible'])

    def test_positive_interaction_does_not_admit_losing_tuned_expansion(self):
        result = regularization.choose_l2(dict(M={10: [.25, .25], 50: [.5, .5]},
            E={10: [.125, .125], 50: [.4375, .4375]}))
        self.assertTrue(all(d > 0 for d in result['diagnostics']['interaction_D']))
        self.assertFalse(result['candidate_eligible'])

    def test_negative_or_mixed_interaction_does_not_block_winning_tuned_expansion(self):
        result = regularization.choose_l2(dict(M={10: [.25, .25], 50: [.5, .5]},
            E={10: [.75, .5], 50: [.875, .875]}))
        self.assertEqual(result['chosen_l2'], dict(M=50, E=50))
        self.assertEqual(result['diagnostics']['interaction_D'], [-.125, .125])
        self.assertTrue(result['candidate_eligible'])
        self.assertFalse(result['customer_holdout_authorized'])

    def test_invalid_cells_nonfinite_bool_and_out_of_range_rejected(self):
        points = dict(M={10: [.25, .5], 50: [.375, .375]}, E={10: [.5, .5], 50: [.375, .625]})
        for value in (float('nan'), float('inf'), True, -.1, 1.01):
            bad = deepcopy(points); bad['E'][50][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                regularization.choose_l2(bad)
        bad = deepcopy(points); del bad['M'][50]
        with self.assertRaises(ValueError):
            regularization.choose_l2(bad)


class PlanTests(unittest.TestCase):
    def setUp(self):
        fixture = group_fixtures.GroupDecisionTests('test_stage2_strict_marginal_improvement_and_total_width')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        root_patch = patch.object(regularization, 'ROOT', self.root)
        root_patch.start(); self.addCleanup(root_patch.stop)
        for name in regularization.SOURCES:
            (self.root/'scripts'/name).write_bytes((SOURCE_ROOT/'scripts'/name).read_bytes())
        self.sources = {name: selection.digest((self.root/'scripts'/name).read_bytes())
                        for name in regularization.SOURCES}
        self.plan_path = self.root/'artifacts/hm-auto-v2/plans/l2.json'
        self.output = self.root/regularization.OUTPUT

    def plan_document(self, decision_sha, decision=None):
        manual = self.fixture.manual
        programs = [] if decision is None else decision['selected_programs']
        names = manual['numeric']+manual['categorical']
        m_names = 'artifacts/hm-campaign/feature-study/M_names.json'
        e_names = 'artifacts/hm-auto-v2/l2/E_names.json'
        names_files = dict(M=dict(path=m_names, sha256=write(self.root/m_names, names)),
            E=dict(path=e_names, sha256=write(self.root/e_names, names+programs)))
        folds = []
        for fold, anchor in enumerate(selection.ANCHORS):
            m_relative = self.fixture.fixture.references[fold]+'/report.json'
            e_relative = m_relative
            if decision is not None:
                dimensions = decision['selected_groups']
                e_relative = (f'artifacts/hm-auto-v2/group1/{dimensions[0]}/{anchor}/report.json' if len(dimensions) == 1 else
                    f'artifacts/hm-auto-v2/group2/{dimensions[0]}__{dimensions[1]}/{anchor}/report.json')
            folds.append(dict(anchor=anchor,
                M10=dict(path=m_relative, sha256=selection.digest((self.root/m_relative).read_bytes())),
                E10=dict(path=e_relative, sha256=selection.digest((self.root/e_relative).read_bytes())),
                M50=f'artifacts/hm-auto-v2/l2/M50/{anchor}', E50=f'artifacts/hm-auto-v2/l2/E50/{anchor}',
                audit=f'artifacts/hm-auto-v2/audits/l2-{anchor}/report.json'))
        return dict(format='hm-auto-l2-plan-v2',
            protocol=dict(path=selection.PROTOCOL, sha256=selection.PROTOCOL_SHA),
            selection=dict(path=regularization.GROUP_DECISION, sha256=decision_sha), sources=self.sources,
            features=dict(M=manual, E=dict(numeric=manual['numeric']+programs, categorical=manual['categorical'])),
            names_files=names_files, folds=folds, output=regularization.OUTPUT)

    def make_plan(self, second_group=True):
        self.fixture.decide()
        maps = ([[.625, .75, .5, .4375], [.8125, .875, .75, .9375]] if second_group else
                [[.5, .4375, .5625, .375], [.75, .875, .75, .625]])
        paths, _, _ = self.fixture.write_group_audits(2, 'department_no', maps)
        decision = groups.group_decision(paths, self.root/'artifacts/hm-auto-v2/decisions/group2', stage=2)
        self.plan = self.plan_document(selection.digest((self.root/regularization.GROUP_DECISION).read_bytes()), decision)
        self.plan_sha = write(self.plan_path, self.plan)
        return decision

    def write_l2_audits(self):
        self.paths, self.audits, self.reports = [], [], []
        for fold, item in enumerate(self.plan['folds']):
            audit = deepcopy(self.fixture.audits[fold]); audit['fits'] = []
            paths = []
            for index, (arm, l2) in enumerate(regularization.CELLS):
                old = item[arm+'10']['path']
                report = json.loads((self.root/old).read_text(encoding='utf-8'))
                relative = old
                if l2 == 50:
                    relative = item[arm+'50']+'/report.json'
                    report['hyperparameters']['l2_leaf_reg'] = 50
                    report['code'] = {name: self.sources[name] if name == 'hm_auto_fit.py' else
                        self.fixture.fixture.sources[name] for name in regularization.NEW_FIT_SOURCES}
                    report['validation_metrics']['map_at_12_conditional'] = (
                        [.375, .625][fold] if arm == 'M' else [.8125, .9375][fold])
                    report['fit_identity'] = selection.fit_identity(report)
                    write(self.root/relative, report)
                path = self.root/relative; paths.append(path)
                audit['fits'].append(dict(arm=index, fit_directory=path.parent.as_posix(),
                    report_sha256=selection.digest(path.read_bytes()), fit_identity=report['fit_identity'],
                    metrics=deepcopy(report['validation_metrics']),
                    code={name: dict(recorded_sha256=sha, current_source_matches=True)
                          for name, sha in report['code'].items()}))
            path = self.root/item['audit']; write(path, audit)
            self.paths.append(path); self.audits.append(audit); self.reports.append(paths)

    def change_report(self, fold, index, change):
        path = self.reports[fold][index]
        report = json.loads(path.read_text(encoding='utf-8')); change(report)
        report['fit_identity'] = selection.fit_identity(report)
        sha = write(path, report)
        row = self.audits[fold]['fits'][index]
        row.update(report_sha256=sha, fit_identity=report['fit_identity'], metrics=deepcopy(report['validation_metrics']),
            code={name: dict(recorded_sha256=value, current_source_matches=True) for name, value in report['code'].items()})
        write(self.paths[fold], self.audits[fold])

    def decide(self):
        return regularization.regularization_decision(self.plan_path, self.plan_sha, self.paths, self.output)

    def test_prospective_plan_and_eight_cells_tune_equally_without_test_authorization(self):
        self.make_plan()
        context = regularization.validate_plan(self.plan_path, self.plan_sha, before_fits=True)
        self.assertGreater(context['selection']['width'], 0)
        self.assertFalse(context['customer_holdout_authorized'])
        self.write_l2_audits()
        report = self.decide()
        self.assertEqual(report['chosen_l2'], dict(M=50, E=50))
        self.assertEqual(len(report['cells']), 8)
        self.assertTrue(report['candidate_eligible'])
        self.assertFalse(report['customer_holdout_authorized'])
        self.assertTrue(report['preserve_untouched_customer_holdout'])
        self.assertEqual(report['next_action'], 'requires_separate_customer_holdout_lock')
        self.assertTrue(all(d < 0 for d in report['diagnostics']['interaction_D']))
        self.assertEqual(json.loads((self.output/'report.json').read_text(encoding='utf-8')), report)
        for name, sha in report['provenance'].items():
            self.assertEqual(selection.digest((self.root/name).read_bytes()), sha)
        with self.assertRaises(FileExistsError):
            self.decide()
        self.assertFalse(list(self.root.rglob('*.parquet')))
        self.assertFalse(list(self.root.rglob('*.cbm')))

    def test_no_second_group_uses_exact_group1_e10_models(self):
        decision = self.make_plan(second_group=False)
        self.assertEqual(decision['selected_groups'], ['department_no'])
        regularization.validate_plan(self.plan_path, self.plan_sha, before_fits=True)
        self.assertTrue(all('/group1/department_no/' in fold['E10']['path'] for fold in self.plan['folds']))
        self.write_l2_audits()
        self.assertEqual(len(self.decide()['cells']), 8)

    def test_before_fits_rejects_any_four_fit_two_audit_or_decision_output(self):
        self.make_plan()
        paths = [self.root/fold[arm+'50'] for fold in self.plan['folds'] for arm in ('M', 'E')]
        paths += [(self.root/fold['audit']).parent for fold in self.plan['folds']]+[self.output]
        for path in paths:
            path.mkdir(parents=True)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'must all be absent'):
                regularization.validate_plan(self.plan_path, self.plan_sha, before_fits=True)
            path.rmdir()

    def test_width0_cannot_be_admitted_as_original_v2_l2_probe(self):
        for fold, point in enumerate((.25, .5)):
            for offset in range(5):
                self.fixture.change_group_report(fold, offset,
                    lambda report, p=point: report['validation_metrics'].update(map_at_12_conditional=p))
        self.assertEqual(self.fixture.decide()['width'], 0)
        plan = self.plan_document('a'*64)
        plan_sha = write(self.plan_path, plan)
        with self.assertRaisesRegex(ValueError, 'Nonempty group1'):
            regularization.validate_plan(self.plan_path, plan_sha, before_fits=True)
        self.assertFalse(self.output.exists())

    def test_plan_sha_nonempty_selection_names_order_refs_and_source_pins(self):
        self.make_plan()
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            regularization.validate_plan(self.plan_path, '0'*64)
        original = deepcopy(self.plan)
        for change in (lambda p: p['features']['E']['numeric'].reverse(),
                       lambda p: p['folds'][0].update(E10=p['folds'][0]['M10']),
                       lambda p: p['sources'].update({'hm_auto_fit.py': '0'*64}),
                       lambda p: p['folds'][0].update(anchor='2020-09-16')):
            plan = deepcopy(original); change(plan); sha = write(self.plan_path, plan)
            with self.assertRaises(ValueError):
                regularization.validate_plan(self.plan_path, sha)
        write(self.plan_path, original)
        names = self.root/original['names_files']['E']['path']
        names.write_text('["wrong"]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            regularization.validate_plan(self.plan_path, self.plan_sha)

    def test_new50_wrong_params_code_features_runtime_inputs_and_fit_hash_fail(self):
        self.make_plan(); self.write_l2_audits()
        original = self.reports[0][3].read_bytes()
        for change in (lambda r: r['hyperparameters'].update(l2_leaf_reg=10),
                       lambda r: r.update(code=self.fixture.fixture.report_code),
                       lambda r: r['features']['numeric'].reverse(),
                       lambda r: r['runtime'].update(threads=2),
                       lambda r: r['inputs'][-1].update(qcy_identity='0'*64)):
            self.reports[0][3].write_bytes(original)
            self.change_report(0, 3, change)
            with self.assertRaises(ValueError):
                self.decide()
            self.assertFalse(self.output.exists())
        self.reports[0][3].write_bytes(original)
        self.audits[0]['fits'][3]['report_sha256'] = '0'*64
        write(self.paths[0], self.audits[0])
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.decide()

    def test_audit_paths_four_arm_order_checker_status_and_metric_tolerance(self):
        self.make_plan(); self.write_l2_audits()
        with self.assertRaisesRegex(ValueError, 'audit path/order'):
            regularization.regularization_decision(self.plan_path, self.plan_sha, list(reversed(self.paths)), self.output)
        original = deepcopy(self.audits[0])
        for change in (lambda a: a['fits'].reverse(), lambda a: a['fits'].pop(),
                       lambda a: a.update(status='FAIL'), lambda a: a.update(checker_sha256='0'*64),
                       lambda a: a['fits'][3]['metrics'].update(queries=20000.0),
                       lambda a: a['fits'][3]['metrics'].update(map_at_12_conditional=.8125+2e-12)):
            audit = deepcopy(original); change(audit); write(self.paths[0], audit)
            with self.assertRaises(ValueError):
                self.decide()
            self.assertFalse(self.output.exists())
        audit = deepcopy(original)
        audit['fits'][3]['metrics']['map_at_12_conditional'] += 5e-13
        write(self.paths[0], audit)
        self.assertEqual(self.decide()['cells'][3]['audited_map'], .8125+5e-13)

    def test_nonfinite_and_freshness_fail_before_output(self):
        self.make_plan(); self.write_l2_audits()
        original = self.paths[0].read_text(encoding='utf-8')
        for token in ('NaN', 'Infinity', '1e999'):
            self.paths[0].write_text(original.replace('0.8125', token), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                self.decide()
        self.paths[0].write_text(original, encoding='utf-8')
        choose = regularization.choose_l2
        def mutate(points):
            result = choose(points)
            with self.paths[0].open('a', encoding='utf-8') as stream:
                stream.write(' ')
            return result
        with patch.object(regularization, 'choose_l2', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during L2 decision'):
                self.decide()
        self.assertFalse(self.output.exists())

    def test_cli_requires_explicit_prospective_plan_sha(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            regularization.main(['check-plan', '--plan', str(self.plan_path)])


if __name__ == '__main__':
    unittest.main()
