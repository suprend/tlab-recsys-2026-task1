"""Prompts of the council roles and of the blind reference agent; the stages of the council (contract §3.4).

Stages, each resumable from its file in roles.RUNS (a second run does not call the LLM for what is written):
  reference K   Rb<K>: 12 proposals, sandbox probes, one fix call for the failed ones    reference-rb<K>.json
  wave1         generators G1-G4, 8 cards each, blind                                     cards-wave1.json
  evidence      probes of every card and twin without outcomes (council.evidence)          probes.json
  cross         two foreign-lens critics per card, skeptic, leak auditor; authors hidden  critiques.json
  authors       one reply per lens: revise or withdraw; revised cards are probed again   cards-final.json
  prereg1       hashes of the SQL, sign, strata, kill tests (no LLM)                      prereg-1.json
  curate        council.evidence.curate, code without outcomes                            curation.json
  compute       tables of families, twins and kept Rb on all days of train, val, test     compute.json
Run: TASK1_PERIOD=2020 .venv/bin/python -m council.agents <stage> [--k 1]

The prompts carry no outcome of any model and no number outside the declared sources (council.llm checks
the substitutions before the call). The functions of council.evidence are imported inside the stages.
"""
import argparse
import hashlib
import inspect
import json
import re
from datetime import date
from pathlib import Path

from council import llm, roles

TRIED_LOG = roles.ROOT / 'task1/runs/agent_night20/log.jsonl'
TRIED_PREFIX = 'agent_night20_'
CARDS_PER_LENS = 8
PROPOSALS = 12
MAX_COLUMNS = 4
HIDDEN_PREFIX = 'f_x_c<lens digit>_'  # the column prefix as the critics see it
CRITIC_TYPES = ('LEAK', 'DUPLICATE', 'SHIFT', 'COST', 'MECHANISM_DOUBT', 'RIVAL', 'OK')
TWIN_HOWS = ('time_shuffle', 'neighbour_shuffle', 'seeds_removed')
LENSES = {
    'G1': 'intent and sessions: what the user is trying to do right now; session structure, search and '
          'comparison phases, dwell, revisits, abandoned carts, the stage of the buying funnel.',
    'G2': 'product, time and shift: the life cycle of a product, freshness, price changes, stock-outs, '
          'trends, weekly rhythm, and robustness to shifts of traffic and logging between days.',
    'G3': 'co-occurrence graph and transitions: item-item and category-category graphs, multi-step '
          'diffusion from seed items, sequential transitions, user-user neighbourhoods.',
    'G4': 'misses of the base: targets the current columns describe poorly; reason from the column list '
          'about cold products, users with short histories, groups where many columns are NULL, targets '
          'far from the latest views, and design signals for them. No error tables are given.',
}
# Each card goes to two generators of foreign lenses (round robin), plus the skeptic and the auditor.
CRITICS = {'G1': ('G2', 'G3'), 'G2': ('G3', 'G4'), 'G3': ('G4', 'G1'), 'G4': ('G1', 'G2')}
SPLITS = ('train', 'val', 'test')
# Constants of the problem statement: the only numbers of the templates and the first number source.
CONSTANTS = dict(history_start='2020-01-01', anchors=list(roles.SPANS['train']), active_hours=48,
                 horizon_hours=24, window_days=14, candidates=280, candidate_sources=6, top=20,
                 cards=CARDS_PER_LENS, proposals=PROPOSALS, columns=[1, MAX_COLUMNS], median_seconds=60,
                 lens_digits=[1, 2, 3, 4], reference=[1, 2])

TASK = """Task. REES46 multi-category online store, events from 2020-01-01 on. Every day at the anchor
t = 00:00 UTC we rank products for the users active in [t-48h, t) who have at least one target. A target is
a product whose FIRST cart or purchase by the user happens in [t, t+24h) and that the user never touched
(no event of any type) before t. About 280 candidates per user come from six sources: the global top by
distinct cart/purchase users over 7 days; the top products of the user's 3 heaviest categories and of the
2 heaviest brands; session co-view neighbours of the user's 10 latest views; aggregated co-view scores and
view->acquisition transition scores over the user's 20 latest views. Every product the user touched before
t is excluded, so the (user, candidate) pair itself has no history: user signals work only through the
candidate's category, brand, price, popularity and item-item links to what the user did. A CatBoost model
scores each (user, product) pair; quality is a position-discounted gain over the top 20 products of each
user. Training anchors are 2020-01-15..2020-02-07; the earliest anchors see only two weeks of history.

The level of carts relative to views and purchases may change between days; prefer normalised forms
(shares, ratios, lifts, ranks, logs) and treat cart and purchase together. The base set reads a 14-day
window [t-14d, t).

You can read two DuckDB tables:
  hist(event_time TIMESTAMP, event_type VARCHAR -- 'view'|'cart'|'purchase',
       product_id BIGINT, category_id BIGINT, category_code VARCHAR -- e.g. 'electronics.smartphone', often NULL,
       brand VARCHAR -- often NULL, price DECIMAL(12,2), user_id BIGINT, user_session VARCHAR)
       -- all events strictly before t, starting 2020-01-01; tens of millions of rows, mostly views
  active_users(user_id) -- users with any event in the last 48 hours (a superset of the ranked users)
Write the anchor as TIMESTAMP '{t}' (literally, with the braces), e.g.
  event_time >= TIMESTAMP '{t}' - INTERVAL 3 DAY
"""

FEATURES = """Columns already in the model. Base set by prefix (s_ candidate source, u_ user, i_ item, uc_
candidate's category in the user's history, ub_ brand, up_ price vs user, ui_ popularity vs user, cf_
item-item from recent views), then the tables of the automation (f_x_ columns):
<<features>>
"""

TRIED = """Already tried, all of it in the model above:
- a DFS grid (tables dfs_p, dfs_c, dfs_b, dfs_u): for the candidate product, its category, its brand and the
  user; windows of 1, 3, 7 and 14 days before t; for every event type log(1 + events) and log(1 + distinct
  users), plus smoothed cart-per-view and purchase-per-view rates of distinct users;
- SQL features of an earlier blind agent on an earlier period of the same store, by table (name: idea):
<<tried>>
"""

RULES = """Rules for a feature query:
- one DuckDB SELECT statement (WITH is fine) reading only hist and active_users; no other tables,
  files or settings;
- returns key columns user_id and/or product_id plus 1-4 numeric value columns named <<prefix>><something>,
  names not used by any existing column;
- exactly one row per key, no NULL keys; keys without a row get NULL; afterwards only the keys present
  among the day's candidates are kept;
- the query cannot see the candidates: product-level features cover all products; user-level and
  pair-level queries must filter user_id IN (SELECT user_id FROM active_users), and pair-level ones must
  enumerate pairs narrowly (e.g. products of the user's recent categories or neighbours of recent views)
  so the result stays well under 50M rows;
- the value for a user must not depend on which other users are in active_users: the sandbox compares the
  answer on all active users with the union of the answers on two halves of them;
- deterministic: no random(), setseed(), now() or anything similar; any permutation is ordered by hash(...)
  of keys;
- a user-level feature is constant within a user's ranking and helps only through interactions;
- it runs once per anchor day; the median time must stay under 60 s per day, aim for under 20 s;
- the sandbox refuses a query containing any of these words, matched as whole words in any case anywhere in
  the text, also as aliases, column names or inside strings (* is any continuation):
<<FORBIDDEN>>
All valid columns enter the model without selection by outcome. Superfluous and noisy columns hurt: a few
strong, non-redundant signals are needed.
"""



def forbidden_words():
    """The words of task1.extra.FORBIDDEN, as the prompts list them."""
    from task1.extra import FORBIDDEN
    body = re.fullmatch(r'\\b\((.*)\)\\b', FORBIDDEN.pattern).group(1)
    return [w.replace(r'\w*', '*').replace(r'\w+', '*') for w in body.split('|')]


def _wrap(words, indent='  ', width=110):
    lines, line = [], indent
    for w in words:
        if len(line) + len(w) + 2 > width:
            lines.append(line.rstrip())
            line = indent
        line += w + ', '
    return '\n'.join(lines + [line.rstrip(', ')])


RULES = RULES.replace('<<FORBIDDEN>>', _wrap(forbidden_words()))

REFERENCE = """You are a feature engineer for a ranking model of new products. Reply with JSON only.

""" + TASK + '\n' + FEATURES + '\n' + TRIED + '\n' + RULES + """
Propose <<n>> new features that are likely to improve ranking beyond the current set and differ from what
was tried. Think about what signals the current set misses. Every proposal is checked in the sandbox for
validity, time and coverage; you will see the check output of failed ones once and may fix them.
Answer with a JSON list only:
[{"name": "short_snake_case", "idea": "one sentence", "sql": "SELECT ..."}]
"""

REFERENCE_FIX = """You are a feature engineer for a ranking model of new products. Reply with JSON only.

""" + TASK + '\n' + FEATURES + '\n' + RULES + """
Your proposals below failed the sandbox check. The check output is all you get; no model was fitted.
<<failed>>

Fix every failed proposal, keeping its name, or replace it by another query under the same name.
Answer with a JSON list only:
[{"name": "the same name", "idea": "one sentence", "sql": "SELECT ..."}]
"""

CARD = """Write <<n>> cards. A card is one feature family together with the experiment that could refute it:
{"name": "short_snake_case",
 "mechanism": "which behaviour of users or products the family measures and why it should raise the rank of
               the products that become targets",
 "sign": "+ if adding the family should improve ranking quality, - if you expect it to hurt",
 "stratum": "in words and as an SQL predicate over hist before t (user or user x product): where the gain
             should be",
 "null_stratum": "where the gain should not be, in words and as an SQL predicate",
 "sql": "SELECT user_id, product_id, ... AS <<prefix>>..., ... FROM hist ...",
 "twin": {"how": "time_shuffle | neighbour_shuffle | seeds_removed",
          "sql": "the same query with the mechanism destroyed: same keys and coverage, columns named as yours
                  plus the suffix _tw"},
 "rival": {"explanation": "another reason why the family could help", "stratum": "where the rival predicts
           the gain"}}
Twin forms: time_shuffle permutes event times (e.g. within user and day, ordered by hash(...));
neighbour_shuffle replaces neighbours by others of the same category and popularity decile chosen by
hash(...); seeds_removed drops the seed events that carry the mechanism. The twin keeps the shape of the
family (similar non-NULL share) and must not be a near copy of it.
Columns: 1-4 per card, named <<prefix>><slug>, unique across your cards; use the f_x_ prefix only for
the output columns of the card (and their _tw copies in the twin), never for intermediate aliases.
"""

JUDGED = """How cards are judged before any outcome is seen: validity in the sandbox, seconds per day,
coverage (the share of candidate rows with a non-NULL value), invariance to the batch of users, the rank
correlation rho and R2 within queries to the existing columns (a family with R2 >= 0.9 or |rho| >= 0.95 to
an existing column is a duplicate and is dropped), a stable non-NULL share across days, and the shape of the
knockout twin. Other generators, a skeptic and a leak auditor critique the cards with the authors hidden;
every author answers them once.
"""

GENERATOR = """You are generator <<lens>> of a feature council for a ranking model of new products.
Your lens: <<lens_text>> Other generators work through other lenses; stay inside yours. Reply with JSON only.

""" + TASK + '\n' + FEATURES + '\n' + TRIED + '\n' + RULES + '\n' + JUDGED + '\n' + CARD + """
Answer with a JSON list of <<n>> cards only.
"""

CRITIQUE = """Critique types:
- LEAK: information at or after t, or from other users of the batch, reaches the family; name the clause;
- DUPLICATE: only when citing the measured rho or R2 to a named existing column;
- SHIFT: the family behaves differently across days (cite the non-NULL share per day) or rests on the cart
  level;
- COST: too slow or too large;
- MECHANISM_DOUBT: the mechanism is unlikely, or the twin does not destroy it;
- RIVAL: another explanation of the same gain, with its own stratum;
- OK: no objection.
kill_test: a concrete check that would refute the mechanism, one of: the twin as a factor; a difference of
differences between the stratum and the null stratum; the key level (user vs product vs pair); staleness (the
same query at t - 24h). Say which, and what result would refute the mechanism.
"""

EVIDENCE = """Every card comes with its sandbox measurements, made without any model outcome: validity and
seconds per day, coverage per column, batch invariance, the highest |rho| and R2 within queries to the
existing columns with the nearest column, the shape check of the twin, the non-NULL share per day and the
machine tests.
"""

CRITIC = """You are critic <<lens>> of a feature council for a ranking model of new products. Your lens:
<<lens_text>> Reply with JSON only.

""" + TASK + '\n' + FEATURES + '\n' + RULES + """
Below are <<n>> feature cards written by other generators; the authors are hidden behind the ids C01, C02, ...
""" + EVIDENCE + '\n' + CRITIQUE + """
Critique every card through your lens, 1-3 critiques per card.
<<cards>>

Answer with a JSON list only:
[{"card": "C01", "type": "MECHANISM_DOUBT", "text": "...", "kill_test": "..."}]
"""

SKEPTIC = """You are the skeptic of a feature council for a ranking model of new products. Reply with JSON
only. You judge novelty: a card is new only if its signature (mechanism + predicted stratum + distinguishing
kill_test) differs from the existing columns and from everything already tried.

""" + TASK + '\n' + FEATURES + '\n' + TRIED + '\n' + RULES + """
Below are <<n>> feature cards of the council; the authors are hidden behind the ids C01, C02, ...
""" + EVIDENCE + '\n' + CRITIQUE + """
Give every card at least one critique; name the tried table or existing column a card repeats.
<<cards>>

Answer with a JSON list only:
[{"card": "C01", "type": "DUPLICATE", "text": "...", "kill_test": "..."}]
"""

AUDITOR = """You are the leak auditor of a feature council for a ranking model of new products. Reply with JSON
only. You read the SQL of every card and of its twin and the sandbox protocol. Look for: events at or after
t; anything other than hist and active_users; use of active_users beyond restricting users (the value of a
user must not depend on the batch); nondeterminism; permutations not ordered by hash(...) of keys; twins that
read more than the family. A LEAK veto counts only when a machine test of the protocol is red; otherwise
write LEAK as a suspicion with a kill_test, or OK.

""" + TASK + '\n' + RULES + """
Below are <<n>> cards (SQL and twin only); the authors are hidden behind the ids C01, C02, ...
""" + EVIDENCE + '\n' + CRITIQUE + """
Give every card exactly one critique of type LEAK or OK, or another type when the protocol shows it.
<<cards>>

Answer with a JSON list only:
[{"card": "C01", "type": "OK", "text": "...", "kill_test": "..."}]
"""

AUTHOR = """You are generator <<lens>> of a feature council for a ranking model of new products. Your lens:
<<lens_text>> Reply with JSON only.

""" + TASK + '\n' + FEATURES + '\n' + RULES + '\n' + CARD.replace('Write <<n>> cards. ', '') + """
You wrote the cards below. Each comes with its sandbox measurements (no model outcome) and the critiques of
anonymous critics, a skeptic and a leak auditor. Answer every card once:
- revise: return the full card in the same schema, corrected; it may stay unchanged if the critiques do not
  call for a change. A revised card is measured again.
- withdraw: drop the card, with a reason.
There is no vote; an unresolved critique stays on record as a kill_test.
<<cards>>

Answer with a JSON list only:
[{"card": "<<example>>", "action": "revise", "new": {"name": "...", "mechanism": "...", ...}},
 {"card": "...", "action": "withdraw", "reason": "..."}]
"""

TEMPLATES = dict(reference=REFERENCE, reference_fix=REFERENCE_FIX, generator=GENERATOR, critic=CRITIC,
                 skeptic=SKEPTIC, auditor=AUDITOR, author=AUTHOR)


# ---------------------------------------------------------------- rendering

def render(template, **subs):
    """The template with <<name>> placeholders filled; every placeholder and every substitution used."""
    names = set(re.findall(r'<<(\w+)>>', template))
    if names != set(subs):
        raise ValueError(f'placeholders {sorted(names)} vs substitutions {sorted(subs)}')
    return re.sub(r'<<(\w+)>>', lambda m: str(subs[m.group(1)]), template)


def hplus_schema():
    """Column names of H+r: the base columns of a days6 table and the f_x_ columns of its 34 tables.
    Only the schemas are read."""
    import duckdb
    from task1.model import EXTRA, base_features
    base = base_features(duckdb.read_parquet(str(min(roles.DAYS6.glob('*.parquet')))))
    tables = {}
    for name in roles.HPLUS:
        f = min((EXTRA / name).glob('[0-9]*.parquet'))
        tables[name] = [c for c in duckdb.read_parquet(str(f)).columns if c.startswith('f_x_')]
    return dict(base=base, tables=tables)


def _short(name):
    return name.removeprefix(TRIED_PREFIX)


def _mask(text):
    """Text of earlier agents: no word of a selection result, no name of NAMES."""
    text = re.sub(r'\baccepted\b', 'earlier', str(text), flags=re.I)
    return llm.NAMES.sub('<name>', text)


def tried():
    """Name and idea of every SQL v2 table of H+ (task1/runs/agent_night20/log.jsonl); nothing else of the log."""
    out = []
    for line in TRIED_LOG.read_text().splitlines():
        r = json.loads(line)
        if r.get('name') in roles.HPLUS and 'sql' in r:
            out.append(dict(name=_short(r['name']), idea=_mask(r.get('idea', ''))))
    return out


def features_text(schema):
    lines = ['  base:']
    for g in ('s_', 'u_', 'i_', 'uc_', 'ub_', 'up_', 'ui_', 'cf_'):
        cols = [c for c in schema['base'] if c.startswith(g)]
        if cols:
            lines.append(f"    {g}: {', '.join(cols)}")
    for name, cols in schema['tables'].items():
        lines.append(f"  {_short(name)}: {', '.join(cols)}")
    return '\n'.join(lines)


def tried_text(records):
    return '\n'.join(f"  {r['name']}: {' '.join(r['idea'].split())}" for r in records)


def context():
    """Substitutions shared by the prompts and their number sources."""
    schema, records = hplus_schema(), tried()
    return dict(features=features_text(schema), tried=tried_text(records)), [schema, records]


def _sources(*extra):
    return [CONSTANTS, LENSES, *extra]


def reference_prompt(k, ctx=None):
    subs, src = ctx or context()
    subs = dict(subs, prefix=f'f_x_rb{k}_', n=PROPOSALS)
    return render(REFERENCE, **subs), subs, _sources(*src)


def generator_prompt(lens, ctx=None):
    subs, src = ctx or context()
    subs = dict(subs, lens=lens, lens_text=LENSES[lens], prefix=f'f_x_c{lens[1]}_', n=CARDS_PER_LENS)
    return render(GENERATOR, **subs), subs, _sources(*src)


# ---------------------------------------------------------------- parsing

def slug(text, width=40):
    s = re.sub(r'_+', '_', re.sub(r'[^a-z0-9_]+', '_', str(text).lower())).strip('_')
    s = s if s[:1].isalpha() else 'f_' + s
    return s[:width].strip('_')


def _str(value, field):
    if isinstance(value, dict):
        value = '; '.join(f'{k}: {v}' for k, v in value.items())
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be non-empty text')
    return value.strip()


SIGNS = {'+': '+', 'plus': '+', 'positive': '+', '-': '-', '−': '-', 'minus': '-', 'negative': '-'}


def parse_card(item, cid, lens):
    """A card of the §3.4 schema with the id and lens given by the code; ValueError when unusable."""
    if not isinstance(item, dict):
        raise ValueError('a card must be an object')
    sign = SIGNS.get(str(item.get('sign', '')).strip().lower()[:8].split(' ')[0])
    if sign is None:
        raise ValueError(f"sign must be + or -, got {item.get('sign')!r}")
    twin = item.get('twin')
    if not isinstance(twin, dict):
        raise ValueError('twin must be an object with how and sql')
    how = str(twin.get('how', '')).strip().lower().replace('-', '_').replace(' ', '_')
    rival = item.get('rival')
    if isinstance(rival, str):
        rival = dict(explanation=rival, stratum='')
    if not isinstance(rival, dict):
        raise ValueError('rival must be an object with explanation and stratum')
    if not str(rival.get('stratum') or '').strip():
        raise ValueError('rival.stratum must be non-empty text')
    return dict(id=cid, lens=lens, name=slug(item.get('name') or cid),
                mechanism=_str(item.get('mechanism'), 'mechanism'), sign=sign,
                stratum=_str(item.get('stratum'), 'stratum'), null_stratum=_str(item.get('null_stratum'), 'null_stratum'),
                sql=_str(item.get('sql'), 'sql'),
                twin=dict(how=how, sql=_str(twin.get('sql'), 'twin.sql')),
                rival=dict(explanation=_str(rival.get('explanation'), 'rival.explanation'),
                           stratum=str(rival.get('stratum') or '').strip()))


def _items(value, key):
    if isinstance(value, dict):
        value = value.get(key) or next((v for v in value.values() if isinstance(v, list)), None)
    if not isinstance(value, list):
        raise ValueError('expected a JSON list')
    return value


def parse_cards(value, lens, n=CARDS_PER_LENS):
    """{'cards': [...], 'rejected': [...]}: ids G<l>-<position>; ValueError when no card is usable."""
    cards, rejected, used = [], [], set()
    for i, item in enumerate(_items(value, 'cards')[:n], 1):
        cid = f'{lens}-{i}'
        try:
            card = parse_card(item, cid, lens)
            clash = output_columns(card) & used
            if clash:
                raise ValueError(f'column names {sorted(clash)} repeat an earlier card')
        except ValueError as e:
            rejected.append(dict(id=cid, error=str(e)))
            continue
        cards.append(card)
        used |= output_columns(card)
    if not cards:
        raise ValueError(f'no usable card: {rejected[:3]}')
    return dict(cards=cards, rejected=rejected)


def output_columns(card):
    """The f_x_ names of a card's SQL (as council.evidence.validate_card reads them)."""
    return {t.lower() for t in re.findall(r'\bf_x_\w+', card['sql'], re.I)}


def table(card_id):
    """Table of a family: council_<card id>, e.g. council_g3_2."""
    return 'council_' + slug(card_id)


def parse_proposals(value, k, n=PROPOSALS, names=None):
    """Reference proposals [{name, idea, sql, table}]; with names, only those (a fix reply)."""
    out, seen = [], set()
    for item in _items(value, 'proposals'):
        if not isinstance(item, dict) or not isinstance(item.get('sql'), str) or not item['sql'].strip():
            continue
        name = slug(item.get('name') or f'p{len(out) + 1}', 30)
        if names is not None:
            if name not in names or name in seen:
                continue
        elif name in seen:
            name = f'{name}_{len(out) + 1}'
        seen.add(name)
        out.append(dict(name=name, idea=str(item.get('idea', '')).strip(), sql=item['sql'].strip(),
                        table=f'council_rb{k}_{name}'))
        if len(out) == n:
            break
    if not out:
        raise ValueError('no usable proposal')
    return out


def parse_critiques(value, aliases, critic):
    """Critiques {card, critic, type, text, kill_test} with the real card ids; ValueError when none is usable."""
    out = []
    for item in _items(value, 'critiques'):
        if not isinstance(item, dict):
            continue
        alias = str(item.get('card', '')).strip().upper()
        kind = str(item.get('type', '')).strip().upper().replace(' ', '_')
        if alias not in aliases or kind not in CRITIC_TYPES:
            continue
        out.append(dict(card=aliases[alias], critic=critic, type=kind, text=str(item.get('text', '')).strip(),
                        kill_test=str(item.get('kill_test', '')).strip()))
    if not out:
        raise ValueError('no usable critique')
    return out


def parse_replies(value, own):
    """Author answers {card, action, card_new | reason} for the author's own cards."""
    by_id = {c['id']: c for c in own}
    out, seen = [], set()
    for item in _items(value, 'replies'):
        if not isinstance(item, dict):
            continue
        cid = str(item.get('card', '')).strip().upper()
        action = str(item.get('action', '')).strip().lower()
        if cid not in by_id or cid in seen:
            continue
        if action == 'withdraw':
            out.append(dict(card=cid, action='withdraw', reason=str(item.get('reason', '')).strip()))
        elif action == 'revise':
            new = item.get('new') or item.get('card_new') or item.get('revised')
            try:
                out.append(dict(card=cid, action='revise', new=parse_card(new, cid, by_id[cid]['lens'])))
            except ValueError as e:
                out.append(dict(card=cid, action='unusable', reason=str(e)))
        else:
            continue
        seen.add(cid)
    if not out:
        raise ValueError('no usable answer')
    return out


# ---------------------------------------------------------------- files

def _load(name):
    p = roles.RUNS / name
    return json.loads(p.read_text()) if p.exists() else None


def _default(x):
    if hasattr(x, 'item'):
        return x.item()
    if hasattr(x, 'tolist'):
        return x.tolist()
    if isinstance(x, (set, frozenset, tuple)):
        return sorted(x, key=str)
    return str(x)


def _plain(x):
    return json.loads(json.dumps(x, default=_default))


def _save(name, obj):
    p = roles.RUNS / name
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f'.{p.name}.tmp')
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=_default) + '\n')
    tmp.replace(p)


def sha(text):
    return hashlib.sha256(text.strip().encode()).hexdigest()


def _evidence():
    from council import evidence
    return evidence


# ---------------------------------------------------------------- evidence views (what the prompts show)

PROBE_VIEW = ('check', 'nondeterministic', 'error', 'keys', 'level', 'columns', 'seconds_median', 'coverage',
              'batch_invariant', 'max_abs_rho', 'nearest', 'r2')


def _round(x):
    if isinstance(x, float):
        return float(f'{x:.3g}')
    if isinstance(x, dict):
        return {str(k): _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def probe_view(p):
    """A SQL probe of council.evidence as shown to the roles: the summary fields and the non-NULL share per
    day; no SQL, no per-day statistics, rounded to 3 significant digits."""
    if not isinstance(p, dict):
        return None
    out = {k: p[k] for k in PROBE_VIEW if p.get(k) is not None}
    parity = p.get('parity') or {}
    if parity.get('columns'):
        out['non_null_share_by_day'] = {c: v.get('shares') for c, v in parity['columns'].items()}
        out['parity_ok'] = parity.get('ok')
    return mask_days(_round(_plain(out)))


def mask_days(obj):
    """The probe days as probe_day_1..3 (the third is a day after the training anchors, which no prompt
    names)."""
    text = json.dumps(obj, ensure_ascii=False)
    for i, d in enumerate(roles.PROBE_DAYS, 1):
        text = text.replace(str(d)[:10], f'probe_day_{i}')
    return json.loads(text)


def evidence_view(entry):
    """The evidence of a card (council.evidence.probe of the card) as shown to the roles."""
    if not entry:
        return {'note': 'not measured'}
    tc = entry.get('twin_check') or {}
    return mask_days(dict(schema_problems=entry.get('problems') or [], card=probe_view(entry.get('card')),
                          twin=probe_view(entry.get('twin')),
                          twin_check=_round(_plain(dict(verdict=tc.get('verdict'), reasons=tc.get('reasons') or []))),
                          machine_red=entry.get('machine_red') or []))


def _hide(text):
    """Text of a card with its author hidden: no lens digit in columns or tables, no card id."""
    text = re.sub(r'f_x_c[1-4]_', 'f_x_c_', text)
    text = re.sub(r'council_g[1-4]_\d+', 'council_x', text)
    text = re.sub(r'\bG[1-4]-\d+\b', '<card>', text)
    return re.sub(r'\bG[1-4]\b', '<lens>', text)


def aliases_for(role, cards):
    """{alias: card id}: C01.. in an order given by a hash of role and id, so the lens is not the order."""
    ids = sorted((c['id'] for c in cards), key=lambda i: hashlib.sha256(f'{role}:{i}'.encode()).hexdigest())
    return {f'C{n:02d}': i for n, i in enumerate(ids, 1)}


def critic_assignment(cards):
    """{critic role: cards}: every card to the two generators of CRITICS[lens], the skeptic and the auditor."""
    out = {g: [] for g in LENSES} | {'skeptic': list(cards), 'auditor': list(cards)}
    for c in cards:
        for g in CRITICS[c['lens']]:
            out[g].append(c)
    return out


CARD_FIELDS = ('name', 'mechanism', 'sign', 'stratum', 'null_stratum', 'sql', 'twin', 'rival')


def cards_block(cards, aliases, evidence, fields=CARD_FIELDS, hide=True):
    """Cards for a prompt and the objects shown (the number sources)."""
    by_id = {c['id']: c for c in cards}
    parts, shown = [], []
    for alias, cid in aliases.items():
        c = by_id[cid]
        body = {k: c[k] for k in fields}
        ev = evidence_view(evidence.get(cid))
        text = json.dumps(body, ensure_ascii=False, indent=1)
        evt = json.dumps(ev, ensure_ascii=False)
        if hide:
            text, evt = _hide(text), _hide(evt)
        parts.append(f'--- {alias}\ncard: {text}\nmeasurements: {evt}')
        shown.append(dict(alias=alias, card=text, measurements=evt))
    return '\n'.join(parts), shown


def critic_prompt(role, cards, evidence, ctx=None):
    subs, src = ctx or context()
    aliases = aliases_for(role, cards)
    if role == 'auditor':
        block, shown = cards_block(cards, aliases, evidence, fields=('sql', 'twin'))
        subs = dict(prefix=HIDDEN_PREFIX, n=len(cards), cards=block)
        template = AUDITOR
    else:
        block, shown = cards_block(cards, aliases, evidence)
        if role == 'skeptic':
            subs = dict(subs, prefix=HIDDEN_PREFIX, n=len(cards), cards=block)
            template = SKEPTIC
        else:
            subs = dict(features=subs['features'], lens=role, lens_text=LENSES[role], prefix=HIDDEN_PREFIX,
                        n=len(cards), cards=block)
            template = CRITIC
    return render(template, **subs), subs, _sources(*src, shown, dict(cards_shown=len(cards))), aliases


def author_prompt(lens, cards, critiques, evidence, ctx=None):
    subs, src = ctx or context()
    parts, shown = [], []
    for c in cards:
        mine = [dict(type=q['type'], text=q['text'], kill_test=q['kill_test'],
                     by='skeptic' if q['critic'] == 'skeptic' else 'auditor' if q['critic'] == 'auditor' else 'critic')
                for q in critiques if q['card'] == c['id']]
        body = {k: c[k] for k in ('id',) + CARD_FIELDS}
        item = dict(card=body, measurements=evidence_view(evidence.get(c['id'])), critiques=mine)
        parts.append(f"--- {c['id']}\ncard: {json.dumps(body, ensure_ascii=False, indent=1)}\n"
                     f"measurements: {json.dumps(item['measurements'], ensure_ascii=False)}\n"
                     f"critiques: {json.dumps(mine, ensure_ascii=False, indent=1)}")
        shown.append(item)
    subs = dict(features=subs['features'], lens=lens, lens_text=LENSES[lens], prefix=f'f_x_c{lens[1]}_',
                cards='\n'.join(parts), example=cards[0]['id'])
    return render(AUTHOR, **subs), subs, _sources(*src, shown)


# ---------------------------------------------------------------- stages

def clean(card):
    """The card with exactly the fields of the §3.4 schema (council.evidence.validate_card)."""
    return {k: card[k] for k in ('id', 'lens') + CARD_FIELDS if k in card}


def probe_problems(probe, prefix):
    """Why a reference proposal failed the sandbox check (machine test, time, coverage, column names);
    [] when it passed. No outcome enters."""
    ev = _evidence()
    if not isinstance(probe, dict):
        return ['no probe']
    out = list(ev.machine_red(probe))
    if out:
        return out
    cols = probe.get('columns') or []
    bad = [c for c in cols if not c.startswith(prefix)]
    if bad:
        out.append(f'columns must start with {prefix}: {bad}')
    if not 1 <= len(cols) <= MAX_COLUMNS:
        out.append(f'{len(cols)} value columns, 1-{MAX_COLUMNS} allowed')
    sec = probe.get('seconds_median')
    if sec is None or sec > ev.MAX_SECONDS:
        out.append(f'median seconds per day {sec} above {ev.MAX_SECONDS:.0f}')
    cov = probe.get('coverage') or {}
    low = [c for c, v in cov.items() if v is None or v < ev.MIN_COVERAGE]
    if low:
        out.append(f'coverage below {ev.MIN_COVERAGE} for {low}')
    return out


def reference(k, threads=8, ctx=None):
    """Blind reference agent Rb<k>: one call for 12 proposals, sandbox probes, one fix call for the failed."""
    name = f'reference-rb{k}.json'
    state = _load(name) or dict(k=k)
    if state.get('done'):
        return state
    prefix = f'f_x_rb{k}_'
    if 'proposals' not in state:
        prompt, subs, sources = reference_prompt(k, ctx)
        props, meta = llm.ask(prompt, f'rb{k}', 'reference', subs=subs, sources=sources,
                              check=lambda v: parse_proposals(v, k))
        state.update(proposals=props, llm=[meta])
        _save(name, state)
    ev = _evidence()
    probes = state.setdefault('probes', {})

    def measure():
        for p in state['proposals']:
            h = sha(p['sql'])
            if probes.get(p['table'], {}).get('sql_sha256') != h:
                raw = _plain(ev.probe(p['sql'], roles.PROBE_DAYS, threads))
                probes[p['table']] = dict(sql_sha256=h, columns=raw.get('columns') or [], view=probe_view(raw),
                                          problems=mask_days(probe_problems(raw, prefix)))
                _save(name, state)

    def problems(p):
        """Stored check problems, plus column names that an earlier proposal of this run already has."""
        out = list(probes[p['table']]['problems'])
        earlier = set()
        for q in state['proposals']:
            if q is p:
                break
            if not probes[q['table']]['problems']:
                earlier |= set(probes[q['table']]['columns'])
        clash = sorted(set(probes[p['table']]['columns']) & earlier)
        if clash:
            out.append(f'column names {clash} repeat an earlier proposal')
        return out
    measure()
    if 'fix' not in state:
        failed = [p for p in state['proposals'] if problems(p)]
        state['fix'] = dict(asked=[p['name'] for p in failed])
        if failed:
            listing = [dict(name=p['name'], idea=p['idea'], sql=p['sql'], check=probes[p['table']]['view'],
                            problems=problems(p)) for p in failed]
            subs, src = ctx or context()
            subs = dict(features=subs['features'], prefix=prefix,
                        failed=json.dumps(listing, ensure_ascii=False, indent=1))
            names = {p['name'] for p in failed}
            fixed, meta = llm.ask(render(REFERENCE_FIX, **subs), f'rb{k}', 'reference-fix', subs=subs, free=('failed',),
                                  sources=_sources(*src, listing), check=lambda v: parse_proposals(v, k, names=names))
            by_name = {p['name']: p for p in fixed}
            for p in state['proposals']:
                if p['name'] in by_name:
                    p.update(first_sql=p['sql'], sql=by_name[p['name']]['sql'],
                             idea=by_name[p['name']]['idea'] or p['idea'])
            state['fix'].update(answered=sorted(by_name))
            state['llm'].append(meta)
        _save(name, state)
    measure()
    state['tables'] = [p['table'] for p in state['proposals'] if not problems(p)]
    state['widths'] = [[t, len(probes[t]['columns'])] for t in state['tables']]
    state['width'] = sum(w for _, w in state['widths'])
    state['done'] = True
    _save(name, state)
    return state


def wave1(ctx=None):
    """Blind wave: 8 cards per lens, one call per generator; cards-wave1.json {lens: {cards, rejected, llm}}."""
    state = _load('cards-wave1.json') or {}
    for lens in LENSES:
        if lens in state:
            continue
        prompt, subs, sources = generator_prompt(lens, ctx)
        got, meta = llm.ask(prompt, lens, 'wave1', subs=subs, sources=sources,
                            check=lambda v, lens=lens: parse_cards(v, lens))
        state[lens] = got | dict(llm=meta)
        _save('cards-wave1.json', state)
    return [c for lens in LENSES for c in state[lens]['cards']]


def evidence_stage(cards, threads=8):
    """council.evidence.probe of every card (its SQL, its twin, schema and twin check) plus machine_red;
    probes.json {card id: {sql_sha256, twin_sha256, evidence}}, a card version already measured is not
    probed again. Returns {card id: evidence} for the given cards."""
    ev = _evidence()
    store = _load('probes.json') or {}
    for c in cards:
        h, th = sha(c['sql']), sha(c['twin']['sql'])
        e = store.get(c['id'])
        if e and e['sql_sha256'] == h and e['twin_sha256'] == th:
            continue
        got = _plain(ev.probe(clean(c), roles.PROBE_DAYS, threads))
        got['machine_red'] = ev.machine_red(got['card']) if got.get('card') else ['no probe']
        store[c['id']] = dict(sql_sha256=h, twin_sha256=th, evidence=got)
        _save('probes.json', store)
    return card_evidence(cards, store)


def card_evidence(cards, store=None):
    """{card id: evidence} of the current version of every card from probes.json."""
    store = store if store is not None else (_load('probes.json') or {})
    out = {}
    for c in cards:
        e = store.get(c['id'])
        if e and e['sql_sha256'] == sha(c['sql']) and e['twin_sha256'] == sha(c['twin']['sql']):
            out[c['id']] = e['evidence']
    return out


CRITIC_ORDER = ('G1', 'G2', 'G3', 'G4', 'skeptic', 'auditor')


def cross_exam(cards, probes, ctx=None):
    """Two foreign-lens critics per card (one call per critic), the skeptic and the auditor (one call each);
    critiques.json {role: {aliases, critiques, llm}}. Returns the flat list of critiques."""
    state = _load('critiques.json') or {}
    assignment = critic_assignment(cards)
    for role in CRITIC_ORDER:
        if role in state or not assignment[role]:
            continue
        prompt, subs, sources, aliases = critic_prompt(role, assignment[role], probes, ctx)
        got, meta = llm.ask(prompt, role if role in ('skeptic', 'auditor') else f'critic-{role}', 'cross',
                            subs=subs, free=('cards',), sources=sources, check=lambda v, a=aliases, r=role: parse_critiques(v, a, r))
        state[role] = dict(aliases=aliases, critiques=got, llm=meta)
        _save('critiques.json', state)
    return [q for role in CRITIC_ORDER if role in state for q in state[role]['critiques']]


def author_replies(cards, critiques, probes, ctx=None):
    """One call per lens: revise or withdraw every own card. cards-final.json {replies, cards, withdrawn,
    revised, unanswered}. A card without a usable answer stays as it was."""
    state = _load('cards-final.json') or dict(replies={})
    for lens in LENSES:
        own = [c for c in cards if c['lens'] == lens]
        if lens in state['replies'] or not own:
            continue
        prompt, subs, sources = author_prompt(lens, own, critiques, probes, ctx)
        got, meta = llm.ask(prompt, lens, 'authors', subs=subs, sources=sources, free=('cards',),
                            check=lambda v, own=own: parse_replies(v, own))
        state['replies'][lens] = dict(answers=got, llm=meta)
        _save('cards-final.json', state)
    answers = {a['card']: a for lens in state['replies'] for a in state['replies'][lens]['answers']}
    final, withdrawn, revised, unanswered = [], [], [], []

    def taken(cid):
        """Output names of the other cards (their originals and revisions): a revision may not take them."""
        out = set()
        for o in cards:
            if o['id'] != cid:
                out |= output_columns(o)
                if answers.get(o['id'], {}).get('action') == 'revise':
                    out |= output_columns(answers[o['id']]['new'])
        return out
    for c in cards:
        a = answers.get(c['id'])
        if a and a['action'] == 'withdraw':
            withdrawn.append(dict(id=c['id'], reason=a['reason']))
        elif a and a['action'] == 'revise' and not output_columns(a['new']) & taken(c['id']):
            final.append(clean(a['new']))
            if sha(a['new']['sql']) != sha(c['sql']) or sha(a['new']['twin']['sql']) != sha(c['twin']['sql']):
                revised.append(c['id'])
        else:
            final.append(clean(c))
            unanswered.append(c['id'])
    state.update(cards=final, withdrawn=withdrawn, revised=revised, unanswered=unanswered)
    _save('cards-final.json', state)
    return final


def prereg1(cards, critiques):
    """prereg-1.json: SQL hashes, sign, strata, rival and kill tests of the final cards. Written once."""
    done = _load('prereg-1.json')
    if done:
        return done
    out = dict(cards=[dict(id=c['id'], lens=c['lens'], name=c['name'], table=table(c['id']),
                           sql_sha256=sha(c['sql']), twin_sha256=sha(c['twin']['sql']), twin_how=c['twin']['how'],
                           sign=c['sign'], stratum=c['stratum'], null_stratum=c['null_stratum'], rival=c['rival'],
                           kill_tests=[dict(critic=q['critic'], type=q['type'], kill_test=q['kill_test'])
                                       for q in critiques if q['card'] == c['id'] and q['type'] != 'OK'])
                      for c in cards],
               withdrawn=(_load('cards-final.json') or {}).get('withdrawn', []),
               code_sha256={f: sha((roles.ROOT / 'council' / f).read_text())
                            for f in ('agents.py', 'llm.py', 'evidence.py', 'design.py')})
    _save('prereg-1.json', out)
    return out


def reference_width():
    """The reference arm in its order for council.evidence.curate: [[table, columns], ...] of Rb1 by
    proposal, then Rb2 (cutting from the end removes Rb2 first)."""
    states = [_load(f'reference-rb{k}.json') for k in (1, 2)]
    if not all(s and s.get('done') for s in states):
        raise SystemExit('reference-rb1.json and reference-rb2.json must be done before the curator')
    return [list(x) for s in states for x in s['widths']]


def reference_probes(threads=8):
    """{table: council.evidence.probe(sql)} of every Rb proposal, Rb1 by proposal, then Rb2 (probes are
    cached by council.evidence, so this is cheap after the reference stage)."""
    ev = _evidence()
    out = {}
    for k in (1, 2):
        s = _load(f'reference-rb{k}.json')
        if not s or not s.get('done'):
            raise SystemExit(f'reference-rb{k}.json must be done before the curator')
        for p in s['proposals']:
            out[p['table']] = _plain(ev.probe(p['sql'], roles.PROBE_DAYS, threads))
    return out


def curator_stage(cards, probes, critiques, threads=8):
    """council.evidence.curate (code, no outcomes) on the final cards and the withdrawn ones (critique type
    WITHDRAWN) and on the probes of the Rb tables, which curate filters itself; curation.json (the output of
    curate plus reference_order, the Rb tables in the order given). Written once; a SystemExit of curate
    (parity not reached, no family, no reference width) writes nothing."""
    done = _load('curation.json')
    if done:
        return done
    ev = _evidence()
    final = _load('cards-final.json') or {}
    gone = {w['id'] for w in final.get('withdrawn', [])}
    wave = {c['id']: c for c in (_wave1_cards() if gone else [])}
    all_cards = [clean(c) for c in cards] + [clean(wave[i]) for i in sorted(gone) if i in wave]
    marks = [dict(card=i, critic='author', type='WITHDRAWN', text='', kill_test='') for i in sorted(gone)]
    evidence = dict(probes) | {i: e for i, e in card_evidence([wave[i] for i in gone if i in wave]).items()
                               if i not in probes}
    params = inspect.signature(ev.curate).parameters
    kw = dict(critiques=list(critiques) + marks)
    rp = None
    if 'reference_probes' in params:
        rp = reference_probes(threads)
        kw['reference_probes'] = rp
    elif 'reference_width' in params:  # an older curate without the Rb filter
        kw['reference_width'] = reference_width()
    out = _plain(ev.curate(all_cards, evidence, **kw))
    if rp is not None:
        out['reference_order'] = list(rp)
    _save('curation.json', out)
    return out


def _names(items):
    return [x if isinstance(x, str) else (x.get('table') or x.get('id') or x.get('name')) for x in items or []]


def reference_kept(curation):
    """Rb tables of the arm: the order given to curate without reference_removed and the parity cut; with a
    curate that did not filter Rb, the tables that passed the reference check."""
    drop = set((curation.get('parity') or {}).get('reference_drop') or [])
    if curation.get('reference_order') is not None:
        gone = drop | set(_names(curation.get('reference_removed')))
        return [t for t in curation['reference_order'] if t not in gone]
    return [t for k in (1, 2) for t in (_load(f'reference-rb{k}.json') or {}).get('tables', []) if t not in drop]


def compute_plan(curation, cards):
    """[(table name, sql)] of the families, the twins and the kept Rb tables, in that order."""
    by_id = {c['id']: c for c in cards}
    plan = [(table(i), by_id[i]['sql']) for i in curation['families']]
    plan += [(table(i) + '_tw', by_id[i]['twin']['sql']) for i in curation['twins']]
    sql = {p['table']: p['sql'] for k in (1, 2) for p in (_load(f'reference-rb{k}.json') or {}).get('proposals', [])}
    return plan + [(t, sql[t]) for t in reference_kept(curation)]


STRESS_DAY = date.fromisoformat(roles.SPANS['test'][1])  # the heaviest day: the longest history


def compute_stage(threads=8):
    """Tables of the families, twins and Rb on every day of train, val and test (task1.extra.compute, days6).

    First every table runs on the stress day; a failure (time limit, memory, error) is recorded in
    compute.json as failed_stress and stops the stage before any other table: rebuild the curation without
    it. Then the missing days of every table; days whose file exists are not computed again, after a check
    that the saved feature.sql is the SQL of the plan (otherwise stop)."""
    from task1 import extra
    curation = _load('curation.json')
    final = _load('cards-final.json')
    if not curation or not final or 'cards' not in final:
        raise SystemExit('curation.json and cards-final.json are needed')
    if not (curation.get('parity') or {}).get('ok'):
        raise SystemExit('curation.json: the width parity is not ok')
    plan = compute_plan(curation, final['cards'])
    cols = curation.get('columns') or {}
    names = [c for i in curation['families'] for c in cols.get(i, [])]
    names += [c + '_tw' for i in curation['twins'] for c in cols.get(i, [])]
    rb_cols = {t: e['columns'] for k in (1, 2) for t, e in ((_load(f'reference-rb{k}.json') or {}).get('probes')
                                                            or {}).items()}
    names += [c for t in reference_kept(curation) for c in rb_cols.get(t, [])]
    if len(names) != len(set(names)):
        raise SystemExit(f'column names repeat between tables: {sorted({n for n in names if names.count(n) > 1})}')
    days = [d for s in SPLITS for d in roles.days(s)]
    state = _load('compute.json') or {}

    def present(name, sql):
        d = Path(extra.EXTRA) / name
        f = d / 'feature.sql'
        if f.exists() and f.read_text().strip() != sql.strip():
            raise SystemExit(f'{f} is not the SQL of the plan: stop, the table belongs to another version')
        return {p.stem for p in d.glob('[0-9]*.parquet')}

    for name, sql in plan:
        e = state.get(name, {})
        if e.get('status') == 'failed_stress' and e.get('sql_sha256') == sha(sql):
            raise SystemExit(f"{name} failed the stress day ({e.get('error')}): rebuild the curation without it")
        if STRESS_DAY.isoformat() in present(name, sql):
            continue
        try:
            extra.compute(name, sql, days=[STRESS_DAY], threads=threads, days_dir=roles.DAYS6)
        except Exception as ex:
            state[name] = dict(sql_sha256=sha(sql), status='failed_stress', day=STRESS_DAY.isoformat(),
                               error=f'{type(ex).__name__}: {str(ex)[:500]}')
            _save('compute.json', state)
            raise SystemExit(f'{name} failed on the stress day {STRESS_DAY}: {state[name]["error"]}; '
                             'rebuild the curation without it') from None
        state[name] = dict(sql_sha256=sha(sql), status='stress_ok')
        _save('compute.json', state)
    for name, sql in plan:
        have = present(name, sql)
        missing = [d for d in days if d.isoformat() not in have]
        got = state.get(name, {}).get('columns')
        if missing:
            got = list(extra.compute(name, sql, days=missing, threads=threads, days_dir=roles.DAYS6))
        state[name] = dict(sql_sha256=sha(sql), status='done', columns=got, days=len(days),
                           computed=[d.isoformat() for d in missing])
        _save('compute.json', state)
    return state


# ---------------------------------------------------------------- CLI

def _wave1_cards():
    s = _load('cards-wave1.json')
    if not s or not all(lens in s for lens in LENSES):
        raise SystemExit('run wave1 first')
    return [c for lens in LENSES for c in s[lens]['cards']]


def _critiques():
    s = _load('critiques.json') or {}
    return [q for role in CRITIC_ORDER if role in s for q in s[role]['critiques']]


def _final_cards():
    s = _load('cards-final.json')
    if not s or 'cards' not in s:
        raise SystemExit('run authors first')
    return s['cards']


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('stage', choices=['reference', 'wave1', 'evidence', 'cross', 'authors', 'prereg1', 'curate',
                                      'compute', 'prompt'])
    ap.add_argument('--k', type=int, choices=[1, 2], help='reference run Rb<k>')
    ap.add_argument('--lens', default='G1', help='prompt: the generator whose prompt is printed')
    ap.add_argument('--threads', type=int, default=8)
    args = ap.parse_args(argv)
    if args.stage == 'reference':
        if not args.k:
            ap.error('reference needs --k 1 or --k 2')
        s = reference(args.k, args.threads)
        print(json.dumps(dict(tables=s['tables'], width=s['width'], fix=s['fix'])))
    elif args.stage == 'wave1':
        print(len(wave1()), 'cards')
    elif args.stage == 'evidence':
        print(len(evidence_stage(_wave1_cards(), args.threads)), 'cards measured')
    elif args.stage == 'cross':
        cards = _wave1_cards()
        print(len(cross_exam(cards, evidence_stage(cards, args.threads))), 'critiques')
    elif args.stage == 'authors':
        cards = _wave1_cards()
        final = author_replies(cards, _critiques(), evidence_stage(cards, args.threads))
        evidence_stage(final, args.threads)
        print(len(final), 'final cards')
    elif args.stage == 'prereg1':
        print(len(prereg1(_final_cards(), _critiques())['cards']), 'cards registered')
    elif args.stage == 'curate':
        final = _final_cards()
        print(json.dumps(curator_stage(final, evidence_stage(final, args.threads), _critiques()),
                         ensure_ascii=False)[:2000])
    elif args.stage == 'compute':
        print(json.dumps(compute_stage(args.threads), ensure_ascii=False)[:2000])
    elif args.stage == 'prompt':
        print(generator_prompt(args.lens)[0])


if __name__ == '__main__':
    main()
