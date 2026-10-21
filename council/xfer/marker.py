"""The journal of reads council/runs/xfer-<x>/reads.jsonl and its test.started marker, without labels
(council/runs/xfer/contract.md §10.4). The broker writes the journal; fit.py reads the marker from here so that it
never imports the broker. Nothing here touches a collection or an xfer artefact.

  reads(ds)   the records of Dataset.paths.reads; a broken last line (a process killed while appending) is
              skipped with a warning on stderr, a broken line before it is an error (§8.12, §10.9).
  marker(ds)  the last record with what == MARKER, or None.
  append(path, rec)  one JSON line appended to a journal (reads.jsonl, fits/runs.jsonl); check_tail(path) and
              append give SystemExit if the file ends in a broken line: a record is never glued to it, the broken
              tail is moved aside by hand.
"""
from __future__ import annotations

import json
import sys

from council.xfer import roles

MARKER = 'test.started'


def reads(ds: roles.Dataset) -> list[dict]:
    path = ds.paths.reads
    if not path.exists():
        return []
    lines = [x for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    out = []
    for i, line in enumerate(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            if i != len(lines) - 1:
                raise ValueError(f'{path}: line {i + 1} is broken') from None
            print(f'warning: {path}: the last line is broken and skipped', file=sys.stderr)
    return out


def marker(ds: roles.Dataset) -> dict | None:
    found = [r for r in reads(ds) if r.get('what') == MARKER]
    return found[-1] if found else None


def check_tail(path) -> None:
    """SystemExit if the journal at `path` ends in a broken line (or without a newline)."""
    if not path.exists():
        return
    text = path.read_text(encoding='utf-8')
    lines = [x for x in text.splitlines() if x.strip()]
    try:
        if lines:
            json.loads(lines[-1])
        ok = not text or text.endswith('\n')
    except ValueError:
        ok = False
    if not ok:
        raise SystemExit(f'{path} ends in a broken line; move that line aside by hand before writing again')


def append(path, rec: dict) -> None:
    check_tail(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
