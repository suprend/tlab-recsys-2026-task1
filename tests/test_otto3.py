"""Synthetic tests of scripts/otto3.py: process-local configuration and the replay of an earlier set."""
import json
import unittest
from unittest import mock

from scripts import otto_agent as oa
from scripts import otto_common as oc
from scripts import otto_model as om
from scripts import otto3


class ConfigureTest(unittest.TestCase):
    def tearDown(self):
        otto3.restore()

    def test_paths_constants_and_restore(self):
        prereg = oc.config_path('prereg')
        otto3.configure('i1')
        self.assertEqual(oc.artifacts_dir(), oc.ROOT/'artifacts'/'otto3'/'i1')
        self.assertEqual(oc.config_path('set').name, 'otto3-i1-set.json')
        self.assertEqual(oc.config_path('prereg'), prereg)
        self.assertEqual(oa.journal_dir(), oc.ROOT/'docs'/'otto3-run'/'i1')
        self.assertIs(oc.require_prereg, otto3.require_prereg3)
        self.assertEqual(oc._load_tree('train'), oc.ROOT/'artifacts'/'otto'/'load'/oc._LOAD_TREES['train'])
        self.assertEqual((oa.ROUNDS, oa.S_ROUNDS, oa.MAX_CALLS, oa.MAX_SOURCES, oa.BA_MAX), (8, 4, 16, 10, 300))
        self.assertEqual(oa.ba_union.__defaults__, (300,))
        self.assertEqual([oa.phase_of(r) for r in (1, 4, 5, 8)], ['S', 'S', 'F', 'F'])
        self.assertEqual(oa.PROMPT_CONSTANTS['f_first_round'], 5)
        with mock.patch.object(oc, 'agent_columns', return_value=['a']):
            self.assertEqual(om.frozen_agent_columns({'agent_columns': ['x']}, {}), ['a'])
        otto3.restore()
        self.assertEqual(oc.artifacts_dir(), oc.ROOT/'artifacts'/'otto')
        self.assertEqual(oc.config_path('set').name, 'otto-set.json')
        self.assertEqual((oa.ROUNDS, oa.S_ROUNDS, oa.MAX_SOURCES, oa.BA_MAX), (6, 2, 6, 200))
        self.assertEqual(oa.PROMPT_CONSTANTS['ba_max'], 200)

    def test_unknown_iteration(self):
        with self.assertRaises(oc.ContractError):
            otto3.configure('nope')


def _proposal(number, index, kind):
    return dict(id=f'r{number}p{index}', round=number, index=index, name=f'n{number}{index}', idea='i', kind=kind,
                level='pair', sql='SELECT 1', columns=[], depends=[])


class MainTest(unittest.TestCase):
    def tearDown(self):
        otto3.restore()

    def test_agent_run_and_probe_are_refused(self):
        with mock.patch.object(otto3, 'iteration_root', return_value=oc.ROOT/'artifacts'/'otto3'/'i1'), \
                mock.patch.object(otto3.Path, 'exists', return_value=True), \
                mock.patch.object(oa, 'main', side_effect=AssertionError('reached otto_agent')):
            for command in ('run', 'probe', 'calibrate', 'export'):
                with self.assertRaises(oc.ContractError):
                    otto3.main(['--iteration', 'i1', 'agent', command])


class PartsTest(unittest.TestCase):
    def test_parts_cover_population_once_in_order(self):
        population = list(range(1, 1001))
        parts = otto3.part_sessions(population, 4)
        self.assertEqual(len(parts), 4)
        self.assertEqual([s for part in parts for s in part], oc.first_in_order(population, None))
        self.assertEqual(len(otto3.part_sessions(population[:3], 4)), 3)


class ReplayTest(unittest.TestCase):
    def tearDown(self):
        otto3.ITERATIONS.pop('t1', None)
        otto3.ITERATIONS.pop('t2', None)

    def test_s_rounds_kept_f_rounds_shifted(self):
        otto3.ITERATIONS['t1'] = dict(rounds=4, s_rounds=2, max_sources=6, ba_max=200, replay=None)
        otto3.ITERATIONS['t2'] = dict(rounds=9, s_rounds=4, max_sources=6, ba_max=200, replay='t1')
        record = dict(proposals=[_proposal(1, 2, 'table'), _proposal(2, 1, 'source'), _proposal(3, 1, 'feature'),
                                 _proposal(4, 3, 'feature')])
        record.update(audit=dict(verdict='clean'), digest=oa.set_digest(record['proposals']))
        with mock.patch.object(oc, 'read_json', return_value=record), \
                mock.patch.object(oc, 'committed_clean', return_value=True):
            plan = otto3.replay_plan('t2')
            leak = dict(record, audit=dict(verdict='leak'))
            with mock.patch.object(oc, 'read_json', return_value=leak), self.assertRaises(oc.ContractError):
                otto3.replay_plan('t2')
        self.assertEqual(sorted(plan), [1, 2, 5, 6])
        self.assertEqual(plan[5][0]['name'], 'n31')
        self.assertEqual(set(plan[1][0]), set(oa.FIELDS))

    def test_replay_ask_answers_planned_rounds_only(self):
        plan = {2: [dict(name='a', idea='i', kind='source', level='pair', sql='SELECT 1')]}
        calls = []

        def llm(prompt, model):
            calls.append(prompt)
            return [], dict(cost_usd=1.0)
        ask = otto3.replay_ask(plan, llm)
        items, meta = ask('... This is round 2 of 9 (phase S ...', 'm')
        self.assertEqual(items, plan[2])
        self.assertEqual(meta['cost_usd'], 0.0)
        self.assertEqual(calls, [])
        ask('... This is round 3 of 9 (phase S ...', 'm')
        self.assertEqual(len(calls), 1)

    def test_no_replay(self):
        otto3.ITERATIONS['t1'] = dict(rounds=4, s_rounds=2, max_sources=6, ba_max=200, replay=None)
        self.assertEqual(otto3.replay_plan('t1'), {})


if __name__ == '__main__':
    unittest.main()
