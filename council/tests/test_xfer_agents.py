"""council.xfer.agents: the LLM stages of the council on xfer with a fake LLM (no `claude -p`), fake sandbox probes
and a fake adapter in this process; the real adapters only in their own subprocess (python -I -B), one dataset each
(contract §3 rule 1), building the prompts without any call.

Checks: prompts without company, dataset or competition names and without a quality measure named by code (the
measure in a prompt is the adapter's, at run time); the neutral working directory; the log at
roles.paths(x).llm_log, prompts and replies beside it; cards and proposals carry a level of xa.LEVELS; files at the
roles.paths(x) paths of a temporary root; probe anchors masked in what the roles see; the anchor test and the
budgets of the calls.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_agents -v
"""
import contextlib
import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

from council import agents as A
from council import llm
from council.xfer import agents as X
from council.xfer import roles, sandbox
from scripts import xfer_agent as xa

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
FORBIDDEN = re.compile(r'tinkoff|t-bank|т-банк|sber|сбер|instamart|kuper|xfer|rees46|kaggle|competition|submission',
                       re.I)
CODE_MEASURES = re.compile(r'ndcg|map@|recall|mrr|precision@|hit ?rate', re.I)
PROBE_ANCHORS = (641, 611)
DIGESTS = {'tinkoff': 'ccf381ed2ba739cecaca151a18f6f14fdec931cd37625e1fbb8914cbd1f43ae6',   # adapter.prompt_digest()
           'sber': '607719164d889b0ad6d2718572b976ea59af0aae430688696760160ee8d4947c'}

TEMPLATE = """You are a feature agent. Reply with JSON only.

TASK
A shop with interactions (user, item, step). The quality of a ranking is {quality} over the queries.

CANDIDATES
Popular items.

TRAINING
Trees.

FEATURES ALREADY IN THE MODEL: users_30.

TABLES
ev(user_id BIGINT, item_id BIGINT, t INTEGER)

QUERY RULES
- Forbidden whole words, in any case: label, frame, sample_submission, kaggle_x, query.
- Limits on the probe: no more than the timeout. Budget of the whole set on the probe: {budget} seconds of pair and user queries; a query past it
  gets status budget.

OUTPUT OF A QUERY
- 1 to 3 value columns named by ^ag_[a-z][a-z0-9_]{{1,38}}$; no other columns.

VALIDITY
Every query is checked.

REQUEST
{history}
"""


def fake_adapter():
    constants = dict(k=20, rounds=3, proposals=12)

    def prompt_substitutions(stats, base, feedback, round_index, budget):
        return dict(quality=f"FAKEQ@{constants['k']}", budget=str(budget['pair_user_seconds']), history=feedback)
    return types.SimpleNamespace(PROMPT_TEMPLATE=TEMPLATE, PROMPT_CONSTANTS=constants,
                                 prompt_substitutions=prompt_substitutions, prompt_digest=lambda: 'fake-digest')


LIMITS = dict(timeouts=dict(pair=40.0, user=40.0, item=120.0), budget=dict(pair_user_seconds=600.0, item_seconds=900.0))
PATH_ERROR = 'IO Error: artifacts/xfer/tinkoff/load/probe-641/x.parquet'
AGENT_SET = dict(prompt_digest='fake-digest', proposals=[
    dict(name='recent_pop', level='item', columns=['ag_recent_pop'], idea='Distinct users of the item in 30 steps.'),
    dict(name='user_pace', level='user', columns=['ag_pace_a', 'ag_pace_b'],
         idea='Accepted pace of the user, as on Kaggle.')])


def fake_probe(ds, sql, level, data=None, threads=4):
    """A probe dict of the sandbox schema: the anchors as their texts; an error (naming an anchor) when the SQL
    says bad +."""
    cols = list(dict.fromkeys(re.findall(r'\bag_\w+', sql)))
    days = [str(a) for a in PROBE_ANCHORS]
    if 'bad +' in sql:
        return dict(sql=sql, level=level, days=days, check=None, nondeterministic=None, error=f'{days[0]}: boom; {PATH_ERROR}',
                    per_day={}, columns=None, seconds_median=None, coverage={})
    return dict(sql=sql, level=level, days=days, check=None, nondeterministic=None, error=None, keys=['user_id'],
                columns=cols, per_day={d: dict(rows=10, coverage={c: 0.5 for c in cols}) for d in days},
                seconds_median=1.5, coverage={c: 0.5 for c in cols}, batch_invariant=True, max_abs_rho=0.2,
                nearest='users_30', r2=0.1,
                parity=dict(ok=True, columns={c: dict(shares={days[0]: 0.5, days[1]: 0.4}) for c in cols}))


def card_sql(d, i, twin=False):
    """Card 1: SQL a scrubber would spoil (a/b/c, % 1000000007, LIMIT 611, x_611); card 2: SQL naming a step of the
    test period (641), which no prompt may show."""
    tw = '_tw' if twin else ''
    if i == 1:
        return (f'SELECT user_id, item_id, count(*)/t/t % 1000000007 AS f_x_c{d}_hits{i}{tw} FROM '
                f'(SELECT *, t AS x_611 FROM ev WHERE t < {{A}} LIMIT 611) GROUP BY user_id, item_id')
    return (f'SELECT user_id, item_id, count(*) AS f_x_c{d}_hits{i}{tw} FROM ev '
            f"WHERE t < {{A}} AND t <> 641 GROUP BY user_id, item_id")


def card(d, i, sql=None):
    level = ('pair', 'user', 'item')[i % 3]
    return dict(name=f'family_{d}_{i}', level=level, mechanism='repeat interest, as in a competition, window x_650',
                sign='+',
                stratum='users with repeats', null_stratum='users without repeats', sql=sql or card_sql(d, i),
                twin=dict(how='time_shuffle', sql=card_sql(d, i, True)),
                rival=dict(explanation='popularity', stratum='popular items'))


class FakeLLM:
    """llm._call(prompt, model, cwd): replies by role, read from the prompt; records every call."""

    def __init__(self):
        self.calls = []

    def __call__(self, prompt, model, cwd=None):
        self.calls.append(dict(prompt=prompt, model=model, cwd=cwd))
        aliases = re.findall(r'^--- (C\d\d)$', prompt, re.M)
        if prompt == '["fine"]':
            reply = ['ok']
        elif 'failed the sandbox check' in prompt:
            k = re.search(r'ag_rb(\d)_', prompt).group(1)
            listing = json.loads(prompt[prompt.index('\n[\n {') + 1:prompt.index('\n]\n') + 2])
            reply = []
            for item in listing:                     # the SQL as shown, without the failing part
                reply.append(dict(name=item['name'], idea='fixed', level=item['name'] == 'late_one' and 'item' or 'pair',
                                  sql=item['sql'].replace('bad + ', '1.0 + ')))
        elif 'Propose ' in prompt:
            k = re.search(r'ag_rb(\d)_', prompt).group(1)
            reply = [dict(name='item_cnt', idea='count', level='item', sql=f'SELECT item_id, count(*) AS ag_rb{k}_cnt FROM ev GROUP BY 1'),
                     dict(name='broken', idea='bad, as in a submission', level='PAIR',
                          sql=f'SELECT user_id, item_id, bad + a/b/c % 1000000007 AS ag_rb{k}_bad FROM cand'),
                     dict(name='late_one', idea='late', level='item',
                          sql=f'SELECT item_id, bad + 1 AS ag_rb{k}_late FROM ev WHERE t <> 641'),
                     dict(name='no_level', idea='x', sql=f'SELECT item_id, 1 AS ag_rb{k}_x FROM ev')]
            reply += [dict(e, sql=e['sql'].format(k=k)) for e in getattr(self, 'extra', [])]
        elif 'You wrote the cards below' in prompt:
            reply = []                               # every card back as shown, unchanged
            for m in re.finditer(r'^--- (G\d-\d+)\ncard: (.*?)\nmeasurements:', prompt, re.M | re.S):
                body = json.loads(m.group(2))
                body.pop('id')
                reply.append(dict(card=m.group(1), action='revise', new=body))
        elif prompt.startswith('You are the leak auditor'):
            reply = [dict(card=a, type='OK', text='clean', kill_test='') for a in aliases]
        elif prompt.startswith('You are the skeptic'):
            reply = [dict(card=a, type='DUPLICATE', text='near users_30 on Kaggle', kill_test='rho at step 641')
                     for a in aliases]
        elif prompt.startswith('You are critic'):
            reply = [dict(card=a, type='MECHANISM_DOUBT', text='weak', kill_test='staleness') for a in aliases]
        elif prompt.startswith('You are generator'):
            d = re.search(r'generator G(\d)', prompt).group(1)
            reply = [card(d, 1), card(d, 2), dict(name='broken')]
        else:
            raise AssertionError('unknown prompt: ' + prompt[:200])
        return json.dumps(reply), 0.5


def _rmtree_tlab(path):
    path = Path(path)
    if not str(path).startswith('/tmp/tlab-agents-test-'):
        raise ValueError(path)
    for d, dirs, files in os.walk(path, topdown=False):
        for n in files:
            os.unlink(Path(d) / n)
        for n in dirs:
            os.rmdir(Path(d) / n)
    os.rmdir(path)


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='tlab-agents-test-', dir='/tmp'))
        self.addCleanup(_rmtree_tlab, self.root)
        self.ds = types.SimpleNamespace(
            name='tinkoff', adapter=fake_adapter(), paths=roles.paths('tinkoff', self.root),
            anchors={'roles': {'train': [581, 611], 'val': [641], 'test': [701], 'probe': [641]}},
            prompt_cutoff=641, probe_anchors=list(PROBE_ANCHORS))
        self.llm = FakeLLM()
        self.gate_waits, self.probe_data_calls, self.probed = [], [], []
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(X, 'limits', lambda ds: LIMITS))
        stack.enter_context(mock.patch.object(X, 'base', lambda ds: {'features': ['users_30']}))
        stack.enter_context(mock.patch.object(X, 'agent_set', lambda ds: AGENT_SET))
        stack.enter_context(mock.patch.object(X, 'code', lambda ds: {'council': {'fake': '0'}}))
        stack.enter_context(mock.patch.object(sandbox, 'wait_gate', lambda gate, *a, **k: self.gate_waits.append(gate) or 0))
        stack.enter_context(mock.patch.object(sandbox, 'probe_data', lambda ds, threads=4: self.probe_data_calls.append(threads) or ['data']))
        stack.enter_context(mock.patch.object(sandbox, 'probe', self.probe))
        stack.enter_context(mock.patch.object(llm, '_call', self.llm))

    def probe(self, ds, sql, level, data=None, threads=4):
        self.probed.append((sql, level, data))
        return fake_probe(ds, sql, level, data, threads)

    def prompts(self):
        return [c['prompt'] for c in self.llm.calls]

    def assert_clean(self):
        p = self.ds.paths
        self.assertTrue(self.llm.calls)
        for call in self.llm.calls:
            self.assertEqual(call['cwd'], p.llm)
            self.assertIsNone(FORBIDDEN.search(str(call['cwd'])))
            self.assertIsNone(FORBIDDEN.search(call['prompt']), call['prompt'][:300])
            self.assertIsNone(CODE_MEASURES.search(call['prompt']))
            self.assertIn('FAKEQ@20', call['prompt'])          # the measure of the adapter, at run time
            for a in (641, 650):                               # steps of the test period, also as x_650
                self.assertNotIn(str(a), call['prompt'])
        log = [json.loads(line) for line in p.llm_log.read_text().splitlines()]
        self.assertEqual(sum(r['call'] for r in log), len(self.llm.calls))
        self.assertTrue(p.llm_log.is_relative_to(self.root))
        for r in log:
            self.assertTrue((p.prompts / f"{r['stage']}-{r['role']}.txt").exists())
            self.assertTrue((p.replies / f"{r['stage']}-{r['role']}.txt").exists())
        for f in p.prompts.iterdir():
            self.assertIn(f'# cwd: {p.llm}\n', f.read_text())

    def write_probes(self, cards):
        store = {'cards': {}, 'reference': {}}
        for c in cards:
            sql, tw = sandbox.to_sandbox(c['sql']), sandbox.to_sandbox(c['twin']['sql'])
            store['cards'][c['id']] = dict(format='card', id=c['id'], problems=[], card=fake_probe(self.ds, sql, c['level']),
                                           twin=dict(fake_probe(self.ds, tw, c['level']), error=PATH_ERROR),
                                           twin_check=dict(verdict='ok', reasons=[]))
        self.ds.paths.run_file('probes.json').write_text(json.dumps(store))


class TestReference(Base):
    def test_rb_proposals_fix_and_files(self):
        state = X.reference(self.ds, 1)
        p = self.ds.paths
        self.assertEqual(json.loads(p.run_file('reference-rb1.json').read_text()), json.loads(json.dumps(state)))
        self.assertEqual(len(self.llm.calls), 2)                       # 12 proposals, then one fix
        props = state['proposals']
        self.assertEqual([q['name'] for q in props], ['item_cnt', 'broken', 'late_one'])   # no level: skipped
        for q in props:
            self.assertIn(q['level'], xa.LEVELS)
            self.assertEqual(q['table'], roles.rb_table(1, q['name']))
            self.assertTrue(q['columns'] and all(roles.RB_COLUMN.fullmatch(c) for c in q['columns']))
        # the fix copied the SQL as shown: a/b/c and % 1000000007 survive the round
        self.assertEqual(props[1]['sql'], 'SELECT user_id, item_id, 1.0 + a/b/c % 1000000007 AS ag_rb1_bad FROM cand')
        self.assertEqual(props[1]['level'], 'pair')
        # the SQL naming 641 was withheld; the reply copying the placeholder is unusable: the proposal stays failed
        self.assertEqual(props[2]['sql'], 'SELECT item_id, bad + 1 AS ag_rb1_late FROM ev WHERE t <> 641')
        self.assertEqual([u['name'] for u in state['fix']['unusable']], ['late_one'])
        self.assertIn('<sql withheld', state['fix']['unusable'][0]['reason'])
        self.assertEqual(state['fix']['answered'], ['broken'])
        self.assertEqual(state['tables'], [roles.rb_table(1, 'item_cnt'), roles.rb_table(1, 'broken')])
        # the light gate before every probe, the probe data once, each proposal at its level
        self.assertEqual(len(self.gate_waits), len(self.probed))
        self.assertEqual(len(self.probed), 4)
        self.assertEqual(self.probe_data_calls, [sandbox.THREADS])
        self.assertEqual([lv for _, lv, _ in self.probed], ['item', 'pair', 'item', 'pair'])
        # the failure as the role saw it: the anchor masked
        fix = self.llm.calls[1]['prompt']
        self.assertIn('probe_day_1: boom; IO Error: <path>', fix)
        self.assertNotRegex(fix, r'(?i)tinkoff|xfer|641|artifacts|submission')
        self.assertIn('as in a <name>', fix)
        self.assertIn('bad + a/b/c % 1000000007 AS ag_rb1_bad', fix)
        self.assertIn(X.WITHHELD, fix)
        self.assertIn('the SQL is withheld', fix)
        self.assertIn('ag_rb1_<slug>', self.llm.calls[0]['prompt'])
        self.assertNotIn('^ag_[a-z]', self.llm.calls[0]['prompt'])
        self.assert_clean()

    def test_rb2_prefix_and_tried_masked(self):
        X.reference(self.ds, 2)
        first = self.llm.calls[0]['prompt']
        self.assertIn('ag_rb2_', first)
        self.assertIn('user_pace [user]: ag_pace_a, ag_pace_b', first)
        self.assertIn('earlier pace of the user, as on <name>.', first)
        self.assertNotIn('sample_submission', first)
        self.assertIn('label, frame, query.', first)
        self.assertNotIn('Budget of the whole set', first)
        self.assertTrue(self.ds.paths.run_file('reference-rb2.json').exists())

    def test_names_the_prompts_would_change(self):
        """A failed Rb proposal named competition_share is stored as p<i>, shown so, and its fix is taken."""
        self.llm.extra = [dict(name='competition_share', idea='share', level='item',
                               sql='SELECT item_id, bad + 2 AS ag_rb{k}_share FROM ev')]
        state = X.reference(self.ds, 1)
        names = [q['name'] for q in state['proposals']]
        self.assertEqual(names, ['item_cnt', 'broken', 'late_one', 'p4'])
        self.assertEqual(state['fix']['answered'], ['broken', 'p4'])
        self.assertEqual(state['proposals'][3]['sql'], 'SELECT item_id, 1.0 + 2 AS ag_rb1_share FROM ev')
        self.assertIn(roles.rb_table(1, 'p4'), state['tables'])
        self.assertIn('"name": "p4"', self.llm.calls[1]['prompt'])
        c = X.context(self.ds)
        got = A.parse_card(dict(card('1', 3), name='competition_rank'), 'G1-3', 'G1', context=c)
        self.assertEqual(got['name'], 'g1_3')
        self.assertEqual(A.parse_card(card('1', 3), 'G1-3', 'G1', context=c)['name'], 'family_1_3')
        self.assert_clean()

    def test_done_state_is_not_asked_again(self):
        X.reference(self.ds, 1)
        n = len(self.llm.calls)
        X.reference(self.ds, 1)
        self.assertEqual(len(self.llm.calls), n)


class TestCouncil(Base):
    def test_wave1_cross_authors_prereg(self):
        p = self.ds.paths
        cards = X.wave1(self.ds)
        self.assertEqual(len(self.llm.calls), 4)
        wave = json.loads(p.run_file('cards-wave1.json').read_text())
        self.assertEqual(wave['cards'], cards)
        self.assertEqual(len(cards), 8)
        for c in cards:
            self.assertIn(c['level'], xa.LEVELS)
            self.assertEqual(list(c)[:4], ['id', 'lens', 'name', 'level'])
        self.assertTrue(all(wave[g]['rejected'] for g in X.LENSES))
        with self.assertRaises(SystemExit):
            X.cross_exam(self.ds)                                     # no probes yet
        self.write_probes(cards)
        crit = X.cross_exam(self.ds)
        self.assertEqual(len(self.llm.calls), 10)
        self.assertTrue(p.run_file('critiques.json').exists())
        self.assertEqual({q['critic'] for q in crit}, {'G1', 'G2', 'G3', 'G4', 'skeptic', 'auditor'})
        for call in self.llm.calls[4:]:
            prompt = call['prompt']
            self.assertNotRegex(prompt, r'\bG[1-4]-\d')                # authors hidden
            self.assertNotRegex(prompt, r'f_x_c[1-4]_|ag_c[1-4]_')
            self.assertIn('probe_day_1', prompt)                     # the measurements, anchors masked
            self.assertIn('"level"', prompt)
        for call in self.llm.calls[4:]:                           # SQL as written, or withheld
            self.assertIn('count(*)/t/t % 1000000007 AS f_x_c_hits1', call['prompt'])
            self.assertIn('t AS x_611 FROM ev WHERE t < {A} LIMIT 611', call['prompt'])
            self.assertIn(X.WITHHELD, call['prompt'])
        for call in self.llm.calls[4:]:                           # the texts of the models, scrubbed
            if call['prompt'].startswith('You are the leak auditor'):
                continue                                          # level, SQL and twin only
            self.assertIn('<late>', call['prompt'])
            self.assertIn('<name>', call['prompt'])
        auditor = next(c['prompt'] for c in self.llm.calls[4:] if c['prompt'].startswith('You are the leak auditor'))
        self.assertNotIn('"mechanism"', auditor.split('Below are')[1])
        final = X.author_replies(self.ds)
        self.assertEqual(len(self.llm.calls), 14)
        for call in self.llm.calls[10:]:
            self.assertIn('as in a <name>, window x_<late>', call['prompt'])
            self.assertIn('rho at step probe_day_1', call['prompt'])
        state = json.loads(p.run_file('cards-final.json').read_text())
        self.assertEqual(state['cards'], final)
        # every card came back as shown: card 1 unchanged byte for byte, card 2 copied the withheld placeholder
        self.assertEqual((state['withdrawn'], state['revised']), ([], []))
        self.assertEqual(sorted(state['unanswered']), ['G1-2', 'G2-2', 'G3-2', 'G4-2'])
        self.assertEqual([(c['id'], c['sql'], c['twin']['sql']) for c in final],
                         [(c['id'], c['sql'], c['twin']['sql']) for c in cards])
        answers = [a for lens in state['replies'].values() for a in lens['answers']]
        self.assertEqual(sorted(a['card'] for a in answers if a['action'] == 'unusable'), ['G1-2', 'G2-2', 'G3-2', 'G4-2'])
        self.assertTrue(all('<sql withheld' in a['reason'] for a in answers if a['action'] == 'unusable'))
        self.assertTrue(all(c['level'] in xa.LEVELS for c in final))
        pre = X.prereg1(self.ds)
        self.assertEqual(json.loads(p.run_file('prereg-1.json').read_text()), json.loads(json.dumps(pre)))
        self.assertEqual(pre['dataset'], 'tinkoff')
        self.assertEqual(pre['probe_anchors'], ['641', '611'])
        self.assertEqual(pre['code_sha256'], {'council': {'fake': '0'}})
        for c in pre['cards']:
            self.assertIn(c['level'], xa.LEVELS)
            self.assertEqual(c['table'], roles.family_table(c['id']))
        self.assertEqual(len(self.llm.calls), 14)
        self.assert_clean()
        self.assertLessEqual(len(self.llm.calls), roles.LLM_MAX_CALLS)

    def test_a_revised_card_needs_its_probe(self):
        cards = X.wave1(self.ds)
        self.write_probes(cards[1:])
        with self.assertRaises(SystemExit) as e:
            X.cross_exam(self.ds)
        self.assertIn(cards[0]['id'], str(e.exception))


class TestGuards(Base):
    def test_late_steps_and_dates(self):
        late = X.late(self.ds)
        self.assertEqual(late('steps 640, 641 and 701, 5000, 650.5, x_650, 660_x, ag_c1_w670'), ['641', '701', '650', '660'])
        s = types.SimpleNamespace(prompt_cutoff='2020-08-19', anchors={})
        late = X.late(s)
        self.assertEqual(late('2020-08-18 and 2020-08-19, 2020-09-02, x_2020-08-20'), ['2020-08-19', '2020-09-02', '2020-08-20'])

    def test_refused_before_any_call(self):
        c = X.llm_context(self.ds)
        for prompt in ('rank with kaggle tricks', 'compare with step 641', 'a T-Bank feature', 'а Т — банк',
                       'СберМаркет'):
            with self.assertRaises(llm.PromptRefused):
                llm.ask(prompt, 'r', 's', subs={}, context=c)
        for text in ('the kaggle way', f'see {PATH_ERROR}'):     # a free slot is tested too
            with self.assertRaises(llm.PromptRefused):
                llm.ask(f'cards: {text}', 'r', 's', subs={'cards': text}, free=('cards',), sources=[[text]], context=c)
        bad = dataclasses.replace(c, workdir=self.root / 'sber-llm')
        with self.assertRaises(llm.PromptRefused):
            llm.ask('fine', 'r', 's', subs={}, context=bad)
        self.assertEqual(self.llm.calls, [])
        log = [json.loads(line) for line in self.ds.paths.llm_log.read_text().splitlines()]
        self.assertEqual([r['call'] for r in log], [False] * 8)
        self.assertFalse(any(r.get('started') for r in log))

    def journal(self, path, costs, open_calls=0):
        """Calls with these costs (None: no cost known), then calls started without a result."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for i, cost in enumerate(costs):
            lines += [dict(started=True, call_id=f'c{i}', call=False), dict(call=True, call_id=f'c{i}', cost_usd=cost)]
        lines += [dict(started=True, call_id=f'o{i}', call=False) for i in range(open_calls)]
        path.write_text(''.join(json.dumps(r) + '\n' for r in lines))

    def test_budgets(self):
        c = X.llm_context(self.ds)
        log = self.ds.paths.llm_log
        self.assertEqual((c.max_calls, c.max_usd, c.total_usd), (24, 25.0, roles.LLM_TOTAL_USD))
        self.assertEqual(c.others, (roles.paths('sber', self.root).llm_log,))
        # the last call that could pass $25: 22.5 spent + the reserve 4.5 (the largest observed cost)
        self.journal(log, [4.5] * 5)
        with self.assertRaises(llm.BudgetSpent):
            llm.ask('fine', 'r', 's', subs={}, context=c)
        self.journal(log, [4.5] * 4)
        llm.ask('["fine"]', 'r', 's', subs={}, context=c)
        self.assertEqual(len(self.llm.calls), 1)
        records = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([r.get('started', False) for r in records[-2:]], [True, False])
        self.assertEqual(records[-1]['call_id'], records[-2]['call_id'])
        self.assertEqual(llm.calls_made(c), 5)
        self.assertAlmostEqual(llm.dollars_spent(c), 18.5)
        # 24 calls, the last one killed midway: it counts, and is charged the reserve
        self.journal(log, [0.1] * 23, open_calls=1)
        self.assertEqual(llm.calls_made(c), 24)
        self.assertAlmostEqual(llm.dollars_spent(c), 2.3 + 0.1)
        with self.assertRaises(llm.BudgetSpent):
            llm.ask('fine', 'r', 's', subs={}, context=c)
        # an argument does not raise the cap of the context
        with self.assertRaises(llm.BudgetSpent):
            llm.ask('fine', 'r', 's', subs={}, context=c, max_calls=100)
        # all datasets together: the journal of the other dataset in the same root
        self.journal(log, [])
        self.journal(roles.paths('sber', self.root).llm_log, [4.6] * 10)
        with self.assertRaises(llm.BudgetSpent) as e:
            llm.ask('fine', 'r', 's', subs={}, context=c)
        self.assertIn('all datasets', str(e.exception))
        self.assertEqual(len(self.llm.calls), 1)

    def test_timeout_without_cost_is_charged_the_reserve(self):
        c = X.llm_context(self.ds)

        def timeout(prompt, model, cwd=None):
            raise llm.LLMError('no answer within 900 s')
        with mock.patch.object(llm, '_call', timeout), self.assertRaises(llm.LLMError):
            llm.ask('fine', 'r', 's', subs={}, context=c)
        self.assertEqual(llm.calls_made(c), 1)
        self.assertEqual(llm.dollars_spent(c), llm.RESERVE_USD)
        self.journal(self.ds.paths.llm_log, [3.0, None])
        self.assertEqual(llm.dollars_spent(c), 6.0)

    def test_the_lock_orders_the_cap_check(self):
        """While another process holds the lock, a call neither checks the caps nor records its start."""
        import fcntl
        import threading
        import time
        c = X.llm_context(self.ds)
        self.assertEqual(c.lock, self.ds.paths.llm.parent / 'tlab-council-llm.lock')
        done = []
        with open(c.lock, 'a') as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            t = threading.Thread(target=lambda: done.append(llm.ask('["fine"]', 'r', 's', subs={}, context=c)))
            t.start()
            time.sleep(0.5)
            started = [r for r in llm._records(c) if r.get('started')]
            self.assertEqual((started, done), ([], []))
            fcntl.flock(fh, fcntl.LOCK_UN)
        t.join(10)
        self.assertEqual(len(done), 1)
        self.assertEqual(llm.calls_made(c), 1)

    def test_task_sections(self):
        task, rules = X.task_sections(X.agent_prompt(self.ds))
        self.assertTrue(task.startswith('TASK\n') and 'TABLES' in task and 'QUERY RULES' not in task)
        self.assertTrue(rules.startswith('QUERY RULES\n') and 'OUTPUT OF A QUERY' in rules and 'VALIDITY' not in rules)
        self.assertIn('<<prefix>><slug>', rules)

        def render(template):
            return template.format(quality='q', budget='1', history='')
        for broken in (TEMPLATE.replace('A shop', 'A Kaggle shop'), TEMPLATE.replace('\nVALIDITY\n', '\n'),
                       TEMPLATE.replace('Budget of the whole set', 'Budget of the set'),
                       TEMPLATE.replace('\nTRAINING\n', '\nTraining\n'),
                       TEMPLATE.replace('OUTPUT OF A QUERY', 'OUTPUT OF A QUERY\n\nEXTRA RULES\n- none')):
            with self.assertRaises(ValueError):
                X.task_sections(render(broken))
        with mock.patch.object(X, 'agent_set', lambda ds: dict(AGENT_SET, prompt_digest='another')):
            with self.assertRaises(ValueError):
                X.agent_prompt(self.ds)

    def test_masking_and_hiding(self):
        mask = X.masker(self.ds)
        got = mask({'641': {'a': '611: x'}, 'days': ['641', '611'], 'n': 6410, 'e': PATH_ERROR,
                    'f': 'probe-641 of Sber, run 1234567890123, ag_c1_w611, 0.641, x_611, step 700'})
        self.assertEqual(got, {'probe_day_1': {'a': 'probe_day_2: x'}, 'days': ['probe_day_1', 'probe_day_2'], 'n': 6410,
                               'e': 'IO Error: <path>',
                               'f': 'probe-probe_day_1 of <name>, run <hex>, ag_c1_w611, 0.641, x_probe_day_2, step <late>'})
        self.assertEqual(X.hide('G3-2 g3_2 g3_2_tw ag_c3_x f_x_c3_x G3'), '<card> <table> <table> ag_c_x f_x_c_x <lens>')

    def test_templates_keep_council_placeholders(self):
        out = X.templates('TASK\nt', 'QUERY RULES\nr')
        self.assertEqual(set(out), set(A.TEMPLATES))
        for text in out.values():
            self.assertIsNone(FORBIDDEN.search(text))
            self.assertIsNone(CODE_MEASURES.search(text))

    def test_rees46_defaults_untouched(self):
        self.assertTrue(all(v is None for v in vars(A.Context()).values()))
        self.assertIs(A._template('generator', None), A.TEMPLATES['generator'])
        self.assertEqual(A.card_fields(), A.CARD_FIELDS)
        self.assertEqual(A.rb_prefix(1), 'f_x_rb1_')
        self.assertIsNone(llm.Context.__dataclass_fields__['max_usd'].default)


CHILD = textwrap.dedent("""
    import json, re, sys, tempfile
    sys.path.append(sys.argv[2])
    from council import agents as A, llm
    from council.xfer import agents as X, roles
    from scripts import xfer_agent as xa, xfer_common as xc
    x = sys.argv[1]
    root = tempfile.mkdtemp(prefix='tlab-agents-test-', dir='/tmp')
    ds = roles.activate(x, root)
    c = X.context(ds)
    out = dict(workdir=str(c.llm.workdir), log=str(c.llm.log), paths_log=str(ds.paths.llm_log),
               levels=list(c.levels), cut=str(ds.prompt_cutoff), prompts={})
    for name, (prompt, subs, src) in dict(reference=A.reference_prompt(1, context=c),
                                          generator=A.generator_prompt('G3', context=c)).items():
        llm.check_prompt(prompt, subs, src, context=c.llm)
        out['prompts'][name] = prompt
    out['late'] = c.llm.late(f'anchor {ds.prompt_cutoff}')
    out['digest'] = ds.adapter.prompt_digest()
    days = [xc.anchor_text(a) for a in ds.probe_anchors]
    err = f'IO Error: artifacts/xfer/{x}/load/probe-{days[0]}/x.parquet'

    def probe(sql, error=None):
        cols = sorted(set(re.findall(r'ag_c[1-4]_\\w+', sql)))
        return dict(sql=sql, level='pair', days=days, check=None, nondeterministic=None, error=error,
                    keys=['user_id'], columns=cols, per_day={d: {} for d in days}, seconds_median=1.5,
                    coverage={k: 0.5 for k in cols}, batch_invariant=True, max_abs_rho=0.2, nearest='x', r2=0.1,
                    parity=dict(ok=True, columns={k: dict(shares={d: 0.5 for d in days}) for k in cols}))
    cards, evidence = [], {}
    for lens in ('G1', 'G2', 'G3', 'G4'):
        d = lens[1]
        sql = f"SELECT user_id, {ds.anchors.get('item_key', 'item_id')}, 1.0 AS f_x_c{d}_one FROM cand"
        item = dict(name=f'one_{d}', level='pair', mechanism='m', sign='+', stratum='s', null_stratum='n', sql=sql,
                    twin=dict(how='time_shuffle', sql=sql.replace('_one', '_one_tw')),
                    rival=dict(explanation='r', stratum='s'))
        cd = A.parse_card(item, f'{lens}-1', lens, context=c)
        cards.append(cd)
        evidence[cd['id']] = dict(problems=[err], card=probe(sql.replace('f_x_', 'ag_'), err),
                                  twin=probe(sql.replace('f_x_', 'ag_')), twin_check=dict(verdict='ok', reasons=[err]),
                                  machine_red=['error: ' + err])
    built = {}
    for role in ('G1', 'skeptic', 'auditor'):
        prompt, subs, src, _ = A.critic_prompt(role, cards, evidence, context=c)
        built['critic' if role == 'G1' else role] = (prompt, subs, src, ('cards',))
    crit = [dict(card=cards[0]['id'], critic='skeptic', type='SHIFT', text='t', kill_test='k')]
    prompt, subs, src = A.author_prompt('G1', cards[:1], crit, evidence, context=c)
    built['author'] = (prompt, subs, src, ('cards',))
    raw = probe('SELECT 1 AS ag_rb1_x', err)
    listing = [dict(name='x', idea='i', sql='SELECT 1 AS ag_rb1_x', check=A.probe_view(raw, c),
                    problems=c.mask(c.problems(raw, 'ag_rb1_')))]
    texts, src = c.texts()
    subs = dict(features=texts['features'], prefix='ag_rb1_', failed=json.dumps(listing, ensure_ascii=False, indent=1))
    built['reference_fix'] = (A.render(A._template('reference_fix', c), **subs), subs, [*A._sources(*src, context=c), listing],
                              ('failed',))
    for name, (prompt, subs, src, free) in built.items():
        llm.check_prompt(prompt, subs, src, free, context=c.llm)
        out['prompts'][name] = prompt
    out['days'] = days
    import shutil; shutil.rmtree(root)
    print(json.dumps(out))
""")


class TestRealAdapters(unittest.TestCase):
    """The prompts of both datasets, built from their real adapters and agent sets, each in its own process."""

    def test_prompts_of_both_datasets(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')} | {'TASK1_PERIOD': '2020'}
        for x, letter in (('tinkoff', 'a'), ('sber', 'b')):
            with self.subTest(x):
                r = subprocess.run([PY, '-I', '-B', '-c', CHILD, x, str(ROOT)], cwd=ROOT, env=env,
                                   capture_output=True, text=True, timeout=300)
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                out = json.loads(r.stdout.strip().splitlines()[-1])
                self.assertTrue(out['workdir'].endswith(f'/tlab-council-llm-{letter}'))
                self.assertIsNone(FORBIDDEN.search(out['workdir']))
                self.assertEqual(out['log'], out['paths_log'])
                self.assertTrue(out['log'].endswith(f'council/runs/xfer-{x}/llm.jsonl'))
                self.assertEqual(out['levels'], list(xa.LEVELS))
                self.assertEqual(out['late'], [out['cut']])
                self.assertEqual(out['digest'], DIGESTS[x])         # a change of the adapter prompt fails here
                self.assertEqual(set(out['prompts']), {'reference', 'generator', 'critic', 'skeptic', 'auditor', 'author',
                                                       'reference_fix'})
                for name, prompt in out['prompts'].items():
                    self.assertIsNone(FORBIDDEN.search(prompt), (x, name))
                    self.assertIn('QUERY RULES', prompt)
                    self.assertNotIn('^ag_[a-z]', prompt)
                    self.assertNotRegex(prompt, r'artifacts|/load/')
                    for day in out['days']:
                        self.assertNotIn(day, prompt, (x, name))
                    if name != 'auditor':
                        self.assertIn('Columns of an earlier feature agent', prompt)
                for name in ('critic', 'skeptic', 'auditor', 'author', 'reference_fix'):
                    self.assertIn('<path>', out['prompts'][name])
                    self.assertIn('probe_day_1', out['prompts'][name])


if __name__ == '__main__':
    unittest.main()
