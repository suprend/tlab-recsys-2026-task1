"""One isolated `claude -p` call of a council role (contract §3.4).

Before the call the prompt substitutions pass the number test: every number in them must come from the
sources the caller declares (constants of the problem statement and evidence without outcomes: coverage,
rho_wq, R2_wq, seconds, column counts, and the texts of blind agents). A number from anywhere else refuses
the prompt. The call runs from the empty roles.LLM_DIR with a minimal environment, no tools and no MCP
servers; its reply is reduced to the first JSON list or object. Every call is logged to RUNS/llm.jsonl
(stage, role, prompt hash, seconds, cost, error) and its prompt is kept in RUNS/prompts/<stage>-<role>.txt.
The number of calls of the whole campaign is capped (llm.jsonl is the counter); a reply without JSON is asked
once more.

Names of the competition and days after the training anchors are refused in the template and in every
substitution the code writes; the free text of blind agents (cards, critiques, proposals: the slots the caller
names in `free`) is exempt from that word test, as an ordinary word such as 'competition' in a mechanism is not
a leak. The number test covers every substitution.

Isolation, as it is: `--tools ''` and `--strict-mcp-config` remove tools and MCP servers, the working directory
is empty, so no project CLAUDE.md is read, and the user memory (~/.claude/CLAUDE.md) is empty. `--bare` is
not used, because it breaks the login of `claude -p`: hooks and plugins of the user settings are still loaded.
The flags of every call are written to llm.jsonl and to the head of the prompt file.

`context` (a Context; None = REES46: roles.RUNS, roles.LLM_DIR, NAMES, the days of roles.SPANS, MAX_CALLS) moves
the journal, the prompt and reply files and the working directory to another dataset and replaces the name and day
tests (council/runs/xfer/contract.md §3, §3.4). With a context the name and day tests cover the whole prompt (free
slots included) and the path of the working directory. Its journal records a call as `started` before `claude`
runs, under a file lock together with the check of the caps, so two processes cannot both take the last call; the
calls are counted by these records, and a call without a known cost (killed, timed out) is charged the reserve: the
largest cost observed in the journals (RESERVE_USD before any). A call is refused when the dollars spent plus the
reserve would pass the cap of the dataset, or the cap of all journals of the context together.
"""
import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import time
import uuid
from contextlib import contextmanager
import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from council import roles

MODEL = 'opus'
TIMEOUT_S = 900
MAX_CALLS = 40
RESERVE_USD = 4.0      # the charge of a call without a known cost while no cost is observed (context only)
FLAGS = ['--output-format', 'json', '--tools', '', '--strict-mcp-config']
ENV_KEYS = ('HOME', 'PATH', 'USER', 'LOGNAME', 'TMPDIR')  # no CLAUDE_*, MCP_*, plugin directories
NUMBER = re.compile(r'(?<![A-Za-z0-9_.@])\d+(?:\.\d+)?(?![A-Za-z0-9_])')  # as xfer_agent.NUMBER
# Names that never reach a council prompt: the competition and its brands.
NAMES = re.compile(r'kaggle|leaderboard|competition|submission|tinkoff|sber|instamart', re.I)
DATE = re.compile(r'\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b')


class LLMError(RuntimeError):
    pass


class PromptRefused(LLMError):
    pass


class BudgetSpent(LLMError):
    pass


@dataclass(frozen=True)
class Context:
    """The calls of one dataset: where they are logged and run, what their prompts may not name, their caps."""
    log: Path                               # the journal (llm.jsonl): also the counter of calls and dollars
    prompts: Path                           # prompts/<stage>-<role>.txt
    replies: Path                           # replies/<stage>-<role>.txt
    workdir: Path                           # the empty working directory of `claude -p`
    names: re.Pattern                       # names refused in the prompt and in the path of workdir
    late: Callable[[str], list]             # what the text names of the period after the training anchors
    max_calls: int = MAX_CALLS
    max_usd: float | None = None            # None: no dollar cap
    others: tuple = ()                      # journals of the other datasets, counted by total_usd
    total_usd: float | None = None          # the cap of all journals together; None: none
    lock: Path | None = None                # the lock file of the check and the started record; None: log + '.lock'


def log_path(context=None):
    return roles.RUNS / 'llm.jsonl' if context is None else context.log


def _leaves(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _leaves(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def allowed(*sources):
    """Tokens and numeric values of the declared sources."""
    tokens, values = set(), set()

    def add_text(text):
        for token in NUMBER.findall(text):
            tokens.add(token)
            values.add(float(token))
    for source in sources:
        for leaf in _leaves(source):
            if leaf is None or isinstance(leaf, bool):
                continue
            if isinstance(leaf, (int, float)):
                if math.isfinite(leaf):
                    values.update((float(leaf), abs(float(leaf))))
                add_text(json.dumps(leaf))
            add_text(str(leaf))
    return tokens, values


def number_problems(subs, *sources):
    """[(slot, token)] for numbers of the substitutions found in none of the sources; [] when clean."""
    tokens, values = allowed(*sources)
    problems = []
    for slot, value in subs.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        for token in NUMBER.findall(text):
            if token not in tokens and float(token) not in values:
                problems.append((str(slot), token))
    return problems


def check_prompt(prompt, subs, sources, free=(), context=None):
    """PromptRefused unless the substitutions pass the number test and the prompt outside the free slots
    (texts of blind agents) names nothing of NAMES and no day from the first day after the training anchors on
    (with a context: nothing of context.names and nothing context.late finds)."""
    problems = number_problems(subs, *sources)
    if problems:
        shown = ', '.join(f'{slot}:{token}' for slot, token in problems[:10])
        raise PromptRefused(f'numbers outside the declared sources: {shown}')
    unknown = set(free) - set(subs)
    if unknown:
        raise PromptRefused(f'free slots {sorted(unknown)} are not substitutions')
    rest = prompt
    for slot in free if context is None else ():   # a context tests the whole prompt
        rest = rest.replace(str(subs[slot]), '')
    hit = (NAMES if context is None else context.names).search(rest)
    if hit:
        raise PromptRefused(f'the prompt names {hit.group(0)!r}')
    if context is None:
        late = sorted({d for d in DATE.findall(rest) if d >= roles.SPANS['val'][0]})
    else:
        late = sorted(set(context.late(rest)))
    if late:
        raise PromptRefused(f'the prompt names days after the training anchors: {late[:5]}')


def extract_json(text):
    """The first JSON list or object in the reply text; ValueError when there is none."""
    if not isinstance(text, str):
        raise ValueError('the reply is not text')
    decoder = json.JSONDecoder()
    for m in re.finditer(r'[\[{]', text):
        try:
            value, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(value, (list, dict)) and value:
            return value
    raise ValueError(f'no JSON list or object in the reply: {" ".join(text.split())[:300]}')


def _records(context=None, path=None):
    path = log_path(context) if path is None else path
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue  # an unfinished last line of a killed process
        if isinstance(record, dict):
            yield record


def _cost(r):
    c = r.get('cost_usd')
    return float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else None


def calls_made(context=None):
    """Calls of the campaign so far: records of llm.jsonl that reached `claude` (with a context: the started
    records, so a call killed midway counts)."""
    if context is None:
        return sum(bool(r.get('call')) for r in _records(context))
    return sum(bool(r.get('started')) for r in _records(context))


def reserve_usd(context):
    """The charge of a call without a known cost: the largest cost in the journals of the context, else
    RESERVE_USD."""
    costs = [c for path in (context.log, *context.others) for r in _records(path=path) if (c := _cost(r)) is not None]
    return max(costs, default=RESERVE_USD)


def dollars_spent(context=None, path=None, reserve=None):
    """The cost_usd of the campaign so far, summed over llm.jsonl. With a context, every started call is charged
    its cost, or the reserve when its result has none (killed midway, timed out, still running)."""
    records = list(_records(context, path))
    if context is None:
        return sum(c for r in records if (c := _cost(r)) is not None)
    reserve = reserve_usd(context) if reserve is None else reserve
    paid = {r['call_id']: _cost(r) for r in records if r.get('call_id') and not r.get('started') and _cost(r) is not None}
    started = [r['call_id'] for r in records if r.get('started')]
    loose = sum(c for r in records if not r.get('call_id') and (c := _cost(r)) is not None)
    return loose + sum(paid.get(i, reserve) for i in started)


@contextmanager
def _locked(context):
    """The exclusive lock of the cap check and the started record of a context."""
    path = context.lock or context.log.with_name(context.log.name + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _start(context, record):
    """Check the caps and write the started record of one call, under the lock; BudgetSpent when a cap is
    reached. Returns the call id."""
    with _locked(context):
        if calls_made(context) >= context.max_calls:
            raise BudgetSpent(f'the campaign cap of {context.max_calls} LLM calls is spent')
        reserve = reserve_usd(context)
        own = dollars_spent(context, reserve=reserve)
        if context.max_usd is not None and own + reserve > context.max_usd:
            raise BudgetSpent(f'{own:.2f} USD spent: one more call (reserve {reserve:.2f}) may pass the cap of '
                              f'{context.max_usd} USD')
        if context.total_usd is not None:
            total = own + sum(dollars_spent(context, path=o, reserve=reserve) for o in context.others)
            if total + reserve > context.total_usd:
                raise BudgetSpent(f'{total:.2f} USD spent by all datasets: one more call (reserve {reserve:.2f}) '
                                  f'may pass the cap of {context.total_usd} USD')
        call_id = uuid.uuid4().hex
        _log(record | dict(started=True, call_id=call_id, call=False), context)
        return call_id


def _log(record, context=None):
    path = log_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    cut = path.exists() and path.stat().st_size and not path.read_bytes().endswith(b'\n')
    with path.open('a') as fh:  # after an unfinished line of a killed process the record starts a new line
        fh.write(('\n' if cut else '') + json.dumps(record, ensure_ascii=False) + '\n')


def command(prompt, model):
    return ['claude', '-p', prompt, '--model', model, *FLAGS]


def flags(model):
    """The argv of the call without the prompt, as it is recorded."""
    return ['claude', '-p', '<prompt>', '--model', model, *FLAGS]


def _workdir(d=None):
    d = roles.LLM_DIR if d is None else d
    d.mkdir(parents=True, exist_ok=True)
    if any(d.iterdir()):
        raise LLMError(f'{d} must be empty: the call would see its files')
    return d


def _call(prompt, model, cwd=None):
    """(reply text, cost) of one `claude -p` in cwd (None: roles.LLM_DIR); LLMError on a failed call."""
    env = {k: os.environ[k] for k in ENV_KEYS if k in os.environ} | {'LANG': 'en_US.UTF-8'}
    try:
        r = subprocess.run(command(prompt, model), cwd=roles.LLM_DIR if cwd is None else cwd, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise LLMError(f'no answer within {TIMEOUT_S} s') from None
    except OSError as e:
        raise LLMError(f'claude could not start: {e}') from None
    try:
        out = json.loads(r.stdout)
    except ValueError:
        raise LLMError(f'exit {r.returncode}, stdout is not JSON: {(r.stderr or r.stdout)[-300:]}') from None
    cost = out.get('total_cost_usd') if isinstance(out, dict) else None
    if r.returncode or not isinstance(out, dict) or out.get('is_error') or not isinstance(out.get('result'), str):
        raise LLMError(f'claude failed (exit {r.returncode}): {str(out)[-300:]}', cost)
    return out['result'], cost


def ask(prompt, role, stage, model=MODEL, *, subs, sources=(), free=(), max_calls=None, check=None, context=None):
    """(parsed JSON, meta) of one council call.

    subs     the substitutions the prompt was rendered from; they pass the number test against sources;
    free     slots of subs holding free text of blind agents: exempt from the word and day test (without a
             context only; a context tests the whole prompt);
    check    optional function of the parsed JSON (normalises it or raises ValueError); a reply that does
             not parse or check is asked once more;
    max_calls the cap of calls of the whole campaign, counted from llm.jsonl (None: MAX_CALLS, or the cap of
             the context; with a context at most its cap);
    context  a Context of another dataset (module docstring); None: REES46.
    """
    if max_calls is None:
        max_calls = MAX_CALLS if context is None else context.max_calls
    elif context is not None:
        max_calls = min(max_calls, context.max_calls)   # an argument never raises the cap of a context
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    argv = flags(model)
    base = dict(stage=stage, role=role, model=model, prompt_sha256=digest, command=argv, free=list(free))
    workdir = roles.LLM_DIR if context is None else context.workdir
    try:
        check_prompt(prompt, subs, sources, free, context)
        if context is None:
            _workdir()
        else:
            hit = context.names.search(str(workdir))
            if hit:
                raise PromptRefused(f'the working directory {workdir} names {hit.group(0)!r}')
            _workdir(workdir)
    except LLMError as e:  # refused before any call: the cap is not spent
        _log(base | dict(time=datetime.now().isoformat(timespec='seconds'), call=False, error=str(e)), context)
        raise
    prompts = roles.RUNS / 'prompts' if context is None else context.prompts
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / f'{stage}-{role}.txt').write_text(
        f'# command: {json.dumps(argv)}\n# cwd: {workdir}\n# prompt_sha256: {digest}\n\n{prompt}')
    last = None
    for attempt in (1, 2):
        rec = base | dict(time=datetime.now().isoformat(timespec='seconds'), call=True, attempt=attempt)
        if context is None:
            if calls_made(context) >= max_calls:
                raise BudgetSpent(f'the campaign cap of {max_calls} LLM calls is spent')
        else:
            if max_calls != context.max_calls:
                context = dataclasses.replace(context, max_calls=max_calls)
            rec['call_id'] = _start(context, rec)
        t0 = time.time()
        try:
            text, cost = _call(prompt, model) if context is None else _call(prompt, model, workdir)
        except LLMError as e:
            cost = e.args[1] if len(e.args) > 1 else None
            _log(rec | dict(seconds=round(time.time() - t0, 1), cost_usd=cost, error=str(e.args[0])[:500]), context)
            raise LLMError(e.args[0]) from None
        rec |= dict(seconds=round(time.time() - t0, 1), cost_usd=cost)
        replies = roles.RUNS / 'replies' if context is None else context.replies
        replies.mkdir(parents=True, exist_ok=True)
        (replies / f'{stage}-{role}.txt').write_text(text)
        try:
            value = extract_json(text)
            if check is not None:
                value = check(value)
        except ValueError as e:
            last = e
            _log(rec | dict(error=f'parse: {str(e)[:500]}'), context)
            continue
        _log(rec | dict(error=None), context)
        return value, dict(seconds=rec['seconds'], cost_usd=cost, attempts=attempt, prompt_sha256=digest)
    raise LLMError(f'{stage}/{role}: no usable JSON after two replies: {last}')
