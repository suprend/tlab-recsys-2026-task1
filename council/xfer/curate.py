"""The curator code of the council on xfer: a port of council.evidence.curate with the dataset rules injected
(council/runs/xfer/contract.md §3.4, §7.2, golden test 2 of §3).

Same steps and output as evidence.curate (machine red, duplicates with H+r, duplicates between cards, lens
quotas, width parity with _widths/cut_reference, the Rb filter, twins, placebo); what REES46 hard-codes is a
parameter here:

  validate      card -> [problems]           REES46: evidence.validate_card; xfer: sandbox.validate_card(ds, .)
  max_seconds   float | {level: seconds}      REES46: evidence.MAX_SECONDS (60); xfer: xa.limits(x)['timeouts']
  cross_fn      (probe, probe) -> dict|None   REES46: evidence.cross; xfer: sandbox.cross(ds, ., .)
  twin_check_fn (probe, probe) -> dict        REES46: evidence.twin_check; xfer: sandbox.twin_check(ds, ., .)

The thresholds MIN_COVERAGE, R2_DUP, RHO_DUP, PER_LENS, MAX_FAMILIES, TWINS, PLACEBO, PARITY_TOL and LENSES come
from council.evidence unchanged, and so do the texts of the reasons (the golden test compares bytes; 'H+' and
'days' there mean H+r and the probe anchors). Pure: no file is read or written by curate(); stage() does the I/O.
With the REES46 injections, curate() on council/runs/rees46-2020 cards and probes.json gives curation.json byte
for byte (golden test 2, council/tests/test_xfer_curate.py).
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterable, Mapping

import numpy as np

from council import evidence as ev
from council.xfer import roles

Validate = Callable[[dict], list]
Cross = Callable[[dict, dict], 'dict | None']
TwinCheck = Callable[[dict, dict], dict]

CRITIC_ORDER = ('G1', 'G2', 'G3', 'G4', 'skeptic', 'auditor')     # council.agents.CRITIC_ORDER


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _order(card_id):
    m = roles.CARD_ID.fullmatch(str(card_id))
    return (int(m.group(1)), int(m.group(2))) if m else (9, 10 ** 9)


def _widths(reference_width):
    if reference_width is None:
        return [], 0
    if isinstance(reference_width, (int, np.integer)):
        return None, int(reference_width)
    items = [(str(t), int(w)) for t, w in (reference_width.items() if isinstance(reference_width, dict)
                                           else reference_width)]
    return items, sum(w for _, w in items)


def seconds_limit(p: dict, max_seconds: float | Mapping[str, float]) -> float | None:
    """The time limit of one SQL probe: max_seconds itself, or max_seconds[p['level']] (None: no limit known for
    that level, which step1 reports)."""
    if isinstance(max_seconds, Mapping):
        v = max_seconds.get(p.get('level'))
        return None if v is None else float(v)
    return max_seconds


def step1(p: dict, max_seconds: float | Mapping[str, float]) -> str | None:
    """Reason step 1 removes a SQL probe (evidence.machine_red, median seconds over the limit, coverage below
    evidence.MIN_COVERAGE, parity across probe anchors broken), or None."""
    red = ev.machine_red(p)
    if red:
        return 'machine test red: ' + red[0]
    limit = seconds_limit(p, max_seconds)
    if limit is None:
        return f'no time limit for level {p.get("level")!r}'
    if p.get('seconds_median') is None or p['seconds_median'] > limit:
        return f'median seconds {p.get("seconds_median")} > {limit:.0f}'
    if not p.get('coverage') or min(p['coverage'].values()) < ev.MIN_COVERAGE:
        return f'coverage {min((p.get("coverage") or {None: 0.0}).values()):.4%} < {ev.MIN_COVERAGE:.1%}'
    if not p['parity']['ok']:
        bad = {c: v['outside'] for c, v in p['parity']['columns'].items() if v['outside']}
        return f'non-NULL parity across days broken: {bad}'
    return None


def _dup_hplus(p):
    """Reason step 2 removes a SQL probe as a duplicate of H+r (R2_wq >= 0.9 or max|rho_wq| >= 0.95), or None."""
    for c in p['columns']:
        if (p['r2'][c] is not None and p['r2'][c] >= ev.R2_DUP) or (
                p['max_abs_rho'][c] is not None and p['max_abs_rho'][c] >= ev.RHO_DUP):
            return f'duplicate of H+: {c} R2_wq {p["r2"][c]}, max|rho_wq| {p["max_abs_rho"][c]} ({p["nearest"][c]})'
    return None


def _dup_cross(cr):
    """(max|rho|, max R2) when two probes duplicate each other, else None."""
    if cr is None:
        return None
    r2 = max([v for v in list(cr['r2_a_on_b'].values()) + list(cr['r2_b_on_a'].values()) if v is not None],
             default=None)
    if (cr['max_abs_rho'] is not None and cr['max_abs_rho'] >= ev.RHO_DUP) or (r2 is not None and r2 >= ev.R2_DUP):
        return cr['max_abs_rho'], r2
    return None


def _filter_reference(reference_probes, cross_fn, max_seconds):
    """Steps 1 and 2 for the reference arm. The order is kept; inside Rb1 u Rb2 the earlier table stays."""
    removed, kept = [], []
    for table, p in reference_probes.items():
        why = step1(p, max_seconds)
        step = 1
        if why is None:
            why, step = _dup_hplus(p), 2
        if why is None:
            for other in kept:
                dup = _dup_cross(cross_fn(p, reference_probes[other]))
                if dup:
                    why = f'duplicate of {other}: max|rho_wq| {dup[0]}, R2_wq {dup[1]}'
                    break
        if why:
            removed.append(dict(table=table, step=step, reason=why))
        else:
            kept.append(table)
    return [(t, len(reference_probes[t]['columns'])) for t in kept], removed


def curate(cards: list[dict], probes: dict, reference_width=None, critiques: Iterable[dict] = (),
           cross_fn: Cross | None = None, reference_probes: dict | None = None, *, validate: Validate,
           max_seconds: float | Mapping[str, float], twin_check_fn: TwinCheck | None = None) -> dict:
    """evidence.curate with the injected rules; arguments and return value as there:
    {families, columns, width, twins, twin_checks, placebo, placebo_families, removed, parity,
     reference_removed, reference, warnings, critiques}. cross_fn and twin_check_fn are required in practice on
    xfer (the defaults are the REES46 ones, kept only for the golden test). SystemExit as evidence.curate."""
    cross_fn = cross_fn or ev.cross
    twin_check_fn = twin_check_fn or ev.twin_check
    warnings = []
    if reference_probes is not None:
        if reference_width is not None:
            warnings.append('reference_width ignored: the widths come from reference_probes')
        items, reference_removed = _filter_reference(reference_probes, cross_fn, max_seconds)
    else:
        warnings.append('reference arm not filtered: no reference_probes (steps 1 and 2 not applied to Rb)')
        items, reference_removed = _widths(reference_width)[0], []
    w_r = _widths(reference_width)[1] if items is None else sum(w for _, w in items)
    if w_r <= 0:
        raise SystemExit(f'curate: the reference width is 0 after the filter ({reference_removed})')

    removed = []
    by_id = {}
    for card in sorted(cards, key=lambda c: _order(c.get('id'))):
        by_id[card.get('id')] = card
    withdrawn = {c.get('card') for c in critiques if str(c.get('type', '')).upper() == 'WITHDRAWN'}
    alive = []
    for cid, card in by_id.items():
        pr = probes.get(cid)
        why = None
        if pr is None or pr.get('card') is None:
            why = 'no probe'
        elif validate(card) or pr.get('problems'):
            why = 'invalid: ' + '; '.join((validate(card) + list(pr.get('problems') or []))[:3])
        else:
            why = step1(pr['card'], max_seconds)
        if why is None and cid in withdrawn:
            why = 'withdrawn by the author'
        if why:
            removed.append(dict(id=cid, step=1, reason=why))
        else:
            alive.append(cid)

    # 2. duplicates: to H+r ...
    kept = []
    for cid in alive:
        why = _dup_hplus(probes[cid]['card'])
        if why:
            removed.append(dict(id=cid, step=2, reason=why))
        else:
            kept.append(cid)
    # ... and inside the council
    pref = sorted(kept, key=lambda c: (len(probes[c]['card']['columns']),) + _order(c))
    survivors = []
    for cid in pref:
        dup = None
        for other in survivors:
            d = _dup_cross(cross_fn(probes[cid]['card'], probes[other]['card']))
            if d:
                dup = (other,) + d
                break
        if dup:
            removed.append(dict(id=cid, step=2, reason=f'duplicate of {dup[0]}: max|rho_wq| {dup[1]}, R2_wq {dup[2]}'))
        else:
            survivors.append(cid)

    # 3. quotas: round robin over lenses, by card number
    lenses = ev.LENSES
    queues = {lens: sorted([c for c in survivors if by_id[c]['lens'] == lens], key=_order) for lens in lenses}
    families, taken = [], {lens: 0 for lens in lenses}
    while len(families) < ev.MAX_FAMILIES and any(queues[lens] and taken[lens] < ev.PER_LENS for lens in lenses):
        for lens in lenses:
            if len(families) < ev.MAX_FAMILIES and queues[lens] and taken[lens] < ev.PER_LENS:
                families.append(queues[lens].pop(0))
                taken[lens] += 1
    for lens in lenses:
        for cid in queues[lens]:
            removed.append(dict(id=cid, step=3, reason=f'quota: {ev.PER_LENS} per lens, {ev.MAX_FAMILIES} in all'))

    if not families:
        raise SystemExit(f'curate: no family survives steps 1-3 ({len(removed)} cards removed)')

    # 6. width parity (contract §2), before twins and placebo so that both come from the final families
    width = {c: len(probes[c]['card']['columns']) for c in families}
    w_c = sum(width.values())
    par = dict(w_council=w_c, w_reference=w_r, cut=[], council_removed=[], reference_drop=[])
    rest = None if items is None else list(items)

    def within():
        return abs(w_c - w_r) <= ev.PARITY_TOL * w_r

    def cut_council():
        nonlocal w_c
        par['cut'].append('council')
        while families and w_c - w_r > ev.PARITY_TOL * w_r:
            cid = families.pop()
            w_c -= width[cid]
            par['council_removed'].append(cid)
            removed.append(dict(id=cid, step=6, reason='width parity with the reference arm'))

    def cut_reference():
        nonlocal w_r
        if rest is None:
            raise SystemExit(f'curate: the reference arm must lose {w_r - w_c} columns, but only its width is known')
        par['cut'].append('reference')
        while rest and w_r - w_c > ev.PARITY_TOL * w_r:
            t, w = rest.pop()
            w_r -= w
            par['reference_drop'].append(t)

    for _ in range(2):           # the larger side first; if the cut overshoots, the other side once
        if within():
            break
        cut_council() if w_c > w_r else cut_reference()
    par['w_council_after'], par['w_reference_after'] = w_c, w_r
    par['ok'] = within() and w_r > 0
    if not par['ok']:
        raise SystemExit(f'curate: width parity not reached: council {w_c}, reference {w_r}, cuts {par["cut"]}')
    if not families:
        raise SystemExit('curate: no family left after the width parity')

    # 4. twins: one per lens, the first family of the lens with a working twin; else the next lens round
    checks = {}
    for c in families:
        tc = probes[c].get('twin_check')
        if tc is None and probes[c].get('twin') is not None:
            tc = twin_check_fn(probes[c]['card'], probes[c]['twin'])
        checks[c] = tc or dict(verdict='TWIN-BROKEN', reasons=['no twin probe'])
    twins = []
    for i, lens in enumerate(lenses):
        if len(twins) >= ev.TWINS:
            break
        for k in range(len(lenses)):
            lens_k = lenses[(i + k) % len(lenses)]
            pick = next((c for c in families if by_id[c]['lens'] == lens_k and c not in twins
                         and checks[c]['verdict'] == 'ok'), None)
            if pick:
                twins.append(pick)
                break

    # 5. placebo: the first columns of the first 4 families in sha256(name) order
    by_hash = sorted(families, key=lambda c: (_sha(by_id[c]['name']), c))[:ev.PLACEBO]
    placebo = [probes[c]['card']['columns'][0] for c in by_hash]

    return dict(families=families, columns={c: probes[c]['card']['columns'] for c in families},
                width=sum(width[c] for c in families), twins=twins,
                twin_checks={c: checks[c]['verdict'] for c in families}, placebo=placebo,
                placebo_families=by_hash, removed=removed, parity=par, reference_removed=reference_removed,
                reference=[t for t, _ in (rest or [])] if rest is not None else None, warnings=warnings,
                critiques={c: sorted({str(x.get('type')) for x in critiques if x.get('card') == c}) for c in families})


# ---------------------------------------------------------------- the stage (I/O)

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


def _load(ds: roles.Dataset, name: str):
    p = ds.paths.run_file(name)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def _save(ds: roles.Dataset, name: str, obj) -> None:
    """council.agents._save: indent 1, no ASCII escaping, a final newline, atomic."""
    p = ds.paths.run_file(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f'.{p.name}.tmp')
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=_default) + '\n', encoding='utf-8')
    tmp.replace(p)


def flat_critiques(state) -> list[dict]:
    """critiques.json {role: {critiques: [...]}} in council.agents.CRITIC_ORDER (other roles after, by name), or a
    plain list."""
    if not state:
        return []
    if isinstance(state, list):
        return list(state)
    roles_ = [r for r in CRITIC_ORDER if r in state] + sorted(r for r in state if r not in CRITIC_ORDER)
    return [q for r in roles_ for q in (state[r] or {}).get('critiques', [])]


def _same_version(probe: dict | None, card: dict) -> bool:
    """The card probe was made on this version of the card (its sandbox SQL, twin SQL and level)."""
    from council.xfer import sandbox
    if not probe or not isinstance(probe.get('card'), dict):
        return bool(probe) and probe.get('card') is None and probe.get('id') == card.get('id')
    try:
        sql, twin = sandbox.to_sandbox(card['sql']), sandbox.to_sandbox(card['twin']['sql'])
    except (KeyError, TypeError, ValueError):
        return False
    tw = probe.get('twin') or {}
    return (probe['card'].get('sql') == sql and probe['card'].get('level') == card.get('level')
            and tw.get('sql') == twin)


def stage(ds: roles.Dataset) -> dict:
    """The curate stage: reads council/runs/xfer-<x>/cards-final.json, probes.json, critiques.json and the Rb
    tables of reference-rb1.json / reference-rb2.json; calls curate() with sandbox.validate_card,
    xa.limits(ds.name)['timeouts'], sandbox.cross and sandbox.twin_check bound to ds; writes and returns
    council/runs/xfer-<x>/curation.json (plus `reference_order`, the Rb table order given to curate).

    As council.agents.curator_stage: written once (an existing curation.json is returned); the cards withdrawn by
    their authors (cards-final.json `withdrawn`) enter in their wave1 version with a WITHDRAWN critique; a card
    probe of another version of the card counts as no probe; an Rb proposal whose column names differ from the
    output of its probe stops the stage (their order may differ: compute.py takes the probe's); a SystemExit of
    curate writes nothing."""
    from council.xfer import sandbox
    from scripts import xfer_agent as xa
    done = _load(ds, 'curation.json')
    if done:
        return done
    final = _load(ds, 'cards-final.json')
    if not final or 'cards' not in final:
        raise SystemExit('cards-final.json is needed: run authors first')
    store = _load(ds, 'probes.json') or {}
    card_probes, ref_store = store.get('cards') or {}, store.get('reference') or {}
    clean = [{k: c[k] for k in sandbox.CARD_FIELDS if k in c} for c in final['cards']]
    gone = sorted({w['id'] for w in final.get('withdrawn') or []})
    wave = {c['id']: c for c in ((_load(ds, 'cards-wave1.json') or {}).get('cards') or [])} if gone else {}
    clean += [{k: wave[i][k] for k in sandbox.CARD_FIELDS if k in wave[i]} for i in gone if i in wave]
    evidence = {c['id']: card_probes[c['id']] for c in clean
                if c['id'] in card_probes and _same_version(card_probes[c['id']], c)}
    marks = [dict(card=i, critic='author', type='WITHDRAWN', text='', kill_test='') for i in gone]
    critiques = flat_critiques(_load(ds, 'critiques.json')) + marks

    reference_probes = {}
    for k in (1, 2):
        s = _load(ds, f'reference-rb{k}.json')
        if not s or not s.get('proposals'):
            raise SystemExit(f'reference-rb{k}.json with proposals is needed before the curator')
        for p in s['proposals']:
            got = ref_store.get(p['table'])
            if not got or got.get('sql') != p['sql'] or got.get('level') != p['level']:
                raise SystemExit(f'Rb table {p["table"]}: no probe of its SQL in probes.json: run evidence first')
            if got.get('columns') is not None and sorted(got['columns']) != sorted(p.get('columns') or []):
                raise SystemExit(f'Rb table {p["table"]}: columns {p.get("columns")} of reference-rb{k}.json are not '
                                 f'the output columns {got["columns"]} of its probe')
            reference_probes[p['table']] = got

    out = _plain(curate(clean, evidence, critiques=critiques, reference_probes=reference_probes,
                        validate=lambda c: sandbox.validate_card(ds, c),
                        max_seconds=xa.limits(ds.name)['timeouts'],
                        cross_fn=lambda a, b: sandbox.cross(ds, a, b),
                        twin_check_fn=lambda a, b: sandbox.twin_check(ds, a, b)))
    out['reference_order'] = list(reference_probes)
    _save(ds, 'curation.json', out)
    return out
