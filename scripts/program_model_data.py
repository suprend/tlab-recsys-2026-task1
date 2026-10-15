"""Append one externally accepted three-column program to accepted B41 arrays.

The immutable base loader selects development Q before opening Y. This module
does not open Y, choose queries, calculate source formulas, fit or grant approval.
The caller must verify the full source export and exact arm allocation first.
"""
from dataclasses import replace
from pathlib import Path
import re

import duckdb
import numpy as np
import pandas as pd

from scripts import model_data as base
from scripts.protocol_manifest import _relative_path

ROOT=Path(__file__).resolve().parents[1]
MAX_ROWS=5720000
MAX_QUERIES=26000


def _schema(value):
    if type(value) is not list or len(value)!=57:
        raise ValueError('Externally accepted exact57-column source schema required')
    out=[]
    for field in value:
        if type(field) not in (list,tuple) or len(field)!=2:
            raise ValueError('Invalid source schema field')
        name,dtype=field
        if type(name) is not str or re.fullmatch(r'[a-z][a-z0-9_]{0,63}',name) is None or type(dtype) is not str:
            raise ValueError('Invalid source column name/type')
        out.append((name,dtype))
    if len({n for n,t in out})!=57:raise ValueError('Duplicate source columns')
    types=dict(out)
    if any(types.get(n)!=t for n,t in [('query_id','VARCHAR'),('user_id','BIGINT'),
        ('product_id','BIGINT'),('anchor','TIMESTAMP')]):raise ValueError('Exact source key types required')
    return out


def _paths(names):
    if type(names) is not list or not 1<=len(names)<=15:raise ValueError('Explicit1..15 source paths required')
    result=[]
    for name in names:
        _relative_path(name);p=(ROOT/name).resolve();p.relative_to(ROOT.resolve());result.append(str(p))
    if len(set(result))!=len(result):raise ValueError('Duplicate physical source path')
    return result


def append_program_features(data,feature_paths,*,extra_columns,expected_source_schema,
                            matrix_byte_cap=2*2**30,chunk_vectors=32,check=lambda:None):
    """Keep Q/C/Y/base values exact and append only one frozen physical delta.

    The byte cap covers both simultaneously live base and merged numeric arrays,
    shared key/Y arrays and the three-column float32 chunk. It does not claim to
    bound DuckDB, Python objects, native Pool memory or the caller's process RSS.
    The caller releases its old base object after a successful return. This
    function leaves that object untouched, including on failure.
    """
    if not isinstance(data,base.ModelData) or data.categorical is not None or data.categorical_names:
        raise ValueError('Accepted numeric B41 development ModelData required')
    n=len(data.items);qn=len(data.queries)
    if (len(data.feature_names)!=41 or len(set(data.feature_names))!=41 or data.x.shape!=(n,41)
            or data.x.dtype!=np.float32 or data.group.shape!=(n,) or data.group.dtype!=np.int32
            or data.items.shape!=(n,) or data.items.dtype!=np.int64 or data.y.shape!=(n,) or data.y.dtype!=np.int8
            or n>MAX_ROWS or qn>MAX_QUERIES or n>qn*220):raise ValueError('Bounded B41 array representation differs')
    if type(matrix_byte_cap) is not int or not 1<=matrix_byte_cap<=2*2**30:raise ValueError('Invalid live-array byte cap')
    if type(chunk_vectors) is not int or not 1<=chunk_vectors<=32:raise ValueError('Invalid chunk vector cap')
    schema=_schema(expected_source_schema);types=dict(schema)
    if type(extra_columns) is not list or len(extra_columns)!=3:raise ValueError('One exact three-column physical program required')
    delta=[]
    for field in extra_columns:
        if type(field) is not dict or set(field)!={'name','dtype'}:raise ValueError('Invalid declared physical delta')
        name,dtype=field['name'],field['dtype']
        if (type(name) is not str or re.fullmatch(r'auto_[a-z0-9_]{1,58}',name) is None
                or dtype not in {'BIGINT','DOUBLE','BOOLEAN'} or types.get(name)!=dtype):
            raise ValueError('Program name/type must match accepted source schema')
        delta.append(name)
    if len(set(delta))!=3 or set(delta)&set(data.feature_names):raise ValueError('Program/base column collision')
    for name in delta:
        if types[name]=='DOUBLE' and (name+'_missing' not in delta or types.get(name+'_missing')!='BOOLEAN'):
            raise ValueError('Program recency requires its physical missing mask')
        if types[name]=='BOOLEAN' and (not name.endswith('_missing') or name[:-8] not in delta or types[name[:-8]]!='DOUBLE'):
            raise ValueError('Program mask must belong to the same selected recency')
    query_rows=[]
    for i,q in enumerate(data.queries):
        if len(q)!=4 or type(q[0]) is not str or type(q[1]) is not int:
            raise ValueError('Accepted exact query triples/targets required')
        query_rows.append((q[0],q[1],q[2],i))
    if len({q[0] for q in query_rows})!=qn or len({q[1:3] for q in query_rows})!=qn:
        raise ValueError('Duplicate base query identity')
    if n:
        g=data.group;it=data.items
        if (np.any(g<0) or np.any(g>=qn) or np.any(g[1:]<g[:-1])
                or np.any((g[1:]==g[:-1])&(it[1:]<=it[:-1]))):raise ValueError('Base row/group ordering differs')
    live_bytes=data.x.nbytes+n*(44*4+4+8+1)+min(n,2048*chunk_vectors)*3*4
    if live_bytes>matrix_byte_cap:raise MemoryError('Live base-plus-program arrays exceed cap before allocation')
    check();source_paths=_paths(feature_paths);con=duckdb.connect(':memory:')
    try:
        con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");con.execute("SET max_temp_directory_size='0B'")
        con.read_parquet(source_paths).create_view('program_source')
        actual=[tuple(r[:2]) for r in con.execute('DESCRIBE program_source').fetchall()]
        if actual!=schema:raise ValueError('Actual full source schema/order differs from acceptance')
        # Use an explicit four-column frame and explicit projection. Unknown Q
        # fields can never shadow the generated group index.
        frame=pd.DataFrame(query_rows,columns=['query_id','user_id','anchor','program_group'])
        frame['query_id']=frame['query_id'].astype('string')
        frame['user_id']=frame['user_id'].astype('int64')
        frame['anchor']=pd.to_datetime(frame['anchor'])
        frame['program_group']=frame['program_group'].astype('int32')
        con.register('program_queries',frame)
        con.execute('''CREATE TEMP VIEW program_chosen AS SELECT e.query_id,e.product_id,e.user_id,e.anchor,
            q.program_group FROM program_source e JOIN program_queries q ON e.query_id=q.query_id''')
        count,unique,bad=con.execute('''SELECT count(*),count(DISTINCT(query_id,product_id)),
            count(*) FILTER(WHERE product_id IS NULL OR user_id IS NULL OR anchor IS NULL) FROM program_chosen''').fetchone()
        mismatch=con.execute('''SELECT count(*) FROM program_chosen e JOIN program_queries q USING(query_id)
            WHERE e.user_id IS DISTINCT FROM q.user_id OR e.anchor IS DISTINCT FROM q.anchor''').fetchone()[0]
        if count!=n or count!=unique or bad or mismatch:raise ValueError('Program/base chosen key cover or query identity differs')
        check();merged=np.empty((n,44),dtype=np.float32);merged[:,:41]=data.x
        fields=','.join('e."'+name+'"' for name in delta)
        con.execute('SELECT q.program_group,e.product_id,'+fields+' FROM program_source e JOIN program_queries q USING(query_id) ORDER BY q.program_group,e.product_id')
        cursor=chunks=largest=0
        while True:
            check();part=con.fetch_df_chunk(chunk_vectors)
            if part.empty:break
            size=len(part);stop=cursor+size
            if size>2048*chunk_vectors or stop>n:raise ValueError('Program chunk/row cap differs')
            for name in ['program_group','product_id']:
                if not pd.api.types.is_integer_dtype(part[name].dtype) or part[name].isna().any():
                    raise ValueError('Exact nonnullable integer program keys required')
            if (not np.array_equal(part['program_group'].to_numpy(dtype=np.int64),data.group[cursor:stop])
                    or not np.array_equal(part['product_id'].to_numpy(dtype=np.int64),data.items[cursor:stop])):
                raise ValueError('Every sorted program key must equal the accepted B row')
            values=part[delta].to_numpy(dtype=np.float32,na_value=np.nan)
            if np.isinf(values).any():raise ValueError('Infinite program feature after float32 conversion')
            for j,name in enumerate(delta):
                if types[name]=='BOOLEAN' and (np.isnan(values[:,j]).any() or not np.isin(values[:,j],[0,1]).all()):
                    raise ValueError('Program missing flag must be nonnullable boolean')
                if types[name]=='BIGINT' and (np.isnan(values[:,j]).any() or np.any(values[:,j]<0)):
                    raise ValueError('Program count must be nonnegative and nonnullable')
                if types[name]=='DOUBLE':
                    mask=name+'_missing'
                    if mask not in delta or types.get(mask)!='BOOLEAN':raise ValueError('Program recency requires its physical missing mask')
                    missing=np.isnan(values[:,j])
                    if (not np.array_equal(missing,values[:,delta.index(mask)].astype(bool))
                            or np.any(values[~missing,j]<=0)):raise ValueError('Program recency NULL/mask/strict-past range differs')
            merged[cursor:stop,41:]=values;cursor=stop;chunks+=1;largest=max(largest,size);check()
        if cursor!=n:raise ValueError('Program source did not cover every B row')
        preparation=dict(data.preparation,program=dict(selected_columns=delta,rows=n,chunks=chunks,
            largest_chunk_rows=largest,live_array_bytes=live_bytes,outcome_relations_opened=0,
            query_selection='reuse_immutable_B_Q_C_and_Y_no_sampling',source_formula_proof='external_acceptance_required'))
        check();return replace(data,x=merged,feature_names=[*data.feature_names,*delta],preparation=preparation)
    finally:con.close()
