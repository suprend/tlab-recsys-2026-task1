"""Resume preserves the search protocol without calling an LLM or fitting a model."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from task1 import agent, exp

class ResumeProtocolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / 'saved'
        self.run.mkdir()
        self.log = self.run / 'log.jsonl'
        self.records = [dict(config=exp.DEFAULT | {'days': 'unused'}, proxy={},
                             args=dict(min_gain=0.01, per_round=2, model='recorded-model', max_llm_calls=3))]
        self.save()
        self.addCleanup(patch.stopall)
        patch.object(agent, 'RUNS', self.root).start()
        self.columns = patch.object(agent, 'day_features', return_value=['s_rank']).start()
        self.ask = patch.object(agent, 'ask_llm', side_effect=RuntimeError('synthetic failure')).start()
        self.fit = patch.object(exp, 'run', side_effect=AssertionError('a fit must not run')).start()
        patch.object(agent.P, 'only_2019').start()

    def save(self):
        self.log.write_text(''.join(json.dumps(r) + '\n' for r in self.records), encoding='utf-8')

    def resume(self, *args):
        with patch('sys.argv', ['agent', '--run', 'saved', '--rounds', '0', *args]):
            agent.main()

    def test_interrupted_round_uses_recorded_threshold(self):
        self.records.append(dict(round=1, name='candidate', idea='fixture', sql='SELECT 1',
                                 columns=['f_x_new'], d=0.005, d2=0.005,
                                 ci=[0.004, 0.006], ci2=[0.004, 0.006]))
        self.save()
        self.resume()
        self.assertEqual(json.loads((self.run / 'summary.json').read_text())['extra'], [])
        self.ask.assert_not_called()
        self.fit.assert_not_called()

    def test_conflicting_search_settings_fail_before_work_or_writes(self):
        before = self.log.read_bytes()
        for args in (('--min-gain', '0.001'), ('--per-round', '5'), ('--model', 'another-model')):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.resume(*args)
            self.assertEqual(before, self.log.read_bytes())
        self.columns.assert_not_called()
        self.ask.assert_not_called()
        self.assertFalse((self.run / 'summary.json').exists())

    def test_new_round_inherits_model_proposal_count_and_threshold(self):
        with patch.object(agent, 'render', wraps=agent.render) as render, contextlib.redirect_stdout(io.StringIO()):
            self.resume('--rounds', '1')
        self.assertEqual(render.call_args.args[3:], (2, 0.01))
        self.assertEqual(self.ask.call_args.args[1], 'recorded-model')
        self.fit.assert_not_called()

    def test_recorded_call_budget_is_retained_and_can_be_extended(self):
        self.records.extend(dict(round=i, llm_error='fixture', accepted_set=[]) for i in range(1, 4))
        self.save()
        with contextlib.redirect_stdout(io.StringIO()):
            self.resume('--rounds', '1')
        self.ask.assert_not_called()
        with contextlib.redirect_stdout(io.StringIO()):
            self.resume('--rounds', '1', '--max-llm-calls', '4')
        self.ask.assert_called_once()
        self.fit.assert_not_called()

if __name__ == '__main__':
    unittest.main()
