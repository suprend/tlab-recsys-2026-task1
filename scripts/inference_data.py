"""Label-blind, bounded matrices from externally verified query/base/extra F.

This boundary accepts no Y relation and returns no fake targets. Callers own
semantic source/clock acceptance; this proves the physical array/key layer.
"""
from dataclasses import dataclass
from pathlib import Path
import re

import duckdb
import numpy as np
import pandas as pd

from scripts import train_baselines as b
from scripts.protocol_manifest import _relative_path

ROOT=Path(__file__).resolve().parents[1]
MAX_QUERIES=14000
MAX_ROWS=3080000


@dataclass
class InferenceData:
    queries:list
    group:np.ndarray
    items:np.ndarray
    x:np.ndarray
    feature_names:list
    calendar_maturity:np.ndarray
    preparation:dict


def paths(names):
    if type(names) is not list or not 1<=len(names)<=15:raise ValueError('Explicit1..15 verified paths required')
    result=[]
    for name in names:
        _relative_path(name);path=(ROOT/name).resolve();path.relative_to(ROOT.resolve());result.append(str(path))
    if len(set(result))!=len(result):raise ValueError('Repeated physical input')
    return result


def load_inference_data(query_paths,base_feature_paths,*,expected_feature_names,extra_feature_paths=None,
                        extra_feature_names=(),max_queries=MAX_QUERIES,max_rows=MAX_ROWS,
                        matrix_byte_cap=2*2**30,chunk_vectors=32,check=lambda:None):
    if type(max_queries) is not int or not 1<=max_queries<=MAX_QUERIES:raise ValueError('Inference query cap')
    if type(max_rows) is not int or not 1<=max_rows<=MAX_ROWS:raise ValueError('Inference row cap')
    if type(matrix_byte_cap) is not int or not 1<=matrix_byte_cap<=2*2**30:raise ValueError('Inference matrix cap')
    if type(chunk_vectors) is not int or not 1<=chunk_vectors<=32:raise ValueError('Inference chunk cap')
    if type(expected_feature_names) is not list or len(expected_feature_names) not in range(41,45):raise ValueError('Frozen B41 plus at most3 extras required')
    extra=list(extra_feature_names)
    if len(extra)>3 or len(set(extra))!=len(extra) or len(set(expected_feature_names))!=len(expected_feature_names):raise ValueError('Extra feature count/duplicates')
    for name in [*expected_feature_names,*extra]:
        if type(name) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) is None:raise ValueError('Invalid feature identifier')
    if set(expected_feature_names)&{'query_id','user_id','product_id','candidate_category_id','anchor','last_user_event_time','_group','label_is_mature'}:
        raise ValueError('Keys/clock metadata cannot become model features')
    if extra!=expected_feature_names[41:] or bool(extra)!=(extra_feature_paths is not None):raise ValueError('Frozen extra projection differs')
    check()
    con=duckdb.connect(':memory:')
    try:
        con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");con.execute("SET max_temp_directory_size='0B'")
        con.read_parquet(paths(query_paths)).create_view('inference_q')
        con.read_parquet(paths(base_feature_paths)).create_view('inference_f')
        qtypes={r[0]:r[1] for r in con.execute('DESCRIBE inference_q').fetchall()}
        if any(qtypes.get(n)!=v for n,v in dict(query_id='VARCHAR',user_id='BIGINT',anchor='TIMESTAMP',label_is_mature='BOOLEAN').items()):raise ValueError('Query schema/calendar maturity differs')
        columns=con.execute('DESCRIBE inference_f').fetchall();types={r[0]:r[1] for r in columns}
        if any(types.get(n)!=v for n,v in dict(query_id='VARCHAR',user_id='BIGINT',product_id='BIGINT',anchor='TIMESTAMP',last_user_event_time='TIMESTAMP').items()):raise ValueError('Base key/time schema differs')
        names=b.numeric_feature_names([r[0] for r in columns])
        if len(names)!=41 or names!=expected_feature_names[:41]:raise ValueError('Immutable B41 feature order differs')
        def numeric_type(value):
            return value in {'BOOLEAN','TINYINT','SMALLINT','INTEGER','BIGINT','HUGEINT','UTINYINT','USMALLINT','UINTEGER','UBIGINT','FLOAT','DOUBLE'} or value.startswith('DECIMAL(')
        if any(not numeric_type(types[name]) for name in names[:-2]):raise ValueError('Base feature physical types must be numeric')
        check()
        con.execute('''CREATE TEMP TABLE inference_chosen AS SELECT query_id,user_id,anchor,label_is_mature,
            row_number()OVER(ORDER BY query_id)-1 _group FROM inference_q''')
        qn,unique,pairs,invalid=con.execute('''SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)),
            count(*)FILTER(WHERE query_id IS NULL OR user_id IS NULL OR anchor IS NULL OR label_is_mature IS NULL) FROM inference_chosen''').fetchone()
        if invalid or qn!=unique or qn!=pairs or qn>max_queries:raise ValueError('Complete unique query population/cap')
        bad=con.execute('''SELECT count(*) FROM inference_f f LEFT JOIN inference_chosen q USING(query_id)
            WHERE q.query_id IS NULL OR f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor
            OR f.product_id IS NULL OR f.last_user_event_time>=q.anchor''').fetchone()[0]
        n,unique=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM inference_f').fetchone()
        max_per=con.execute('SELECT coalesce(max(n),0) FROM(SELECT count(*) n FROM inference_f GROUP BY query_id)').fetchone()[0]
        if bad or n!=unique or n>max_rows or max_per>220:raise ValueError('Exact nonorphan candidate feature keys/cap/strict past')
        estimated=n*(len(expected_feature_names)*4+4+8)+qn
        if estimated>matrix_byte_cap:raise MemoryError('Inference matrix cap exceeded before allocation')
        check()
        if extra:
            con.read_parquet(paths(extra_feature_paths)).create_view('inference_extra')
            et={r[0]:r[1] for r in con.execute('DESCRIBE inference_extra').fetchall()}
            if et.get('query_id')!='VARCHAR' or et.get('product_id')!='BIGINT' or any(name not in et for name in extra):raise ValueError('Extra physical schema differs')
            if any(not numeric_type(et[name]) for name in extra):raise ValueError('Extra feature physical types must be numeric')
            missing=con.execute('''SELECT count(*) FROM((SELECT query_id,product_id FROM inference_f EXCEPT ALL SELECT query_id,product_id FROM inference_extra)
                UNION ALL(SELECT query_id,product_id FROM inference_extra EXCEPT ALL SELECT query_id,product_id FROM inference_f))''').fetchone()[0]
            if missing:raise ValueError('Extra/base exact key multiset differs')
        check()
        query_rows=con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM inference_chosen ORDER BY _group').fetchall()
        queries=[row[:3] for row in query_rows]
        calendar_maturity=np.asarray([row[3] for row in query_rows],dtype=np.bool_)
        fields=[f'CAST(f."{name}" AS FLOAT) AS "{name}"' for name in names[:-2]]
        fields+=['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds',
                 'CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
        fields += [f'CAST(a."{name}" AS FLOAT) AS "{name}"' for name in extra]
        join=' JOIN inference_extra a USING(query_id,product_id)' if extra else ''
        check();x=np.empty((n,len(expected_feature_names)),dtype=np.float32)
        group=np.empty(n,dtype=np.int32);items=np.empty(n,dtype=np.int64)
        con.execute('SELECT q._group,f.product_id,'+','.join(fields)+' FROM inference_f f JOIN inference_chosen q USING(query_id)'+join+' ORDER BY q._group,f.product_id')
        cursor=chunks=largest=0
        while True:
            check();frame=con.fetch_df_chunk(chunk_vectors)
            if frame.empty:break
            size=len(frame);stop=cursor+size
            if size>65536 or stop>n:raise ValueError('Inference chunk/row boundary')
            for name in ['_group','product_id']:
                if not pd.api.types.is_integer_dtype(frame[name].dtype) or frame[name].isna().any():raise ValueError('Nonnullable exact integer transport required')
            g=frame['_group'].to_numpy(dtype=np.int64)
            if g.min()<0 or g.max()>=qn:raise ValueError('Group domain')
            group[cursor:stop]=g;items[cursor:stop]=frame['product_id'].to_numpy(dtype=np.int64)
            for i,name in enumerate(expected_feature_names):
                x[cursor:stop,i]=frame[name].to_numpy(dtype=np.float32,na_value=np.nan)
            if np.isinf(x[cursor:stop]).any():raise ValueError('Infinite inference feature')
            cursor=stop;chunks+=1;largest=max(largest,size);check()
        if cursor!=n:raise ValueError('Incomplete inference row coverage')
        return InferenceData(queries,group,items,x,list(expected_feature_names),calendar_maturity,dict(queries=qn,rows=n,array_bytes=estimated,
            chunks=chunks,largest_chunk=largest,outcome_relations_opened=0,sampling='none_all_explicit_queries',
            proof='external_source_acceptance_required_physical_key_and_array_boundary_only'))
    finally:con.close()
