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
"""
import hashlib
import json
import math
import os
import re
import subprocess
import time
from datetime import datetime

from council import roles

MODEL = 'opus'
TIMEOUT_S = 900
MAX_CALLS = 40
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


def log_path():
    return roles.RUNS / 'llm.jsonl'


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


def check_prompt(prompt, subs, sources, free=()):
    """PromptRefused unless the substitutions pass the number test and the prompt outside the free slots
    (texts of blind agents) names nothing of NAMES and no day from the first day after the training anchors on."""
    problems = number_problems(subs, *sources)
    if problems:
        shown = ', '.join(f'{slot}:{token}' for slot, token in problems[:10])
        raise PromptRefused(f'numbers outside the declared sources: {shown}')
    unknown = set(free) - set(subs)
    if unknown:
        raise PromptRefused(f'free slots {sorted(unknown)} are not substitutions')
    rest = prompt
    for slot in free:
        rest = rest.replace(str(subs[slot]), '')
    hit = NAMES.search(rest)
    if hit:
        raise PromptRefused(f'the prompt names {hit.group(0)!r}')
    late = sorted({d for d in DATE.findall(rest) if d >= roles.SPANS['val'][0]})
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


def calls_made():
    """Calls of the campaign so far: records of llm.jsonl that reached `claude`."""
    path = log_path()
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text().splitlines():
        try:
            n += bool(json.loads(line).get('call'))
        except (ValueError, AttributeError):
            continue  # an unfinished last line of a killed process
    return n


def _log(record):
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cut = path.exists() and path.stat().st_size and not path.read_bytes().endswith(b'\n')
    with path.open('a') as fh:  # after an unfinished line of a killed process the record starts a new line
        fh.write(('\n' if cut else '') + json.dumps(record, ensure_ascii=False) + '\n')


def command(prompt, model):
    return ['claude', '-p', prompt, '--model', model, *FLAGS]


def flags(model):
    """The argv of the call without the prompt, as it is recorded."""
    return ['claude', '-p', '<prompt>', '--model', model, *FLAGS]


def _workdir():
    d = roles.LLM_DIR
    d.mkdir(parents=True, exist_ok=True)
    if any(d.iterdir()):
        raise LLMError(f'{d} must be empty: the call would see its files')
    return d


def _call(prompt, model):
    """(reply text, cost) of one `claude -p`; LLMError on a failed call."""
    env = {k: os.environ[k] for k in ENV_KEYS if k in os.environ} | {'LANG': 'en_US.UTF-8'}
    try:
        r = subprocess.run(command(prompt, model), cwd=roles.LLM_DIR, env=env, stdin=subprocess.DEVNULL,
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


def ask(prompt, role, stage, model=MODEL, *, subs, sources=(), free=(), max_calls=MAX_CALLS, check=None):
    """(parsed JSON, meta) of one council call.

    subs     the substitutions the prompt was rendered from; they pass the number test against sources;
    free     slots of subs holding free text of blind agents: exempt from the word and day test;
    check    optional function of the parsed JSON (normalises it or raises ValueError); a reply that does
             not parse or check is asked once more;
    max_calls the cap of calls of the whole campaign, counted from llm.jsonl.
    """
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    argv = flags(model)
    base = dict(stage=stage, role=role, model=model, prompt_sha256=digest, command=argv, free=list(free))
    try:
        check_prompt(prompt, subs, sources, free)
        _workdir()
    except LLMError as e:  # refused before any call: the cap is not spent
        _log(base | dict(time=datetime.now().isoformat(timespec='seconds'), call=False, error=str(e)))
        raise
    prompts = roles.RUNS / 'prompts'
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / f'{stage}-{role}.txt').write_text(
        f'# command: {json.dumps(argv)}\n# cwd: {roles.LLM_DIR}\n# prompt_sha256: {digest}\n\n{prompt}')
    last = None
    for attempt in (1, 2):
        if calls_made() >= max_calls:
            raise BudgetSpent(f'the campaign cap of {max_calls} LLM calls is spent')
        t0 = time.time()
        rec = base | dict(time=datetime.now().isoformat(timespec='seconds'), call=True, attempt=attempt)
        try:
            text, cost = _call(prompt, model)
        except LLMError as e:
            cost = e.args[1] if len(e.args) > 1 else None
            _log(rec | dict(seconds=round(time.time() - t0, 1), cost_usd=cost, error=str(e.args[0])[:500]))
            raise LLMError(e.args[0]) from None
        rec |= dict(seconds=round(time.time() - t0, 1), cost_usd=cost)
        replies = roles.RUNS / 'replies'
        replies.mkdir(parents=True, exist_ok=True)
        (replies / f'{stage}-{role}.txt').write_text(text)
        try:
            value = extract_json(text)
            if check is not None:
                value = check(value)
        except ValueError as e:
            last = e
            _log(rec | dict(error=f'parse: {str(e)[:500]}'))
            continue
        _log(rec | dict(error=None))
        return value, dict(seconds=rec['seconds'], cost_usd=cost, attempts=attempt, prompt_sha256=digest)
    raise LLMError(f'{stage}/{role}: no usable JSON after two replies: {last}')
