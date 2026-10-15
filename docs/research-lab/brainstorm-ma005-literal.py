from collections import Counter
from pathlib import Path
import json
D=86400
# timestamp,user,item,category,action: invented rows only, including a raw duplicate.
events=[(0,1,1,10,'view'),(0,1,1,10,'view'),(D,1,2,20,'view'),(7*D,1,1,None,'cart'),(7*D,2,1,30,'purchase'),(8*D,2,1,40,'view'),(8*D,3,1,50,'view'),(8*D+2*3600,9,9,60,'view'),(9*D,4,1,60,'view'),(9*D,5,1,None,'view')]
anchors=[7*D,8*D,9*D,9*D+3600]
# Last all-action timestamp is resolved as one global peer block, never row order.
def metadata(rows,item):
    rr=[e for e in rows if e[2]==item]
    if not rr:return {'category':None,'ambiguous':False,'first':None,'last':None}
    last=max(e[0] for e in rr);peer=[e[3] for e in rr if e[0]==last];cats={x for x in peer if x is not None};hasnull=None in peer
    return {'category':next(iter(cats)) if len(cats)==1 and not hasnull else None,'ambiguous':len(cats)>1 or bool(cats) and hasnull,'first':min(e[0] for e in rr),'last':last}
def summarize(rows,t):
    past=[e for e in rows if e[0]<t]
    r={}
    for w in (24,168):
        v=[e for e in past if e[0]>=t-w*3600 and e[4]=='view' and e[2]==1]
        r['item_view_'+str(w)]=len(v);r['item_distinct_viewers_'+str(w)]=len({e[1] for e in v if e[1] is not None})
    uv=[e for e in past if e[0]>=t-168*3600 and e[4]=='view' and e[1]==1]
    r['user_view_168']=len(uv);r['user_distinct_items_168']=len({e[2] for e in uv if e[2] is not None})
    pair=[e[0] for e in past if e[1]==1 and e[2]==2 and e[4]=='view'];r['observed_pair_recency']=t-max(pair) if pair else None
    m=metadata(past,1);r['metadata']=m
    if m['category'] is None:r['item_category_count']=None;r['category_count']=None;r['share']=None
    else:
        cat=m['category'];support=[e for e in past if e[0]>=t-168*3600 and e[4]=='view' and e[3]==cat]
        num=sum(e[2]==1 for e in support);den=len(support);r['item_category_count']=num;r['category_count']=den;r['share']=[num,den] if den else None
    return r
bounds=sorted({0,*anchors,*[max(0,t-w*3600) for t in anchors for w in (24,168)]})
panes=[tuple(e for e in events if lo<=e[0]<hi) for lo,hi in zip(bounds,bounds[1:])]
# Range materialization here uses rows only to independently check exact boundary partition.
# A future engine replaces these by typed count/set/max/metadata merge states.
comparisons=[]
for t in anchors:
    direct=summarize(events,t)
    exact_prefix=[e for k,p in enumerate(panes) if bounds[k+1]<=t for e in p]
    tiled=summarize(exact_prefix,t)
    assert direct==tiled
    assert summarize(list(reversed(events)),t)==direct
    assert summarize(events+[(t+1,99,1,999,'view')],t)==direct
    comparisons.append({'anchor':t,'equal':True,'values':direct})
assert comparisons[0]['values']['metadata']['category']==10
assert comparisons[1]['values']['metadata']['category'] is None and comparisons[1]['values']['metadata']['ambiguous']
assert comparisons[2]['values']['metadata']['ambiguous']
# At the last anchor, latest timestamp contains category60 plus NULL: no row-order tie choice.
assert comparisons[3]['values']['metadata']['category'] is None and comparisons[3]['values']['metadata']['ambiguous']
# Remove one invented peer to form a legal resolved-metadata companion fixture.
resolved=[e for e in events if e!=(9*D,5,1,None,'view')]
r=summarize(resolved,9*D+3600);assert r['share']==[1,2]
# Raw duplicates and last/nonlast-copy expiry. Width2 in literal time units.
dups=[(0,'x'),(0,'x'),(1,'x')];expiry=[]
for t in (2,3,4):
    c=Counter(v for time,v in dups if t-2<=time<t);expiry.append({'t':t,'raw':sum(c.values()),'distinct':len(c)})
assert [(x['raw'],x['distinct']) for x in expiry]==[(3,1),(1,1),(0,0)]
# Count-distinct is neither sum of pane cardinalities nor invertible cumulative set difference.
a,b={1},{1};assert len(a|b)==1 and len(a)+len(b)==2 and (a|b)-a!=b
partial_checks=0
for t in anchors:
    for w in (24,168):
        selected=[p for k,p in enumerate(panes) if bounds[k]>=max(0,t-w*3600) and bounds[k+1]<=t]
        count=0;values=set()
        for pane in selected:
            vv=[e for e in pane if e[2]==1 and e[4]=='view']
            count+=len(vv);values|={e[1] for e in vv if e[1] is not None}
        expected=summarize(events,t)
        assert count==expected['item_view_'+str(w)]
        assert len(values)==expected['item_distinct_viewers_'+str(w)]
        partial_checks+=2
    latest=None;cats=set();hasnull=False;first=None
    for k,pane in enumerate(panes):
        if bounds[k+1]>t:continue
        rr=[e for e in pane if e[2]==1]
        if not rr:continue
        pt=max(e[0] for e in rr);pf=min(e[0] for e in rr)
        pc={e[3] for e in rr if e[0]==pt and e[3] is not None}
        pn=any(e[3] is None for e in rr if e[0]==pt)
        first=pf if first is None else min(first,pf)
        if latest is None or pt>latest:latest,cats,hasnull=pt,pc,pn
        elif pt==latest:cats|=pc;hasnull|=pn
    merged={'category':next(iter(cats)) if len(cats)==1 and not hasnull else None,'ambiguous':len(cats)>1 or bool(cats) and hasnull,'first':first,'last':latest}
    assert merged==metadata([e for e in events if e[0]<t],1)
    partial_checks+=1
# Dyadic range-cover operation accounting: include initial hierarchy construction.
def cover(lo,hi):
    q=[]
    while lo<hi:
        size=1
        while lo%(2*size)==0 and lo+2*size<=hi:size*=2
        q.append((lo,lo+size));lo+=size
    return q
ranges=[(1,8),(2,9),(3,10)];covers=[cover(*r) for r in ranges]
flat_ops=sum(hi-lo-1 for lo,hi in ranges);query_ops=sum(len(c)-1 for c in covers);build_ops=15
assert flat_ops==18 and query_ops==6 and build_ops+query_ops==21
# Sparse exact sets: same one interval, payload cardinality grows with values, not C/Q count.
set_sizes=[len(set(range(n))) for n in (1,16,256)];assert set_sizes==[1,16,256]
# Moment-state indistinguishability witness from independent helper.
x=(0,0,3,3);y=(0,1,1,4);assert (len(x),sum(x),sum(z*z for z in x))==(len(y),sum(y),sum(z*z for z in y)) and len(set(x))!=len(set(y))
result={'kind':'source-free standard-library literal; noSQL/repoimports/data','event_rows':len(events),'anchors':anchors,'atomic_interval_count':len(panes),'snapshot_comparisons':comparisons,'typed_partial_checks':partial_checks,'resolved_metadata_offC_denominator':r,'duplicate_expiry':expiry,'distinct_failures':{'sum_pane_cardinality':2,'exact_union':1,'cumulative_set_difference_loses_surviving_copy':True,'payload_cardinalities':set_sizes,'moments_equal_distinct_2_vs_3':True},'dyadic_build_cost_witness':{'equal_decoded_rows_each_plan':16,'ranges':ranges,'covers':covers,'flat_query_combines':flat_ops,'hierarchy_query_combines':query_ops,'hierarchy_build_combines':build_ops,'total_hierarchy_combines':build_ops+query_ops,'negative_vs_flat':True},'limits':'semantic and operation-count witnesses only; no timing/physicalIO/executableequivalence claim'}
p=Path('/tmp/tlab-wave005-models-a-literal.json');p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'literal':'pass','events':len(events),'anchors':len(anchors),'bounds':len(panes),'duplicate_expiry':expiry,'flat_ops':flat_ops,'hierarchy_total_ops':build_ops+query_ops,'offC_share':r['share']}))
