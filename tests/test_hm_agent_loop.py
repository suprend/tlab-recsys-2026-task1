"""Synthetic witnesses for the H&M agent loop (scripts/hm_agent_loop.py).

No real claude call and no data/ or artifacts/ access: ``claude -p`` is a scripted
subprocess.run stand-in, evaluate_proposal a fake sandbox returning
contract-shaped records, and kaggle.ARTIFACTS points into a /tmp scratch.
"""
from contextlib import redirect_stdout
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import pandas as pd

from scripts import hm_agent_loop as loop
from scripts import hm_agent_sandbox as SANDBOX
from scripts import hm_experiment as experiment
from scripts import hm_kaggle as kaggle
from scripts.hm_feature_engine import CATEGORICAL_FEATURES, PILOT_NUMERIC_FEATURES, feature_registry

CUSTOMERS = [hashlib.sha256(f'probe-customer-{i}'.encode()).hexdigest() for i in range(4)]
ARTICLES = [f'{706016001+7*i:010d}' for i in range(4)]
EXPORT_DIGEST = hashlib.sha256(b'synthetic hm-agent export').hexdigest()
STATS = {'history_before': '2020-09-09',
         'rows': {'7d': 254321, '28d': 1003210, '90d': 3171234, '365d': 15876543, 'total': 28813456},
         'purchases_per_customer_90d': {'p25': 2, 'p50': 4, 'p90': 13},
         'share_customers_two_days': 0.4375,
         'price': {'p01': 0.0050678, 'p50': 0.0254068, 'p99': 0.1186271},
         'sales_channel_id': {'1': 0.2871, '2': 0.7129},
         'attributes': {'product_type_name': {'cardinality': 131,
                                              'top10': [['272', 'Trousers', 0.0912], ['253', 'Vest top', 0.0581]]}},
         'candidates': {'recent_mean': 17.25, 'global_share': 0.8562}}
M23 = list(PILOT_NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES)


def write(path, value):
    Path(path).write_text(json.dumps(value), encoding='utf-8')


def proposal(name, level='pair', columns=None, sql=None):
    columns = columns or (f'ag_{name}',)
    keys = {'pair': 'customer_id, article_id', 'customer': 'customer_id', 'article': 'article_id'}[level]
    source = {'pair': 'cand', 'customer': 'users', 'article': 'articles'}[level]
    values = ', '.join(f'count(*) AS {column}' for column in columns)
    return dict(name=name, idea=f'one sentence about {name}', level=level,
                sql=sql or f'SELECT {keys}, {values} FROM {source} GROUP BY ALL')


DROP = object()  # an init or result key the scripted line leaves out
BUILTIN = dict(name='agents-md', path='builtin', source='agents-md@builtin')
INIT = dict(type='system', subtype='init', session_id='synthetic', tools=[], mcp_servers=[], model=loop.MODEL,
            permissionMode='default', slash_commands=[], apiKeySource='none', claude_code_version='2.1.284',
            output_style='default', agents=['general-purpose'], skills=[], plugins=[BUILTIN], uuid='synthetic-init')
COMMAND = ['claude', '-p', '--model', 'claude-opus-5-5', '--safe-mode', '--setting-sources', 'project', '--tools', '',
           '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence', '--no-chrome',
           '--output-format', 'stream-json', '--verbose']


def stream(text, cost, cwd, init=None, result=None):
    """stdout of ``--output-format stream-json --verbose``: init, one assistant message, result."""
    lines = []
    if init is not False:
        lines.append({**INIT, 'cwd': cwd, **(init or {})})
    lines.append(dict(type='assistant', message=dict(role='assistant', content=[dict(type='text', text=text)])))
    if result is not False:
        lines.append({**dict(type='result', subtype='success', is_error=False, duration_ms=4321, num_turns=1,
                             result=text, stop_reason='end_turn', total_cost_usd=cost, usage={'output_tokens': 1500},
                             modelUsage={loop.MODEL: {'costUSD': cost}}), **(result or {})})
    lines = [{key: value for key, value in line.items() if value is not DROP} for line in lines]
    return ''.join(json.dumps(line)+'\n' for line in lines)


class Reply:
    """A scripted reply whose init or result line differs from a clean call."""

    def __init__(self, text, init=None, result=None, code=0, stderr='', extra=''):
        self.text, self.init, self.result, self.code, self.stderr, self.extra = text, init, result, code, stderr, extra


class FakeClaude:
    """subprocess.run stand-in for ``claude -p``: one scripted reply per call."""

    def __init__(self, replies, cost=0.25):
        self.replies, self.cost, self.calls = list(replies), cost, []

    def __call__(self, argv, **kwargs):
        cwd = Path(kwargs['cwd'])
        self.calls.append(dict(argv=list(argv), prompt=argv[2], cwd=cwd, empty=cwd.is_dir() and not any(cwd.iterdir()),
                               timeout=kwargs.get('timeout'), stdin=kwargs.get('stdin'), env=kwargs.get('env')))
        reply = self.replies.pop(0) if self.replies else '[]'
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, subprocess.CompletedProcess):
            return reply
        if not isinstance(reply, Reply):
            reply = Reply(reply)
        text = reply.text if isinstance(reply.text, str) else json.dumps(reply.text)
        stdout = stream(text, self.cost, str(cwd), reply.init, reply.result) + reply.extra
        return subprocess.CompletedProcess(argv, reply.code, stdout=stdout, stderr=reply.stderr)


class FakeSandbox:
    """evaluate_proposal stand-in in the sandbox's coarse record form: the outcome by proposal name
    (``seconds`` exact), value columns from the SQL; seconds, rows and distinct as log2 buckets,
    shares to 2 decimals, |rho| to 1 decimal, the exact seconds on the frame only."""

    def __init__(self, outcomes=None, load=None):
        self.outcomes, self.calls, self.load = outcomes or {}, [], load

    def __call__(self, probe, export, proposal, prior_values, threads=3):
        self.calls.append(dict(id=proposal['id'], name=proposal['name'], probe=probe, export=export, threads=threads,
                               load=self.load.values[-1] if self.load and self.load.values else None,
                               prior=[c for frame in prior_values for c in frame.columns if c.startswith('ag_')]))
        outcome = dict(status='valid', seconds=1.0, error=None)
        outcome.update(self.outcomes.get(proposal['name'], {}))
        if isinstance(outcome.get('raise'), BaseException):
            raise outcome['raise']
        names = re.findall(r'\bAS (ag_[a-z0-9_]+)', proposal['sql'])
        valid = outcome['status'] == 'valid'
        columns = [dict(name=name, non_null_share=0.75, non_null_share_recent=0.94, non_null_share_global=0.69,
                        distinct=SANDBOX.log2_bucket(12), max_abs_spearman=0.4, nearest='u_tx28')
                   for name in names]
        record = dict(proposal, status=outcome['status'], error=outcome['error'],
                      seconds=SANDBOX.log2_bucket(outcome['seconds']),
                      rows=SANDBOX.log2_bucket(len(CUSTOMERS)) if valid else None, columns=columns)
        values = None
        if valid:
            values = pd.DataFrame(dict(customer_id=CUSTOMERS, article_id=ARTICLES,
                                       **{name: [float(i) for i in range(len(CUSTOMERS))] for name in names}))
            values.attrs['probe_seconds'] = outcome['seconds']
        return record, values


class FakeLoad:
    """os.getloadavg stand-in: every reading is a new, recognisable triple."""

    def __init__(self):
        self.values = []

    def __call__(self):
        value = (float(len(self.values)+1), 0.5, 0.25)
        self.values.append(value)
        return value


class ProposalError(ValueError):
    """Same name as the sandbox's proposal-level error."""


class AgentLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='tlab-hm-agent-loop-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.artifacts = self.tmp/'artifacts'
        self.artifacts.mkdir()
        for target, name, value in ((kaggle, 'ARTIFACTS', self.artifacts),
                                    (experiment, 'resource_preflight', lambda output: dict(stub=True))):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.export, self.probe = self.tmp/'export', self.tmp/'probe'
        self.export.mkdir()
        self.probe.mkdir()
        write(self.export/'export.json', dict(format='hm-agent-export-v1', status='completed', digest=EXPORT_DIGEST))
        self.write_probe(STATS)

    def write_probe(self, stats=None, **fields):
        """probe.json as the sandbox writes it, hashing the current stats.json."""
        if stats is not None:
            write(self.probe/'stats.json', stats)
        record = dict(format='hm-agent-probe-v1', status='completed', anchor='2020-09-09', users=5000,
                      export_digest=EXPORT_DIGEST, files={'stats.json': experiment.sha256_file(self.probe/'stats.json')})
        record.update(fields)
        write(self.probe/'probe.json', record)

    def next_probe(self):
        """Another probe (same fields, one more note): the one-run rule is per probe, so independent runs
        of a test each get their own."""
        record = json.loads((self.probe/'probe.json').read_text(encoding='utf-8'))
        record['note'] = record.get('note', 0) + 1
        write(self.probe/'probe.json', record)

    def run_dir(self, name, family=None):
        """Each run in its own parent unless a family is named: siblings are refused (one-run rule)."""
        if isinstance(family, Path):
            return family/name
        return self.artifacts/'hm-agent'/(family or name.removeprefix('run-'))/name

    def run_agent(self, replies, outcomes=None, name='run-t1', sandbox=None, family=None, same_probe=False, **kwargs):
        if not same_probe:
            self.next_probe()
        claude, sandbox = FakeClaude(replies), sandbox or FakeSandbox(outcomes)
        out = self.run_dir(name, family)
        with mock.patch.object(loop.subprocess, 'run', claude):
            report = loop.run_loop(self.export, self.probe, out, evaluate=sandbox, **kwargs)
        return report, claude, sandbox, out

    def run_failing(self, replies, error, outcomes=None, name='run-t1', family=None, same_probe=False, **kwargs):
        """A run expected to raise; its run.json as written on failure."""
        if not same_probe:
            self.next_probe()
        claude, sandbox = FakeClaude(replies), FakeSandbox(outcomes)
        out = self.run_dir(name, family)
        with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(BaseException, error):
            loop.run_loop(self.export, self.probe, out, evaluate=sandbox, **kwargs)
        return json.loads((out/'run.json').read_text(encoding='utf-8')), claude, sandbox, out

    @staticmethod
    def records(run):
        return [json.loads(line) for line in (run/'log.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_call_limit_default_and_refusal_above_forty(self):
        defaults = inspect.signature(loop.run_loop).parameters
        self.assertEqual((defaults['max_calls'].default, defaults['model'].default, defaults['rounds'].default,
                          defaults['proposals'].default, defaults['threads'].default), (12, 'claude-opus-5-5', 6, 5, 3))
        for bad in (41, 1000, 0, -1, True, 12.0, None):
            claude = FakeClaude([])
            with self.subTest(max_calls=bad), mock.patch.object(loop.subprocess, 'run', claude):
                with self.assertRaises(ValueError):
                    loop.run_loop(self.export, self.probe, self.run_dir('run-refused'), max_calls=bad,
                                  evaluate=FakeSandbox())
                self.assertEqual(claude.calls, [])
        self.assertFalse(self.run_dir('run-refused').exists())
        # Every round needs its retry: two calls a round, and the default limit of 12 ends round 7 unasked.
        retried = [reply for n in range(7) for reply in ('no list here', [proposal(f'd{n}')])]
        report, claude, sandbox, _ = self.run_agent(retried, name='run-default', rounds=7)
        self.assertEqual((len(claude.calls), report['calls'], report['rounds_run'], report['stop'], report['status']),
                         (12, 12, 6, 'max_calls', 'completed'))
        self.assertEqual([c['id'] for c in sandbox.calls], [f'r{n}p1' for n in range(1, 7)])
        # A failed last call leaves no call for its retry: that is an exhausted retry too, and the run fails.
        report, claude, sandbox, run = self.run_failing(retried, 'Round 3: the call failed or was unparsable and '
                                                        'max_calls leaves no call', name='run-five', max_calls=5)
        self.assertEqual((len(claude.calls), report['calls'], report['rounds_run'], report['stop'], report['status'],
                          report['failed_round']), (5, 5, 3, 'retries_exhausted', 'failed', 3))
        self.assertEqual([(c['round'], c['attempt']) for c in report['call_log']], [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)])
        self.assertEqual([c['id'] for c in sandbox.calls], ['r1p1', 'r2p1'])
        self.assertEqual(len(json.loads((run/'reply-r3.json').read_text(encoding='utf-8'))['attempts']), 1)
        # A successful last call ends the run at the limit as completed.
        report, claude, _, _ = self.run_agent(retried, name='run-four', max_calls=4)
        self.assertEqual((report['calls'], report['rounds_run'], report['stop'], report['status']),
                         (4, 2, 'max_calls', 'completed'))
        report, claude, _, _ = self.run_agent([[proposal('one')]], name='run-forty', rounds=1, max_calls=40)
        self.assertEqual((len(claude.calls), report['status'], report['max_calls']), (1, 'completed', 40))

    def test_one_retry_per_round_and_an_exhausted_retry_stops_the_run(self):
        broken = subprocess.CompletedProcess(['claude'], 1, stdout='', stderr='API Error: overloaded')
        replies = ['Here are my ideas, in prose.', [proposal('first'), proposal('second')],
                   broken, [proposal(f'm{i}') for i in range(7)],
                   subprocess.TimeoutExpired('claude', 900), [proposal('third')],
                   Reply([proposal('tooled')], init=dict(tools=['Bash'])), [proposal('fifth')],
                   'still no list', '[{"name": "x", "idea": "y", "level": "pair"}]',
                   [proposal('never')]]
        report, claude, sandbox, run = self.run_failing(replies, 'Round 5: the call and its retry both failed', rounds=6)
        self.assertEqual([(c['round'], c['attempt'], c['status']) for c in report['call_log']],
                         [(1, 1, 'failed'), (1, 2, 'ok'), (2, 1, 'failed'), (2, 2, 'ok'), (3, 1, 'failed'), (3, 2, 'ok'),
                          (4, 1, 'failed'), (4, 2, 'ok'), (5, 1, 'failed'), (5, 2, 'failed')])
        self.assertEqual(len(claude.calls), 10)
        self.assertEqual(claude.calls[0]['prompt'], claude.calls[1]['prompt'])
        # Contract 2: the exhausted retry of round 5 is a technical failure; nothing after it runs.
        self.assertEqual((report['status'], report['stop'], report['failed_round'], report['rounds_run']),
                         ('failed', 'retries_exhausted', 5, 5))
        self.assertEqual(report['error']['type'], 'RuntimeError')
        self.assertFalse((run/'prompt-r6.txt').exists())
        fifth_round = json.loads((run/'reply-r5.json').read_text(encoding='utf-8'))
        self.assertEqual((len(fifth_round['attempts']), fifth_round['kept']), (2, 0))
        with self.assertRaisesRegex(ValueError, 'completed'):
            loop.freeze(run, self.tmp/'never.json')
        # Extra proposals are dropped.
        self.assertEqual((report['call_log'][3]['proposals'], report['call_log'][3]['kept']), (7, 5))
        self.assertEqual([c['id'] for c in sandbox.calls],
                         ['r1p1', 'r1p2', 'r2p1', 'r2p2', 'r2p3', 'r2p4', 'r2p5', 'r3p1', 'r4p1'])
        self.assertEqual(sandbox.calls[-1]['name'], 'fifth')
        first = json.loads((run/'reply-r1.json').read_text(encoding='utf-8'))
        self.assertEqual([a['text'] for a in first['attempts']][0], 'Here are my ideas, in prose.')
        self.assertIn('Unparsable reply', first['attempts'][0]['error'])
        self.assertEqual(first['kept'], 2)
        # Call errors use the no-sql form: every token with a digit is masked.
        self.assertIn('claude exited with <v> API Error: overloaded', report['call_log'][2]['error'])
        self.assertIn('no answer within <v> s', report['call_log'][4]['error'])
        # A call that is not isolated is a failed call: refused, retried once, its init kept as evidence.
        self.assertIn('claude call refused: init tools is not empty', report['call_log'][6]['error'])
        fourth = json.loads((run/'reply-r4.json').read_text(encoding='utf-8'))
        self.assertEqual([a['init']['tools'] for a in fourth['attempts']], [['Bash'], []])
        # Every reply file and run.json carry the argv without the prompt and the init of each call.
        for number in range(1, 6):
            replied = json.loads((run/f'reply-r{number}.json').read_text(encoding='utf-8'))
            self.assertEqual(replied['llm_command'], COMMAND)
            self.assertTrue(all(set(a['meta']).isdisjoint({'text', 'init', 'command'}) for a in replied['attempts']))
        self.assertEqual(report['llm_command'], COMMAND)
        inits = [c['init'] for c in report['call_log']]
        self.assertEqual([init is None for init in inits], [False, False, True, False, True] + [False]*5)
        self.assertEqual({init['claude_code_version'] for init in inits if init}, {'2.1.284'})
        # Failed calls are paid too; the broken and the timed-out one report no cost.
        self.assertEqual((report['cost_usd'], report['cost_unknown_calls']), (2.0, 2))
        self.assertEqual(sorted(p.name for p in run.glob('prompt-r*.txt')), [f'prompt-r{n}.txt' for n in range(1, 6)])

    def test_parse_reply_takes_the_first_json_list_and_checks_fields(self):
        item = proposal('first')
        listed = json.dumps([item, dict(item, name='second', sql='SELECT [1, 2] AS ag_x')])
        text = f'Thoughts [see below].\n```json\n{listed}\n```\nAnd [1].'
        self.assertEqual([p['name'] for p in loop.parse_reply(text)], ['first', 'second'])
        missing = {key: value for key, value in item.items() if key != 'sql'}
        for bad in ('[]', ' [ ] ', '', 'no list at all', '{"name": "x"}', '[1, 2]', f'tools: [] then {json.dumps([item])}',
                    json.dumps([dict(item, columns=['ag_x'])]),
                    json.dumps([missing]), json.dumps([dict(item, level=None)]), json.dumps([dict(item, sql=['SELECT 1'])]),
                    None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                loop.parse_reply(bad)

    def test_ask_llm_runs_an_isolated_claude_from_a_fresh_empty_directory(self):
        claude = FakeClaude([[proposal('one')], 'no list', Reply('API Error', result=dict(is_error=True))], cost=0.4321)
        home, temp = str(self.tmp/'home'), tempfile.gettempdir()
        environ = dict(HOME=home, PATH='/usr/bin:/bin', USER='someone', LOGNAME='someone', TMPDIR=temp,
                       LANG='ru_RU.UTF-8', CLAUDECODE='1', CLAUDE_CODE_PLUGIN_DIRS='/plugins', CLAUDE_CONFIG_DIR='/c',
                       ANTHROPIC_API_KEY='dummy', ANTHROPIC_MODEL='claude-other', MCP_TIMEOUT='5', PYTHONPATH='/x')
        with mock.patch.dict(loop.os.environ, environ, clear=True), mock.patch.object(loop.subprocess, 'run', claude):
            proposals, meta = loop.ask_llm('PROMPT TEXT', 'claude-opus-5-5')
            with self.assertRaisesRegex(loop.LLMError, 'Unparsable') as unparsable:
                loop.ask_llm('PROMPT TEXT', 'claude-opus-5-5')
            with self.assertRaisesRegex(loop.LLMError, 'is_error True') as failed:
                loop.ask_llm('PROMPT TEXT', 'claude-opus-5-5', timeout=5)
        self.assertEqual(claude.calls[0]['argv'], [
            'claude', '-p', 'PROMPT TEXT', '--model', 'claude-opus-5-5', '--safe-mode', '--setting-sources', 'project',
            '--tools', '', '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence', '--no-chrome',
            '--output-format', 'stream-json', '--verbose'])
        self.assertEqual((meta['command'], loop.llm_command('claude-opus-5-5')), (COMMAND, COMMAND))
        # Only the minimal environment reaches claude: nothing named CLAUDE*, ANTHROPIC* or MCP*.
        for call in claude.calls:
            self.assertEqual(call['env'], dict(HOME=home, PATH='/usr/bin:/bin', USER='someone', LOGNAME='someone',
                                               TMPDIR=temp, LANG='en_US.UTF-8'))
            self.assertFalse([key for key in call['env'] if key.startswith(('CLAUDE', 'ANTHROPIC', 'MCP'))])
        with mock.patch.dict(loop.os.environ, dict(PATH='/bin', CLAUDE_CODE_ENTRYPOINT='cli'), clear=True):
            self.assertEqual(loop.llm_env(), dict(PATH='/bin', LANG='en_US.UTF-8'))
        self.assertEqual([c['timeout'] for c in claude.calls], [900, 900, 5])
        self.assertEqual({c['stdin'] for c in claude.calls}, {subprocess.DEVNULL})
        self.assertTrue(all(c['empty'] and c['cwd'].name.startswith('tlab-hm-agent-llm-') for c in claude.calls))
        self.assertEqual(len({c['cwd'] for c in claude.calls}), 3)
        self.assertFalse(any(c['cwd'].exists() for c in claude.calls))
        # The init line's identity and the result line's fields are kept for the run records.
        self.assertEqual(proposals, [proposal('one')])
        self.assertEqual(meta['init'], dict(
            cwd=str(claude.calls[0]['cwd']), tools=[], mcp_servers=[], model='claude-opus-5-5', slash_commands=[],
            skills=[], plugins=[BUILTIN], agents=['general-purpose'], apiKeySource='none', permissionMode='default',
            claude_code_version='2.1.284', output_style='default'))
        self.assertEqual(meta['result'], dict(subtype='success', is_error=False, total_cost_usd=0.4321,
                                              usage={'output_tokens': 1500}, modelUsage={loop.MODEL: {'costUSD': 0.4321}},
                                              duration_ms=4321, num_turns=1, stop_reason='end_turn'))
        self.assertEqual((meta['cost_usd'], meta['models'], meta['text']), (0.4321, [loop.MODEL], json.dumps([proposal('one')])))
        self.assertEqual((unparsable.exception.meta['cost_usd'], unparsable.exception.meta['text']), (0.4321, 'no list'))
        self.assertEqual(unparsable.exception.meta['init']['plugins'], [BUILTIN])
        self.assertEqual(failed.exception.meta['cost_usd'], 0.4321)

    def test_ask_llm_parses_the_result_string_never_the_raw_stream(self):
        listed = [proposal('one'), proposal('two')]
        lines = [{**INIT, 'cwd': '/tmp/tlab-hm-agent-llm-x'},
                 dict(type='result', subtype='success', is_error=False, result=json.dumps(listed), total_cost_usd=0.1,
                      usage={}, modelUsage={loop.MODEL: {}}, duration_ms=1, num_turns=1, stop_reason='end_turn')]
        stdout = ''.join(json.dumps(line, separators=(',', ':'))+'\n' for line in lines)
        self.assertIn('"tools":[]', stdout.splitlines()[0])
        with self.assertRaisesRegex(ValueError, 'empty'):
            loop.parse_reply(stdout)  # the raw stream's first list is the init event's empty tools
        claude = FakeClaude([subprocess.CompletedProcess(['claude'], 0, stdout=stdout, stderr='')])
        with mock.patch.object(loop.subprocess, 'run', claude):
            proposals, meta = loop.ask_llm('PROMPT TEXT', loop.MODEL)
        self.assertEqual((proposals, meta['text']), (listed, json.dumps(listed)))

    def test_an_empty_reply_is_unparsable_and_retried(self):
        report, _, sandbox, _ = self.run_agent(['[]', [proposal('after')], '[ ]', [proposal('second')]], rounds=2)
        self.assertEqual([(c['round'], c['attempt'], c['status']) for c in report['call_log']],
                         [(1, 1, 'failed'), (1, 2, 'ok'), (2, 1, 'failed'), (2, 2, 'ok')])
        self.assertIn('Unparsable reply: The reply holds an empty JSON list', report['call_log'][0]['error'])
        self.assertIn('empty JSON list', report['call_log'][2]['error'])
        self.assertEqual([c['id'] for c in sandbox.calls], ['r1p1', 'r2p1'])
        # Two empty replies in a round exhaust its retry.
        report, _, sandbox, _ = self.run_failing(['[]', '[]'], 'Round 1', name='run-empty', rounds=1)
        self.assertEqual((report['stop'], sandbox.calls), ('retries_exhausted', []))
        # Any ask returning an empty set is retried alike, and its cost still counts.
        answers = [([], dict(cost_usd=0.1)), ([proposal('custom')], dict(cost_usd=0.1))]
        sandbox = FakeSandbox()
        self.next_probe()
        report = loop.run_loop(self.export, self.probe, self.run_dir('run-ask'), rounds=1,
                               ask=lambda prompt, model: answers.pop(0), evaluate=sandbox)
        self.assertEqual([(c['attempt'], c['status']) for c in report['call_log']], [(1, 'failed'), (2, 'ok')])
        self.assertIn('ValueError: The reply holds an empty JSON list', report['call_log'][0]['error'])
        self.assertEqual(([c['name'] for c in sandbox.calls], report['cost_usd']), (['custom'], 0.2))

    def test_log_records_carry_the_load_average_read_before_evaluate(self):
        load = FakeLoad()
        replies = [[proposal('ok'), proposal('bad'), proposal('raised'), proposal('slow', level='article')]]
        outcomes = {'bad': dict(status='invalid', error='Binder Error: column x not found'),
                    'raised': {'raise': ProposalError('two statements')}, 'slow': dict(seconds=500.0)}
        with mock.patch.object(loop.os, 'getloadavg', load):
            _, _, sandbox, run = self.run_agent(replies, rounds=1, sandbox=FakeSandbox(outcomes, load))
        records = self.records(run)
        self.assertEqual([r['status'] for r in records], ['valid', 'invalid', 'invalid', 'budget'])
        # One reading per proposal, the last one before its evaluation; every record carries it.
        self.assertEqual(len(load.values), 4)
        self.assertEqual([r['loadavg'] for r in records], [list(c['load']) for c in sandbox.calls])
        self.assertEqual([r['loadavg'] for r in records], [[float(n), 0.5, 0.25] for n in (1, 2, 3, 4)])
        _, _, _, run = self.run_agent([[proposal('real')]], name='run-real', rounds=1)
        (loadavg,) = [record['loadavg'] for record in self.records(run)]
        self.assertTrue(len(loadavg) == 3 and all(isinstance(value, float) for value in loadavg))

    def test_ask_llm_refuses_a_call_that_is_not_isolated(self):
        valid = [proposal('one')]
        foreign = dict(name='english-lesson', path='/plugins/english-lesson', source='english-lesson@local')
        second_init = json.dumps({**INIT, 'cwd': '/elsewhere'})+'\n'
        cases = [('init plugins other than agents-md@builtin', Reply(valid, init=dict(plugins=[BUILTIN, foreign]))),
                 ('init plugins other than agents-md@builtin', Reply(valid, init=dict(plugins=DROP))),
                 ('init tools is not empty', Reply(valid, init=dict(tools=['Bash', 'Read']))),
                 ('init mcp_servers is not empty', Reply(valid, init=dict(mcp_servers=[dict(name='figma', status='ok')]))),
                 ('init skills is not empty', Reply(valid, init=dict(skills=['tutor']))),
                 ('init slash_commands is not empty', Reply(valid, init=dict(slash_commands=['review']))),
                 ('init tools is not empty', Reply(valid, init=dict(tools=DROP))),
                 ("init model is 'claude-sonnet-4-5', not 'claude-opus-5-5'", Reply(valid, init=dict(model='claude-sonnet-4-5'))),
                 ('no init line', Reply(valid, init=False)),
                 ('more than one init line', Reply(valid, extra=second_init)),
                 ('no result line', Reply(valid, result=False)),
                 ('subtype error_max_turns', Reply(valid, result=dict(subtype='error_max_turns'))),
                 ('is_error None', Reply(valid, result=dict(is_error=DROP))),
                 ('claude exited with 2', Reply(valid, code=2))]
        for message, reply in cases:
            claude = FakeClaude([reply])
            with self.subTest(message), mock.patch.object(loop.subprocess, 'run', claude):
                with self.assertRaisesRegex(loop.LLMError, re.escape(message)) as refused:
                    loop.ask_llm('PROMPT TEXT', loop.MODEL)
                # Refused calls are paid when a result line reports their cost; the init stays as evidence.
                expected = None if reply.result is False else 0.25
                self.assertEqual(refused.exception.meta['cost_usd'], expected)
                self.assertEqual(refused.exception.meta['command'], COMMAND)
                if reply.init not in (False, None) and reply.init.get('plugins') not in (None, DROP):
                    self.assertEqual(refused.exception.meta['init']['plugins'], reply.init['plugins'])
        # The same reply from a clean session passes.
        with mock.patch.object(loop.subprocess, 'run', FakeClaude([Reply(valid)])):
            self.assertEqual(loop.ask_llm('PROMPT TEXT', loop.MODEL)[0], valid)

    def test_freeze_keeps_round_index_column_order_and_digest(self):
        replies = [[proposal('pa', columns=('ag_one', 'ag_two')), proposal('bad'), proposal('art', level='article')],
                   [proposal('cus', level='customer'), proposal('pb', columns=('ag_three',))]]
        outcomes = {'bad': dict(status='invalid', error='Binder Error: column x not found')}
        report, _, _, run = self.run_agent(replies, outcomes, rounds=2)
        self.assertEqual((report['status'], report['model'], report['id']), ('completed', 'claude-opus-5-5', 't1'))
        self.assertEqual(report['code']['hm_kaggle.py'], experiment.sha256_file(kaggle.ROOT/'scripts/hm_kaggle.py'))
        self.assertEqual(report['code']['hm_agent_loop.py'], experiment.sha256_file(kaggle.ROOT/'scripts/hm_agent_loop.py'))
        target = self.tmp/'hm-agent-set.json'
        frozen = loop.freeze(run, target)
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), frozen)
        self.assertEqual(list(frozen), ['format', 'run', 'probe', 'proposals', 'attempts', 'columns', 'budget', 'digest'])
        self.assertEqual(frozen['format'], 'hm-agent-set-v1')
        self.assertEqual([p['id'] for p in frozen['proposals']], ['r1p1', 'r1p3', 'r2p1', 'r2p2'])
        self.assertEqual(frozen['columns'], ['ag_one', 'ag_two', 'ag_art', 'ag_cus', 'ag_three'])
        self.assertEqual([(a['id'], a['status']) for a in frozen['attempts']],
                         [('r1p1', 'valid'), ('r1p2', 'invalid'), ('r1p3', 'valid'), ('r2p1', 'valid'), ('r2p2', 'valid')])
        expected = hashlib.sha256(json.dumps([[p['id'], p['level'], p['sql'], p['columns']] for p in frozen['proposals']],
                                             sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(frozen['digest'], expected)
        self.assertEqual(frozen['proposals'][0], dict(id='r1p1', round=1, index=1, **replies[0][0],
                                                      columns=['ag_one', 'ag_two'], probe_seconds='2^0\u20132^1'))
        self.assertEqual(frozen['run'], dict(id='t1', model='claude-opus-5-5', rounds=2, proposals_per_round=5,
                                             calls=2, cost_usd=0.5))
        self.assertEqual(frozen['probe'], dict(anchor='2020-09-09', users=5000, export_digest=EXPORT_DIGEST))
        self.assertEqual(frozen['budget'], dict(pair_customer_seconds=0, article_seconds=0))  # 3 s and 1 s, to 10 s
        self.assertEqual(sorted(p.name for p in (run/'values').iterdir()),
                         ['r1p1.parquet', 'r1p3.parquet', 'r2p1.parquet', 'r2p2.parquet'])
        # Re-freezing is idempotent; a different file at the output is never overwritten.
        self.assertEqual(loop.freeze(run, target), frozen)
        other = self.tmp/'other.json'
        other.write_text('{}\n', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            loop.freeze(run, other)
        # The log is frozen as the run completed it: edits and reordering are refused.
        log = run/'log.jsonl'
        lines = log.read_text(encoding='utf-8').splitlines(keepends=True)
        log.write_text(''.join([lines[1], lines[0], *lines[2:]]), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'log.jsonl differs'):
            loop.freeze(run, self.tmp/'s2.json')
        status = json.loads((run/'run.json').read_text(encoding='utf-8'))
        kaggle.atomic_json(run/'run.json', dict(status, log_sha256=experiment.sha256_file(log)))
        with self.assertRaisesRegex(ValueError, 'order'):
            loop.freeze(run, self.tmp/'s3.json')
        kaggle.atomic_json(run/'run.json', dict(status, status='failed'))
        with self.assertRaisesRegex(ValueError, 'completed'):
            loop.freeze(run, self.tmp/'s4.json')
        self.assertFalse(any((self.tmp/name).exists() for name in ('s2.json', 's3.json', 's4.json')))

    def test_prompts_carry_no_ids_from_the_probe(self):
        leaky = f"Conversion Error: Could not convert string '{CUSTOMERS[0]}' to INT64 near '{ARTICLES[1]}'"
        literal = proposal('lit', sql=f"SELECT customer_id, article_id, 1 AS ag_lit FROM cand "
                                      f"WHERE article_id <> '{ARTICLES[2]}' AND customer_id <> '{CUSTOMERS[3]}'")
        replies = [[proposal('ok'), proposal('leak'), literal], [proposal('second')], [proposal('third')]]
        outcomes = {'leak': dict(status='invalid', error=leaky),
                    'lit': dict(status='invalid', error=f'Out of Range Error: {int(ARTICLES[3])} at {CUSTOMERS[2][:40]}')}
        report, claude, _, run = self.run_agent(replies, outcomes, rounds=3)
        prompts = [(run/f'prompt-r{n}.txt').read_text(encoding='utf-8') for n in (1, 2, 3)]
        self.assertEqual(prompts, [c['prompt'] for c in claude.calls])
        for prompt in prompts:
            self.assertIsNone(re.search('[0-9a-fA-F]{64}', prompt))
            self.assertIsNone(re.search('[0-9]{9}', prompt))  # masking starts at 9 digits
            for ident in CUSTOMERS + ARTICLES + [a.lstrip('0') for a in ARTICLES] + [c[:16] for c in CUSTOMERS]:
                self.assertNotIn(ident, prompt)
            for name in M23:
                self.assertIn(f'- {name}: ', prompt)
            self.assertIn('PROBE STATISTICS (history before 2020-09-09 only)\nhistory_before: 2020-09-09', prompt)
        self.assertIn('reason: Conversion Error: Could not convert string', prompts[1])
        self.assertIn('<hex>', prompts[1])
        self.assertIn('<digits>', prompts[1])
        # Errors in the Git-bound log are redacted too; the SQL stays exactly as proposed.
        records = self.records(run)
        errors = ' '.join(record['error'] or '' for record in records)
        for ident in CUSTOMERS + ARTICLES + [c[:16] for c in CUSTOMERS]:
            self.assertNotIn(ident, errors)
        self.assertEqual(records[2]['sql'], literal['sql'])
        # stats.json with an id-shaped value is refused before any output or call.
        for leak in ({'top_customer': CUSTOMERS[0]}, {'top_article': ARTICLES[0]}, {'nested': [[int(ARTICLES[0])]]}):
            with self.subTest(leak=leak), self.assertRaisesRegex(ValueError, 'id-shaped'):
                loop.render_prompt(dict(STATS, **leak), feature_registry(), [], 5, dict(loop.BUDGET))
        self.write_probe(dict(STATS, top_customer=CUSTOMERS[0]))
        with self.assertRaisesRegex(ValueError, 'id-shaped'):
            self.run_agent([[proposal('x')]], name='run-leak')
        self.assertFalse(self.run_dir('run-leak').exists())

    def test_prompt_lists_m23_with_registry_formulas_and_the_warning(self):
        prompt = loop.render_prompt(STATS, feature_registry(), [], 5, dict(loop.BUDGET))
        definitions = {definition.name: definition for definition in feature_registry()}
        self.assertEqual(len(M23), 23)
        for name in M23:
            formula, missing = definitions[name].formula, definitions[name].missing
            self.assertRegex(prompt, rf'(?m)^- {name}: {re.escape(formula)}.*; missing: {re.escape(missing)}$')
        self.assertIn(loop.WARNING, prompt)
        for phrase in ('enter the model without selection', 'noisy columns hurt', 'non-redundant',
                       'Customer-level columns work only through interactions'):
            self.assertIn(phrase, prompt)
        for phrase in ("t_dat >= DATE '{A}' - INTERVAL 28 DAY", 'Propose 5 new features', 'Answer with a JSON list only',
                       'share_customers_two_days: 0.4375', '- [272, Trousers, 0.0912]', 'MAP@12',
                       'Probe time budget left (rounded down to 10 s): pair+customer about 90 s of 90 s; '
                       'article about 180 s of 180 s.'):
            self.assertIn(phrase, prompt)
        with self.assertRaisesRegex(ValueError, 'ui_recency'):
            loop.render_prompt(STATS, [d for d in feature_registry() if d.name != 'ui_recency'], [], 5, dict(loop.BUDGET))
        for bad in (0, True, 5.0):
            with self.subTest(n=bad), self.assertRaises(ValueError):
                loop.render_prompt(STATS, feature_registry(), [], bad, dict(loop.BUDGET))

    def test_probe_time_budget_and_cost_accounting(self):
        replies = [[proposal('pa'), proposal('cu', level='customer'), proposal('pb'), proposal('pc'),
                    proposal('ar', level='article')],
                   [proposal('as', level='article'), proposal('at', level='article'), proposal('slow', level='article')]]
        outcomes = dict(pa=dict(seconds=50.0), cu=dict(seconds=30.0), pb=dict(seconds=20.0), pc=dict(seconds=10.0),
                        ar=dict(seconds=170.0), at=dict(seconds=10.0), slow=dict(status='invalid', seconds=60.0,
                                                                                error='Interrupted: timeout 60 s'))
        outcomes['as'] = dict(seconds=20.0)
        report, _, sandbox, run = self.run_agent(replies, outcomes, rounds=2)
        records = self.records(run)
        self.assertEqual([(r['name'], r['status']) for r in records],
                         [('pa', 'valid'), ('cu', 'valid'), ('pb', 'budget'), ('pc', 'valid'), ('ar', 'valid'),
                          ('as', 'budget'), ('at', 'valid'), ('slow', 'invalid')])
        self.assertIn('over the probe budget', records[2]['error'])
        # Only accepted values reach later evaluations and values/.
        self.assertEqual(sandbox.calls[3]['prior'], ['ag_pa', 'ag_cu'])
        self.assertEqual(sandbox.calls[7]['prior'], ['ag_pa', 'ag_cu', 'ag_pc', 'ag_ar', 'ag_at'])
        self.assertEqual({(c['probe'], c['export'], c['threads']) for c in sandbox.calls},
                         {(self.probe.resolve(), self.export.resolve(), 3)})
        self.assertEqual(sorted(report['values']), ['r1p1', 'r1p2', 'r1p4', 'r1p5', 'r2p2'])
        self.assertEqual(sorted(p.stem for p in (run/'values').glob('*.parquet')), sorted(report['values']))
        # Exact seconds come from values.attrs and stay in run.json (ignored artifacts).
        self.assertEqual(report['budget']['used'], dict(pair_customer_seconds=90.0, article_seconds=180.0))
        self.assertEqual(report['probe_seconds'], dict(r1p1=50.0, r1p2=30.0, r1p4=10.0, r1p5=170.0, r2p2=10.0))
        # The second prompt shows what is left after round 1, rounded down to 10 s; rejected time does not count.
        second = (run/'prompt-r2.txt').read_text(encoding='utf-8')
        self.assertIn('Probe time budget left (rounded down to 10 s): pair+customer about 0 s of 90 s; '
                      'article about 10 s of 180 s.', second)
        self.assertIn('r1p1 pa [pair]: valid (2^5\u20132^6 s, 2^2\u20132^3 rows)', second)
        self.assertIn('ag_pa: non-null 0.75, recent 0.94, global 0.69, distinct 2^3\u20132^4, max |rho| 0.4, '
                      'nearest u_tx28', second)
        self.assertEqual('over the probe budget: pair_customer_seconds has too little time left for this query',
                         records[2]['error'])
        self.assertIn('r1p3 pb [pair]: budget (2^4\u20132^5 s, 2^2\u20132^3 rows)', second)
        history = second[second.index('EARLIER ATTEMPTS'):]
        for text in (history, (run/'log.jsonl').read_text(encoding='utf-8')):
            self.assertIsNone(re.search(r'\b(50|30|170)(\.0)? s\b', text))
            self.assertIsNone(re.search(r'\bp(01|50|99)\b', text))
        frozen = loop.freeze(run, self.tmp/'set.json')
        self.assertEqual(frozen['budget'], dict(pair_customer_seconds=90, article_seconds=180))
        self.assertEqual([p['probe_seconds'] for p in frozen['proposals']],
                         ['2^5\u20132^6', '2^4\u20132^5', '2^3\u20132^4', '2^7\u20132^8', '2^3\u20132^4'])
        self.assertEqual(SANDBOX.read_agent_set(self.tmp/'set.json')['digest'], frozen['digest'])
        # Freeze refuses a run.json whose exact seconds do not match the valid proposals.
        status = json.loads((run/'run.json').read_text(encoding='utf-8'))
        kaggle.atomic_json(run/'run.json', dict(status, probe_seconds=dict(status['probe_seconds'], r1p3=1.0)))
        with self.assertRaisesRegex(ValueError, 'probe_seconds and the valid proposals'):
            loop.freeze(run, self.tmp/'s5.json')
        kaggle.atomic_json(run/'run.json', dict(status, probe_seconds=dict(status['probe_seconds'], r1p1=None)))
        with self.assertRaisesRegex(ValueError, 'r1p1: run.json holds no exact probe seconds'):
            loop.freeze(run, self.tmp/'s6.json')
        # Dollar cost: every call at the envelope's total_cost_usd.
        self.assertEqual((report['calls'], report['cost_usd'], frozen['run']['cost_usd']), (2, 0.5, 0.5))

    def test_record_checks_and_failures(self):
        replies = [[proposal('dup', columns=('ag_same',)), proposal('again', columns=('ag_same',)),
                    proposal('rejected'), proposal('fine')]]
        outcomes = {'rejected': {'raise': ProposalError('two statements')}}
        report, _, sandbox, run = self.run_agent(replies, outcomes, rounds=1)
        records = self.records(run)
        self.assertEqual([(r['id'], r['status']) for r in records],
                         [('r1p1', 'valid'), ('r1p2', 'invalid'), ('r1p3', 'invalid'), ('r1p4', 'valid')])
        self.assertIn('already accepted', records[1]['error'])
        self.assertEqual(records[2]['error'], 'ProposalError: two statements')
        self.assertEqual(report['columns'], ['ag_same', 'ag_fine'])
        # Any other failure of the sandbox stops the run and is recorded as failed.
        outcomes = {'boom': {'raise': RuntimeError('disk full')}}
        with self.assertRaisesRegex(RuntimeError, 'disk full'):
            self.run_agent([[proposal('first'), proposal('boom')]], outcomes, name='run-boom', rounds=1)
        status = json.loads((self.run_dir('run-boom')/'run.json').read_text(encoding='utf-8'))
        self.assertEqual((status['status'], status['error']['type'], status['attempts']), ('failed', 'RuntimeError', 1))
        with self.assertRaisesRegex(ValueError, 'completed'):
            loop.freeze(self.run_dir('run-boom'), self.tmp/'boom.json')
        # A probe of another anchor or another export is refused before any output.
        self.write_probe(anchor='2020-09-16')
        with self.assertRaisesRegex(ValueError, '2020-09-09'):
            self.run_agent([], name='run-anchor')
        self.write_probe(export_digest='0'*64)
        with self.assertRaisesRegex(ValueError, 'export'):
            self.run_agent([], name='run-export')
        self.assertFalse(any(self.run_dir(name).exists() for name in ('run-anchor', 'run-export')))

    def test_errors_reach_log_prompt_run_and_set_sanitized(self):
        raw = ("Conversion Error: Could not convert string 'a b c 1 2 3 x y z' to INT64 in "
               "/Users/someone/tlab/data/part-0.parquet near 7 0 6 0 1 6 0 0 1")
        fragments = ('a b c', '1 2 3', '/Users/someone', 'part-0.parquet', '7 0 6 0 1 6 0 0 1')
        broken = subprocess.CompletedProcess(['claude'], 1, stdout='', stderr=raw)
        replies = [broken, [proposal('ok'), proposal('bad'), proposal('raised')], [proposal('second')]]
        outcomes = {'bad': dict(status='invalid', error=raw), 'raised': {'raise': ProposalError(raw)}}
        report, claude, _, run = self.run_agent(replies, outcomes, rounds=2)
        clean = loop.sandbox.sanitize_error(raw)[:loop.ERROR_CHARS]
        self.assertEqual(clean, "Conversion Error: Could not convert string '…' to INT64 in <path> near <digits>")
        records = self.records(run)
        self.assertEqual([r['error'] for r in records[1:3]], [clean, 'ProposalError: '+clean])
        self.assertIn(clean, report['call_log'][0]['error'])
        frozen = loop.freeze(run, self.tmp/'set.json')
        self.assertEqual([a['error'] for a in frozen['attempts']], [None, clean, 'ProposalError: '+clean, None])
        second = (run/'prompt-r2.txt').read_text(encoding='utf-8')
        self.assertEqual(second, claude.calls[2]['prompt'])
        self.assertIn(clean, second)
        texts = [second, *(path.read_text(encoding='utf-8') for path in
                           (run/'log.jsonl', run/'run.json', run/'reply-r1.json', self.tmp/'set.json'))]
        for text in texts:
            for fragment in fragments:
                self.assertNotIn(fragment, text)
        # A failure that stops the run is kept sanitized as well, traceback included.
        outcomes = {'boom': {'raise': RuntimeError(raw)}}
        failed, _, _, _ = self.run_failing([[proposal('boom')]], 'Conversion Error', outcomes, name='run-crash', rounds=1)
        self.assertEqual(failed['error']['message'], clean)
        for fragment in fragments:
            self.assertNotIn(fragment, json.dumps(failed, ensure_ascii=False))
        # The prompt names the DuckDB functions the sandbox refuses.
        for name in ('current_setting', 'sniff_*', 'checkpoint', 'force_checkpoint', 'which_secret', 'error()',
                     'strptime()'):
            self.assertIn(name, second)

    def test_proposal_errors_keep_their_own_sql_tokens_and_call_errors_mask_them(self):
        raw = ('Binder Error: Referenced column "ag_bad2" not found in FROM clause! Candidate bindings: "ag_old7", '
               'at row 77 LINE 1: SELECT customer_id, article_id, count(*) AS ag_bad2')
        bad = proposal('bad2')
        broken = subprocess.CompletedProcess(['claude'], 1, stdout='', stderr=raw)
        replies = [broken, [proposal('ok'), bad], [proposal('second')]]
        report, claude, _, run = self.run_agent(replies, {'bad2': dict(status='invalid', error=raw)}, rounds=2)
        own = ('Binder Error: Referenced column "ag_bad2" not found in FROM clause! Candidate bindings: "…", '
               'at row <v> LINE 1: SELECT customer_id, article_id, count(*) AS ag_bad2')
        self.assertEqual(own, loop.sandbox.sanitize_error(raw, bad['sql']))
        self.assertEqual(self.records(run)[1]['error'], own)
        self.assertIn(own, (run/'prompt-r2.txt').read_text(encoding='utf-8'))
        self.assertIn(own, claude.calls[2]['prompt'])
        self.assertEqual(loop.freeze(run, self.tmp/'set.json')['attempts'][1]['error'], own)
        # The same text as a claude error belongs to no proposal: every token with a digit is masked.
        call = report['call_log'][0]['error']
        self.assertIn('Referenced column "…"', call)
        self.assertIn('count(*) AS <v>', call)
        self.assertNotIn('ag_bad2', call)
        for text in ((run/'log.jsonl').read_text(encoding='utf-8'), (run/'prompt-r2.txt').read_text(encoding='utf-8')):
            self.assertNotIn('ag_old7', text)
            self.assertNotIn('row 77', text)

    def test_probe_must_be_a_completed_v1_probe_with_its_stats_hash(self):
        cases = [(dict(format='hm-agent-probe-v0'), 'completed hm-agent-probe-v1'),
                 (dict(status='running'), 'completed hm-agent-probe-v1'),
                 (dict(files={}), 'stats.json differs'),
                 (dict(files={'stats.json': '0'*64}), 'stats.json differs')]
        for number, (fields, error) in enumerate(cases):
            with self.subTest(fields=fields):
                self.write_probe(**fields)
                claude, output = FakeClaude([[proposal('x')]]), self.run_dir(f'run-probe{number}')
                with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(ValueError, error):
                    loop.run_loop(self.export, self.probe, output, evaluate=FakeSandbox())
                self.assertEqual(claude.calls, [])
                self.assertFalse(output.exists())
        # stats.json edited after the probe hashed it.
        self.write_probe()
        write(self.probe/'stats.json', dict(STATS, history_before='2020-09-02'))
        claude, output = FakeClaude([[proposal('x')]]), self.run_dir('run-edited')
        with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(ValueError, 'stats.json differs'):
            loop.run_loop(self.export, self.probe, output, evaluate=FakeSandbox())
        self.assertEqual(claude.calls, [])
        self.assertFalse(output.exists())

    def test_freeze_refuses_a_run_without_a_valid_proposal(self):
        outcomes = {name: dict(status='invalid', error='Binder Error: column x not found') for name in ('a', 'b')}
        report, _, _, run = self.run_agent([[proposal('a'), proposal('b')]], outcomes, rounds=1)
        self.assertEqual((report['status'], report['valid']), ('completed', 0))
        with self.assertRaisesRegex(ValueError, 'nothing to freeze'):
            loop.freeze(run, self.tmp/'empty.json')
        self.assertFalse((self.tmp/'empty.json').exists())

    def test_one_run_per_probe_and_declared_retries_of_failed_runs(self):
        exhausted = ['no list', 'still none']
        hm = self.artifacts/'hm-agent'

        def refused(output, error, **kwargs):
            claude = FakeClaude([[proposal('never')]])
            with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(ValueError, error):
                loop.run_loop(self.export, self.probe, output, rounds=1, evaluate=FakeSandbox(), **kwargs)
            self.assertEqual(claude.calls, [])
            self.assertFalse(output.exists())

        first, _, _, a = self.run_failing(exhausted, 'Round 1', name='run-a', family='fam', rounds=1)
        self.assertEqual((first['status'], first['retry_of'], first['reason']), ('failed', None, None))
        # One run per probe, wherever it lies under the artifacts and whatever the parent.
        for output in (hm/'fam'/'run-b', self.artifacts/'hm-agent-2'/'run-1', self.artifacts/'x'/'deep'/'run-n'):
            refused(output, 'This probe already has a run')
        # A run directory is named run-*.
        for name in ('attempt-2', 'run-', 'RUN-2', 'run-a b'):
            refused(hm/'fam'/name, 'named run-')
        refused(hm/'fam'/'run-b', 'go together', reason='overloaded')
        refused(hm/'fam'/'run-b', 'go together', retry_of=a)
        refused(hm/'fam'/'run-b', 'non-empty', retry_of=a, reason='  ')
        refused(hm/'fam'/'run-b', 'run of this probe', retry_of=hm/'fam'/'run-missing', reason='overloaded')
        # The declared retry of a failed run may sit anywhere under the artifacts.
        second, _, _, b = self.run_failing(exhausted, 'Round 1', name='run-b', family=self.artifacts/'hm-agent-2', rounds=1,
                                           same_probe=True, retry_of=a, reason='API overloaded')
        self.assertEqual(b, self.artifacts/'hm-agent-2'/'run-b')
        self.assertEqual((second['retry_of'], second['reason']), (str(a.resolve()), 'API overloaded'))
        refused(hm/'fam'/'run-c', 'run-a was already retried by run-b', retry_of=a, reason='again')
        report, _, _, d = self.run_agent([[proposal('retried')]], name='run-d', family='fam', rounds=1,
                                         same_probe=True, retry_of=b, reason=' overloaded again ')
        self.assertEqual((report['status'], report['retry_of'], report['reason']),
                         ('completed', str(b.resolve()), 'overloaded again'))
        stored = json.loads((d/'run.json').read_text(encoding='utf-8'))
        self.assertEqual((stored['retry_of'], stored['reason']), (report['retry_of'], report['reason']))
        refused(hm/'fam'/'run-e', 'a completed run is never retried', retry_of=d, reason='better luck')
        # A failed run on a probe that has a completed one is not retried either.
        shutil.copytree(a, hm/'fam'/'run-z')
        refused(hm/'fam'/'run-e', 'run-d completed on this probe', retry_of=hm/'fam'/'run-z', reason='better luck')
        shutil.rmtree(hm/'fam'/'run-z')
        # freeze: only artifacts/task1/v2020/sealed is not scanned, and nothing under a sealed directory is frozen.
        sealed = self.artifacts/'task1'/'v2020'/'sealed'/'run-d'
        shutil.copytree(d, sealed)
        self.assertEqual(loop.freeze(d, self.tmp/'set.json')['proposals'][0]['id'], 'r1p1')
        with self.assertRaisesRegex(ValueError, 'under a sealed directory'):
            loop.freeze(sealed, self.tmp/'sealed.json')
        # Any other directory named sealed is scanned like the rest.
        shutil.copytree(d, self.artifacts/'scratch'/'sealed'/'run-s1')
        with self.assertRaisesRegex(ValueError, 'More than one completed run on this probe'):
            loop.freeze(d, self.tmp/'set2.json')
        shutil.rmtree(self.artifacts/'scratch')
        shutil.copytree(d, self.artifacts/'elsewhere'/'deep'/'run-copy')
        with self.assertRaisesRegex(ValueError, 'More than one completed run on this probe'):
            loop.freeze(d, self.tmp/'set2.json')
        shutil.copytree(d, self.artifacts/'elsewhere'/'attempt')
        with self.assertRaisesRegex(ValueError, 'named run-'):
            loop.freeze(self.artifacts/'elsewhere'/'attempt', self.tmp/'set3.json')
        self.assertFalse(any((self.tmp/name).exists() for name in ('set2.json', 'set3.json', 'sealed.json')))
        # Another probe is another family: its runs are untouched by these.
        _, _, _, other = self.run_agent([[proposal('other')]], name='run-a', family='fam-other', rounds=1)
        self.assertEqual(loop.freeze(other, self.tmp/'other.json')['proposals'][0]['id'], 'r1p1')

    def test_the_scan_sees_runs_under_other_sealed_dirs_and_refuses_unreadable_ones(self):
        def refused(output, error, **kwargs):
            claude = FakeClaude([[proposal('never')]])
            with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(ValueError, error):
                loop.run_loop(self.export, self.probe, output, rounds=1, evaluate=FakeSandbox(), **kwargs)
            self.assertEqual(claude.calls, [])
            self.assertFalse(output.exists())

        # A run moved under some other sealed/ still holds its probe; no run is made under any sealed/.
        _, _, _, first = self.run_agent([[proposal('first')]], name='run-s1', rounds=1)
        hidden = self.artifacts/'scratch'/'sealed'/'run-s1'
        hidden.parent.mkdir(parents=True)
        shutil.move(first, hidden)
        refused(self.run_dir('run-second'), 'This probe already has a run')
        refused(self.artifacts/'scratch'/'sealed'/'run-s2', 'under a sealed directory')
        refused(self.artifacts/'task1'/'v2020'/'sealed'/'run-s3', 'under a sealed directory')
        # The exact sealed tree is not read: a run there neither blocks a new run nor is it scanned.
        self.next_probe()
        exempt = self.artifacts/'task1'/'v2020'/'sealed'/'run-old'
        shutil.copytree(hidden, exempt)
        (exempt/'run.json').write_text('{broken', encoding='utf-8')
        report, _, _, run = self.run_agent([[proposal('fresh')]], name='run-fresh', same_probe=True, rounds=1)
        self.assertEqual(report['status'], 'completed')
        # An unreadable run.json anywhere else stops run and freeze with its path.
        broken = self.artifacts/'junk'/'run-bad'
        broken.mkdir(parents=True)
        (broken/'run.json').write_text('{broken', encoding='utf-8')
        self.next_probe()
        refused(self.run_dir('run-blocked'), 'Unreadable run.json under the artifacts: .*junk/run-bad/run.json')
        with self.assertRaisesRegex(ValueError, 'junk/run-bad/run.json'):
            loop.freeze(run, self.tmp/'set.json')
        self.assertFalse((self.tmp/'set.json').exists())
        # So does a directory the scan cannot list.
        shutil.rmtree(broken)
        locked = self.artifacts/'junk'/'locked'
        locked.mkdir()
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        refused(self.run_dir('run-locked'), 'Unreadable directory under the artifacts: .*junk/locked')
        locked.chmod(0o755)
        self.assertEqual(loop.freeze(run, self.tmp/'set.json')['proposals'][0]['name'], 'fresh')

    def refused_run(self, output, error, exception=ValueError, **kwargs):
        claude = FakeClaude([[proposal('never')]])
        with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(exception, error):
            loop.run_loop(self.export, self.probe, output, rounds=1, evaluate=FakeSandbox(), **kwargs)
        self.assertEqual(claude.calls, [])
        self.assertFalse(output.exists())

    def test_sealed_is_matched_in_any_case_and_by_file_identity(self):
        sealed = self.artifacts/'task1'/'v2020'/'sealed'
        sealed.mkdir(parents=True)
        self.next_probe()
        for spelling in ('SEALED', 'Sealed', 'sEaLeD'):
            self.refused_run(self.artifacts/'task1'/'v2020'/spelling/'run-s1', 'under a sealed directory')
            self.refused_run(self.artifacts/'scratch'/spelling/'run-s1', 'under a sealed directory')
        self.assertEqual(list(sealed.iterdir()), [])
        # An alias of the sealed tree resolves into it.
        (self.artifacts/'alias').symlink_to(sealed, target_is_directory=True)
        self.refused_run(self.artifacts/'alias'/'run-s2', 'sealed directory')
        self.assertEqual(list(sealed.iterdir()), [])

    @unittest.skipUnless(Path(tempfile.gettempdir().upper()).exists() and
                         os.path.samefile(tempfile.gettempdir(), tempfile.gettempdir().upper()),
                         'needs a case-insensitive file system (APFS default)')
    def test_the_sealed_tree_is_found_by_identity_not_by_spelling(self):
        # A sealed name the case-folded word check does not catch: only the file identity does.
        vault = self.artifacts/'task1'/'v2020'/'vault'
        vault.mkdir(parents=True)
        self.next_probe()
        with mock.patch.object(loop, 'SEALED', ('task1', 'v2020', 'vault')):
            self.refused_run(self.artifacts/'TASK1'/'V2020'/'VAULT'/'run-v1', 'under the sealed directory')
            self.assertEqual(list(vault.iterdir()), [])
            # The scan skips the tree under any spelling of SEALED: its broken run.json is never read.
            (vault/'run-old').mkdir()
            (vault/'run-old'/'run.json').write_text('{broken', encoding='utf-8')
            with mock.patch.object(loop, 'SEALED', ('TASK1', 'V2020', 'VAULT')):
                report, _, _, _ = self.run_agent([[proposal('fresh')]], name='run-fresh', rounds=1)
        self.assertEqual(report['status'], 'completed')

    def test_one_lock_covers_the_one_run_check_and_the_first_run_json(self):
        lock_path = self.artifacts/loop.LOCK_NAME
        self.next_probe()
        # Another start holding the lock: this one is refused before any output or call.
        held = kaggle.hold_lock(lock_path)
        try:
            self.refused_run(self.run_dir('run-race'), 'Another process holds hm-agent.lock', RuntimeError)
        finally:
            kaggle.release_lock(held)
        # The authoritative check runs under the lock; the early one only refuses sooner.
        checks, real = [], loop.run_family

        def family(*args, **kwargs):
            try:
                kaggle.release_lock(kaggle.hold_lock(lock_path))
                checks.append('free')
            except RuntimeError:
                checks.append('held')
            return real(*args, **kwargs)

        # The lock is released once run.json exists: a second start during the run sees the first one.
        seen = []

        def ask(prompt, model):
            kaggle.release_lock(kaggle.hold_lock(lock_path))
            seen.append(json.loads((self.run_dir('run-first')/'run.json').read_text(encoding='utf-8'))['status'])
            with self.assertRaisesRegex(ValueError, 'This probe already has a run'):
                loop.run_loop(self.export, self.probe, self.run_dir('run-second'), rounds=1, evaluate=FakeSandbox())
            return [proposal('first')], dict(cost_usd=0.1)

        writes, write_json = [], kaggle.atomic_json

        def atomic_json(path, value):
            if Path(path).name == 'run.json' and Path(path).parent.name == 'run-first':
                try:
                    kaggle.release_lock(kaggle.hold_lock(lock_path))
                    writes.append('free')
                except RuntimeError:
                    writes.append('held')
            return write_json(path, value)

        with mock.patch.object(loop, 'run_family', family), mock.patch.object(loop.kaggle, 'atomic_json', atomic_json):
            report = loop.run_loop(self.export, self.probe, self.run_dir('run-first'), rounds=1, ask=ask,
                                   evaluate=FakeSandbox())
        self.assertEqual((report['status'], seen), ('completed', ['running']))
        self.assertEqual(checks, ['free', 'held', 'free'])
        self.assertEqual(writes[0], 'held')
        self.assertEqual(set(writes[1:]), {'free'})
        self.assertFalse(self.run_dir('run-second').exists())

    def test_at_most_two_retries_per_probe(self):
        exhausted = ['no list', 'still none']
        _, _, _, a = self.run_failing(exhausted, 'Round 1', name='run-a', family='chain', rounds=1)
        _, _, _, b = self.run_failing(exhausted, 'Round 1', name='run-b', family='chain', rounds=1, same_probe=True,
                                      retry_of=a, reason='API overloaded')
        second, _, _, c = self.run_failing(exhausted, 'Round 1', name='run-c', family='chain', rounds=1,
                                           same_probe=True, retry_of=b, reason='API overloaded again')
        self.assertEqual(second['retry_of'], str(b.resolve()))
        claude, output = FakeClaude([[proposal('never')]]), self.run_dir('run-d', 'chain')
        with mock.patch.object(loop.subprocess, 'run', claude), \
                self.assertRaisesRegex(ValueError, r'already has 2 retries \(run-b, run-c\); at most 2'):
            loop.run_loop(self.export, self.probe, output, rounds=1, evaluate=FakeSandbox(), retry_of=c,
                          reason='third time lucky')
        self.assertEqual(claude.calls, [])
        self.assertFalse(output.exists())

    def test_an_operator_abort_or_a_stuck_run_is_never_retried(self):
        hm = self.artifacts/'hm-agent'
        # Ctrl-C while claude answers: the run is failed with error.type KeyboardInterrupt and stays unretried.
        aborted, _, sandbox, k = self.run_failing([KeyboardInterrupt()], '', name='run-k', rounds=2)
        notes = {k: json.loads((self.probe/'probe.json').read_text(encoding='utf-8'))['note']}
        self.assertEqual((aborted['status'], aborted['error']['type'], sandbox.calls), ('failed', 'KeyboardInterrupt', []))
        # Ctrl-C during evaluation, after proposals were seen.
        seen, _, sandbox, s = self.run_failing([[proposal('first'), proposal('stop')]], '', name='run-s', rounds=1,
                                               outcomes={'stop': {'raise': KeyboardInterrupt()}})
        self.assertEqual((seen['error']['type'], [c['id'] for c in sandbox.calls]), ('KeyboardInterrupt', ['r1p1', 'r1p2']))
        notes[s] = json.loads((self.probe/'probe.json').read_text(encoding='utf-8'))['note']
        for previous, note in notes.items():
            self.write_probe(note=note)  # the probe of that run again
            self.assertEqual(loop.probe_identity(self.export, self.probe)['probe_sha256'],
                             json.loads((previous/'run.json').read_text(encoding='utf-8'))['probe']['probe_sha256'])
            claude, output = FakeClaude([[proposal('never')]]), hm/'again'/f'run-{previous.name}-2'
            with mock.patch.object(loop.subprocess, 'run', claude), \
                    self.assertRaisesRegex(ValueError, 'stopped by the operator \\(KeyboardInterrupt\\)'):
                loop.run_loop(self.export, self.probe, output, rounds=1, evaluate=FakeSandbox(),
                              retry_of=previous, reason='I pressed Ctrl-C by mistake')
            self.assertEqual(claude.calls, [])
            self.assertFalse(output.exists())
        # A run killed while running stays unretried under the rule: only failed runs are retried.
        stuck, _, _, run = self.run_failing(['no list', 'none'], 'Round 1', name='run-stuck', rounds=1)
        kaggle.atomic_json(run/'run.json', dict(stuck, status='running', error=None))
        claude, output = FakeClaude([]), hm/'again'/'run-stuck-2'
        with mock.patch.object(loop.subprocess, 'run', claude), self.assertRaisesRegex(ValueError, 'is not failed'):
            loop.run_loop(self.export, self.probe, output, rounds=1, evaluate=FakeSandbox(), retry_of=run, reason='killed')
        self.assertEqual(claude.calls, [])

    def test_the_real_sandbox_through_the_loop_prompt_and_freeze(self):
        """A's evaluate_proposal on its own synthetic fixture: no fake between the loop and DuckDB."""
        from tests.test_hm_agent_sandbox import A, USERS, build_database, write_source
        from tests.test_hm_kaggle import purchases
        tenure = ("SELECT customer_id, date_diff('day', min(t_dat), DATE '{A}') AS ag_cust_tenure, "
                  "avg(CASE WHEN sales_channel_id = '2' THEN 1 ELSE 0 END) AS ag_cust_online "
                  "FROM tx SEMI JOIN users USING (customer_id) GROUP BY customer_id")
        buyers = ("SELECT article_id, avg(CASE WHEN sales_channel_id = '2' THEN 1.0 ELSE 0.0 END) AS ag_art_online "
                  "FROM tx GROUP BY article_id")
        binder = 'SELECT customer_id, missing_column AS ag_missing FROM users'
        runtime = 'SELECT customer_id, CAST(customer_id AS INTEGER) AS ag_conv FROM users'
        with mock.patch.object(kaggle, 'isolated', lambda: True):
            (self.artifacts/'eda').mkdir()
            database = self.artifacts/'eda'/'audit.duckdb'
            build_database(database, purchases())
            write_source(database)
            export, probe = self.artifacts/'agent'/'export', self.artifacts/'agent'/'probe'
            SANDBOX.export_history(database, export, threads=2)
            SANDBOX.prepare_probe(database, export, A, USERS, probe, threads=2)
            replies = [[dict(name='tenure', idea='tenure and online share', level='customer', sql=tenure),
                        dict(name='missing', idea='a column that does not exist', level='customer', sql=binder),
                        dict(name='conv', idea='a cast that fails at run time', level='customer', sql=runtime)],
                       [dict(name='online', idea='online share of the article', level='article', sql=buyers)]]
            claude, run = FakeClaude(replies), self.run_dir('run-real')
            with mock.patch.object(loop.subprocess, 'run', claude):
                report = loop.run_loop(export, probe, run, rounds=2, threads=2)
        records = self.records(run)
        self.assertEqual([(r['name'], r['status']) for r in records],
                         [('tenure', 'valid'), ('missing', 'invalid'), ('conv', 'invalid'), ('online', 'valid')],
                         [r['error'] for r in records])
        self.assertIn('BinderException', records[1]['error'])
        self.assertIn('could not be converted at run time', records[2]['error'])
        for record in records:
            self.assertTrue(record['seconds'] is None or SANDBOX._is_bucket(record['seconds']), record['seconds'])
            for column in record['columns']:
                self.assertFalse({'p01', 'p50', 'p99'} & set(column))
        # Exact seconds only in run.json; the prompt and the log carry buckets and the coarse summary.
        self.assertEqual(sorted(report['probe_seconds']), ['r1p1', 'r2p1'])
        second = (run/'prompt-r2.txt').read_text(encoding='utf-8')
        history = second[second.index('EARLIER ATTEMPTS'):]
        self.assertIn(f"r1p1 tenure [customer]: valid ({records[0]['seconds']} s, {records[0]['rows']} rows)", history)
        self.assertIn(f"distinct {records[0]['columns'][0]['distinct']}", history)
        self.assertIn('could not be converted at run time', history)
        self.assertIsNone(re.search(r'\bp(01|50|99)\b', history))
        for exact in report['probe_seconds'].values():
            self.assertNotIn(str(exact), history)
        frozen = loop.freeze(run, self.tmp/'set.json')
        self.assertEqual([p['name'] for p in frozen['proposals']], ['tenure', 'online'])
        self.assertEqual([p['probe_seconds'] for p in frozen['proposals']], [records[0]['seconds'], records[3]['seconds']])
        self.assertEqual(frozen['columns'], ['ag_cust_tenure', 'ag_cust_online', 'ag_art_online'])
        self.assertEqual(SANDBOX.read_agent_set(self.tmp/'set.json'), frozen)

    def test_cli_requires_isolation_and_prints_one_json_line(self):
        output = self.run_dir('run-cli')
        command = ['run', '--export', str(self.export), '--probe', str(self.probe), '--output', str(output), '--rounds', '1']

        def main(argv, isolated=True):
            stream = io.StringIO()
            with mock.patch.object(kaggle, 'isolated', lambda: isolated), redirect_stdout(stream):
                code = loop.main(argv)
            lines = stream.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            return code, json.loads(lines[0])

        code, line = main(command, isolated=False)
        self.assertEqual((code, line['status'], line['error_type']), (1, 'failed', 'RuntimeError'))
        code, line = main(command+['--max-calls', '41'])
        self.assertEqual((code, line['error_type']), (1, 'ValueError'))
        self.assertFalse(output.exists())
        # The CLI takes the sandbox's evaluate_proposal; a stand-in replaces it here.
        with mock.patch.object(loop.sandbox, 'evaluate_proposal', FakeSandbox()), \
                mock.patch.object(loop.subprocess, 'run', FakeClaude([[proposal('one'), proposal('two')]])):
            code, line = main(command)
        self.assertEqual((code, line['status'], line['calls'], line['valid'], line['columns']), (0, 'completed', 1, 2, 2))
        code, line = main(['freeze', '--run', str(output), '--output', str(self.tmp/'set.json')])
        frozen = json.loads((self.tmp/'set.json').read_text(encoding='utf-8'))
        self.assertEqual((code, line['status'], line['digest'], line['columns']), (0, 'completed', frozen['digest'], 2))
        code, line = main(['freeze', '--run', str(output)])
        self.assertEqual((code, line['error_type']), (1, 'UsageError'))
        # The one-run rule from the CLI: no second run beside a completed one, retried or not.
        beside = self.run_dir('run-cli2', 'cli')
        beside_command = ['run', '--export', str(self.export), '--probe', str(self.probe), '--output', str(beside)]
        for extra, error in (([], 'already has a run'), (['--reason', 'x'], 'go together'),
                             (['--retry-of', str(output), '--reason', 'x'], 'never retried')):
            with mock.patch.object(loop.subprocess, 'run', FakeClaude([])) as claude:
                code, line = main(beside_command+extra)
            self.assertEqual((code, line['error_type'], claude.calls), (1, 'ValueError', []))
            self.assertIn(error, line['message'])
        self.assertFalse(beside.exists())


if __name__ == '__main__':
    unittest.main()
