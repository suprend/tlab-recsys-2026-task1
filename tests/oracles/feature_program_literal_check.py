import importlib.util,json,resource,time
from datetime import datetime,timedelta
from pathlib import Path
import duckdb
s=importlib.util.spec_from_file_location('oracle',str(Path(__file__).resolve().with_name('feature_program_audit.py')));o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
start=datetime(2019,10,1);anchor=datetime(2019,10,9)
events=[(anchor-timedelta(hours=1),'view',10,1)]*2+[(anchor-timedelta(hours=24),'view',10,1),(anchor-timedelta(hours=24,seconds=1),'cart',10,1),(start,'cart',10,1),(anchor,'purchase',10,1),(anchor+timedelta(seconds=1),'cart',20,2),(anchor-timedelta(hours=1),'cart',20,2),(anchor-timedelta(hours=2),'purchase',20,2),(anchor-timedelta(hours=1),'cart',20,None),(anchor-timedelta(days=6),'cart',20,4),(anchor-timedelta(days=8),'cart',20,5)]
con=duckdb.connect();con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)');con.executemany('INSERT INTO events VALUES(?,?,?,?)',events)
checks=0
for a in [anchor,anchor+timedelta(days=1)]:
 con.execute('CREATE OR REPLACE TABLE audit_q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)');con.executemany('INSERT INTO audit_q VALUES(?,?,?)',[('a',1,a),('b',2,a),('empty',3,a)])
 con.execute('CREATE OR REPLACE TABLE audit_c(query_id VARCHAR,product_id BIGINT)');pairs=[('a',10,1),('a',20,1),('b',20,2)];con.executemany('INSERT INTO audit_c VALUES(?,?)',[(q,i) for q,i,u in pairs]);o.build_expected(con,start,a)
 rows=con.execute('SELECT * FROM audit_expected ORDER BY query_id,product_id').fetchall()
 for row,(q,item,user) in zip(rows,pairs):
  assert row[:2]==(q,item)
  observed=dict(zip([n for n,t in o.COLUMNS],row[2:]))
  expected={}
  for name,spec in o.expected_programs().items():
   lower=start if spec['window']=='observed' else max(start,a-timedelta(hours=spec['window']))
   matching=[e for e in events if lower<=e[0]<a and e[1]==spec['event_type'] and (e[3]==user if spec['grain']=='user' else e[2]==item if spec['grain']=='item' else e[3]==user and e[2]==item)]
   if spec['operator']=='count':value=len(matching)
   elif spec['operator']=='count_distinct':value=len({e[3] for e in matching if e[3] is not None})
   else:value=(a-max(e[0] for e in matching)).total_seconds() if matching else None
   expected[name]=value
  expected[o.RECENCY+'_missing']=expected[o.RECENCY] is None
  assert observed==expected,(q,item);checks+=12
 con.execute('CREATE OR REPLACE TABLE audit_actual AS SELECT * FROM audit_expected');o.compare_every_value(con)
 con.execute('UPDATE audit_actual SET auto_pair_view_count_24h=auto_pair_view_count_24h+1 WHERE query_id=\'a\' AND product_id=10')
 try:o.compare_every_value(con)
 except ValueError:checks+=1
 else:raise AssertionError('Legal wrong count survived independent formula check')
con.close();r=resource.getrusage(resource.RUSAGE_SELF);print(json.dumps(dict(status='passed',literal_scalar_checks=checks,source_rows=len(events),actual_data=False,fits=0,actual_cpu_seconds=r.ru_utime+r.ru_stime)))
