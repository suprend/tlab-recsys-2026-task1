"""Audit optional category names in bounded prefixes of official monthly files.

Run from the project root after EDA. Raw names are never replaced. Outputs are
provisional metadata candidates, not semantically verified training features.
"""

import argparse
import csv
import hashlib
import io
import json
import tempfile
import urllib.request
import zlib
from collections import defaultdict
from pathlib import Path

import duckdb

MONTHS = ('2019-Nov', '2019-Dec', '2020-Jan', '2020-Feb', '2020-Mar', '2020-Apr')
BASE = 'https://data.rees46.com/datasets/marketplace/'
LIMIT = 16 * 1024 * 1024


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for month in MONTHS:
        path = directory / f'{month}.prefix.gz.part'
        meta_path = directory / f'{month}.json'
        if path.exists() and meta_path.exists():
            continue
        if path.exists() or meta_path.exists():
            raise ValueError(f'Incomplete existing source pair: {month}')
        url = BASE + month + '.csv.gz'
        req = urllib.request.Request(url, headers={'Range': f'bytes=0-{LIMIT - 1}'})
        with urllib.request.urlopen(req, timeout=90) as response:
            if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes 0-{LIMIT - 1}/'):
                raise ValueError(f'Unexpected range response for {month}')
            headers = dict(response.headers.items())
            raw = response.read(LIMIT + 1)
        if len(raw) != LIMIT:
            raise ValueError(f'Unexpected prefix size for {month}')
        path.write_bytes(raw)
        meta_path.write_text(json.dumps(dict(month=month, url=url, headers=headers,
            compressed_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
            complete_file=False), indent=2) + '\n')
        print(f'{month}: downloaded {len(raw)} compressed bytes', flush=True)


def audit(db, directory, output):
    output.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db), read_only=True)
    con.execute("SET memory_limit='3GB'")
    con.execute('SET threads=4')
    categories = {cid: dict(raw_code=code, event_count=n) for cid, code, n in con.execute(
        'SELECT category_id, min(category_code), count(*) FROM events GROUP BY category_id').fetchall()}
    if con.execute('SELECT count(*) FROM (SELECT category_id FROM events GROUP BY category_id HAVING count(DISTINCT category_code)>1)').fetchone()[0]:
        raise ValueError('Conflicting category codes in original month')
    if con.execute('SELECT count(*) FROM (SELECT product_id FROM events GROUP BY product_id HAVING count(DISTINCT category_id)>1)').fetchone()[0]:
        raise ValueError('Product-to-category mapping is not unique in original month')
    con.execute('CREATE TEMP TABLE oct_products AS SELECT product_id, min(category_id) AS category_id, min(brand) AS brand FROM events GROUP BY product_id')
    candidates = defaultdict(lambda: defaultdict(dict))
    sources = []
    for month in MONTHS:
        path = directory / f'{month}.prefix.gz.part'
        meta = json.loads((directory / f'{month}.json').read_text())
        raw = path.read_bytes()
        if (meta.get('month') != month or meta.get('url') != BASE + month + '.csv.gz'
                or meta.get('compressed_bytes') != len(raw) or len(raw) != LIMIT
                or meta.get('complete_file') is not False):
            raise ValueError(f'Unexpected cached source metadata: {month}')
        if hashlib.sha256(raw).hexdigest() != meta['sha256']:
            raise ValueError(f'Prefix checksum mismatch: {month}')
        # An incomplete gzip stream has no verified end-of-stream CRC. Discard
        # its partial final CSV row; never describe this as a complete month.
        decoded_bytes = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
        decoded = decoded_bytes[:decoded_bytes.rfind(b'\n') + 1].decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        count = 0
        first = last = None
        month_codes = defaultdict(set)
        for row in reader:
            count += 1
            first = first or row['event_time']
            last = row['event_time']
            cid, code = int(row['category_id']), row['category_code']
            if code:
                month_codes[cid].add(code)
                observations = candidates[cid][code]
                observations[month] = min(observations.get(month, row['event_time']), row['event_time'])
        known_overlap = {cid for cid in month_codes if cid in categories and categories[cid]['raw_code']}
        changed = {cid for cid in known_overlap if month_codes[cid] != {categories[cid]['raw_code']}}
        with tempfile.TemporaryDirectory() as temp:
            csv_path = Path(temp) / 'prefix.csv'
            csv_path.write_text(decoded)
            con.execute("CREATE OR REPLACE TEMP TABLE later AS SELECT DISTINCT product_id,category_id,brand FROM read_csv(?,header=true,columns={event_time:VARCHAR,event_type:VARCHAR,product_id:BIGINT,category_id:BIGINT,category_code:VARCHAR,brand:VARCHAR,price:VARCHAR,user_id:VARCHAR,user_session:VARCHAR})", [str(csv_path)])
        overlap, same_id = con.execute('SELECT count(*),count(*) FILTER(WHERE l.category_id=o.category_id) FROM later l JOIN oct_products o USING(product_id)').fetchone()
        sources.append(dict(month=month, url=meta['url'], sha256=meta['sha256'],
            compressed_bytes=len(raw), complete_file=False, row_count=count,
            first_event_time=first, last_event_time=last,
            known_oct_ids_with_code=len(known_overlap), known_oct_ids_with_changed_code=len(changed),
            distinct_product_category_brand_tuples_overlapping_october=overlap,
            overlapping_tuples_with_same_category_id=same_id))
    records = []
    for cid, original in sorted(categories.items()):
        later = candidates[cid]
        all_codes = set(later) | ({original['raw_code']} if original['raw_code'] else set())
        code = next(iter(all_codes)) if len(all_codes) == 1 else None
        status = 'conflict' if len(all_codes)>1 else ('original' if original['raw_code'] else ('candidate_only' if code else 'unknown'))
        records.append(dict(category_id=str(cid), category_code_raw=original['raw_code'],
            category_code_candidate=code if status=='candidate_only' else None,
            status=status, october_event_count=original['event_count'],
            later_observations=later,
            first_later_observed_time=min((t for observations in later.values() for t in observations.values()), default=None),
            semantic_validation='not_performed', usable_in_october_by_observation=False if status=='candidate_only' else None))
    (output/'category_name_candidates.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
    missing = [r for r in records if r['category_code_raw'] is None]
    found = [r for r in missing if r['status']=='candidate_only']
    summary = dict(sources=sources, october_category_ids=len(records), october_missing_ids=len(missing),
        october_missing_events=sum(r['october_event_count'] for r in missing),
        candidate_ids=len(found), candidate_october_events=sum(r['october_event_count'] for r in found),
        conflicting_ids=sum(r['status']=='conflict' for r in records),
        policy='No replacement of raw codes; candidate status is not semantic validation or proof of October availability.')
    (output/'category_recovery_audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    con.close()
    print(json.dumps({k:v for k,v in summary.items() if k!='sources'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('data/processed/october.duckdb'))
    parser.add_argument('--prefix-dir', type=Path, default=Path('data/external/category-probes'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/category-recovery'))
    parser.add_argument('--download', action='store_true', help='Fetch six 16 MiB prefixes (96 MiB total); never complete archives')
    args = parser.parse_args()
    if args.download:
        fetch(args.prefix_dir)
    audit(args.db, args.prefix_dir, args.output)
