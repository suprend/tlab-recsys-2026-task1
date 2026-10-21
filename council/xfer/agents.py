"""The LLM stages of the council on xfer (council/runs/xfer/contract.md §3.4, §7.7, §8.9): reference(ds, k),
wave1(ds), cross_exam(ds), author_replies(ds), prereg1(ds), as council/xfer/run.py calls them.

Thin: the rendering, parsing, files and calls of every stage are council.agents and council.llm, given the
dataset through their `context` parameter (no stage is copied). This module builds that context from the
activated dataset:

  templates   the council roles of council.agents with the dataset's own task: the TASK .. TABLES and QUERY
              RULES .. OUTPUT sections of the adapter's PROMPT_TEMPLATE, rendered at run time as the xfer agent
              renders round 1 (adapter.prompt_substitutions on base.json, xa.prompt_number_problems on its
              substitutions); the task, the quality measure and the base come only from there. The column name
              rule of the agent becomes <<prefix>><slug>; names of NAMES in a list of forbidden words are dropped
              from it (the sandbox still refuses them); the budget of a whole agent set is cut.
  texts       features: the columns of the frozen xfer agent set by proposal; tried: its (name, idea) pairs.
  llm         council/runs/xfer-<x>/llm.jsonl, prompts/, replies/ (roles.paths), the neutral working directory
              /tmp/tlab-council-llm-a|b, NAMES (with spelling variants), the anchor test on the whole prompt
              (T: steps from the S0 anchor to the last anchor; S: dates from the S0 anchor on), 24 calls and 25 USD
              per dataset, LLM_TOTAL_USD over the journals of both, a call without a known cost charged the
              largest observed cost (council.llm).
  cards       f_x_c<lens>_<slug> with a level of xa.LEVELS; tables roles.family_table; at most xa.MAX_VALUES
              columns. Rb<k>: columns ag_rb<k>_<slug> (sandbox names), tables roles.rb_table, probed by
              sandbox.probe on the probe data with the light gate before every probe (contract §8.7).
  masking     the probe anchors as probe_day_1, probe_day_2 (sandbox.mask_anchors) in everything the roles see (§8.9),
              and every text of the sandbox or of a model (cards, critiques, failed proposals, tried ideas)
              through scrubber(): paths, NAMES, ids, anchors, late steps or dates. SQL is never scrubbed: it is
              shown as written, or withheld when the prompt test would refuse it (shower); a reply whose SQL
              copies a placeholder is unusable (bad_sql): the card stays, the Rb proposal stays failed. A name the
              scrubber would change is replaced (name_ok): Rb p<i>, a card the slug of its id. The hidden
              author also covers sandbox columns ag_c<lens>_ and family tables g<lens>_<n>.

Files (roles.paths(x).runs): reference-rb<k>.json {proposals: [{name, idea, level, sql, columns, table}], tables,
...}; cards-wave1.json {G1..G4: {cards, rejected, llm}, cards: [...]}; critiques.json; cards-final.json {replies,
cards, withdrawn, revised, unanswered}; prereg-1.json. The probes of the cards come from probes.json {cards: {id:
card probe}} of sandbox.probe_stage (the evidence stage of run.py); a card whose current version is not there stops
the stage.
"""
from __future__ import annotations

import hashlib
import re

from council import agents as A
from council import llm
from council.xfer import queue, roles, sandbox
from scripts import xfer_agent as xa
from scripts import xfer_common as xc

# The names no prompt and no working directory may carry (contract §3.4).
GAP = r'[\s\-\u2010-\u2015_.]{0,3}'      # spaces, dashes, dots or underscores inside a name
VARIANTS = (rf'\bt{GAP}bank', rf'\bт{GAP}банк', rf'сбер{GAP}маркет', r'сбер')
NAMES = re.compile('|'.join(f'(?:{p})' for p in (llm.NAMES.pattern, xa.NAMES_IN_PROMPT.pattern,
                                                  xa.NAMES_IN_SUBSTITUTIONS.pattern, roles.LLM_EXTRA_NAMES,
                                                  *VARIANTS)), re.I)
PATH = re.compile(r'[~.]{0,2}/?(?:[\w.\-]+/){2,}[\w.\-]*')   # a file path (two slashes at least): <path>
STATS = {'note': 'not shown'}               # the agent's probe statistics are not part of the council prompts
SECTIONS = ('TASK', 'QUERY RULES', 'VALIDITY')
HEADING = re.compile(r'^([A-Z]{3,})(?=$|[ :(])', re.M)    # the first word of a section heading
HEADINGS = (('TASK', 'CANDIDATES', 'TRAINING', 'FEATURES', 'TABLES'), ('QUERY', 'OUTPUT'))
SET_BUDGET = re.compile(r'\s*Budget of the whole set on the probe:.*?gets status budget\.', re.S)
MAX_SLUG = 30
CARD_FIELDS = A.CARD_FIELDS[:1] + ('level',) + A.CARD_FIELDS[1:]

LENSES = {
    'G1': 'intent and recency of the user: what the user is doing right now; the latest interactions, their pace '
          'and gaps, repeats and returns, bursts and pauses, the start of a new interest or the end of an old one.',
    'G2': 'item, time and shift: the life cycle of an item, freshness, growth and decay of its audience, periodic '
          'rhythm, and robustness to shifts of traffic between anchors.',
    'G3': 'co-occurrence graph and transitions: item-item graphs, multi-step diffusion from seed items, sequential '
          'transitions, user-user neighbourhoods.',
    'G4': 'misses of the base: what the current columns describe poorly; reason from the column list about cold '
          'items, users with short histories, groups where many columns are NULL, candidates far from the latest '
          'interactions, and design signals for them. No error tables are given.',
}

# ---------------------------------------------------------------- council parts (the task is the adapter's)

FEATURES = """Columns of an earlier feature agent, in the model besides the base above (proposal name [level]: columns):
<<features>>
"""

TRIED = """Ideas of that agent, all of them in the model above (name: idea):
<<tried>>
"""

COUNCIL_RULES = """COUNCIL RULES
- The value columns of a query are the names with the prefix <<prefix>> in its SELECT; the sandbox runs the
  query with exactly these output columns. Use the prefix only for output columns, never for intermediate
  aliases; the part after the prefix is lower-case snake_case of at most """ + str(MAX_SLUG) + """ characters.
- Every query states its level (pair, user or item); the level fixes its keys.
- The probe runs every query at two anchors, named probe_day_1 and probe_day_2 in what you see.
- All valid columns enter the model without selection by outcome. Superfluous and noisy columns hurt: a few
  strong, non-redundant signals are needed.
"""

CARD = """Write <<n>> cards. A card is one feature family together with the experiment that could refute it:
{"name": "short_snake_case",
 "level": "pair | user | item: the level of the query and of its twin",
 "mechanism": "which behaviour of users or items the family measures and why it should raise the rank of
               the candidates the user turns to next",
 "sign": "+ if adding the family should improve ranking quality, - if you expect it to hurt",
 "stratum": "in words and as an SQL predicate over the tables before {A} (user or user x item): where the gain
             should be",
 "null_stratum": "where the gain should not be, in words and as an SQL predicate",
 "sql": "SELECT <the keys of the level>, ... AS <<prefix>>..., ... FROM ...",
 "twin": {"how": "time_shuffle | neighbour_shuffle | seeds_removed",
          "sql": "the same query with the mechanism destroyed: same level, keys and coverage, columns named as
                  yours plus the suffix _tw"},
 "rival": {"explanation": "another reason why the family could help", "stratum": "where the rival predicts
           the gain"}}
Twin forms: time_shuffle permutes interaction times (e.g. within a user, ordered by hash(...) of keys);
neighbour_shuffle replaces neighbours by others of similar popularity (and category, where the data have one)
chosen by hash(...); seeds_removed drops the seed interactions that carry the mechanism. The twin keeps the shape
of the family (similar non-NULL share) and must not be a near copy of it.
Columns: 1-3 per card, named <<prefix>><slug>, unique across your cards; use the prefix only for the output
columns of the card (and their _tw copies in the twin), never for intermediate aliases.
"""

JUDGED = """How cards are judged before any outcome is seen: validity in the sandbox, seconds per probe anchor,
coverage (the share of candidate rows with a non-NULL value), invariance to the batch of users, the rank
correlation rho and R2 within queries to the existing columns (a family with R2 >= 0.9 or |rho| >= 0.95 to
an existing column is a duplicate and is dropped), a stable non-NULL share across the probe anchors, and the shape
of the knockout twin. Other generators, a skeptic and a leak auditor critique the cards with the authors hidden;
every author answers them once.
"""

CRITIQUE = """Critique types:
- LEAK: information at or after the anchor {A}, or from other users of the batch, reaches the family; name the
  clause;
- DUPLICATE: only when citing the measured rho or R2 to a named existing column;
- SHIFT: the family behaves differently across anchors (cite the non-NULL share per probe anchor);
- COST: too slow or too large;
- MECHANISM_DOUBT: the mechanism is unlikely, or the twin does not destroy it;
- RIVAL: another explanation of the same gain, with its own stratum;
- OK: no objection.
kill_test: a concrete check that would refute the mechanism, one of: the twin as a factor; a difference of
differences between the stratum and the null stratum; the key level (user vs item vs pair); staleness (the
same query one anchor earlier). Say which, and what result would refute the mechanism.
"""

EVIDENCE = """Every card comes with its sandbox measurements, made without any model outcome: validity and
seconds per probe anchor, coverage per column, batch invariance, the highest |rho| and R2 within queries to the
existing columns with the nearest column, the shape check of the twin, the non-NULL share per probe anchor
(non_null_share_by_day) and the machine tests.
"""

ENGINEER = 'You are a feature engineer for a ranking model. Reply with JSON only.\n\n'
PROPOSAL = '{"name": "short_snake_case", "idea": "one sentence", "level": "pair|user|item", "sql": "SELECT ..."}'
FIXED = '{"name": "the same name", "idea": "one sentence", "level": "pair|user|item", "sql": "SELECT ..."}'


def templates(task: str, rules: str) -> dict:
    """The seven council templates (keys and placeholders of council.agents.TEMPLATES) around the dataset's task
    and query rules (task_sections)."""
    rules = rules.rstrip('\n') + '\n\n' + COUNCIL_RULES
    task = task.rstrip('\n') + '\n'
    reference = ENGINEER + task + '\n' + FEATURES + '\n' + TRIED + '\n' + rules + """
Propose <<n>> new features that are likely to improve ranking beyond the current set and differ from what
was tried. Think about what signals the current set misses. Every proposal is checked in the sandbox for
validity, time and coverage; you will see the check output of failed ones once and may fix them.
Answer with a JSON list only:
[""" + PROPOSAL + ']\n'
    reference_fix = ENGINEER + task + '\n' + FEATURES + '\n' + rules + """
Your proposals below failed the sandbox check. The check output is all you get; no model was fitted.
<<failed>>

Fix every failed proposal, keeping its name, or replace it by another query under the same name.
Answer with a JSON list only:
[""" + FIXED + ']\n'
    generator = """You are generator <<lens>> of a feature council for a ranking model.
Your lens: <<lens_text>> Other generators work through other lenses; stay inside yours. Reply with JSON only.

""" + task + '\n' + FEATURES + '\n' + TRIED + '\n' + rules + '\n' + JUDGED + '\n' + CARD + """
Answer with a JSON list of <<n>> cards only.
"""
    critic = """You are critic <<lens>> of a feature council for a ranking model. Your lens:
<<lens_text>> Reply with JSON only.

""" + task + '\n' + FEATURES + '\n' + rules + """
Below are <<n>> feature cards written by other generators; the authors are hidden behind the ids C01, C02, ...
""" + EVIDENCE + '\n' + CRITIQUE + """
Critique every card through your lens, 1-3 critiques per card.
<<cards>>

Answer with a JSON list only:
[{"card": "C01", "type": "MECHANISM_DOUBT", "text": "...", "kill_test": "..."}]
"""
    skeptic = """You are the skeptic of a feature council for a ranking model. Reply with JSON only. You judge
novelty: a card is new only if its signature (mechanism + predicted stratum + distinguishing kill_test) differs
from the existing columns and from everything already tried.

""" + task + '\n' + FEATURES + '\n' + TRIED + '\n' + rules + """
Below are <<n>> feature cards of the council; the authors are hidden behind the ids C01, C02, ...
""" + EVIDENCE + '\n' + CRITIQUE + """
Give every card at least one critique; name the tried proposal or existing column a card repeats.
<<cards>>

Answer with a JSON list only:
[{"card": "C01", "type": "DUPLICATE", "text": "...", "kill_test": "..."}]
"""
    auditor = """You are the leak auditor of a feature council for a ranking model. Reply with JSON only. You read
the level, the SQL of every card and of its twin, and the sandbox protocol. Look for: rows at or after the anchor
{A}; tables other than those listed; use of cand and users beyond restricting keys (the value of a key must not
depend on the batch); nondeterminism; permutations not ordered by hash(...) of keys; twins that read more than the
family; a level that does not match the keys of the query. A LEAK veto counts only when a machine test of the
protocol is red; otherwise write LEAK as a suspicion with a kill_test, or OK.

""" + task + '\n' + rules + """
Below are <<n>> cards (level, SQL and twin only); the authors are hidden behind the ids C01, C02, ...
""" + EVIDENCE + '\n' + CRITIQUE + """
Give every card exactly one critique of type LEAK or OK, or another type when the protocol shows it.
<<cards>>

Answer with a JSON list only:
[{"card": "C01", "type": "OK", "text": "...", "kill_test": "..."}]
"""
    author = """You are generator <<lens>> of a feature council for a ranking model. Your lens:
<<lens_text>> Reply with JSON only.

""" + task + '\n' + FEATURES + '\n' + rules + '\n' + CARD.replace('Write <<n>> cards. ', '') + """
You wrote the cards below. Each comes with its sandbox measurements (no model outcome) and the critiques of
anonymous critics, a skeptic and a leak auditor. Answer every card once:
- revise: return the full card in the same schema, corrected; it may stay unchanged if the critiques do not
  call for a change. A revised card is measured again.
- withdraw: drop the card, with a reason.
There is no vote; an unresolved critique stays on record as a kill_test.
<<cards>>

Answer with a JSON list only:
[{"card": "<<example>>", "action": "revise", "new": {"name": "...", "level": "...", "mechanism": "...", ...}},
 {"card": "...", "action": "withdraw", "reason": "..."}]
"""
    out = dict(reference=reference, reference_fix=reference_fix, generator=generator, critic=critic,
               skeptic=skeptic, auditor=auditor, author=author)
    for name, text in out.items():
        found = set(re.findall(r'<<(\w+)>>', text))
        want = set(re.findall(r'<<(\w+)>>', A.TEMPLATES[name])) | {'prefix'}
        if found != want:
            raise ValueError(f'template {name}: placeholders {sorted(found)}, council.agents needs {sorted(want)}')
    return out


# ---------------------------------------------------------------- the dataset's task, from its adapter

def base(ds) -> dict:
    """base.json of the dataset (configs/datasets/xfer-<x>-base.json, digest checked)."""
    return xc.read_base(ds.name)


def limits(ds) -> dict:
    """xa.limits of the dataset: probe timeouts per level and the budget of an agent set."""
    return xa.limits(ds.name)


def agent_prompt(ds) -> str:
    """The adapter's PROMPT_TEMPLATE as the xfer agent renders round 1 (xa.render_prompt), on the active adapter:
    no probe statistics, no history, the whole probe budget left; xa.prompt_number_problems on the
    substitutions."""
    adapter, b = ds.adapter, base(ds)
    digest, frozen = adapter.prompt_digest(), agent_set(ds).get('prompt_digest')
    if digest != frozen:
        raise ValueError(f'{ds.name}: the prompt of the adapter ({digest}) is not the prompt of the agent set ({frozen})')
    rounds = adapter.PROMPT_CONSTANTS['rounds']
    budget = xa.feedback_budget(limits(ds)['budget'])
    feedback = xa.format_feedback([])
    subs = adapter.prompt_substitutions(STATS, b, feedback, 1, budget)
    problems = xa.prompt_number_problems(subs, STATS, b, adapter.PROMPT_CONSTANTS,
                                         xa.feedback_outputs(feedback, 1, rounds, budget))
    if problems:
        raise ValueError(f'{ds.name}: substitutions with numbers outside the xfer sources: {problems[:5]}')
    return adapter.PROMPT_TEMPLATE.format(**subs)


def drop_names(text: str) -> str:
    """The text without the words of a comma list that contain a name of NAMES; ValueError when a name stands
    elsewhere."""
    while True:
        m = NAMES.search(text)
        if not m:
            return text
        i, j = m.start(), m.end()
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] in '_*'):
            i -= 1
        while j < len(text) and (text[j].isalnum() or text[j] in '_*'):
            j += 1
        if text.startswith(', ', j):
            text = text[:i] + text[j + 2:]
        elif text[:i].endswith(', '):
            text = text[:i - 2] + text[j:]
        else:
            raise ValueError(f'the task text names {m.group(0)!r} outside a list of words')


def task_sections(prompt: str) -> tuple[str, str]:
    """(task, rules) of an agent prompt: TASK up to QUERY RULES, QUERY RULES up to VALIDITY; the agent's column
    name rule replaced by <<prefix>><slug>, the budget of a whole agent set cut (exactly once), NAMES dropped;
    ValueError unless the headings of the two parts are HEADINGS."""
    at = []
    for head in SECTIONS:
        marker = f'\n{head}\n'
        if prompt.count(marker) != 1:
            raise ValueError(f'the agent prompt has {prompt.count(marker)} sections {head!r}, one is needed')
        at.append(prompt.index(marker) + 1)
    if not at[0] < at[1] < at[2]:
        raise ValueError(f'the sections {SECTIONS} are out of order')
    task, rules = prompt[at[0]:at[1]].rstrip('\n'), prompt[at[1]:at[2]].rstrip('\n')
    rule = f'^{xa.NAME.pattern}$'
    if rules.count(rule) != 1:
        raise ValueError(f'the column name rule {rule} is not in the query rules once')
    rules, cut = SET_BUDGET.subn('', rules.replace(rule, '<<prefix>><slug>'))
    if cut != 1:
        raise ValueError(f'the budget of the agent set is in the query rules {cut} times, once is expected')
    for part, want in zip((task, rules), HEADINGS):
        got = tuple(HEADING.findall(part))
        if got != want:
            raise ValueError(f'the headings {got} of the agent prompt are not {want}')
    return drop_names(task), drop_names(rules)


# ---------------------------------------------------------------- texts, masking, hiding

def mask_text(text: str) -> str:
    text = re.sub(r'\baccepted\b', 'earlier', str(text), flags=re.I)
    return NAMES.sub('<name>', text)


def agent_set(ds) -> dict:
    """The frozen xfer agent set (configs/datasets/xfer-<x>-set.json, checked by xa.read_set)."""
    return xa.read_set(ds.name)


def texts(ds):
    """(subs, sources) of the features and tried slots: the agent set by proposal; nothing else of the set."""
    scrub = scrubber(ds)
    records = [dict(name=p['name'], level=p['level'], columns=list(p['columns']),
                    idea=scrub(mask_text(p.get('idea', '')))) for p in agent_set(ds)['proposals']]
    features = '\n'.join(f"  {r['name']} [{r['level']}]: {', '.join(r['columns'])}" for r in records)
    tried = '\n'.join(f"  {r['name']}: {' '.join(r['idea'].split())}" for r in records)
    return dict(features=features, tried=tried), [records]


def scrubber(ds):
    """Function of a text (the output of the sandbox, the text of a model: cards, critiques, failed proposals) as the
    roles see it: file paths as <path>, names of NAMES as <name>, id-shaped runs redacted (xa.redact), a probe
    anchor as probe_day_<i> also after a dash, slash or underscore (probe-641, x_641), and whatever late() still
    finds as <late>. The test of the whole prompt in council.llm stays the last barrier."""
    texts = sorted((xc.anchor_text(a) for a in ds.probe_anchors), key=len, reverse=True)
    names = {xc.anchor_text(a): sandbox.MASK.format(i) for i, a in enumerate(ds.probe_anchors, 1)}
    loose = re.compile(r'(?<![A-Za-z0-9.])(' + '|'.join(re.escape(t) for t in texts) + r')(?![A-Za-z0-9]|\.[0-9])')
    is_late, token = late(ds), late_token(ds)

    def scrub(text):
        text = xa.redact(NAMES.sub('<name>', PATH.sub('<path>', str(text))))
        text = loose.sub(lambda m: names[m.group(1)], text)
        return token.sub(lambda m: '<late>' if is_late(m.group(0)) else m.group(0), text)
    return scrub


WITHHELD = '<sql withheld: mentions a name or a test-period number>'
QUOTED_PATH = re.compile(r"'[^']*/[^']*/[^']*'")             # a file path in an SQL string literal
PLACEHOLDER = re.compile(r'<path>|<name>|<late>|<digits>|<hex>|probe_day_[0-9]|<sql withheld')


def shower(ds):
    """Function of a card, critique or failed proposal of a model -> the object a prompt shows: every text through
    scrubber(ds) except SQL (key sql, also twin.sql), which is shown as written, or as WITHHELD when the test of
    the whole prompt would refuse it (a name of NAMES, a step or date of late(), a path in a string literal); a
    withheld proposal also gets the reason in its problems."""
    scrub, is_late = scrubber(ds), late(ds)

    def withheld(sql):
        return bool(NAMES.search(sql) or is_late(sql) or QUOTED_PATH.search(sql))

    def show(x, key=None):
        if isinstance(x, dict):
            out = {k: show(v, k) for k, v in x.items()}
            if isinstance(x.get('sql'), str) and out['sql'] == WITHHELD and isinstance(x.get('problems'), list):
                out['problems'] = list(out['problems']) + ['the SQL is withheld: it mentions a name or a test-period '
                                                           'number; write it anew']
            return out
        if isinstance(x, list):
            return [show(v, key) for v in x]
        if isinstance(x, str):
            return (WITHHELD if withheld(x) else x) if key == 'sql' else scrub(x)
        return x
    return show


def bad_sql(sql: str) -> str | None:
    """Why the SQL of a reply is unusable: it copies a placeholder of a prompt (scrubber, WITHHELD); None if not."""
    m = PLACEHOLDER.search(sql)
    return f'the SQL copies the placeholder {m.group(0)!r} of the prompt' if m else None


def masker(ds):
    """Function of an object (a probe view, check problems) as the roles see it: the probe anchors as probe_day_1,
    probe_day_2 (sandbox.mask_anchors, §8.9), then every text and key through scrubber(ds)."""
    scrub = scrubber(ds)

    def walk(x):
        if isinstance(x, dict):
            return {scrub(k) if isinstance(k, str) else k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return scrub(x) if isinstance(x, str) else x
    return lambda obj: walk(sandbox.mask_anchors(ds, obj))


def hide(text: str) -> str:
    """council.agents._hide plus the sandbox names of card columns and the family tables of roles."""
    text = A._hide(text)
    text = re.sub(r'ag_c[1-4]_', 'ag_c_', text)
    return re.sub(r'\bg[1-4]_[0-9]+(?:_tw)?\b', '<table>', text)


STEP = re.compile(r'(?<![A-Za-z0-9.@])\d+(?:\.\d+)?(?![A-Za-z0-9])')   # llm.NUMBER, also next to an underscore
DAY = re.compile(r'(?<![0-9])20[0-9]{2}-[0-9]{2}-[0-9]{2}(?![0-9])')    # llm.DATE, also next to an underscore


def late_token(ds):
    """The tokens late() looks at: integer steps on T, dates on S."""
    return STEP if type(ds.prompt_cutoff) is int else DAY


def late(ds):
    """Function of a text: the anchors it names from the S0 anchor on (T: integer steps up to the last anchor of
    the dataset; S: dates), also next to an underscore (x_641)."""
    cut = ds.prompt_cutoff
    if type(cut) is int:
        top = max(xc.anchor_int(a) for anchors in ds.anchors['roles'].values() for a in anchors)
        return lambda text: [t for t in STEP.findall(text) if '.' not in t and cut <= int(t) <= top]
    first = xc.anchor_text(cut)
    return lambda text: [d for d in DAY.findall(text) if d >= first]


# ---------------------------------------------------------------- Rb probes

def probe_gate(ds):
    """The light gate of a probe, as run.py gives it to sandbox.probe_stage: () -> reasons a probe may not run
    now; queue.light_gate('probe') next to the heavy step of the moment over the queue journals of both
    datasets."""
    journals = [roles.paths(x, ds.paths.root).queue_log for x in roles.DATASETS]
    return lambda: queue.light_gate('probe', heavy=queue.heavy_now(journals))


def prober(ds):
    """Function (proposal, threads) -> sandbox.probe of an Rb proposal at its level on the probe data (loaded
    once); before every probe it waits while the light gate gives reasons (§8.7). council.agents.reference calls it
    only for a proposal not measured yet."""
    data = {}

    def probe(proposal, threads):
        sandbox.wait_gate(probe_gate(ds))
        if 'probe' not in data:
            data['probe'] = sandbox.probe_data(ds, threads)
        return sandbox.probe(ds, proposal['sql'], proposal['level'], data['probe'], threads)
    return probe


def checker(ds):
    """Function (probe, prefix) -> why an Rb proposal failed the check (council.agents.probe_problems with the
    xfer column names, value cap and probe timeouts per level); [] when it passed."""
    timeouts = limits(ds)['timeouts']

    def problems(probe, prefix):
        from council import evidence as ev
        if not isinstance(probe, dict):
            return ['no probe']
        out = list(ev.machine_red(probe))
        if out:
            return out
        cols = probe.get('columns') or []
        bad = [c for c in cols if not (c.startswith(prefix) and roles.RB_COLUMN.fullmatch(c))]
        if bad:
            out.append(f'columns must be {prefix}<slug of at most {MAX_SLUG} characters>: {bad}')
        if not 1 <= len(cols) <= xa.MAX_VALUES:
            out.append(f'{len(cols)} value columns, 1-{xa.MAX_VALUES} allowed')
        sec, limit = probe.get('seconds_median'), timeouts.get(probe.get('level'))
        if sec is None or limit is None or sec > limit:
            out.append(f'median seconds per probe anchor {sec} above the limit {limit} of level {probe.get("level")}')
        cov = probe.get('coverage') or {}
        low = [c for c, v in cov.items() if v is None or v < ev.MIN_COVERAGE]
        if low:
            out.append(f'coverage below {ev.MIN_COVERAGE} for {low}')
        return out
    return problems


# ---------------------------------------------------------------- the context

def code(ds) -> dict:
    """What prereg-1 records of the code: council.agents, council.llm, council.evidence, the council stamp
    (council/xfer/*.py, council/design.py) and xc.code_identity of the dataset."""
    shared = {f'council/{f}': hashlib.sha256((roles.ROOT / 'council' / f).read_bytes()).hexdigest()
              for f in ('agents.py', 'llm.py', 'evidence.py')}
    return dict(council=shared | roles.council_stamp(), scripts=xc.code_identity(ds.name))


def llm_context(ds) -> llm.Context:
    p = ds.paths
    others = tuple(roles.paths(x, p.root).llm_log for x in roles.DATASETS if x != ds.name)
    return llm.Context(log=p.llm_log, prompts=p.prompts, replies=p.replies, workdir=p.llm, names=NAMES,
                       late=late(ds), max_calls=roles.LLM_MAX_CALLS, max_usd=roles.LLM_MAX_USD, others=others,
                       total_usd=roles.LLM_TOTAL_USD, lock=p.llm.parent / 'tlab-council-llm.lock')


def context(ds) -> A.Context:
    """The council.agents context of the dataset (module docstring)."""
    task, rules = task_sections(agent_prompt(ds))
    scrub = scrubber(ds)
    constants = dict(cards=A.CARDS_PER_LENS, proposals=A.PROPOSALS, columns=[1, xa.MAX_VALUES],
                     lens_digits=[1, 2, 3, 4], reference=[1, 2], probe_anchors=[1, 2], slug=MAX_SLUG)
    limitation = ('The second probe anchor is the last train anchor; its users are those of its training frame, '
                  'a set conditional on the outcome window of that anchor. No outcome value is read by a probe.')
    return A.Context(
        templates=templates(task, rules), constants=constants, lenses=LENSES, texts=lambda: texts(ds),
        runs=ds.paths.runs, llm=llm_context(ds), levels=tuple(xa.LEVELS),
        rb_prefix=lambda k: f'ag_rb{k}_', rb_table=roles.rb_table, family_table=roles.family_table,
        mask=masker(ds), hide=hide, show=shower(ds), bad_sql=bad_sql, name_ok=lambda name: scrub(name) == name,
        probe=prober(ds), problems=checker(ds), code=lambda: code(ds),
        prereg=dict(dataset=ds.name, probe_anchors=[xc.anchor_text(a) for a in ds.probe_anchors],
                    limitations=[limitation]))


# ---------------------------------------------------------------- inputs of the stages

def card_probes(ds, cards, context=None) -> dict:
    """{card id: evidence} of the cards from probes.json of sandbox.probe_stage, with machine_red of the card
    probe; SystemExit when a card is not measured in its current version (its SQL and its twin's, as written or
    in sandbox names)."""
    from council import evidence as ev
    store = (A._load('probes.json', context) or {}).get('cards') or {}

    def forms(sql):
        out = {' '.join(sql.split())}
        try:
            out.add(' '.join(sandbox.to_sandbox(sql).split()))
        except ValueError:
            pass
        return out

    def measured(probe, sql):
        return isinstance(probe, dict) and isinstance(probe.get('sql'), str) and ' '.join(probe['sql'].split()) in forms(sql)
    out, missing = {}, []
    for c in cards:
        e = store.get(c['id'])
        if not (isinstance(e, dict) and measured(e.get('card'), c['sql']) and measured(e.get('twin'), c['twin']['sql'])):
            missing.append(c['id'])
            continue
        out[c['id']] = dict(e, machine_red=ev.machine_red(e['card']))
    if missing:
        raise SystemExit(f'run evidence first: probes.json lacks the current version of {missing}')
    return out


def _context(ds, context):
    return context if context is not None else globals()['context'](ds)


# ---------------------------------------------------------------- stages (run.py)

def reference(ds, k, context=None) -> dict:
    """Rb<k>: council.agents.reference with the xfer context -> reference-rb<k>.json."""
    return A.reference(k, threads=sandbox.THREADS, context=_context(ds, context))


def wave1(ds, context=None) -> list[dict]:
    """G1-G4, 8 cards each -> cards-wave1.json, plus its flat list under 'cards' (contract §7.7)."""
    c = _context(ds, context)
    cards = A.wave1(context=c)
    state = A._load('cards-wave1.json', c)
    if state.get('cards') != cards:
        A._save('cards-wave1.json', state | dict(cards=cards), c)
    return cards


def cross_exam(ds, context=None) -> list[dict]:
    """Critiques of the wave1 cards with their probes -> critiques.json."""
    c = _context(ds, context)
    cards = A._wave1_cards(c)
    return A.cross_exam(cards, card_probes(ds, cards, c), context=c)


def author_replies(ds, context=None) -> list[dict]:
    """Revise or withdraw -> cards-final.json; the revised cards are probed by the next evidence stage."""
    c = _context(ds, context)
    cards = A._wave1_cards(c)
    return A.author_replies(cards, A._critiques(c), card_probes(ds, cards, c), context=c)


def prereg1(ds, context=None) -> dict:
    """prereg-1.json of the final cards (written once)."""
    c = _context(ds, context)
    return A.prereg1(A._final_cards(c), A._critiques(c), context=c)
