"""Independent source oracle; no producer imports or aggregate-minus-self mean."""
from collections import defaultdict
from datetime import timedelta
from math import isfinite,fsum,log1p
import importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location('list_oracle',Path(__file__).with_name('metadata_price.py'))
_o=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_o)

def extract_snapshot(con,source_start,anchor,candidate_products,check=lambda:None):
    """Independent MAX timestamp extraction preserves every tie; Python resolves fields."""
    check();rows=con.execute('''WITH last_seen AS (
      SELECT product_id,max(event_time) last_time FROM source.events
      WHERE event_time>=? AND event_time<? AND product_id IS NOT NULL GROUP BY product_id)
      SELECT e.product_id,e.event_time,e.category_id,e.category_code,e.brand,CAST(e.price AS DOUBLE)
      FROM source.events e JOIN last_seen d ON e.product_id=d.product_id AND e.event_time=d.last_time
      WHERE e.event_time>=? AND e.event_time<? ORDER BY e.product_id''',[source_start,anchor,source_start,anchor]).fetchall();check()
    buckets=defaultdict(list)
    for pos,(pid,stamp,cat,code,brand,price) in enumerate(rows):
        buckets[pid].append(dict(event_time=stamp,category_id=cat,category_code=code,brand=brand,price=price))
        if pos%10000==0:check()
    chosen=set(candidate_products);snapshots={};reference={};bycat=defaultdict(dict)
    for pos,pid in enumerate(buckets.keys()|chosen):
        bucket=buckets.get(pid,[]);last=bucket[0]['event_time'] if bucket else None
        active=last is not None and last>=anchor-timedelta(days=7)
        if active or pid in chosen:
            for row in bucket:
                if row['price'] is not None and not isfinite(float(row['price'])):
                    raise ValueError('Independent selected latest-bucket nonfinite source price')
        fields={name:_o._field(bucket,name) for name in ['category_id','category_code','brand','price']}
        state,price=fields['price'];z=log1p(float(price)) if state=='clean' and price>0 else None
        snapshots[pid]=dict(last=last,active=active,fields=fields,log_price=z)
        cstate,c=fields['category_id']
        if active and cstate=='clean' and z is not None:
            reference[pid]=(c,z);bycat[c][pid]=z
        if pos%10000==0:check()
    dictionary=defaultdict(set);first_known={}
    check()
    for cat,code,first in con.execute('''SELECT category_id,category_code,min(event_time)
        FROM source.events WHERE event_time>=? AND event_time<?
        AND category_id IS NOT NULL AND category_code IS NOT NULL
        GROUP BY category_id,category_code''',[source_start,anchor]).fetchall():
        dictionary[cat].add(code)
        first_known[cat]=min(first_known.get(cat,first),first)
    check()
    return dict(snapshots=snapshots,reference=reference,bycat=bycat,dictionary=dictionary,first_known=first_known,cache={})

def expected_product(snapshot,pid):
    if pid in snapshot['cache']:return snapshot['cache'][pid]
    s=snapshot['snapshots'][pid];fields=s['fields']
    cstate,cat=fields['category_id'];bstate,brand=fields['brand'];pstate,price=fields['price'];rawstate,rawcode=fields['category_code']
    codes=snapshot['dictionary'].get(cat,set()) if cstate=='clean' else set()
    code_state='missing' if not codes else 'clean' if len(codes)==1 else 'ambiguous';code=next(iter(codes)) if code_state=='clean' else None
    reference=snapshot['bycat'].get(cat,{}) if cstate=='clean' else {}
    # Direct list exclusion: intentionally no sum-minus-self expression.
    peers=[z for other,z in reference.items() if other!=pid]
    support=len(peers) if cstate=='clean' else None;mean=fsum(peers)/len(peers) if peers else None
    z=s['log_price'];difference=z-mean if z is not None and mean is not None else None
    model=dict(category_id_nominal=_o._encode(cat,cstate).decode(),category_code_by_id=_o._encode(code,code_state).decode(),brand=_o._encode(brand,bstate).decode(),
        brand_missing=bstate!='clean',brand_ambiguous=bstate=='ambiguous',code_missing=code_state=='missing',code_ambiguous=code_state=='ambiguous',
        code_recovered=code_state=='clean' and not(rawstate=='clean' and rawcode==code),log_price=z,
        price_missing=pstate!='clean',price_ambiguous=pstate=='ambiguous',price_zero=pstate=='clean' and price==0,price_negative=pstate=='clean' and price<0,
        category_peer_log_price_mean=mean,category_peer_product_support=support,category_log_price_difference=difference,
        category_peer_mean_missing=mean is None,category_price_difference_missing=difference is None)
    provenance=dict(latest_timestamp=s['last'],category_id=cat,category_ambiguous=cstate=='ambiguous',
        latest_code=rawcode,latest_code_ambiguous=rawstate=='ambiguous',latest_brand=brand,latest_brand_ambiguous=bstate=='ambiguous',
        latest_price=float(price) if price is not None else None,latest_price_ambiguous=pstate=='ambiguous',
        dictionary_code=code,dictionary_code_count=len(codes),dictionary_first_known=snapshot['first_known'].get(cat) if cstate=='clean' else None,
        in_reference=pid in reference)
    result=(model,provenance);snapshot['cache'][pid]=result;return result
