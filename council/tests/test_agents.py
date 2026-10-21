"""council.llm and council.agents without a real `claude -p` and without council.evidence (both mocked).

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_agents -v
"""
import contextlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from council import agents, llm, roles

# Words of the package boundary (contract §3), assembled so that this file does not carry them either.
BOUNDARY = ['la' + 'bel', 'n_tar' + 'gets', 'nd' + 'cg', 're' + 'call', 'per_' + 'query']
LATE_DAYS = [d.isoformat() for s in ('val', 'test') for d in roles.days(s)]
CTX = (dict(features='  base:\n    s_: s_pop_rank, s_cat_rank\n  dfs_p: f_x_dfs_p_view_n_1d',
            tried='  r1p1_first_touch: lift within 24h of a first touch over 7 days'),
       [dict(base=['s_pop_rank', 's_cat_rank'], tables={'dfs_p': ['f_x_dfs_p_view_n_1d']}),
        [dict(name='r1p1_first_touch', idea='lift within 24h of a first touch over 7 days')]])


def card_json(lens, i, sql=None):
    d = lens[1]
    col = f'f_x_c{d}_s{i}'
    return dict(name=f'family_{i}', mechanism=f'mechanism {i} of {lens}', sign='+',
                stratum='users with 2 or more sessions: count(DISTINCT user_session) >= 2',
                null_stratum='single-session users', sql=sql or f'SELECT user_id, product_id, 0.5 AS {col} FROM hist',
                twin=dict(how='time_shuffle', sql=f'SELECT user_id, product_id, 0.25 AS {col}_tw FROM hist'),
                rival=dict(explanation='category popularity', stratum='popular categories'))


def sql_probe(sql):
    cols = sorted(set(re.findall(r'\bf_x_\w+', sql)))
    return dict(check=None, nondeterministic=None, error='Binder Error: boom' if 'BAD' in sql else None,
                keys=['user_id', 'product_id'], level='pair', columns=cols, seconds_median=4.21,
                coverage={c: 0.1234 for c in cols}, batch_invariant=True, max_abs_rho={c: 0.3123 for c in cols},
                nearest={c: 'cf_cv_cos_max' for c in cols}, r2={c: 0.2711 for c in cols}, sql=sql,
                per_day={d: {'rows': 123456} for d in roles.PROBE_DAYS},
                parity=dict(ok=True, columns={c: dict(shares={d: 0.12 for d in roles.PROBE_DAYS}, outside=[])
                                              for c in cols}))


class FakeEvidence:
    MAX_SECONDS = 60.0
    MIN_COVERAGE = 0.005

    def __init__(self):
        self.probed, self.curated, self.fail = [], None, None
        self.capped = 0

    @contextlib.contextmanager
    def capped_extra(self):
        self.capped += 1
        yield

    def probe(self, card_or_sql, days=roles.PROBE_DAYS, threads=10):
        if isinstance(card_or_sql, dict):
            c = card_or_sql
            self.probed.append(c['id'])
            return dict(problems=[], card=sql_probe(c['sql']), twin=sql_probe(c['twin']['sql']),
                        twin_check=dict(verdict='ok', reasons=[], columns={}))
        self.probed.append(card_or_sql)
        return sql_probe(card_or_sql)

    @staticmethod
    def machine_red(p):  # as council.evidence.machine_red: a probe without days is red
        if p.get('error'):
            return [f"error: {roles.PROBE_DAYS[2]}: {p['error']}"]
        return [] if p.get('per_day') else ['error: no day was probed']

    def curate(self, cards, probes, reference_width=None, critiques=(), cross_fn=None, reference_probes=None):
        self.curated = (cards, probes, reference_probes, critiques)
        if self.fail:
            raise SystemExit(self.fail)
        fams = [c['id'] for c in cards if not any(q['card'] == c['id'] and q['type'] == 'WITHDRAWN' for q in critiques)]
        order = list(reference_probes)
        return dict(families=fams[:2], twins=fams[:1], placebo=[], reference_removed=[order[2]],
                    parity=dict(ok=True, reference_drop=[order[-1]]),
                    columns={i: [f'f_x_c{i[1]}_s{i.split("-")[1]}'] for i in fams[:2]})


class FakeLLM:
    """Stands in for council.llm.ask: runs the real prompt check, answers by stage and role, counts calls."""

    def __init__(self, bad_first=()):
        self.calls, self.prompts = [], {}
        self.bad_first = set(bad_first)

    def reply(self, prompt, role, stage):
        if stage == 'wave1':
            return [card_json(role, i) for i in range(1, 9)]
        if stage == 'reference':
            k = role[-1]
            return [dict(name=f'p{i}', idea=f'idea {i}',
                         sql=f'SELECT product_id, 1.0 AS f_x_rb{k}_p{i} FROM hist' + (' BAD' if i == 3 else ''))
                    for i in range(1, 13)]
        if stage == 'reference-fix':
            k = role[-1]
            return [dict(name='p3', idea='fixed', sql=f'SELECT product_id, 2.0 AS f_x_rb{k}_p3 FROM hist')]
        if stage == 'cross':
            return [dict(card=a, type='MECHANISM_DOUBT', text='doubt', kill_test='twin as a factor')
                    for a in re.findall(r'^--- (C\d\d)$', prompt, re.M)]
        if stage == 'authors':
            ids = re.findall(r'^--- (G\d-\d+)$', prompt, re.M)
            out = []
            for cid in ids:
                lens, i = cid.split('-')
                if i == '2':
                    out.append(dict(card=cid, action='withdraw', reason='weak'))
                elif i == '1':
                    sql = f'SELECT user_id, product_id, 0.75 AS f_x_c{lens[1]}_s1 FROM hist'
                    out.append(dict(card=cid, action='revise', new=card_json(lens, 1, sql)))
                else:
                    out.append(dict(card=cid, action='revise', new=card_json(lens, int(i))))
            return out
        raise AssertionError(stage)

    def __call__(self, prompt, role, stage, model='opus', *, subs, sources=(), free=(), max_calls=40, check=None):
        llm.check_prompt(prompt, subs, sources, free)
        self.calls.append((stage, role))
        self.prompts[(stage, role)] = prompt
        value = self.reply(prompt, role, stage)
        return (check(value) if check else value), dict(seconds=1.0, cost_usd=0.1, attempts=1)


class TmpRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        for p in (mock.patch.object(roles, 'RUNS', root / 'runs'), mock.patch.object(roles, 'LLM_DIR', root / 'llm')):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.ev = FakeEvidence()
        p = mock.patch.object(agents, '_evidence', return_value=self.ev)
        p.start()
        self.addCleanup(p.stop)

    def fake_llm(self, **kw):
        fake = FakeLLM(**kw)
        p = mock.patch.object(llm, 'ask', fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def read(self, name):
        return json.loads((roles.RUNS / name).read_text())


def completed(result, cost=0.42, code=0, is_error=False):
    out = json.dumps(dict(type='result', result=result, total_cost_usd=cost, is_error=is_error))
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr='')


# ---------------------------------------------------------------- llm

class TestLLM(TmpRuns):
    def test_command_cwd_env_log_and_prompt_file(self):
        with mock.patch.object(subprocess, 'run', return_value=completed('Here:\n```json\n[{"a": 7}]\n```')) as run, \
                mock.patch.dict('os.environ', {'CLAUDE_CODE_PLUGIN_DIRS': '/x', 'MCP_X': '1'}):
            value, meta = llm.ask('prompt with 7 items', 'G1', 'wave1', subs=dict(n='7'), sources=[dict(n=7)])
        self.assertEqual(value, [{'a': 7}])
        argv, kw = run.call_args
        self.assertEqual(argv[0], ['claude', '-p', 'prompt with 7 items', '--model', 'opus', '--output-format', 'json',
                                   '--tools', '', '--strict-mcp-config'])
        self.assertEqual(kw['cwd'], roles.LLM_DIR)
        self.assertEqual(kw['timeout'], 900)
        self.assertFalse([k for k in kw['env'] if k.startswith(('CLAUDE', 'MCP', 'ANTHROPIC'))])
        rec = [json.loads(x) for x in (roles.RUNS / 'llm.jsonl').read_text().splitlines()]
        self.assertEqual(len(rec), 1)
        self.assertEqual((rec[0]['stage'], rec[0]['role'], rec[0]['cost_usd'], rec[0]['error']), ('wave1', 'G1', 0.42, None))
        self.assertEqual(len(rec[0]['prompt_sha256']), 64)
        self.assertIn('seconds', rec[0])
        self.assertEqual(rec[0]['command'], ['claude', '-p', '<prompt>', '--model', 'opus', '--output-format', 'json',
                                             '--tools', '', '--strict-mcp-config'])
        self.assertNotIn('--bare', rec[0]['command'])
        head, body = (roles.RUNS / 'prompts/wave1-G1.txt').read_text().split('\n\n', 1)
        self.assertEqual(body, 'prompt with 7 items')
        self.assertIn('# command: ' + json.dumps(rec[0]['command']), head)
        self.assertIn(f'# cwd: {roles.LLM_DIR}', head)
        self.assertIn(rec[0]['prompt_sha256'], head)
        self.assertEqual(meta['cost_usd'], 0.42)

    def test_number_outside_sources_is_refused_before_the_call(self):
        with mock.patch.object(subprocess, 'run') as run:
            with self.assertRaises(llm.PromptRefused):
                llm.ask('x', 'critic-G1', 'cross', subs=dict(cards='rho 0.31, gain 0.0021'), sources=[dict(rho=0.31)])
            run.assert_not_called()
        self.assertEqual(llm.calls_made(), 0)
        self.assertFalse(json.loads((roles.RUNS / 'llm.jsonl').read_text())['call'])
        self.assertEqual(llm.number_problems(dict(a='rho 0.31 and 12 cards'), dict(rho=0.31), 'twelve 12'), [])

    def test_names_and_days_after_the_training_anchors_are_refused(self):
        for prompt in ('a Kaggle leaderboard', 'anchors 2020-01-15..2020-02-08'):
            with self.subTest(prompt=prompt), mock.patch.object(subprocess, 'run') as run:
                with self.assertRaises(llm.PromptRefused):
                    llm.ask(prompt, 'G1', 'wave1', subs={})
                run.assert_not_called()
        llm.check_prompt('anchors 2020-01-15..2020-02-07', {}, [])

    def test_free_slots_skip_the_word_and_day_test_but_not_the_template(self):
        text = 'a competition card for 2020-02-12'
        prompt = f'Cards:\n{text}\nend'
        llm.check_prompt(prompt, dict(cards=text), [dict(d='2020-02-12')], free=('cards',))
        for subs, free in ((dict(cards=text), ()), (dict(cards=text, other='x'), ('other',))):
            with self.subTest(free=free), self.assertRaises(llm.PromptRefused):
                llm.check_prompt(prompt, subs, [dict(d='2020-02-12')], free=free)
        with self.assertRaises(llm.PromptRefused):  # the template outside the slot is still checked
            llm.check_prompt('Kaggle ' + prompt, dict(cards=text), [dict(d='2020-02-12')], free=('cards',))
        with self.assertRaises(llm.PromptRefused):  # the numbers of a free slot are still checked
            llm.check_prompt(prompt, dict(cards=text + ' 0.31'), [dict(d='2020-02-12')], free=('cards',))
        with self.assertRaises(llm.PromptRefused):
            llm.check_prompt(prompt, dict(cards=text), [dict(d='2020-02-12')], free=('nope',))

    def test_unparsable_reply_is_asked_once_more(self):
        replies = [completed('I think the answer is no list at all'), completed('[{"name": "a"}]')]
        with mock.patch.object(subprocess, 'run', side_effect=replies) as run:
            value, meta = llm.ask('p', 'G2', 'wave1', subs={})
        self.assertEqual((value, meta['attempts'], run.call_count), ([{'name': 'a'}], 2, 2))
        with mock.patch.object(subprocess, 'run', side_effect=[completed('none'), completed('still none'),
                                                               completed('[1]')]) as run:
            with self.assertRaises(llm.LLMError):
                llm.ask('p', 'G3', 'wave1', subs={})
        self.assertEqual(run.call_count, 2)
        self.assertEqual(llm.calls_made(), 4)

    def test_check_failure_counts_as_a_parse_failure(self):
        def check(v):
            raise ValueError('no usable card')
        with mock.patch.object(subprocess, 'run', return_value=completed('[{"x": 1}]')) as run:
            with self.assertRaises(llm.LLMError):
                llm.ask('p', 'G1', 'wave1', subs={}, check=check)
        self.assertEqual(run.call_count, 2)

    def test_failed_call_is_logged_and_counted(self):
        with mock.patch.object(subprocess, 'run', return_value=completed('overloaded', code=1, is_error=True)):
            with self.assertRaises(llm.LLMError):
                llm.ask('p', 'G1', 'wave1', subs={})
        rec = json.loads((roles.RUNS / 'llm.jsonl').read_text())
        self.assertTrue(rec['call'] and rec['error'])
        self.assertEqual(llm.calls_made(), 1)

    def test_campaign_cap(self):
        roles.RUNS.mkdir(parents=True)
        (roles.RUNS / 'llm.jsonl').write_text(''.join(json.dumps(dict(call=True)) + '\n' for _ in range(40)))
        with mock.patch.object(subprocess, 'run') as run:
            with self.assertRaises(llm.BudgetSpent):
                llm.ask('p', 'G1', 'wave1', subs={})
            run.assert_not_called()
        (roles.RUNS / 'llm.jsonl').write_text('')
        with mock.patch.object(subprocess, 'run', return_value=completed('no json')) as run:
            with self.assertRaises(llm.BudgetSpent):  # the retry does not pass the cap
                llm.ask('p', 'G1', 'wave1', subs={}, max_calls=1)
        self.assertEqual(run.call_count, 1)

    def test_workdir_must_be_empty(self):
        roles.LLM_DIR.mkdir(parents=True)
        (roles.LLM_DIR / 'CLAUDE.md').write_text('x')
        with mock.patch.object(subprocess, 'run') as run:
            with self.assertRaises(llm.LLMError):
                llm.ask('p', 'G1', 'wave1', subs={})
            run.assert_not_called()
        self.assertEqual(llm.calls_made(), 0)
        self.assertFalse(json.loads((roles.RUNS / 'llm.jsonl').read_text())['call'])

    def test_unfinished_last_line_of_the_log(self):
        roles.RUNS.mkdir(parents=True)
        (roles.RUNS / 'llm.jsonl').write_text(json.dumps(dict(call=True)) + '\n' + '[1]\n' + '{"call": tr')
        self.assertEqual(llm.calls_made(), 1)
        with mock.patch.object(subprocess, 'run', return_value=completed('[{"a": 1}]')):
            llm.ask('p', 'G1', 'wave1', subs={})
        self.assertEqual(llm.calls_made(), 2)  # the new record starts its own line

    def test_extract_json(self):
        self.assertEqual(llm.extract_json('```json\n[{"a": [1, 2]}]\n```'), [{'a': [1, 2]}])
        self.assertEqual(llm.extract_json('Cards [see below]: {"cards": [{"a": 1}]}'), {'cards': [{'a': 1}]})
        self.assertEqual(llm.extract_json('[] then [{"b": 2}]'), [{'b': 2}])
        for bad in ('no json', '[unclosed', None):
            with self.assertRaises(ValueError):
                llm.extract_json(bad)


# ---------------------------------------------------------------- prompts

class TestPrompts(unittest.TestCase):
    def test_templates_carry_no_result_words_days_or_boundary_words(self):
        listed = agents._wrap(agents.forbidden_words())
        for name, t in agents.TEMPLATES.items():
            with self.subTest(template=name):
                t = t.replace(listed, '')
                low = t.lower()
                self.assertIsNone(llm.NAMES.search(t))
                self.assertIsNone(re.search(r'\b(validation|val|holdout|public|private|leaderboard)\b', low))
                rest = low.replace('kill_test', '').replace('machine test', '')
                self.assertIsNone(re.search(r'\btests?\b', rest))
                self.assertFalse([d for d in LATE_DAYS if d in t])
                self.assertFalse([w for w in BOUNDARY if w in low])

    def test_rules_list_the_forbidden_words_of_extra(self):
        from task1.extra import FORBIDDEN
        words = agents.forbidden_words()
        self.assertGreater(len(words), 10)
        for w in words:
            self.assertIn(w, agents.RULES)
            self.assertTrue(FORBIDDEN.search(w.replace('*', 'x')), w)
        prompt = agents.generator_prompt('G1', CTX)[0]
        self.assertIn(agents._wrap(words), prompt)

    def test_rendered_prompts_pass_the_check(self):
        prompts = [agents.generator_prompt(lens, CTX) for lens in agents.LENSES] + [agents.reference_prompt(2, CTX)]
        for prompt, subs, sources in prompts:
            llm.check_prompt(prompt, subs, sources)
            self.assertNotIn('<<', prompt)
        self.assertIn('f_x_c3_', agents.generator_prompt('G3', CTX)[0])
        self.assertIn('f_x_rb2_', prompts[-1][0])

    def test_render_needs_every_placeholder(self):
        with self.assertRaises(ValueError):
            agents.render('a <<x>> <<y>>', x=1)
        with self.assertRaises(ValueError):
            agents.render('a <<x>>', x=1, y=2)

    @unittest.skipUnless(agents.TRIED_LOG.exists() and any(roles.DAYS6.glob('*.parquet')), 'no H+ data here')
    def test_real_prompts_hold_the_hplus_names_and_no_outcome_of_the_log(self):
        ctx = agents.context()
        schema = ctx[1][0]
        self.assertEqual(len(schema['base']) + sum(map(len, schema['tables'].values())), roles.HPLUS_FEATURES)
        self.assertEqual(len(ctx[1][1]), 30)
        # every number the log keeps besides name, idea and SQL is a measured outcome or a timing
        outcome = set()
        for line in agents.TRIED_LOG.read_text().splitlines():
            r = json.loads(line)
            for k, v in r.items():
                if k in ('name', 'idea', 'sql', 'round', 'start', 'config', 'args'):
                    continue
                for leaf in llm._leaves(v):
                    if isinstance(leaf, float) and len(repr(abs(leaf))) >= 6:
                        outcome.add(abs(leaf))
        self.assertGreater(len(outcome), 30)
        for lens in agents.LENSES:
            prompt, subs, sources = agents.generator_prompt(lens, ctx)
            llm.check_prompt(prompt, subs, sources)
            numbers = {float(x) for x in llm.NUMBER.findall(prompt)}
            self.assertFalse(numbers & outcome, lens)
            self.assertNotIn('accepted', prompt.lower())
            self.assertNotIn('agent_night20', prompt)
            for c in schema['base'][:3] + schema['tables']['dfs_u'][-2:]:
                self.assertIn(c, prompt)
        prompt = agents.reference_prompt(1, ctx)[0]
        self.assertFalse({float(x) for x in llm.NUMBER.findall(prompt)} & outcome)


# ---------------------------------------------------------------- parsing

class TestParsing(unittest.TestCase):
    def test_cards_are_parsed_robustly(self):
        raw = [card_json('G2', 1) | dict(id='G9-77', lens='G4', extra='x'),
               card_json('G2', 2) | dict(sign='positive', name='3D Graph-Walk!'),
               'not a card',
               card_json('G2', 4) | dict(twin='no twin'),
               card_json('G2', 5) | dict(stratum={'words': 'w', 'sql': 'p'}),
               card_json('G2', 6) | dict(rival='plain popularity'),
               card_json('G2', 7) | dict(rival=dict(explanation='popularity', stratum=' ')),
               card_json('G2', 8) | dict(stratum='')] + [card_json('G2', i) for i in range(9, 12)]
        got = agents.parse_cards({'cards': raw}, 'G2')
        ids = [c['id'] for c in got['cards']]
        self.assertEqual(ids, ['G2-1', 'G2-2', 'G2-5'])  # 8 positions at most
        self.assertEqual([r['id'] for r in got['rejected']], ['G2-3', 'G2-4', 'G2-6', 'G2-7', 'G2-8'])
        for bad in (dict(null_stratum=None), dict(null_stratum='  '), dict(stratum={}),
                    dict(rival=dict(explanation='x')), dict(rival=None)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                agents.parse_card(card_json('G2', 1) | bad, 'G2-1', 'G2')
        c1, c2, c5 = got['cards'][0], got['cards'][1], got['cards'][2]
        self.assertEqual((c1['lens'], set(c1)), ('G2', {'id', 'lens'} | set(agents.CARD_FIELDS)))
        self.assertEqual((c2['sign'], c2['name']), ('+', 'f_3d_graph_walk'))
        self.assertIn('sql: p', c5['stratum'])
        with self.assertRaises(ValueError):
            agents.parse_cards(['x', {'sign': '?'}], 'G1')
        same = agents.parse_cards([card_json('G1', 1), card_json('G1', 2, card_json('G1', 1)['sql'])], 'G1')
        self.assertEqual(([c['id'] for c in same['cards']], same['rejected'][0]['id']), (['G1-1'], 'G1-2'))

    def test_critiques_map_aliases_and_drop_junk(self):
        aliases = {'C01': 'G1-3', 'C02': 'G4-1'}
        got = agents.parse_critiques([dict(card='c01', type='rival', text='t', kill_test='k'),
                                      dict(card='C02', type='LIKE', text='t'), dict(card='C09', type='OK'), 'junk',
                                      dict(card='C02', type='mechanism doubt', text='u')], aliases, 'G2')
        self.assertEqual([(q['card'], q['type'], q['critic']) for q in got],
                         [('G1-3', 'RIVAL', 'G2'), ('G4-1', 'MECHANISM_DOUBT', 'G2')])
        with self.assertRaises(ValueError):
            agents.parse_critiques([dict(card='C09', type='OK')], aliases, 'G2')

    def test_replies(self):
        own = agents.parse_cards([card_json('G3', i) for i in range(1, 4)], 'G3')['cards']
        got = agents.parse_replies([dict(card='G3-1', action='revise', new=card_json('G3', 1)),
                                    dict(card='g3-2', action='withdraw', reason='r'),
                                    dict(card='G3-3', action='revise', new={'sign': '+'}),
                                    dict(card='G1-1', action='withdraw')], own)
        self.assertEqual([(a['card'], a['action']) for a in got],
                         [('G3-1', 'revise'), ('G3-2', 'withdraw'), ('G3-3', 'unusable')])
        self.assertEqual(got[0]['new']['id'], 'G3-1')

    def test_proposals(self):
        got = agents.parse_proposals([dict(name='A b', idea='i', sql='SELECT 1'), dict(name='a_b', sql='SELECT 2'),
                                      dict(name='c'), 'x'], 1)
        self.assertEqual([(p['name'], p['table']) for p in got], [('a_b', 'council_rb1_a_b'), ('a_b_2', 'council_rb1_a_b_2')])
        self.assertEqual(agents.table('G3-2'), 'council_g3_2')


# ---------------------------------------------------------------- stages

class TestStages(TmpRuns):
    def wave(self):
        return agents.wave1(CTX)

    def test_wave1_is_resumable(self):
        fake = self.fake_llm()
        cards = self.wave()
        self.assertEqual(len(cards), 32)
        self.assertEqual([c for c, _ in fake.calls], ['wave1'] * 4)
        self.wave()
        self.assertEqual(len(fake.calls), 4)
        state = self.read('cards-wave1.json')
        del state['G3'], state['G4']
        (roles.RUNS / 'cards-wave1.json').write_text(json.dumps(state))
        self.wave()
        self.assertEqual([r for _, r in fake.calls[4:]], ['G3', 'G4'])

    def test_wave1_stops_at_the_cap_with_the_real_ask(self):
        roles.RUNS.mkdir(parents=True)
        (roles.RUNS / 'llm.jsonl').write_text(''.join(json.dumps(dict(call=True)) + '\n' for _ in range(39)))
        reply = completed(json.dumps([card_json('G1', i) for i in range(1, 9)]))
        with mock.patch.object(subprocess, 'run', return_value=reply) as run:
            with self.assertRaises(llm.BudgetSpent):
                self.wave()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(list(self.read('cards-wave1.json')), ['G1'])

    def test_critic_assignment(self):
        cards = [dict(id=f'{g}-{i}', lens=g) for g in agents.LENSES for i in range(1, 9)]
        a = agents.critic_assignment(cards)
        for c in cards:
            critics = [g for g in agents.LENSES if c in a[g]]
            self.assertEqual(len(critics), 2)
            self.assertNotIn(c['lens'], critics)
            self.assertEqual(tuple(critics), tuple(sorted(agents.CRITICS[c['lens']])))
        for g in agents.LENSES:
            self.assertEqual(len(a[g]), 16)
            self.assertFalse([c for c in a[g] if c['lens'] == g])
        self.assertEqual(len(a['skeptic']), 32)
        self.assertEqual(len(a['auditor']), 32)

    def test_evidence_cross_authors_prereg_curate(self):
        fake = self.fake_llm()
        cards = self.wave()
        probes = agents.evidence_stage(cards)
        self.assertEqual(len(probes), 32)
        n = len(self.ev.probed)
        agents.evidence_stage(cards)
        self.assertEqual(len(self.ev.probed), n)  # nothing measured twice

        critiques = agents.cross_exam(cards, probes, CTX)
        cross = [r for s, r in fake.calls if s == 'cross']
        self.assertEqual(cross, ['critic-G1', 'critic-G2', 'critic-G3', 'critic-G4', 'skeptic', 'auditor'])
        for (stage, role), prompt in fake.prompts.items():
            if stage != 'cross':
                continue
            self.assertIsNone(re.search(r"\bG[1-4]\b", prompt.split("Below are", 1)[1]), role)
            self.assertIsNone(re.search(r'f_x_c[1-4]_', prompt), role)
            self.assertNotIn('council_g', prompt)
            self.assertNotIn('"lens"', prompt)
            self.assertNotIn('"id"', prompt)
        self.assertIn('Already tried', fake.prompts[('cross', 'skeptic')])
        self.assertNotIn('Already tried', fake.prompts[('cross', 'critic-G1')])
        self.assertNotIn('mechanism', json.dumps(re.findall(r'^card: .*', fake.prompts[('cross', 'auditor')], re.M)))
        state = self.read('critiques.json')
        for role in ('G1', 'G2', 'G3', 'G4'):
            seen = set(state[role]['aliases'].values())
            self.assertEqual(seen, {c['id'] for c in cards if role in agents.CRITICS[c['lens']]})
            self.assertEqual({q['card'] for q in state[role]['critiques']}, seen)
        per_card = {c['id']: [q['critic'] for q in critiques if q['card'] == c['id']] for c in cards}
        self.assertTrue(all(len(v) == 4 for v in per_card.values()))
        agents.cross_exam(cards, probes, CTX)
        self.assertEqual(len(fake.calls), 10)

        final = agents.author_replies(cards, critiques, probes, CTX)
        self.assertEqual([r for s, r in fake.calls if s == 'authors'], list(agents.LENSES))
        self.assertIn('doubt', fake.prompts[('authors', 'G2')])
        self.assertNotIn('G1-', fake.prompts[('authors', 'G2')])
        self.assertEqual(len(final), 28)
        st = self.read('cards-final.json')
        self.assertEqual(sorted(w['id'] for w in st['withdrawn']), ['G1-2', 'G2-2', 'G3-2', 'G4-2'])
        self.assertEqual(st['revised'], ['G1-1', 'G2-1', 'G3-1', 'G4-1'])
        self.assertTrue(all(set(c) == {'id', 'lens'} | set(agents.CARD_FIELDS) for c in final))
        agents.author_replies(cards, critiques, probes, CTX)
        self.assertEqual(len(fake.calls), 14)

        before = len(self.ev.probed)
        probes2 = agents.evidence_stage(final)
        self.assertEqual(self.ev.probed[before:], ['G1-1', 'G2-1', 'G3-1', 'G4-1'])  # only revised cards again
        pre = agents.prereg1(final, critiques)
        self.assertEqual(len(pre['cards']), 28)
        c = pre['cards'][0]
        self.assertEqual((c['id'], c['table'], c['sign']), ('G1-1', 'council_g1_1', '+'))
        self.assertEqual(c['sql_sha256'], agents.sha(final[0]['sql']))
        self.assertEqual(len(c['kill_tests']), 4)
        self.assertEqual(sorted(pre['code_sha256']), ['agents.py', 'design.py', 'evidence.py', 'llm.py'])
        self.assertEqual(pre['code_sha256']['evidence.py'],
                         agents.sha((roles.ROOT / 'council/evidence.py').read_text()))

        for k in (1, 2):
            agents.reference(k, ctx=CTX)
        self.ev.fail = 'parity not reached'
        with self.assertRaises(SystemExit):
            agents.curator_stage(final, probes2, critiques)
        self.assertFalse((roles.RUNS / 'curation.json').exists())
        self.ev.fail = None
        cur = agents.curator_stage(final, probes2, critiques)
        cards_in, probes_in, rb_in, crit_in = self.ev.curated
        self.assertEqual(len(cards_in), 32)
        self.assertEqual(sorted(q['card'] for q in crit_in if q['type'] == 'WITHDRAWN'),
                         ['G1-2', 'G2-2', 'G3-2', 'G4-2'])
        self.assertEqual(len(probes_in), 32)
        order = [f'council_rb{k}_p{i}' for k in (1, 2) for i in range(1, 13)]
        self.assertEqual(list(rb_in), order)  # Rb1 by proposal, then Rb2
        self.assertTrue(all(p['per_day'] and p['columns'] for p in rb_in.values()))
        self.assertEqual(rb_in['council_rb1_p3']['sql'], self.read('reference-rb1.json')['proposals'][2]['sql'])
        self.assertEqual(cur['reference_order'], order)
        self.assertEqual(cur, self.read('curation.json'))
        kept = agents.reference_kept(cur)
        self.assertEqual(kept, [t for t in order if t not in ('council_rb1_p3', 'council_rb2_p12')])
        plan = [n for n, _ in agents.compute_plan(cur, final)]
        self.assertEqual(plan, ['council_g1_1', 'council_g1_3', 'council_g1_1_tw'] + kept)
        self.assertEqual(agents.curator_stage(final, probes2, critiques), cur)
        self.assertEqual(len(fake.calls), 14 + 4)

    def test_reference_fix_once_and_resume(self):
        fake = self.fake_llm()
        s = agents.reference(1, ctx=CTX)
        self.assertEqual(fake.calls, [('reference', 'rb1'), ('reference-fix', 'rb1')])
        fix = fake.prompts[('reference-fix', 'rb1')]
        self.assertIn('Binder Error: boom', fix)
        self.assertEqual(re.findall(r'"name": "(p\d+)"', fix), ['p3'])
        self.assertEqual(s['fix'], dict(asked=['p3'], answered=['p3']))
        self.assertEqual(len(s['tables']), 12)
        self.assertEqual(s['width'], 12)
        self.assertNotIn('BAD', s['proposals'][2]['sql'])
        self.assertIn('BAD', s['proposals'][2]['first_sql'])
        agents.reference(1, ctx=CTX)
        self.assertEqual(len(fake.calls), 2)

    def test_reference_without_failures_makes_one_call(self):
        fake = self.fake_llm()
        fake.reply = lambda prompt, role, stage: [dict(name='q', idea='i', sql='SELECT product_id, 1 AS f_x_rb2_q FROM hist'),
                                                  dict(name='r', idea='i', sql='SELECT product_id, 1 AS f_x_c1_r FROM hist')]
        s = agents.reference(2, ctx=CTX)
        self.assertEqual(len(fake.calls), 2)  # the wrong prefix of r is a failure of the check
        self.assertEqual(s['fix']['asked'], ['r'])

    def test_reference_column_names_may_not_repeat(self):
        fake = self.fake_llm()
        sql = 'SELECT product_id, 1 AS f_x_rb2_q FROM hist'
        fake.reply = lambda prompt, role, stage: [dict(name='q', idea='i', sql=sql), dict(name='r', idea='i', sql=sql)]
        s = agents.reference(2, ctx=CTX)
        self.assertEqual((s['fix']['asked'], s['tables']), (['r'], ['council_rb2_q']))

    def compute_setup(self, ok=True):
        roles.RUNS.mkdir(parents=True)
        cards = agents.parse_cards([card_json('G1', i) for i in (1, 2)], 'G1')['cards']
        (roles.RUNS / 'cards-final.json').write_text(json.dumps(dict(cards=cards)))
        self.curation = dict(families=['G1-1', 'G1-2'], twins=['G1-2'], reference_removed=['council_rb1_x'],
                             reference_order=['council_rb1_a', 'council_rb1_x', 'council_rb2_a', 'council_rb2_b'],
                             parity=dict(ok=ok, reference_drop=['council_rb2_b']),
                             columns={'G1-1': ['f_x_c1_s1'], 'G1-2': ['f_x_c1_s2']})
        (roles.RUNS / 'curation.json').write_text(json.dumps(self.curation))
        for k, names in ((1, ['a', 'x']), (2, ['a', 'b'])):
            props = [dict(name=n, sql=f'SELECT product_id, 1 AS f_x_rb{k}_{n} FROM hist', table=f'council_rb{k}_{n}')
                     for n in names]
            (roles.RUNS / f'reference-rb{k}.json').write_text(json.dumps(dict(
                done=True, proposals=props, tables=[p['table'] for p in props],
                probes={p['table']: dict(columns=[f'f_x_rb{k}_{p["name"]}']) for p in props})))
        extra_dir = Path(self.tmp.name) / 'extra'
        self.fail_on = set()

        def compute(name, sql, days=None, threads=8, days_dir=None):
            if name in self.fail_on and days == [agents.STRESS_DAY]:
                raise MemoryError('out of memory')
            d = extra_dir / name
            d.mkdir(parents=True, exist_ok=True)
            (d / 'feature.sql').write_text(sql.strip() + '\n')
            for day in days:
                (d / f'{day}.parquet').write_text('x')
            return re.findall(r'f_x_\w+', sql)
        self.extra = SimpleNamespace(EXTRA=extra_dir, compute=mock.Mock(side_effect=compute))
        for p in (mock.patch.dict('sys.modules', {'task1.extra': self.extra}),
                  mock.patch('task1.extra', self.extra, create=True)):
            p.start()
            self.addCleanup(p.stop)
        return extra_dir

    def calls(self):
        return [(c.args[0], c.kwargs['days']) for c in self.extra.compute.call_args_list]

    def test_compute_stage_stress_day_first_then_the_rest(self):
        self.compute_setup()
        st = agents.compute_stage(threads=3)
        names = ['council_g1_1', 'council_g1_2', 'council_g1_2_tw', 'council_rb1_a', 'council_rb2_a']
        calls = self.calls()
        self.assertEqual(calls[:5], [(n, [agents.STRESS_DAY]) for n in names])
        self.assertEqual(agents.STRESS_DAY.isoformat(), '2020-02-29')
        self.assertEqual([n for n, _ in calls[5:]], names)
        all_days = [d for s in agents.SPLITS for d in roles.days(s)]
        self.assertEqual(len(all_days), 46)
        self.assertEqual(calls[5][1], [d for d in all_days if d != agents.STRESS_DAY])
        kw = self.extra.compute.call_args.kwargs
        self.assertEqual((kw['days_dir'], kw['threads']), (roles.DAYS6, 3))
        self.assertEqual(st['council_g1_2_tw']['columns'], ['f_x_c1_s2_tw'])
        self.assertEqual({e['status'] for e in st.values()}, {'done'})
        self.assertEqual(self.ev.capped, 1)                 # under the answer cap of council.evidence
        agents.compute_stage(threads=3)
        self.assertEqual(self.extra.compute.call_count, 10)  # everything is on disk

    def test_compute_stage_resumes_missing_days_only(self):
        extra_dir = self.compute_setup()
        agents.compute_stage(threads=3)
        gone = roles.days('val')[:2]
        for d in gone:
            (extra_dir / 'council_rb2_a' / f'{d}.parquet').unlink()
        (extra_dir / 'council_g1_1' / f'{agents.STRESS_DAY}.parquet').unlink()
        n = self.extra.compute.call_count
        st = agents.compute_stage(threads=3)
        self.assertEqual(self.calls()[n:], [('council_g1_1', [agents.STRESS_DAY]), ('council_rb2_a', gone)])
        self.assertEqual(st['council_rb2_a']['computed'], [d.isoformat() for d in gone])
        self.assertEqual(st['council_g1_2']['computed'], [])

    def test_compute_stage_stops_on_a_foreign_feature_sql(self):
        extra_dir = self.compute_setup()
        (extra_dir / 'council_g1_2').mkdir(parents=True)
        (extra_dir / 'council_g1_2' / 'feature.sql').write_text('SELECT 1 AS f_x_c1_s2\n')
        with self.assertRaises(SystemExit) as e:
            agents.compute_stage(threads=3)
        self.assertIn('feature.sql', str(e.exception))
        self.assertEqual([n for n, _ in self.calls()], ['council_g1_1'])

    def test_compute_stage_failed_stress_stops_before_the_others(self):
        self.compute_setup()
        self.fail_on = {'council_g1_2_tw'}
        with self.assertRaises(SystemExit) as e:
            agents.compute_stage(threads=3)
        self.assertIn('without it', str(e.exception))
        self.assertEqual(self.calls(), [(n, [agents.STRESS_DAY]) for n in ('council_g1_1', 'council_g1_2',
                                                                          'council_g1_2_tw')])
        st = self.read('compute.json')
        self.assertEqual((st['council_g1_2_tw']['status'], st['council_g1_2_tw']['day']), ('failed_stress', '2020-02-29'))
        self.assertIn('MemoryError', st['council_g1_2_tw']['error'])
        self.fail_on = set()
        with self.assertRaises(SystemExit):  # the record stops the same plan without computing again
            agents.compute_stage(threads=3)
        self.assertEqual(self.extra.compute.call_count, 3)

    def test_compute_stage_needs_parity_and_unique_columns(self):
        self.compute_setup(ok=False)
        with self.assertRaises(SystemExit):
            agents.compute_stage(threads=3)
        self.curation['parity']['ok'] = True
        self.curation['columns']['G1-2'] = ['f_x_c1_s1']
        (roles.RUNS / 'curation.json').write_text(json.dumps(self.curation))
        with self.assertRaises(SystemExit):
            agents.compute_stage(threads=3)
        self.extra.compute.assert_not_called()


class TestBoundary(unittest.TestCase):
    def test_no_boundary_words_in_the_three_files(self):
        here = Path(__file__).resolve()
        for f in (here.parents[1] / 'llm.py', here.parents[1] / 'agents.py', here):
            text = f.read_text().lower()
            self.assertFalse([w for w in BOUNDARY if w in text], f.name)
            self.assertNotIn('exp.' + '_read', text)


if __name__ == '__main__':
    unittest.main()
