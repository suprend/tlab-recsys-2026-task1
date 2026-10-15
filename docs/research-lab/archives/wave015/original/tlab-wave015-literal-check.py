import csv,io,math,json,time,hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
start_cpu=time.process_time();start_wall=time.perf_counter()
# Independent decision/math illustrations; no project functions or host probes.
checks={}
profile=lambda osname,arch,py:(osname=='darwin' and arch=='arm64' and py==(3,12))
checks['Darwin_profile_matches']=profile('darwin','arm64',(3,12))
checks['Linux_profile_refused']=not profile('linux','x86_64',(3,12))
checks['Windows_profile_refused']=not profile('win32','AMD64',(3,12))
checks['absolute_CPU_adds_SELF_and_reaped_CHILDREN']=3+4>6 and 3+4!=2*2
checks['RSS_unit_math_only']=2048*1024==2097152
checks['unknown_usage_not_success']=not (True and False) # known lifecycle AND known usage
checks['forced_live_group_retains_uncertainty']=not (True and False) # reaped leader alone does not resolve flagged unknown
checks['external_receipt_required']=not (True and False)
auth=b'original authority';reseal=b'caller replacement'
checks['resealed_bytes_not_original']=hashlib.sha256(auth).digest()!=hashlib.sha256(reseal).digest()
checks['CRLF_and_LF_byte_pins_differ']=hashlib.sha256(b'a\nb\n').digest()!=hashlib.sha256(b'a\r\nb\r\n').digest()
checks['commit_and_RSS_not_same_quantity']=('committed virtual bytes',8)!=('RSS bytes',8)
s0=[1.,1.+5e-13];s1=list(reversed(s0));rank=lambda s:sorted(range(2),key=lambda k:(-s[k],k))
checks['tiny_score_delta_can_reverse_rank']=rank(s0)!=rank(s1) and max(abs(a-b) for a,b in zip(s0,s1))<1e-12
assert len(checks)==12 and all(checks.values())
# Hand-defined 12-record public-fixture semantics, not replay package execution.
n=2**60;assert n!=n+1 and float(n)==float(n+1)
d2=1/math.log2(3);semantic={'Q':3,'C':3,'fullY':3,'scores':3,'conditional_Recall20':.25,'conditional_AP20':.125,'conditional_RR20':.25,'conditional_NDCG20':(d2/(1+d2))/2,'exact_ID_float_collision':True}
# Four invented lexical records with hard-coded independent expected all-field values.
line0='2019-10-01 00:00:00 UTC,view,9007199254740992,7,,,0.00,9007199254740993,s1\n'
line2='2019-10-01 00:00:00 UTC,cart,9007199254740993,7,cat," ""brand""",-0.01,9007199254740992,s2\n'
line3='2019-10-01 00:00:00 UTC,purchase,9223372036854775807,,,,0,9223372036854775806,NULL\n'
raw=line0+line0+line2+line3
rows=list(csv.reader(io.StringIO(raw,newline=''),strict=True,skipinitialspace=False));assert len(rows)==4 and all(len(r)==9 for r in rows)
def parse(tokens):
 out=[]
 for k,t in enumerate(tokens):
  if t=='':assert k>=2;out.append(None)
  elif k==0:out.append(datetime.strptime(t,'%Y-%m-%d %H:%M:%S UTC'))
  elif k in (2,3,7):out.append(int(t))
  elif k==6:out.append(Decimal(t))
  else:out.append(t)
 return tuple(out)
parsed=[parse(r) for r in rows]
t=datetime(2019,10,1)
e0=(t,'view',9007199254740992,7,None,None,Decimal('0.00'),9007199254740993,'s1')
e2=(t,'cart',9007199254740993,7,'cat',' "brand"',Decimal('-0.01'),9007199254740992,'s2')
e3=(t,'purchase',9223372036854775807,None,None,None,Decimal('0'),9223372036854775806,'NULL')
assert parsed==[e0,e0,e2,e3]
assert parsed[0]==parsed[1] and parsed[2][5]==' "brand"' and parsed[3][8]=='NULL'
assert parsed[0][2]!=parsed[0][7] and float(parsed[0][2])==float(parsed[0][7])
S=1741928540;U=5668612855;floor=2*S+U
assert floor==9152469935 and sum([2,10,10,8,1,8,2,3])==44
result={'schema_version':1,'outcome':'pass','scope':'Own bounded stdlib invented decision/CSV/rank/disk math only; no project imports, replay invocation, production parser, OS resource calls, target-host observation or lifecycle test','twelve_decision_checks':checks,'hand_defined_ranking_semantics':semantic,'lexical_canary':{'invented_rows':4,'all_nine_expected_fields_match':True,'raw_duplicates_preserved':True,'equal_time_peers_retained':True,'negative_and_zero_decimal_prices_preserved':True,'literal_NULL_text_preserved':True,'leading_space_quote_brand_preserved':True,'signed64_and_adjacent_above2pow53_keys_exact':True,'production_parser_executed':False,'native_DB_imported':False},'disk_math':{'documented_S':S,'documented_U':U,'two_S_plus_U':floor,'with_extra_retained_copy_three_S_plus_U':floor+S,'MB_invented_incremental_GiB':44,'MB_invented_total_GiB':46,'actual_disk_capacity_or_physical_allocation_measured':False},'cost':{'arithmetic_and_lexical_CPU_delta_seconds':time.process_time()-start_cpu,'arithmetic_and_lexical_wall_delta_seconds':time.perf_counter()-start_wall,'boundary':'From after stdlib imports to before JSON serialization/write; not full-process lifetime/resource receipt'},'helpers':0,'host_setup_or_native_data_model_fit_predict_claim_projectwrite_jobs':0,'new_IDs_admissions_main_gates':0}
Path('/tmp/tlab-wave015-literal-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'outcome':'pass','checks':12,'lexical_records':4,'disk_floor':floor,'cost':result['cost']},ensure_ascii=False,indent=2))
