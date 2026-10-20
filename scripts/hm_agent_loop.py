"""LLM feature agent of the H&M arm MA: prompt, reply parsing, rounds and freeze.

Contract: docs/hm-agent-design.md, sections 1.5, 2 and 6 (agent B). The prompt
carries the task, the M23 formulas from feature_registry(), the sandbox rules,
label-free aggregates from the probe's stats.json (history before 2020-09-09)
and the attempt history with validity statistics only. It never carries data
rows, customer ids, labels or label-week numbers; id-shaped strings are redacted
from the history and refused anywhere else. Data rows reach this module only
through ``evaluate`` (the sandbox's evaluate_proposal).

Run as ``python -I scripts/hm_agent_loop.py run|freeze``. The run directory stays
in the ignored artifacts/ tree; freeze writes configs/datasets/hm-agent-set.json.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import hm_agent_sandbox as sandbox  # noqa: E402
from scripts import hm_experiment as experiment  # noqa: E402
from scripts import hm_kaggle as kaggle  # noqa: E402
from scripts.hm_feature_engine import CATEGORICAL_FEATURES, PILOT_NUMERIC_FEATURES, feature_registry  # noqa: E402

RUN_FORMAT = 'hm-agent-run-v1'
SET_FORMAT = sandbox.SET_FORMAT
EXPORT_FORMAT = sandbox.EXPORT_FORMAT
PROBE_FORMAT = sandbox.PROBE_FORMAT
RETRIES_EXHAUSTED = 'retries_exhausted'
MODEL = 'claude-opus-5-5'  # the pinned id (coordinator decision 7), never the alias
MAX_CALLS = 12
CALL_CEILING = 40  # more calls than this are refused
LLM_TIMEOUT = 900
# The isolated claude -p call (design review item 8): no customizations, tools, MCP, slash
# commands, sessions or Chrome; a minimal environment; stream-json to see the init line.
LLM_FLAGS = ('--safe-mode', '--setting-sources', 'project', '--tools', '', '--strict-mcp-config',
             '--disable-slash-commands', '--no-session-persistence', '--no-chrome',
             '--output-format', 'stream-json', '--verbose')
LLM_ENV = ('HOME', 'PATH', 'USER', 'LOGNAME', 'TMPDIR')
LLM_LANG = 'en_US.UTF-8'
INIT_KEYS = ('cwd', 'tools', 'mcp_servers', 'model', 'slash_commands', 'skills', 'plugins', 'agents',
             'apiKeySource', 'permissionMode', 'claude_code_version', 'output_style')
RESULT_KEYS = ('result', 'subtype', 'is_error', 'total_cost_usd', 'usage', 'modelUsage', 'duration_ms',
               'num_turns', 'stop_reason')
BUILTIN_PLUGIN = 'agents-md@builtin'
PROBE_ANCHOR = '2020-09-09'
LEVELS = ('pair', 'customer', 'article')
FIELDS = ('name', 'idea', 'level', 'sql')
STATUSES = ('valid', 'invalid', 'budget')
# Probe time of the set: valid pair+customer proposals together, article ones separately.
BUDGET = {'pair_customer_seconds': 90.0, 'article_seconds': 180.0}
M23 = tuple(PILOT_NUMERIC_FEATURES) + tuple(CATEGORICAL_FEATURES)
COLUMN = re.compile(r'ag_[a-z][a-z0-9_]{1,38}')
MAX_COLUMNS = 3
ERROR_CHARS = 400
# Id-shaped runs are masked from 9 digits or 12 hex characters on: article ids have 10 digits
# (9 without the leading zero), customer ids 64 hex; shorter runs also catch cut ids.
ID_HEX = re.compile(r'[0-9a-fA-F]{12,}')
ID_DIGITS = re.compile(r'[0-9]{9,}')
HEX64 = re.compile(r'[0-9a-f]{64}')

WARNING = ('All valid columns will enter the model without selection. Superfluous and noisy columns hurt: '
           'a few strong, non-redundant signals are needed. Customer-level columns work only through interactions.')

HEAD = 'You are a feature engineer for a ranking model. Reply with JSON only.'
TASK = """TASK
H&M Personalized Fashion Recommendations. Transactions cover 2018-09-20..2020-09-22. Every anchor A is a
Wednesday. The label of a (customer, article) pair is whether the customer buys the article in [A, A+7 days);
the customer's distinct purchased articles count once each. The metric is MAP@12 over the customers who buy
something in that week."""
CANDIDATES = """CANDIDATES (policy C0-Q120)
Per customer: the last 20 distinct articles the customer bought in [A-90 days, A), by latest purchase date
descending, then article_id; then the global top 200 by distinct buyers in [A-7 days, A) (ties by article_id),
skipping articles already listed, until exactly 120 candidates."""
TRAINING = """TRAINING
CatBoost Logloss, 500 trees, depth 8. Weekly anchors 2020-08-12..2020-09-16 with 20 000 customers each: all
positive pairs plus 20 hash-sampled negatives per customer, with weights. The final model scores anchor
2020-09-23 for every customer with a purchase in the 90 days before it."""
TABLES = """TABLES (DuckDB; a query sees only these four)
tx(t_dat DATE, customer_id VARCHAR, article_id VARCHAR, price DOUBLE, sales_channel_id VARCHAR)
  every transaction row with t_dat < A, duplicates kept
articles: all VARCHAR, one row per article bought before A, no free text: article_id, product_code,
  product_type_no, product_type_name, product_group_name, graphical_appearance_no, graphical_appearance_name,
  colour_group_code, colour_group_name, perceived_colour_value_id, perceived_colour_value_name,
  perceived_colour_master_id, perceived_colour_master_name, department_no, department_name, index_code,
  index_name, index_group_no, index_group_name, section_no, section_name, garment_group_no, garment_group_name
cand(customer_id VARCHAR, article_id VARCHAR): the candidate pairs of the current batch, keys only
users(customer_id VARCHAR): the distinct customers of cand
There is no customer table."""
RULES = """QUERY RULES
- Exactly one SELECT or WITH statement; ';' only at the very end; no comments (-- or /* */).
- Write the anchor only as DATE '{A}', literally with the braces, e.g. t_dat >= DATE '{A}' - INTERVAL 28 DAY.
  No other {...} placeholders and no date literals 'YYYY-MM-DD'.
- Forbidden whole words, in any case: transactions, customers, frame, label, labels, target, targets, hm_*,
  _hm_*; read_*, parquet_*, csv, json*, glob, getenv, query, query_table, duckdb_*, information_schema,
  pg_catalog, sqlite_master, pragma*; attach, detach, copy, export, import, install, load, set, reset, use,
  call, create, drop, insert, update, delete, alter; random, setseed, uuid, gen_random_uuid, now, today,
  current_date, current_time, current_timestamp, get_current_time, sample, tablesample, current_setting,
  sniff_*, checkpoint, force_checkpoint, which_secret; the functions error() and strptime().
- An article-level query must not mention cand or users: its values do not depend on the batch and are cached.

OUTPUT OF A QUERY
- level "pair": key columns customer_id, article_id (pairs of cand); level "customer": customer_id (of users);
  level "article": article_id (of articles). Keys are VARCHAR, never NULL and unique. A key outside its set is
  an error, not a silent filter, so keep queries narrow.
- 1 to 3 value columns named by ^ag_[a-z][a-z0-9_]{1,38}$, unique among the accepted columns and different
  from every feature name above; integer, DECIMAL, FLOAT, DOUBLE or BOOLEAN. VARCHAR, DATE and TIMESTAMP values
  are errors: turn dates into days before {A}. No other columns.
- Values are cast to DOUBLE and left-joined to the batch keys of the level. No row, NULL, a non-finite value or
  a float32 overflow mean "no data": NaN in the model, which CatBoost treats as the minimum. Put your own
  defaults with COALESCE.
- Batch invariance: a value depends only on tx, articles and its own key; cand and users only filter. A window
  PARTITION BY customer_id over cand is allowed (all 120 candidates of a customer are always in one batch);
  aggregates over cand across customers are not. Windows need a full tie-break (..., article_id). Violations
  are caught mechanically.
- Limits on the probe: timeout 20 s for pair and customer queries, 60 s for article queries; at most 20 million
  output rows. Budget of the whole set on the probe: valid pair and customer proposals together at most 90 s,
  valid article proposals at most 180 s; a proposal that does not fit into what is left gets status budget.

VALIDITY
A proposal is accepted or rejected as a whole. It is invalid on an SQL error, a broken rule or a timeout; when
a column has fewer than 2 distinct non-NULL values or fewer than 100 non-NULL rows; when a column has
|Spearman rho| >= 0.999 with an M23 column, an accepted column or another column of the same proposal; or when
batch invariance fails."""
REQUEST = """REQUEST
Propose {n} new features that are likely to improve the ranking beyond M23 and the accepted columns and that
differ from earlier attempts. Answer with a JSON list only:
[{"name": "short_snake_case", "idea": "one sentence", "level": "pair|customer|article", "sql": "SELECT ..."}]"""
# The coarse column summary of the sandbox (section 2), the only fields the prompt shows:
# (key, label, form) with shares to 2 decimals, distinct as a log2 bucket, |rho| to 1 decimal.
COLUMN_STATS = (('non_null_share', 'non-null', 'share'), ('non_null_share_recent', 'recent', 'share'),
                ('non_null_share_global', 'global', 'share'), ('distinct', 'distinct', 'bucket'),
                ('max_abs_spearman', 'max |rho|', 'rho'), ('nearest', 'nearest', 'name'))


class LLMError(RuntimeError):
    """A failed or unparsable LLM call; ``meta`` keeps its cost and raw reply for the run files."""

    def __init__(self, message, meta=None):
        super().__init__(message)
        self.meta = meta if isinstance(meta, dict) else {}


def redact(value):
    """Id-shaped runs (customer ids, article ids) never reach a prompt or a Git-bound log."""
    return ID_DIGITS.sub('<digits>', ID_HEX.sub('<hex>', str(value)))


def clean_error(text, sql='', limit=ERROR_CHARS):
    """Error text fit for the log, the prompt, run.json and the set: sandbox.sanitize_error, clipped.

    ``sql`` is the proposal's SQL when the error belongs to a proposal (its own tokens stay
    readable); call, claude and run errors use the no-sql form, which masks every token with a digit.
    """
    return None if text is None else sandbox.sanitize_error(text, sql or '')[:limit]


def _plain(value):
    """JSON-safe copy: numpy scalars become Python values, non-finite floats null."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if type(value).__module__ == 'numpy' and hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _cost(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _number(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and abs(value) < 1e8:
            return str(int(value))
        return f'{value:.4g}'
    return ' '.join(str(value).split())


def _bucket(value):
    """A log2 bucket of the sandbox, verbatim; anything else (an exact count) is never shown."""
    return value if isinstance(value, str) and sandbox._is_bucket(value) else 'n/a'


def _coarse(value, digits):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 'n/a'
    return f'{round(float(value), digits):.{digits}f}'


def _tens(seconds):
    """Probe seconds as shown or frozen: down to a multiple of 10 s, never the exact sum."""
    return int(max(float(seconds), 0.0) // 10 * 10)


def _text(value, lines=False):
    if value is None:
        return ''
    text = redact(value)
    if lines:
        return '\n'.join(line.rstrip() for line in text.strip().splitlines())
    return ' '.join(text.split())


def _field(definition, key):
    return definition[key] if isinstance(definition, dict) else getattr(definition, key)


def _scalar(value):
    return value is None or isinstance(value, (str, int, float, bool))


def _inline(value):
    if isinstance(value, list):
        return '[' + ', '.join(_inline(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{' + ', '.join(f'{key}: {_inline(item)}' for key, item in value.items()) + '}'
    return _number(value)


def _simple(value):
    if isinstance(value, list):
        return all(_scalar(item) for item in value)
    if isinstance(value, dict):
        return all(_scalar(item) for item in value.values())
    return _scalar(value)


def _tree(value, depth=0):
    """Indented plain-text rendering of stats.json in its own key order."""
    pad, lines = '  '*depth, []
    if isinstance(value, dict):
        for key, item in value.items():
            if _simple(item):
                lines.append(f'{pad}{key}: {_inline(item)}')
            else:
                lines.append(f'{pad}{key}:')
                lines.extend(_tree(item, depth+1))
    elif isinstance(value, list):
        for item in value:
            if _simple(item) or (isinstance(item, list) and all(_simple(part) for part in item)):
                lines.append(f'{pad}- {_inline(item)}')
            else:
                lines.append(f'{pad}-')
                lines.extend(_tree(item, depth+1))
    else:
        lines.append(pad + _inline(value))
    return lines


def _column_names(record):
    return [column['name'] for column in record.get('columns') or []]


def budget_key(level):
    return 'article_seconds' if level == 'article' else 'pair_customer_seconds'


def column_problem(level, names, taken):
    """Contract 1.4 for the columns of a valid proposal; None when they may join the set."""
    if level not in LEVELS:
        return 'level must be pair, customer or article'
    if not 1 <= len(names) <= MAX_COLUMNS:
        return 'a proposal has 1 to 3 value columns'
    if len(set(names)) != len(names):
        return 'value column names repeat'
    registered = {definition.name for definition in feature_registry()} | experiment.RESERVED
    for name in names:
        if not isinstance(name, str) or not COLUMN.fullmatch(name):
            return f'column {name} does not match ^ag_[a-z][a-z0-9_]{{1,38}}$'
        if name in registered:
            return f'column {name} is a registered feature or reserved name'
        if name in taken:
            return f'column {name} is already accepted'
    return None


def _m23_section(registry, history):
    definitions = {_field(definition, 'name'): definition for definition in registry}
    missing = [name for name in M23 if name not in definitions]
    if missing:
        raise ValueError(f'feature_registry() lacks M23 names: {", ".join(missing)}')
    lines = ['FEATURES ALREADY IN THE MODEL: M23 (name: formula; missing). A window of w days is [A - w days, A).']
    for title, names in (('numeric', PILOT_NUMERIC_FEATURES), ('categorical', CATEGORICAL_FEATURES)):
        lines.append(f'{title} ({len(names)}):')
        for name in names:
            definition = definitions[name]
            formula = _field(definition, 'formula')
            if _field(definition, 'window_days') and _field(definition, 'dimension'):
                formula += f" (attribute {_field(definition, 'dimension')}, window {_field(definition, 'window_days')} days)"
            lines.append(f"- {name}: {formula}; missing: {_field(definition, 'missing')}")
    accepted = [name for record in history if record.get('status') == 'valid' for name in _column_names(record)]
    lines.append('Agent columns accepted earlier in this run, also in the model: ' +
                 (', '.join(_text(name) for name in accepted) if accepted else '(none yet)'))
    return '\n'.join(lines)


def _attempt_lines(record):
    status = record.get('status')
    facts = [f'{_bucket(record[key])} {unit}' for key, unit in (('seconds', 's'), ('rows', 'rows'))
             if record.get(key) is not None]
    lines = [f"{_text(record.get('id'))} {_text(record.get('name'))} [{_text(record.get('level'))}]: {status}" +
             (f" ({', '.join(facts)})" if facts else '')]
    lines.append(f"  idea: {_text(record.get('idea'))}")
    if status != 'valid' and record.get('error'):
        lines.append(f"  reason: {_text(clean_error(record['error'], record.get('sql')))}")
    for column in record.get('columns') or []:
        if isinstance(column, dict):
            forms = dict(share=lambda v: _coarse(v, 2), bucket=_bucket, rho=lambda v: _coarse(v, 1), name=_text)
            parts = [f'{label} {forms[form](column[key])}' for key, label, form in COLUMN_STATS if key in column]
            lines.append(f"  {_text(column.get('name'))}: {', '.join(parts)}")
    lines.append('  sql: ' + _text(record.get('sql'), lines=True).replace('\n', '\n    '))
    return lines


def _history_section(history, left):
    lines = ['EARLIER ATTEMPTS IN THIS RUN (validity and coverage on the probe; effects on labels are not shown)']
    if not history:
        lines.append('(none yet)')
    for record in history:
        lines.extend(_attempt_lines(record))
    lines.append(f"Probe time budget left (rounded down to 10 s): pair+customer about "
                 f"{_tens(left['pair_customer_seconds'])} s of {_tens(BUDGET['pair_customer_seconds'])} s; article "
                 f"about {_tens(left['article_seconds'])} s of {_tens(BUDGET['article_seconds'])} s.")
    # Everything here is variable: an outsized count is redacted like an id, never refused.
    return redact('\n'.join(lines))


def render_prompt(stats, registry, history, n, budget):
    """English prompt of one round (design 1.5); ``budget`` is the probe time left per class.

    Variable text from the history is redacted; an id-shaped string anywhere else
    (stats.json included) refuses the prompt, before any call is made.
    """
    if type(n) is not int or n < 1:
        raise ValueError('The number of proposals must be a positive integer')
    if not isinstance(stats, dict) or not stats:
        raise ValueError('stats.json must be a non-empty object')
    if not isinstance(budget, dict) or set(budget) != set(BUDGET) or any(
            isinstance(budget[key], bool) or not isinstance(budget[key], (int, float)) for key in BUDGET):
        raise ValueError('The budget left needs pair_customer_seconds and article_seconds')
    sections = [HEAD, TASK, CANDIDATES, TRAINING, _m23_section(registry, history), TABLES, RULES,
                'PROBE STATISTICS (history before 2020-09-09 only)\n' + '\n'.join(_tree(stats)),
                'WARNING\n' + WARNING, _history_section(history, budget), REQUEST.replace('{n}', str(n))]
    prompt = '\n\n'.join(sections) + '\n'
    if ID_HEX.search(prompt) or ID_DIGITS.search(prompt):
        raise ValueError('The prompt would carry an id-shaped string; stats.json must hold aggregates only')
    return prompt


def _proposals(value):
    if not isinstance(value, list):
        raise ValueError('The reply is not a JSON list')
    if not value:
        raise ValueError('The reply holds an empty JSON list')  # never an empty round in silence
    proposals = []
    for position, item in enumerate(value, 1):
        if not isinstance(item, dict) or set(item) != set(FIELDS):
            raise ValueError(f'Proposal {position} must be an object with exactly name, idea, level, sql')
        if not all(isinstance(item[key], str) for key in FIELDS):
            raise ValueError(f'Proposal {position}: name, idea, level and sql must be strings')
        proposals.append({key: item[key] for key in FIELDS})
    return proposals


def parse_reply(text):
    """The first JSON list in the reply text, checked for fields and types; ValueError otherwise.

    ``text`` is the final result string of the call, never the raw stream-json stdout,
    whose init event (``"tools":[]``) would be the first list. An empty list is unparsable.
    """
    if not isinstance(text, str):
        raise ValueError('The reply is not text')
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\[', text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        return _proposals(value)
    raise ValueError('The reply has no JSON list')


def _tail(text, limit=300):
    return ' '.join(str(text or '').split())[-limit:]


def llm_command(model, prompt=None):
    """argv of the isolated ``claude -p`` call; without ``prompt`` it is the form kept in the records."""
    return ['claude', '-p', *([] if prompt is None else [prompt]), '--model', model, *LLM_FLAGS]


def llm_env():
    """HOME, PATH, USER, LOGNAME and TMPDIR when set, plus LANG; no CLAUDE_*, MCP_* or ANTHROPIC_* variable."""
    env = {key: os.environ[key] for key in LLM_ENV if key in os.environ}
    env['LANG'] = LLM_LANG
    return env


def _stream_lines(stdout):
    """The system/init and result lines of ``--output-format stream-json``; other lines are skipped."""
    inits, results = [], []
    for line in (stdout or '').splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('type') == 'system' and value.get('subtype') == 'init':
            inits.append(value)
        elif isinstance(value, dict) and value.get('type') == 'result':
            results.append(value)
    return inits, results


def isolation_problem(inits, model):
    """None when exactly one init line shows a bare session of ``model``; the reason otherwise."""
    if len(inits) != 1:
        return 'no init line' if not inits else 'more than one init line'
    init = inits[0]
    for key in ('tools', 'mcp_servers', 'skills', 'slash_commands'):
        if init.get(key) != []:
            return f'init {key} is not empty: {_tail(json.dumps(init.get(key)), 200)}'
    if init.get('model') != model:
        return f"init model is {init.get('model')!r}, not {model!r}"
    plugins = init.get('plugins')
    if not isinstance(plugins, list) or any(not isinstance(plugin, dict) or plugin.get('source') != BUILTIN_PLUGIN
                                            for plugin in plugins):
        return f'init plugins other than {BUILTIN_PLUGIN}: {_tail(json.dumps(plugins), 200)}'
    return None


def ask_llm(prompt, model, timeout=LLM_TIMEOUT):
    """One isolated ``claude -p`` call (design review item 8) from a fresh empty directory.

    The environment is llm_env(); the argv is llm_command(). Returns (proposals, meta):
    meta keeps the command without the prompt, the init line's identity fields
    (``init``), the result line's fields (``result``; its text in ``text``), cost_usd
    and the models it reports. A failed, non-isolated or unparsable call raises
    LLMError with the same meta, so its cost is still counted.
    """
    workdir = tempfile.mkdtemp(prefix='tlab-hm-agent-llm-')
    meta = dict(model=model, command=llm_command(model), seconds=None, returncode=None, init=None, result=None,
                cost_usd=None, models=None, text=None)
    started = time.monotonic()
    try:
        try:
            completed = subprocess.run(llm_command(model, prompt), cwd=workdir, env=llm_env(),
                                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise LLMError(f'claude gave no answer within {timeout} s', meta) from None
        except OSError as exc:
            raise LLMError(f'claude could not start: {exc}', meta) from None
        finally:
            meta['seconds'] = round(time.monotonic()-started, 1)
        meta['returncode'] = completed.returncode
        inits, results = _stream_lines(completed.stdout)
        if inits:
            meta['init'] = _plain({key: inits[0].get(key) for key in INIT_KEYS})
        if results:
            line = results[-1]
            meta['result'] = _plain({key: line.get(key) for key in RESULT_KEYS if key != 'result'})
            meta['cost_usd'] = _cost(line.get('total_cost_usd'))
            usage = line.get('modelUsage')
            meta['models'] = sorted(usage) if isinstance(usage, dict) else None
            meta['text'] = line.get('result') if isinstance(line.get('result'), str) else None
        if completed.returncode:
            raise LLMError(f'claude exited with {completed.returncode}: '
                           f'{_tail(meta["text"] or completed.stderr or completed.stdout)}', meta)
        problem = isolation_problem(inits, model)
        if problem:
            raise LLMError(f'claude call refused: {problem}', meta)
        if len(results) != 1:
            raise LLMError('claude call failed: ' + ('no result line' if not results else 'more than one result line'),
                           meta)
        if results[0].get('subtype') != 'success' or results[0].get('is_error') is not False or meta['text'] is None:
            raise LLMError(f"claude call failed: subtype {results[0].get('subtype')}, is_error "
                           f"{results[0].get('is_error')}, {_tail(meta['text'] or completed.stderr)}", meta)
        try:
            return parse_reply(meta['text']), meta  # the result string only, never the raw stream
        except ValueError as exc:
            raise LLMError(f'Unparsable reply: {exc}', meta) from None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def probe_identity(export, probe):
    """Export digest and the probe at 2020-09-09 that the prompt's statistics come from."""
    manifest = kaggle.read_json(Path(export)/'export.json')
    manifest = manifest if isinstance(manifest, dict) else {}
    digest = manifest.get('digest')
    if manifest.get('format') != EXPORT_FORMAT or not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise ValueError(f'export.json of {EXPORT_FORMAT} with a SHA-256 digest is required')
    record = kaggle.read_json(Path(probe)/'probe.json')
    if not isinstance(record, dict) or record.get('format') != PROBE_FORMAT or record.get('status') != 'completed':
        raise ValueError(f'A completed {PROBE_FORMAT} probe.json is required')
    if record.get('export_digest') != digest:
        raise ValueError('The probe was not built from this export')
    if record.get('anchor') != PROBE_ANCHOR:
        raise ValueError(f'The probe anchor must be {PROBE_ANCHOR}; the prompt shows history before it only')
    users = record.get('users')
    if type(users) is not int or users < 1:
        raise ValueError('probe.json needs a positive integer users')
    stats_sha256 = experiment.sha256_file(Path(probe)/'stats.json')
    files = record.get('files')
    if not isinstance(files, dict) or files.get('stats.json') != stats_sha256:
        raise ValueError('stats.json differs from its SHA-256 in probe.json')
    return dict(anchor=PROBE_ANCHOR, users=users, export_digest=digest, path=str(Path(probe).resolve()),
                probe_sha256=experiment.sha256_file(Path(probe)/'probe.json'), stats_sha256=stats_sha256)


RUN_NAME = re.compile(r'run-[A-Za-z0-9][A-Za-z0-9._-]*')
OPERATOR_ABORT = 'KeyboardInterrupt'
MAX_RETRIES = 2  # per probe, over the whole retry chain
SEALED = ('task1', 'v2020', 'sealed')  # the one tree under the artifacts the scan does not enter
LOCK_NAME = 'hm-agent.lock'  # held from the one-run check through the first run.json write


def _sealed_dir():
    return kaggle.ARTIFACTS.joinpath(*SEALED)


def _same(path, other):
    try:
        return os.path.samefile(path, other)
    except OSError:
        return False


def _run_name(path):
    """A run directory is named run-<id> and lies outside every sealed directory.

    Names compare case-insensitively (APFS is), and the sealed tree is matched by file
    identity, so no spelling or alias of it is accepted as an ancestor.
    """
    path = Path(path)
    if not RUN_NAME.fullmatch(path.name):
        raise ValueError(f'A run directory is named run-<id> ([A-Za-z0-9._-]); got {path.name!r}')
    resolved = path.resolve()
    if any(part.casefold() == 'sealed' for part in (*path.parts, *resolved.parts)):
        raise ValueError(f'A run is never made or frozen under a sealed directory: {path}')
    sealed = _sealed_dir()
    if any(_same(ancestor, sealed) for ancestor in (path, *path.parents, resolved, *resolved.parents)):
        raise ValueError(f'A run is never made or frozen under the sealed directory: {path}')


def _walk_error(error):
    raise ValueError(f'Unreadable directory under the artifacts: {error.filename}: {error.strerror}') from error


def probe_runs(probe_sha256, root=None):
    """Every hm-agent run.json under the artifacts made on this probe: {run dir: record}.

    One run per probe holds across folders and names, so the scan is recursive and keyed by
    probe_sha256, not by the parent directory or the run-* name. Only the exact tree
    ARTIFACTS/task1/v2020/sealed is skipped. An unreadable directory or run.json stops the
    scan with its path: a run it might hold is never assumed absent.
    """
    root = Path(kaggle.ARTIFACTS if root is None else root)
    sealed = root.joinpath(*SEALED)
    runs = {}
    for directory, children, files in os.walk(root, onerror=_walk_error):
        here = Path(directory)
        children[:] = sorted(child for child in children if not _same(here/child, sealed))
        if 'run.json' not in files:
            continue
        try:
            record = kaggle.read_json(here/'run.json')
        except (OSError, ValueError) as exc:
            raise ValueError(f'Unreadable run.json under the artifacts: {here/"run.json"}: {exc}') from exc
        if (isinstance(record, dict) and record.get('format') == RUN_FORMAT and isinstance(record.get('probe'), dict)
                and record['probe'].get('probe_sha256') == probe_sha256):
            runs[here.resolve()] = record
    return runs


def run_family(output, probe_sha256, retry_of=None, reason=None):
    """One run per probe (one-run rule): a new run only where no run of this probe exists anywhere
    under the artifacts, or as the declared retry of a failed one. Returns the retried path or None."""
    output = Path(output).resolve()
    _run_name(output)
    if (retry_of is None) != (reason is None):
        raise ValueError('--retry-of and --reason go together')
    runs = {path: record for path, record in probe_runs(probe_sha256).items() if path != output}
    if retry_of is None:
        if runs:
            raise ValueError(f'This probe already has a run ({min(runs)}); a new run is only a declared retry '
                             'of a failed one (--retry-of, --reason)')
        return None
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('A retry needs a non-empty --reason')
    previous = Path(retry_of).resolve()
    if previous not in runs:
        raise ValueError('--retry-of must name a run of this probe under the artifacts')
    status = runs[previous].get('status')
    if status == 'completed':
        raise ValueError(f'{previous.name} completed; a completed run is never retried')
    if status != 'failed':
        raise ValueError(f'{previous.name} is not failed (status {status}); only a failed run is retried')
    error = runs[previous].get('error')
    kind = error.get('type') if isinstance(error, dict) else None
    if not isinstance(kind, str):
        raise ValueError(f'{previous.name} records no error type; only a technical failure is retried')
    if kind == OPERATOR_ABORT:
        raise ValueError(f'{previous.name} was stopped by the operator ({kind}); an abort is not retried')
    for path, record in sorted(runs.items()):
        if record.get('status') == 'completed':
            raise ValueError(f'{path.name} completed on this probe; no further run is made')
        if record.get('retry_of') == str(previous):
            raise ValueError(f'{previous.name} was already retried by {path.name}')
    retries = sorted(path.name for path, record in runs.items() if record.get('retry_of') is not None)
    if len(retries) >= MAX_RETRIES:
        raise ValueError(f'This probe already has {len(retries)} retries ({", ".join(retries)}); '
                         f'at most {MAX_RETRIES} are made')
    return str(previous)


def settle(record, proposal, values, taken):
    """The loop's JSON-safe copy of one evaluate_proposal record (design 2).

    Identity fields come from the proposal as asked. A valid record must carry its
    probe seconds as a log2 bucket and values with its columns, the exact seconds in
    values.attrs['probe_seconds'] (they feed the budget only); columns breaking
    contract 1.4 (name, count, already accepted) make it invalid here as well.
    """
    if not isinstance(record, dict) or record.get('status') not in STATUSES:
        raise RuntimeError('evaluate returned no record with status valid, invalid or budget')
    record = _plain(record)
    record.update({key: proposal[key] for key in ('id', 'round', 'index', *FIELDS)})
    columns = record.get('columns') or []
    if not isinstance(columns, list) or not all(isinstance(c, dict) and isinstance(c.get('name'), str) for c in columns):
        raise RuntimeError('evaluate returned columns without names')
    record['columns'] = columns
    record['error'] = clean_error(record.get('error'), proposal['sql'])
    if record['status'] != 'valid':
        return record
    if not isinstance(record.get('seconds'), str) or not sandbox._is_bucket(record['seconds']):
        raise RuntimeError('A valid record needs its probe seconds as a log2 bucket')
    names = _column_names(record)
    if values is None or not set(names) <= set(getattr(values, 'columns', ())):
        raise RuntimeError('A valid record needs probe values with its columns')
    if probe_seconds(values) is None:
        raise RuntimeError("A valid record needs finite non-negative values.attrs['probe_seconds']")
    problem = column_problem(record['level'], names, taken)
    if problem:
        record.update(status='invalid', error=clean_error(problem, proposal['sql']))
    return record


def probe_seconds(values):
    """Exact probe seconds of a valid result, from the frame (never from the record), or None."""
    seconds = getattr(values, 'attrs', {}).get('probe_seconds')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        return None
    return float(seconds)


def write_values(values, path, threads):
    """Probe values of an accepted proposal, private to the run directory."""
    import duckdb
    partial = path.with_name(f'{path.name}.{os.getpid()}.part')
    con = duckdb.connect(config=dict(threads=threads))
    try:
        con.register('agent_values', values)
        con.sql('SELECT * FROM agent_values').write_parquet(str(partial))
    finally:
        con.close()
    os.replace(partial, path)
    return dict(rows=int(len(values)), sha256=experiment.sha256_file(path))


def _append(path, record):
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n')


def run_loop(export, probe, output, rounds=6, proposals=5, model=MODEL, max_calls=MAX_CALLS, threads=3,
             ask=ask_llm, evaluate=None, retry_of=None, reason=None):
    """Rounds of LLM proposals checked on the probe (design 2); returns the run.json record.

    ``evaluate`` defaults to hm_agent_sandbox.evaluate_proposal. Every call counts
    toward ``max_calls`` (at most 40); a round retries once, only after a failed or
    unparsable call, and a round whose retry fails too stops the run as failed
    (stop ``retries_exhausted``). Extra proposals are dropped, missing ones are not
    asked for again. Valid proposals beyond the probe time budget get status
    ``budget``. A second run on the same probe, anywhere under the artifacts, is only the
    declared retry of a failed one (see run_family).
    """
    for name, value in (('rounds', rounds), ('proposals', proposals), ('max_calls', max_calls), ('threads', threads)):
        if type(value) is not int or value < 1:
            raise ValueError(f'{name} must be a positive integer')
    if max_calls > CALL_CEILING:
        raise ValueError(f'max_calls above {CALL_CEILING} is refused')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('A model id is required')
    if evaluate is None:
        evaluate = sandbox.evaluate_proposal
    _run_name(output)
    export, probe = Path(export).resolve(), Path(probe).resolve()
    identity = probe_identity(export, probe)
    run_family(output, identity['probe_sha256'], retry_of, reason)  # early refusal, before the slower checks
    stats = kaggle.read_json(probe/'stats.json')
    registry = feature_registry()
    recipe = kaggle.locked_recipe('M', kaggle.SEED, threads)
    if tuple(recipe['numeric']) + tuple(recipe['categorical']) != M23:
        raise ValueError('The locked M vector differs from M23 of the feature engine')
    render_prompt(stats, registry, [], proposals, dict(BUDGET))  # refuses bad stats before any output or call
    code = sandbox.agent_code_identity()
    used = dict.fromkeys(BUDGET, 0.0)
    # Two runs started together: the check and the first run.json write happen under one lock,
    # so the second run's check sees the first run.
    lock = kaggle.hold_lock(kaggle.ARTIFACTS/LOCK_NAME)
    try:
        retried = run_family(output, identity['probe_sha256'], retry_of, reason)
        out = kaggle.new_output(output)
        (out/'values').mkdir()
        log = out/'log.jsonl'
        log.touch()
        report = dict(format=RUN_FORMAT, status='running', id=out.name.removeprefix('run-'), model=model,
                      retry_of=retried, reason=None if retried is None else reason.strip(),
                      llm_command=None, rounds=rounds, proposals_per_round=proposals, max_calls=max_calls,
                      threads=threads, export=dict(path=str(export), digest=identity['export_digest']), probe=identity,
                      budget=dict(limits=dict(BUDGET), used=dict(used)), calls=0, cost_usd=0.0, cost_unknown_calls=0,
                      rounds_run=0, stop=None, attempts=0, valid=0, columns=[], call_log=[], prompts={}, values={}, probe_seconds={},
                      code=code, started_at_utc=kaggle.utc_now())
        kaggle.atomic_json(out/'run.json', report)
    finally:
        kaggle.release_lock(lock)
    try:
        report['resources'] = experiment.resource_preflight(out)
        kaggle.atomic_json(out/'run.json', report)
        history, prior = [], []
        for number in range(1, rounds+1):
            if report['calls'] >= max_calls:
                report['stop'] = 'max_calls'
                break
            left = {key: BUDGET[key]-used[key] for key in BUDGET}
            prompt = render_prompt(stats, registry, history, proposals, left)
            (out/f'prompt-r{number}.txt').write_text(prompt, encoding='utf-8', newline='\n')
            report['prompts'][f'r{number}'] = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            report['rounds_run'] = number
            attempts, items = [], None
            for attempt in (1, 2):  # the second call only after a failed or unparsable one
                if report['calls'] >= max_calls:
                    break
                report['calls'] += 1
                call, meta = dict(round=number, attempt=attempt), None
                try:
                    reply, meta = ask(prompt, model)
                    items = _proposals(reply)
                    call['status'] = 'ok'
                except Exception as exc:
                    meta = getattr(exc, 'meta', meta)
                    call.update(status='failed', error=clean_error(f'{type(exc).__name__}: {exc}'))
                meta = _plain(meta) if isinstance(meta, dict) else {}
                if meta.get('command') is not None and report['llm_command'] is None:
                    report['llm_command'] = meta['command']  # argv without the prompt
                cost = _cost(meta.get('cost_usd'))
                call.update(seconds=meta.get('seconds'), cost_usd=cost, init=meta.get('init'))
                if cost is None:
                    report['cost_unknown_calls'] += 1
                else:
                    report['cost_usd'] = round(report['cost_usd']+cost, 6)
                if items is not None:
                    call.update(proposals=len(items), kept=min(len(items), proposals))
                report['call_log'].append(call)
                attempts.append(dict(call, text=meta.get('text'),
                                     meta={k: v for k, v in meta.items() if k not in ('text', 'init', 'command')}))
                kaggle.atomic_json(out/'run.json', report)
                if items is not None:
                    break
            kept = (items or [])[:proposals]
            kaggle.atomic_json(out/f'reply-r{number}.json', dict(round=number, llm_command=report['llm_command'],
                                                                 attempts=attempts, kept=len(kept)))
            if items is None:
                # Contract 2: an exhausted retry is a technical failure; nothing more is evaluated. A failed
                # call with no call left for its retry is exhausted as well.
                report.update(stop=RETRIES_EXHAUSTED, failed_round=number)
                if len(attempts) == 2:
                    raise RuntimeError(f'Round {number}: the call and its retry both failed or were unparsable')
                raise RuntimeError(f'Round {number}: the call failed or was unparsable and max_calls leaves '
                                   'no call for its retry')
            for index, item in enumerate(kept, 1):
                proposal = dict(id=f'r{number}p{index}', round=number, index=index, **item)
                loadavg = list(os.getloadavg())  # shows whether the heavy queue stayed idle
                try:
                    record, values = evaluate(probe, export, dict(proposal), list(prior), threads=threads)
                except Exception as exc:
                    if type(exc).__name__ != 'ProposalError':
                        raise
                    record, values = dict(status='invalid', error=f'ProposalError: {exc}', seconds=None,
                                          rows=None, columns=[]), None
                taken = {name for earlier in history if earlier['status'] == 'valid' for name in _column_names(earlier)}
                record = settle(record, proposal, values, taken)
                record['loadavg'] = loadavg
                if record['status'] == 'valid':
                    key, seconds = budget_key(record['level']), probe_seconds(values)
                    if used[key]+seconds > BUDGET[key]:
                        # No number here: the sanitizer would mask it, and the prompt shows the bucket
                        # of this query and the budget left (to 10 s) anyway.
                        record.update(status='budget', error=clean_error(
                            f'over the probe budget: {key} has too little time left for this query', proposal['sql']))
                    else:
                        used[key] += seconds
                        report['probe_seconds'][record['id']] = seconds  # exact, run.json only (ignored artifacts)
                        report['values'][record['id']] = write_values(values, out/'values'/f"{record['id']}.parquet",
                                                                      threads)
                        prior.append(values)
                _append(log, record)
                history.append(record)
                valid = [earlier for earlier in history if earlier['status'] == 'valid']
                report.update(attempts=len(history), valid=len(valid),
                              columns=[name for earlier in valid for name in _column_names(earlier)],
                              budget=dict(limits=dict(BUDGET), used=dict(used)))
                kaggle.atomic_json(out/'run.json', report)
        report.update(status='completed', stop=report['stop'] or 'rounds', log_sha256=experiment.sha256_file(log),
                      finished_at_utc=kaggle.utc_now())
        kaggle.atomic_json(out/'run.json', report)
        return report
    except BaseException as exc:
        report.update(status='failed', finished_at_utc=kaggle.utc_now(),
                      error=dict(type=type(exc).__name__, message=clean_error(exc, limit=2048),
                                 traceback=sandbox.sanitize_error(traceback.format_exc(limit=12))[-8192:]))
        kaggle.atomic_json(out/'run.json', report)
        raise


set_digest = sandbox.set_digest  # canonical_digest([[id, level, sql, columns], ...]), one definition


def freeze(run_dir, output):
    """hm-agent-set.json from a completed run: every valid proposal in (round, index, column) order."""
    run_dir = Path(run_dir).resolve()
    run = kaggle.read_json(run_dir/'run.json')
    if not isinstance(run, dict) or run.get('format') != RUN_FORMAT or run.get('status') != 'completed':
        raise ValueError('Only a completed hm-agent run is frozen')
    _run_name(run_dir)
    probe_sha256 = run.get('probe', {}).get('probe_sha256') if isinstance(run.get('probe'), dict) else None
    if not isinstance(probe_sha256, str):
        raise ValueError('run.json records no probe_sha256')
    completed = {path for path, record in probe_runs(probe_sha256).items() if record.get('status') == 'completed'}
    completed.add(run_dir)
    if len(completed) > 1:
        raise ValueError(f'More than one completed run on this probe: {", ".join(sorted(map(str, completed)))}; '
                         'the one-run rule leaves nothing to choose')
    log = run_dir/'log.jsonl'
    if experiment.sha256_file(log) != run.get('log_sha256'):
        raise ValueError('log.jsonl differs from the one the run completed with')
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
    order = [(record['round'], record['index']) for record in records]
    if (len(records) != run.get('attempts') or order != sorted(order) or len(set(order)) != len(order) or
            any(record['id'] != f"r{record['round']}p{record['index']}" for record in records)):
        raise ValueError('log.jsonl records are not unique and in (round, index) order')
    proposals, taken, used = [], set(), dict.fromkeys(BUDGET, 0.0)
    exact = run.get('probe_seconds')
    if not isinstance(exact, dict):
        raise ValueError('run.json holds no probe_seconds')
    for record in records:
        if record.get('status') not in STATUSES:
            raise ValueError(f"{record['id']}: unknown status")
        if record['status'] != 'valid':
            continue
        names = _column_names(record)
        problem = column_problem(record['level'], names, taken)
        if problem:
            raise ValueError(f"{record['id']}: {problem}")
        if not isinstance(record.get('seconds'), str) or not sandbox._is_bucket(record['seconds']):
            raise ValueError(f"{record['id']}: probe seconds are not a log2 bucket")
        seconds = exact.get(record['id'])
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError(f"{record['id']}: run.json holds no exact probe seconds for it")
        used[budget_key(record['level'])] += seconds
        taken.update(names)
        proposals.append(dict(id=record['id'], round=record['round'], index=record['index'], name=record['name'],
                              idea=record['idea'], level=record['level'], sql=record['sql'], columns=names,
                              probe_seconds=record['seconds']))
    if not proposals:
        raise ValueError('The run has no valid proposal; there is nothing to freeze')
    if set(exact) != {proposal['id'] for proposal in proposals}:
        raise ValueError('run.json probe_seconds and the valid proposals of the log differ')
    for key, limit in BUDGET.items():
        if used[key] > limit:
            raise ValueError(f'Valid proposals exceed the probe budget {key}')
    probe = run['probe']
    value = {'format': SET_FORMAT,
             'run': dict(id=run['id'], model=run['model'], rounds=run['rounds_run'],
                         proposals_per_round=run['proposals_per_round'], calls=run['calls'], cost_usd=run['cost_usd']),
             'probe': dict(anchor=probe['anchor'], users=probe['users'], export_digest=probe['export_digest']),
             'proposals': proposals,
             'attempts': [dict(id=record['id'], status=record['status'], error=clean_error(record.get('error'), record.get('sql')))
                          for record in records],
             'columns': [name for proposal in proposals for name in proposal['columns']],
             'budget': {key: _tens(used[key]) for key in BUDGET},  # rounded down to 10 s, never exact
             'digest': set_digest(proposals)}
    output = Path(output)
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    with tempfile.TemporaryDirectory(prefix='tlab-hm-agent-set-') as scratch:
        candidate = Path(scratch)/'hm-agent-set.json'
        candidate.write_text(text, encoding='utf-8', newline='\n')
        sandbox.read_agent_set(candidate)  # the reader of the sidecars accepts exactly this file
    if output.exists():
        if output.read_text(encoding='utf-8') != text:
            raise FileExistsError(f'{output.name} exists with other content; it is not overwritten')
        return value
    kaggle.atomic_json(output, value)
    return value


def main(argv=None):
    parser = kaggle.Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('run', help='rounds of LLM proposals checked on the probe')
    command.add_argument('--export', type=Path, required=True)
    command.add_argument('--probe', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--rounds', type=int, default=6)
    command.add_argument('--proposals', type=int, default=5)
    command.add_argument('--model', default=MODEL)
    command.add_argument('--max-calls', type=int, default=MAX_CALLS)
    command.add_argument('--threads', type=int, default=3)
    command.add_argument('--retry-of', type=Path, help='the failed run this run repeats (one-run rule)')
    command.add_argument('--reason', help='why the failed run is repeated; required with --retry-of')
    command = sub.add_parser('freeze', help='hm-agent-set.json from a completed run')
    command.add_argument('--run', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except kaggle.UsageError as exc:
        tokens = sys.argv[1:] if argv is None else list(argv)
        print(json.dumps(dict(status='failed', command=next((t for t in tokens if t in sub.choices), None),
                              error_type='UsageError', message=str(exc)[:500])))
        return 1
    try:
        if not kaggle.isolated():
            raise RuntimeError('Run it as python -I scripts/hm_agent_loop.py')
        if args.command == 'run':
            result = run_loop(args.export, args.probe, args.output, args.rounds, args.proposals, args.model,
                              args.max_calls, args.threads, retry_of=args.retry_of, reason=args.reason)
            print(json.dumps(dict(status=result['status'], id=result['id'], calls=result['calls'],
                                  cost_usd=result['cost_usd'], rounds=result['rounds_run'], stop=result['stop'],
                                  attempts=result['attempts'], valid=result['valid'], columns=len(result['columns']))))
        else:
            result = freeze(args.run, args.output)
            print(json.dumps(dict(status='completed', proposals=len(result['proposals']),
                                  columns=len(result['columns']), digest=result['digest'])))
    except Exception as exc:
        message = clean_error(exc, limit=500)
        if type(exc).__module__.split('.')[0].lstrip('_') in kaggle.NATIVE_ERRORS:
            message = 'Native library error; see run.json if one was written'
        print(json.dumps(dict(status='failed', command=args.command, error_type=type(exc).__name__, message=message)))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
