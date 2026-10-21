"""Golden tests of the REES46 council run (council/runs/xfer/contract.md §3, «Золотые тесты для agents.py /
llm.py»): the current council.agents, council.llm and council.evidence.curate reproduce the saved run
council/runs/rees46-2020 without any LLM call and without running a probe or SQL.

1. Prompts. Every record of llm.jsonl (18) is rebuilt from the saved inputs exactly as council.agents builds it
   at that point of the pipeline, then replayed through council.llm.ask with `claude -p` mocked to return the
   saved reply: the prompt hash equals prompt_sha256, the prompt equals the file prompts/<stage>-<role>.txt, the
   number test passes, the log record equals the saved one (but time and seconds) and the parsed value equals
   the saved state (cards-wave1.json, critiques.json, cards-final.json replies, reference-rb<k>.json).
2. Curator. agents.curator_stage (council.evidence.curate with the reference probes, as the stage passes them)
   on cards-final.json, probes.json and critiques.json writes curation.json byte for byte.

Inputs beyond the git files of the run, read only:
- agents.context(): the column names of H+ (parquet schemas of days6 and of the 34 extra tables, no rows) and
  task1/runs/agent_night20/log.jsonl, as the stages read them;
- the probe cache of council.evidence (artifacts/task1/v2020/council/probes/<sha256(sql)[:16]>.json and its
  .values.parquet samples). It holds the saved raw probes the stages saw where the run files keep only a later
  version: probes.json keeps one entry per card id, so the 18 cards revised by their authors carry only the
  revised probe, and the cross and authors prompts (which show the wave1 version) need the wave1 probes; the
  reference-fix prompts show the pre-fix probes of the failed proposals, which reference-rb<k>.json overwrote
  after the fix. The cache is written with sort_keys=True, while the run held a fresh probe in insertion order
  (the order of its columns); _fresh_order restores that order, and the hash match is what proves it.
  A missing cache entry skips the subtest with the stage and the missing entry named; nothing is computed.
  Every path that would run SQL (_probe_day, sandbox, the cache writers, task1.extra) raises instead.

Deviation 13 of council/runs/rees46-2020/prereg-0.md: reference, reference-fix and wave1 (8 calls) ran with the
agents.py/llm.py before the review fixes. These prompts do NOT reproduce with the current code; the tests pin
the mismatch and its explanation:
- RULES of the current templates carry the list of words the sandbox refuses (task1.extra.FORBIDDEN, <<FORBIDDEN>>);
  the old RULES ended the speed rule with a full stop and had no such list. Removing exactly that block from the
  current rendering reproduces all 8 hashes and files. The block is the whole difference.
- Log flags: the old llm.jsonl records have no `command` and `free`, and their prompt files no header.
- Name masking: the old and the current `tried` text are the same (no idea of the tried tables names a word of
  llm.NAMES; 'accepted' -> 'earlier' was already there), so this fix leaves no trace in these prompts.
The cross and authors prompts (10 calls) ran with the current code and reproduce exactly.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_golden_rees46 -v
(about 10 s for the prompts, about 2 min for the curator: ~240 card-card statistics on the stored samples)
"""
import contextlib
import hashlib
import inspect
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council import agents, llm, roles
from council import evidence as ev
from task1 import extra as X

SAVED = roles.RUNS
RUN_FILES = ('cards-wave1.json', 'cards-final.json', 'probes.json', 'critiques.json', 'reference-rb1.json',
             'reference-rb2.json')
LEGACY = ('reference', 'reference-fix', 'wave1')      # deviation 13: the code before the review fixes
CURRENT = ('cross', 'authors')
EXPECTED_CALLS = ({('reference', f'rb{k}') for k in (1, 2)} | {('reference-fix', f'rb{k}') for k in (1, 2)}
                  | {('wave1', g) for g in agents.LENSES} | {('authors', g) for g in agents.LENSES}
                  | {('cross', f'critic-{g}') for g in agents.LENSES} | {('cross', 'skeptic'), ('cross', 'auditor')})
HEADER = '# command: '

# The rule the review fixes added to RULES (deviation 13): the old text ended the speed rule here.
OLD_RULE_END = 'aim for under 20 s.\n'
NEW_RULE_END = ('aim for under 20 s;\n'
                '- the sandbox refuses a query containing any of these words, matched as whole words in any case '
                'anywhere in\n  the text, also as aliases, column names or inside strings (* is any continuation):\n'
                + agents._wrap(agents.forbidden_words()) + '\n')


class CacheMiss(AssertionError):
    """A saved probe is not in the cache: the input is missing, and nothing may be computed instead."""


def _refuse(what):
    def refuse(*args, **kwargs):
        raise CacheMiss(f'{what} would run: the saved probe is missing')
    return refuse


@contextlib.contextmanager
def offline(runs):
    """roles.RUNS -> runs (a copy), no SQL, no probe computation, no write into the probe cache, no LLM call."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(roles, 'RUNS', Path(runs)))
        for name in ('_probe_day', '_context', 'sandbox', '_run', '_write_json', '_to_parquet'):
            stack.enter_context(mock.patch.object(ev, name, _refuse(f'council.evidence.{name}')))
        for name in ('sandbox', 'compute', 'run_query'):
            stack.enter_context(mock.patch.object(X, name, _refuse(f'task1.extra.{name}')))
        stack.enter_context(mock.patch.object(llm, '_call', _refuse('claude -p')))
        stack.enter_context(mock.patch.object(llm, '_workdir', lambda: roles.LLM_DIR))  # no mkdir in /tmp
        yield


def _copy_run(dest, files=RUN_FILES):
    for f in files:
        shutil.copy(SAVED / f, Path(dest) / f)


def _fresh_order(obj, cols):
    """A cached probe (sort_keys=True) in the order of a fresh one: dicts keyed by the columns in column order."""
    if isinstance(obj, dict):
        if cols and set(obj) == set(cols):
            return {c: _fresh_order(obj[c], cols) for c in cols}
        return {k: _fresh_order(v, cols) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fresh_order(v, cols) for v in obj]
    return obj


def _cache_only_probe(card_or_sql, days=roles.PROBE_DAYS, threads=10, _real=ev.probe):
    """council.evidence.probe served by the cache only (inside offline()), in the order of a fresh probe."""
    if isinstance(card_or_sql, dict):
        return ev._probe_card(card_or_sql, days, threads)      # its SQL probes come back here
    p = _real(card_or_sql, days, threads)
    return _fresh_order(p, p.get('columns') or [])


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _saved_prompt(stage, role):
    """(header lines or None, prompt) of prompts/<stage>-<role>.txt."""
    text = (SAVED / 'prompts' / f'{stage}-{role}.txt').read_text()
    if text.startswith(HEADER):
        head, body = text.split('\n\n', 1)
        return head.splitlines(), body
    return None, text


def _legacy(prompt):
    """The prompt as the code before the review fixes rendered it: RULES without the FORBIDDEN block."""
    if prompt.count(NEW_RULE_END) != 1:
        raise AssertionError('the FORBIDDEN block of RULES is not in the prompt exactly once')
    return prompt.replace(NEW_RULE_END, OLD_RULE_END)


class GoldenPrompts(unittest.TestCase):
    """The 18 prompts of llm.jsonl, rebuilt and replayed through llm.ask."""

    @classmethod
    def setUpClass(cls):
        cls.records = [json.loads(line) for line in (SAVED / 'llm.jsonl').read_text().splitlines()]
        cls.tmp = tempfile.TemporaryDirectory()
        cls.runs = Path(cls.tmp.name) / 'run'
        cls.runs.mkdir()
        _copy_run(cls.runs)
        cls.ctx_error = cls.wave_error = None
        cls.ctx = cls.wave_probes = None
        try:
            cls.ctx = agents.context()
        except Exception as e:  # no days6/extra schemas or no log of the tried tables on this machine
            cls.ctx_error = f'{type(e).__name__}: {e}'
            return
        # The evidence the cross and authors stages saw: evidence_stage(wave1 cards). probes.json holds the wave1
        # version of 14 cards; the 18 revised ones come back from the probe cache (cache only).
        with offline(cls.runs), mock.patch.object(ev, 'probe', _cache_only_probe):
            cls.wave_cards = agents._wave1_cards()
            try:
                cls.wave_probes = agents.evidence_stage(cls.wave_cards)
            except CacheMiss as e:
                cls.wave_error = str(e)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def need_ctx(self):
        if self.ctx_error:
            self.skipTest(f'agents.context() needs the H+ schemas (days6, extra) and {agents.TRIED_LOG}: '
                          f'{self.ctx_error}')

    def need_wave_probes(self, stage):
        self.need_ctx()
        if self.wave_error:
            self.skipTest(f'stage {stage}: missing input: the wave1 probes of the revised cards (probes.json keeps '
                          f'only the revised version; probe cache {roles.PROBES}): {self.wave_error}')

    # ------------------------------------------------------------ the saved run itself

    def test_inventory_and_saved_prompt_files(self):
        """18 calls, one attempt each; every saved prompt file hashes to its record (old files: no header)."""
        self.assertEqual(len(self.records), 18)
        self.assertEqual({(r['stage'], r['role']) for r in self.records}, EXPECTED_CALLS)
        for r in self.records:
            with self.subTest(stage=r['stage'], role=r['role']):
                self.assertTrue(r['call'])
                self.assertEqual(r['attempt'], 1)
                self.assertIsNone(r['error'])
                head, body = _saved_prompt(r['stage'], r['role'])
                self.assertEqual(_sha(body), r['prompt_sha256'])
                if r['stage'] in LEGACY:   # deviation 13, log flags: neither the argv in the log nor a header
                    self.assertIsNone(head)
                    self.assertNotIn('command', r)
                    self.assertNotIn('free', r)
                else:
                    self.assertEqual(head, [f'# command: {json.dumps(r["command"])}', f'# cwd: {roles.LLM_DIR}',
                                            f'# prompt_sha256: {r["prompt_sha256"]}'])
                    self.assertEqual(r['command'], llm.flags(r['model']))
                    self.assertEqual(r['free'], ['cards'])

    def test_wave1_probes_from_cache_match_probes_json(self):
        """The cache reconstruction gives the saved probes.json evidence of the 14 cards that were not revised, and
        the same view in the same order as the prompts show it: the reconstruction of the other 18 rests on that."""
        self.need_wave_probes('cross')
        store = json.loads((SAVED / 'probes.json').read_text())
        final = json.loads((SAVED / 'cards-final.json').read_text())
        kept = [c for c in self.wave_cards if c['id'] not in final['revised']]
        revised = [c for c in self.wave_cards if c['id'] in final['revised']]
        self.assertEqual((len(kept), len(revised)), (14, 18))
        with offline(self.runs), mock.patch.object(ev, 'probe', _cache_only_probe):
            for c in kept:
                with self.subTest(card=c['id']):
                    got = agents._plain(ev.probe(agents.clean(c), roles.PROBE_DAYS, 8))
                    got['machine_red'] = ev.machine_red(got['card']) if got.get('card') else ['no probe']
                    saved = store[c['id']]['evidence']
                    self.assertEqual(got, saved)
                    # what the prompts show, in its order (the cache sorts every key, a fresh probe does not:
                    # only the order of the column-keyed dicts reaches a prompt, and _fresh_order restores it)
                    self.assertEqual(json.dumps(agents.evidence_view(got)), json.dumps(agents.evidence_view(saved)))
        for c in revised:   # probes.json really lost their wave1 version
            self.assertNotEqual(store[c['id']]['sql_sha256'] + store[c['id']]['twin_sha256'],
                                agents.sha(c['sql']) + agents.sha(c['twin']['sql']), c['id'])

    def test_deviation13_name_masking_is_inert(self):
        """No idea of the tried tables names a word of llm.NAMES, so masking leaves the tried text as it was."""
        self.need_ctx()
        raw = [json.loads(line) for line in agents.TRIED_LOG.read_text().splitlines()]
        ideas = [r.get('idea', '') for r in raw if r.get('name') in roles.HPLUS and 'sql' in r]
        self.assertEqual(len(ideas), len(agents.tried()))
        self.assertFalse([i for i in ideas if llm.NAMES.search(i)])

    def test_deviation13_legacy_rule_block(self):
        """The FORBIDDEN block is in every template that carries RULES, once."""
        self.assertEqual(agents.RULES.count(NEW_RULE_END), 1)
        for name in ('reference', 'reference_fix', 'generator', 'critic', 'skeptic', 'auditor', 'author'):
            self.assertEqual(agents.TEMPLATES[name].count(NEW_RULE_END), 1, name)

    # ------------------------------------------------------------ rebuilding

    def rebuild(self, stage, role):
        """dict(prompt, subs, sources, free, check, expected) of one call, from the saved inputs."""
        ctx = self.ctx
        if stage == 'reference':
            k = int(role[2])
            prompt, subs, sources = agents.reference_prompt(k, ctx)
            st = json.loads((SAVED / f'reference-rb{k}.json').read_text())
            # the proposals as first parsed: the fix later overwrote sql (kept in first_sql) and idea
            fixed = set(st['fix'].get('answered', []))
            expected = [dict(name=p['name'], sql=p.get('first_sql', p['sql']), table=p['table'],
                             **({} if p['name'] in fixed else dict(idea=p['idea']))) for p in st['proposals']]
            return dict(prompt=prompt, subs=subs, sources=sources, free=(),
                        check=lambda v: agents.parse_proposals(v, k), expected=expected,
                        compare=lambda got: [{f: g[f] for f in e} for g, e in zip(got, expected)] + got[len(expected):])
        if stage == 'reference-fix':
            return self.rebuild_fix(int(role[2]))
        if stage == 'wave1':
            prompt, subs, sources = agents.generator_prompt(role, ctx)
            st = json.loads((SAVED / 'cards-wave1.json').read_text())[role]
            return dict(prompt=prompt, subs=subs, sources=sources, free=(),
                        check=lambda v: agents.parse_cards(v, role),
                        expected=dict(cards=st['cards'], rejected=st['rejected']))
        if stage == 'cross':
            self.need_wave_probes(stage)
            critic = role.removeprefix('critic-')
            assignment = agents.critic_assignment(self.wave_cards)
            prompt, subs, sources, aliases = agents.critic_prompt(critic, assignment[critic], self.wave_probes, ctx)
            st = json.loads((SAVED / 'critiques.json').read_text())[critic]
            self.assertEqual(aliases, st['aliases'])
            return dict(prompt=prompt, subs=subs, sources=sources, free=('cards',),
                        check=lambda v: agents.parse_critiques(v, aliases, critic), expected=st['critiques'])
        if stage == 'authors':
            self.need_wave_probes(stage)
            own = [c for c in self.wave_cards if c['lens'] == role]
            with offline(self.runs):
                critiques = agents._critiques()
            prompt, subs, sources = agents.author_prompt(role, own, critiques, self.wave_probes, ctx)
            st = json.loads((SAVED / 'cards-final.json').read_text())['replies'][role]
            return dict(prompt=prompt, subs=subs, sources=sources, free=('cards',),
                        check=lambda v: agents.parse_replies(v, own), expected=st['answers'])
        raise AssertionError(f'unknown stage {stage}')

    def rebuild_fix(self, k):
        """The reference-fix call of Rb<k>, as agents.reference builds it after the first measure()."""
        st = json.loads((SAVED / f'reference-rb{k}.json').read_text())
        prefix = f'f_x_rb{k}_'
        # the proposals of the first call come from its saved reply (the fix overwrote sql and idea in the state)
        proposals = agents.parse_proposals(llm.extract_json((SAVED / 'replies' / f'reference-rb{k}.txt').read_text()), k)
        self.assertEqual([p['name'] for p in proposals], [p['name'] for p in st['proposals']])
        self.assertEqual([p['sql'] for p in proposals], [p.get('first_sql', p['sql']) for p in st['proposals']])
        probes = {}
        for p in proposals:
            saved = st['probes'][p['table']]
            if saved['sql_sha256'] == agents.sha(p['sql']):   # not fixed: the state keeps the first measurement
                probes[p['table']] = saved
                continue
            # fixed: the first measurement is the probe of the first SQL, saved in the probe cache (the stage ran
            # with probe VERSION 1, which the current probe() no longer serves, so the file is read directly)
            path = ev.probe_path(p['sql'])
            if not path.exists():
                self.skipTest(f'stage reference-fix rb{k}: missing input: the pre-fix probe of {p["table"]} '
                              f'({path}); reference-rb{k}.json keeps only the probe of the fixed SQL')
            raw = json.loads(path.read_text())
            self.assertEqual(raw['sql'], p['sql'])
            raw = _fresh_order(raw, raw.get('columns') or [])
            probes[p['table']] = dict(sql_sha256=agents.sha(p['sql']), columns=raw.get('columns') or [],
                                      view=agents.probe_view(raw),
                                      problems=agents.mask_days(agents.probe_problems(raw, prefix)))

        def problems(p):   # agents.reference.problems
            out = list(probes[p['table']]['problems'])
            earlier = set()
            for q in proposals:
                if q is p:
                    break
                if not probes[q['table']]['problems']:
                    earlier |= set(probes[q['table']]['columns'])
            clash = sorted(set(probes[p['table']]['columns']) & earlier)
            if clash:
                out.append(f'column names {clash} repeat an earlier proposal')
            return out
        failed = [p for p in proposals if problems(p)]
        self.assertEqual([p['name'] for p in failed], st['fix']['asked'])
        listing = [dict(name=p['name'], idea=p['idea'], sql=p['sql'], check=probes[p['table']]['view'],
                        problems=problems(p)) for p in failed]
        subs, src = self.ctx
        subs = dict(features=subs['features'], prefix=prefix, failed=json.dumps(listing, ensure_ascii=False, indent=1))
        names = {p['name'] for p in failed}
        by_name = {p['name']: p for p in st['proposals']}
        expected = [dict(name=n, sql=by_name[n]['sql']) for n in st['fix']['answered']]
        return dict(prompt=agents.render(agents.REFERENCE_FIX, **subs), subs=subs, sources=agents._sources(*src, listing),
                    free=('failed',), check=lambda v: agents.parse_proposals(v, k, names=names), expected=expected,
                    compare=lambda got: [dict(name=g['name'], sql=g['sql']) for g in got])

    # ------------------------------------------------------------ the 18 calls

    def test_prompts_reproduce(self):
        self.need_ctx()
        for rec in self.records:
            stage, role = rec['stage'], rec['role']
            with self.subTest(stage=stage, role=role):
                head, saved = _saved_prompt(stage, role)
                try:
                    got = self.rebuild(stage, role)
                except CacheMiss as e:
                    self.skipTest(f'stage {stage}/{role}: missing input: {e}')
                prompt = got['prompt']
                if stage in LEGACY:
                    # deviation 13: the current code adds the FORBIDDEN block, and nothing else differs
                    self.assertNotEqual(_sha(prompt), rec['prompt_sha256'])
                    self.assertNotEqual(prompt, saved)
                    prompt = _legacy(prompt)
                self.assertEqual(_sha(prompt), rec['prompt_sha256'])
                self.assertEqual(prompt, saved)
                self.replay(rec, prompt, got)

    def replay(self, rec, prompt, got):
        """llm.ask on the rebuilt prompt with `claude -p` returning the saved reply: the number test passes, the
        prompt file, the log record and the parsed value are the saved ones."""
        stage, role = rec['stage'], rec['role']
        reply = (SAVED / 'replies' / f'{stage}-{role}.txt').read_text()
        calls = []

        def call(p, model):
            calls.append((p, model))
            return reply, rec['cost_usd']
        with tempfile.TemporaryDirectory() as d, offline(d), mock.patch.object(llm, '_call', call):
            value, meta = llm.ask(prompt, role, stage, subs=got['subs'], sources=got['sources'], free=got['free'],
                                  check=got['check'])
            log = [json.loads(line) for line in (Path(d) / 'llm.jsonl').read_text().splitlines()]
            written = (Path(d) / 'prompts' / f'{stage}-{role}.txt').read_text()
            self.assertEqual((Path(d) / 'replies' / f'{stage}-{role}.txt').read_text(), reply)
        self.assertEqual(calls, [(prompt, rec['model'])])
        self.assertEqual(meta['prompt_sha256'], rec['prompt_sha256'])
        self.assertEqual(len(log), 1)
        drop = {'time', 'seconds'}
        new = {k: v for k, v in log[0].items() if k not in drop}
        old = {k: v for k, v in rec.items() if k not in drop}
        saved_file = (SAVED / 'prompts' / f'{stage}-{role}.txt').read_text()
        if stage in LEGACY:   # deviation 13, log flags: the current llm.ask adds the argv and the header
            self.assertEqual({k: v for k, v in new.items() if k not in ('command', 'free')}, old)
            self.assertEqual(written.split('\n\n', 1)[1], saved_file)
        else:
            self.assertEqual(new, old)
            self.assertEqual(written, saved_file)
        compare = got.get('compare', lambda v: v)
        self.assertEqual(agents._plain(compare(value)), got['expected'])


class GoldenCuration(unittest.TestCase):
    """agents.curator_stage on the saved final cards, probes.json, critiques and the reference probes."""

    def test_curation_reproduces_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as d:
            _copy_run(d)
            with offline(d):   # the probes come from probes.json and the probe cache as the stage read them
                final = agents._final_cards()
                self.assertIn('reference_probes', inspect.signature(ev.curate).parameters)
                try:
                    out = agents.curator_stage(final, agents.evidence_stage(final), agents._critiques())
                except CacheMiss as e:
                    self.skipTest(f'stage curate: missing input: a reference probe in {roles.PROBES}: {e}')
            got = (Path(d) / 'curation.json').read_bytes()
        self.assertEqual(json.loads(got), out)
        self.assertEqual(got, (SAVED / 'curation.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
