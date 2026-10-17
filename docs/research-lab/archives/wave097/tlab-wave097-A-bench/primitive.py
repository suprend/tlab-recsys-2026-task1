from __future__ import annotations
import time
START = time.monotonic()
import resource, signal
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
def timeout(signum, frame):
    raise TimeoutError('25 wall seconds maximum')
signal.signal(signal.SIGALRM, timeout)
signal.alarm(25)
import datetime, json, platform, sys
from pathlib import Path
import duckdb
OUT = Path('/tmp/tlab-wave097-A-bench')
START_UTC = datetime.datetime.now(datetime.timezone.utc).isoformat()
con = duckdb.connect(':memory:', config={'threads':1,'memory_limit':'256MiB','max_temp_directory_size':'0B'})
con.execute("CREATE TEMP TABLE pilot_queries AS SELECT CAST(q AS VARCHAR) query_id, TIMESTAMP '2019-10-08' anchor FROM range(600) t(q)")
con.execute('''CREATE TEMP TABLE cc_profiles AS SELECT CAST(q AS VARCHAR) query_id,
    (q+r*7)%30 category_id, r+1 category_rank FROM range(600) x(q),range(3) y(r)
    WHERE q%17<>0 AND NOT(q%11=0 AND r=2)''')
con.execute('''CREATE TEMP TABLE cc_membership AS SELECT TIMESTAMP '2019-10-08' anchor,
    1152921504606846976::BIGINT+c*1000+j product_id,c category_id
    FROM range(30) x(c),range(200) y(j) WHERE c<>29 OR j<7''')
con.execute("INSERT INTO cc_membership VALUES (TIMESTAMP '2019-10-08',1152921504606999999,NULL)")
con.execute('''CREATE TEMP TABLE cc_pop AS SELECT anchor,product_id,
    CASE WHEN product_id%13=0 THEN NULL ELSE product_id%5 END::BIGINT buyers
    FROM cc_membership WHERE product_id%7<>0''')
profile_rows=con.execute('SELECT count(*) FROM cc_profiles').fetchone()[0]
membership_rows=con.execute('SELECT count(*) FROM cc_membership').fetchone()[0]
A = '''CREATE OR REPLACE TEMP TABLE result_A AS SELECT 'C1' arm,p.query_id,m.product_id,
    'K'||CAST(p.category_rank AS VARCHAR) src,
    row_number() OVER(PARTITION BY p.query_id,p.category_rank ORDER BY coalesce(b.buyers,0) DESC,m.product_id ASC) source_rank,
    CAST(p.category_rank+1 AS INTEGER) priority
    FROM cc_profiles p JOIN pilot_queries q USING(query_id)
    JOIN cc_membership m ON m.anchor=q.anchor AND m.category_id=p.category_id
    LEFT JOIN cc_pop b ON b.anchor=m.anchor AND b.product_id=m.product_id
    WHERE q.anchor=TIMESTAMP '2019-10-08' AND p.category_rank<=3 QUALIFY source_rank<=20'''
B_BUILD = '''CREATE OR REPLACE TEMP TABLE top_categories AS SELECT m.anchor,m.category_id,m.product_id,
    row_number() OVER(PARTITION BY m.anchor,m.category_id ORDER BY coalesce(b.buyers,0) DESC,m.product_id ASC) source_rank
    FROM cc_membership m LEFT JOIN cc_pop b ON b.anchor=m.anchor AND b.product_id=m.product_id
    SEMI JOIN (SELECT DISTINCT q.anchor,p.category_id FROM cc_profiles p JOIN pilot_queries q USING(query_id)
        WHERE q.anchor=TIMESTAMP '2019-10-08' AND p.category_rank<=3) selected
    ON selected.anchor=m.anchor AND selected.category_id=m.category_id QUALIFY source_rank<=20'''
B_JOIN = '''CREATE OR REPLACE TEMP TABLE result_B AS SELECT 'C1' arm,p.query_id,t.product_id,
    'K'||CAST(p.category_rank AS VARCHAR) src,t.source_rank,CAST(p.category_rank+1 AS INTEGER) priority
    FROM cc_profiles p JOIN pilot_queries q USING(query_id)
    JOIN top_categories t ON t.anchor=q.anchor AND t.category_id=p.category_id
    WHERE q.anchor=TIMESTAMP '2019-10-08' AND p.category_rank<=3'''
# Predeclared two balanced blocks AB / BA; B pays full build and consumer each time.
rows=[]
for route in ['A','B','B','A']:
    wall,cpu=time.monotonic(),time.process_time()
    for sql in ([A] if route=='A' else [B_BUILD,B_JOIN]): con.execute(sql)
    count=con.execute('SELECT count(*) FROM result_'+route).fetchone()[0]
    rows.append({'route':route,'wall_seconds':time.monotonic()-wall,'process_cpu_seconds':time.process_time()-cpu,'output_rows':count})
difference=con.execute('''SELECT count(*) FROM ((SELECT * FROM result_A EXCEPT ALL SELECT * FROM result_B)
    UNION ALL (SELECT * FROM result_B EXCEPT ALL SELECT * FROM result_A))''').fetchone()[0]
assert difference==0, difference
assert con.execute('SELECT count(*) FROM result_A WHERE product_id<=1152921504606846976').fetchone()[0]==0
pre=con.execute('''SELECT count(*) FROM cc_profiles p JOIN pilot_queries q USING(query_id)
    JOIN cc_membership m ON m.anchor=q.anchor AND m.category_id=p.category_id''').fetchone()[0]
selected=con.execute('''SELECT count(*) FROM cc_membership m SEMI JOIN
    (SELECT DISTINCT q.anchor,p.category_id FROM cc_profiles p JOIN pilot_queries q USING(query_id)) s
    ON s.anchor=m.anchor AND s.category_id=m.category_id''').fetchone()[0]
con.close()
signal.alarm(0)
record={'status':'PASS','scope':'synthetic category-ranking primitive only; no events/source files/labels/models',
 'first_actual_utc':START_UTC,'finished_actual_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'python':sys.version,'platform':platform.platform(),'duckdb':duckdb.__version__,
 'limits':{'cpu_seconds':15,'wall_seconds':25,'duckdb_memory':'256MiB','threads':1,'spill':'0B','fits':0},
 'fixture':{'queries':600,'profile_rows':profile_rows,'categories':30,'membership_rows':membership_rows,'bigint_base':1152921504606846976,
    'corner_cases':['popularity ties','NULL and absent buyers => zero','thin category <20','queries with no/2/3 categories','NULL membership category','BIGINT >2^60']},
 'attempts':rows,'mismatches_except_all':difference,'precap_join_rows_A':pre,'prerank_membership_rows_B':selected,
 'inclusive_process_cpu_seconds':time.process_time(),'inclusive_active_wall_seconds':time.monotonic()-START,
 'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
 'note':'Full synthetic build, B build+join and complete materialized sink paid. No warmup, no retry. Timings include profiling-free same-process warm context; not full pilot throughput or quality.'}
assert not (OUT/'result.json').exists()
(OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
