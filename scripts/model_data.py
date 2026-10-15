"""Bounded chunked model matrices from previously verified development data.

Callers must consume external collection/export acceptances before calling.
This module proves the transformation/key/model boundary; it grants no source
acceptance and opens no model or reserved confirmation phase.
"""
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np

from scripts import train_baselines as b
from scripts import metadata_price_features as m
from scripts.protocol_manifest import _relative_path

ROOT=Path(__file__).resolve().parents[1]
MAX_ROWS=5720000
MAX_QUERIES=26000
MAX_TARGETS=1000000


def local(name):
    _relative_path(name)
    path=(ROOT/name).resolve();path.relative_to(ROOT.resolve())
    return path


@dataclass
class ModelData(b.Prepared):
    categorical: np.ndarray | None
    categorical_names: list
    preparation: dict


def validate_metadata_arrays(numeric,nominal):
    """Vectorized port of the frozen009 representation rules, without SQL.

    Both implementations are compared on synthetic data; frozen producer
    remains unchanged. Values here are already float32 / UTF8 bytes.
    """
    if numeric.dtype!=np.float32 or numeric.ndim!=2 or numeric.shape[1]!=len(m.NUMERIC):
        raise ValueError('Metadata numeric representation differs from fixed15')
    if nominal.dtype!=object or nominal.shape!=(len(numeric),len(m.NOMINAL)):
        raise ValueError('Metadata nominal representation differs from fixed3')
    if np.isinf(numeric).any():raise ValueError('Infinite metadata after float32 conversion')
    def column(name):return numeric[:,m.NUMERIC.index(name)]
    def flag(name):return column(name).astype(bool)
    for name in set(m.NUMERIC)-{'log_price','category_peer_log_price_mean','category_peer_product_support','category_log_price_difference'}:
        if not np.isin(column(name),[0,1]).all():raise ValueError('Invalid boolean metadata flag')
    for value,mask in [('category_peer_log_price_mean','category_peer_mean_missing'),
                       ('category_log_price_difference','category_price_difference_missing')]:
        if not np.array_equal(np.isnan(column(value)),flag(mask)):raise ValueError('Numeric NULL/missing-mask mismatch')
    price_unknown=flag('price_missing')|flag('price_zero')|flag('price_negative')
    if (not np.array_equal(np.isnan(column('log_price')),price_unknown)
            or np.any(flag('price_ambiguous')&~flag('price_missing'))
            or np.any(flag('price_zero')&(flag('price_missing')|flag('price_negative')))
            or np.any(flag('price_negative')&flag('price_missing'))):
        raise ValueError('Price NULL/resolution-mask mismatch')
    for i,missing,ambiguous in [(2,'brand_missing','brand_ambiguous'),(1,'code_missing','code_ambiguous')]:
        values=nominal[:,i]
        unknown=np.isin(values,[b'state:missing',b'state:ambiguous']) if i==2 else values==b'state:missing'
        if not np.array_equal(flag(missing),unknown) or not np.array_equal(flag(ambiguous),values==b'state:ambiguous'):
            raise ValueError('Nominal resolution-mask mismatch')
    if np.any(flag('code_recovered')&np.isin(nominal[:,1],[b'state:missing',b'state:ambiguous'])):
        raise ValueError('Recovered code must be known')
    support=column('category_peer_product_support')
    if np.any(np.isfinite(support)&((support<0)|(support!=np.floor(support)))):
        raise ValueError('Invalid distinct-product support')
    unknown=np.isin(nominal[:,0],[b'state:missing',b'state:ambiguous'])
    if (not np.array_equal(np.isnan(support),unknown)
            or not np.array_equal(flag('category_peer_mean_missing'),np.isnan(support)|(support==0))
            or not np.array_equal(flag('category_price_difference_missing'),price_unknown|flag('category_peer_mean_missing'))):
        raise ValueError('Conditional reference NULL/mask mismatch')


def assert_base_equivalent(data,reference):
    """Exact old008/new base comparison; shapes alone are insufficient."""
    n=len(reference.feature_names)
    if (data.queries!=reference.queries or data.feature_names[:n]!=reference.feature_names
            or data.x.shape[0]!=reference.x.shape[0]
            or not np.array_equal(data.x[:,:n],reference.x,equal_nan=True)
            or any(not np.array_equal(getattr(data,k),getattr(reference,k)) for k in ['group','items','y'])):
        raise ValueError('Chunked/base input equivalence failed')


def prepare_model_data(collection,*,max_queries,max_rows,metadata_paths=None,
                       check=lambda:None,chunk_vectors=32,matrix_byte_cap=2*2**30):
    """Sample Q before reading Y, then stream each sorted candidate row once.

    max_queries=None retains all Q, still bounded by MAX_QUERIES. FullY is
    external to C, including emptyC/allnegative/allpositive groups. No native
    Pool, fit, selection encoder or target-dependent sampling is performed.
    """
    if collection['phase']['role'] not in {'train','selection'}:
        raise ValueError('Only accepted development train/selection data may be loaded')
    if max_queries is not None and (type(max_queries) is not int or not 1<=max_queries<=MAX_QUERIES):
        raise ValueError('Invalid reviewed query cap')
    if type(max_rows) is not int or not 1<=max_rows<=MAX_ROWS:raise ValueError('Invalid reviewed matrix row cap')
    if type(chunk_vectors) is not int or not 1<=chunk_vectors<=32:raise ValueError('Chunk vector count must be1–32')
    if type(matrix_byte_cap) is not int or not 1<=matrix_byte_cap<=2*2**30:raise ValueError('Invalid matrix byte cap')
    mixed=metadata_paths is not None
    if mixed and (not isinstance(metadata_paths,list) or not metadata_paths):raise ValueError('Metadata paths must be a nonempty verified phase list')
    base_names=b.numeric_feature_names(collection['feature_columns'])
    names=[*base_names,*m.NUMERIC] if mixed else base_names
    if len(names)!=len(set(names)):raise ValueError('Duplicate numeric feature names')
    con=duckdb.connect(':memory:')
    try:
        con.execute('SET threads=2');con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='0B'")
        for kind in ['queries','features']:
            con.read_parquet([str(local(p)) for p in collection['refs'][kind]]).create_view('all_'+kind)
        limit='' if max_queries is None else ' LIMIT '+str(max_queries)
        con.execute('''CREATE TEMP TABLE chosen AS SELECT *,row_number() OVER(ORDER BY query_id)-1 group_index
            FROM (SELECT * FROM all_queries ORDER BY sha256(query_id),query_id'''+limit+')')
        qn,unique,pairs=con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)) FROM chosen').fetchone()
        invalid=con.execute('''SELECT count(*) FROM chosen WHERE query_id IS NULL OR user_id IS NULL OR anchor IS NULL
            OR label_is_mature IS DISTINCT FROM true''').fetchone()[0]
        if invalid or qn!=unique or qn!=pairs or qn>MAX_QUERIES:raise ValueError('Invalid mature complete unique queries/query cap')
        con.execute('CREATE TEMP VIEW chosen_features AS SELECT f.*,q.group_index FROM all_features f JOIN chosen q USING(query_id)')
        n,unique=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM chosen_features').fetchone()
        if n>max_rows or n>qn*220:raise ValueError('Matrix row cap exceeded before allocation')
        if n!=unique:raise ValueError('Duplicate candidate feature keys')
        if con.execute('''SELECT count(*) FROM chosen_features f JOIN chosen q USING(query_id)
            WHERE f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor
            OR f.product_id IS NULL OR f.last_user_event_time>=q.anchor''').fetchone()[0]:
            raise ValueError('Feature key/strict-past retrieval mismatch')
        numeric_bytes=n*len(names)*4
        categorical_bytes=n*len(m.NOMINAL)*8 if mixed else 0
        estimate=numeric_bytes+categorical_bytes+n*(4+8+1)
        if estimate>matrix_byte_cap:raise MemoryError('Matrix byte cap exceeded before allocation')
        if mixed:
            con.read_parquet([str(local(p)) for p in metadata_paths]).create_view('all_metadata')
            required=['query_id','product_id',*m.NOMINAL,*m.NUMERIC]
            if [r[0] for r in con.execute('DESCRIBE all_metadata').fetchall()]!=required:
                raise ValueError('Metadata schema/order differs from fixed block')
            con.execute('CREATE TEMP VIEW chosen_metadata AS SELECT a.* FROM all_metadata a SEMI JOIN chosen q USING(query_id)')
            an,au=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM chosen_metadata').fetchone()
            bad=con.execute('''SELECT count(*) FROM ((SELECT query_id,product_id FROM chosen_features EXCEPT ALL SELECT query_id,product_id FROM chosen_metadata)
                UNION ALL (SELECT query_id,product_id FROM chosen_metadata EXCEPT ALL SELECT query_id,product_id FROM chosen_features))''').fetchone()[0]
            if an!=n or an!=au or bad:raise ValueError('Metadata/base exact key cover mismatch')
        check()
        # First label view/read occurs after immutable Q selection and key/caps.
        con.read_parquet([str(local(p)) for p in collection['refs']['labels']]).create_view('all_labels')
        con.execute('CREATE TEMP VIEW chosen_labels AS SELECT l.* FROM all_labels l SEMI JOIN chosen q USING(query_id)')
        yn,yu=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM chosen_labels').fetchone()
        if yn!=yu or yn>MAX_TARGETS or con.execute('SELECT count(*) FROM chosen_labels WHERE product_id IS NULL').fetchone()[0]:
            raise ValueError('Invalid duplicate/null/oversize full targets')
        targets={}
        for qid,item in con.execute('SELECT query_id,product_id FROM chosen_labels ORDER BY query_id,product_id').fetchall():
            targets.setdefault(qid,set()).add(item)
        queries=[(qid,user,anchor,frozenset(targets.get(qid,()))) for qid,user,anchor in
                 con.execute('SELECT query_id,user_id,anchor FROM chosen ORDER BY group_index').fetchall()]
        x=np.empty((n,len(names)),dtype=np.float32)
        categorical=np.empty((n,len(m.NOMINAL)),dtype=object) if mixed else None
        groups=np.empty(n,dtype=np.int32);items=np.empty(n,dtype=np.int64);y=np.empty(n,dtype=np.int8)
        fields=[f'CAST(f."{name}" AS FLOAT) AS "{name}"' for name in base_names[:-2]]
        fields+=['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds',
                 'CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
        if mixed:fields += [f'CAST(a."{name}" AS FLOAT) AS "{name}"' for name in m.NUMERIC]+[f'a."{name}"' for name in m.NOMINAL]
        sql='''SELECT f.group_index,f.product_id,CAST(l.product_id IS NOT NULL AS TINYINT) y,'''+','.join(fields)+'''
            FROM chosen_features f LEFT JOIN chosen_labels l USING(query_id,product_id)'''
        if mixed:sql+=' JOIN chosen_metadata a USING(query_id,product_id)'
        sql+=' ORDER BY f.group_index,f.product_id'
        check();con.execute(sql) # Execute once; connection fetch resumes this result.
        cursor=chunks=0;maximum_chunk=0;previous=None;cache={}
        while True:
            frame=con.fetch_df_chunk(chunk_vectors)
            if frame.empty:break
            check();size=len(frame);stop=cursor+size
            if size>2048*chunk_vectors or stop>n:raise ValueError('Physical chunk/result row cap mismatch')
            for key in ['group_index','product_id']:
                if not np.issubdtype(frame[key].dtype,np.integer):raise ValueError('Raw key transport must be nonnullable integer')
            g=frame['group_index'].to_numpy(dtype=np.int64);it=frame['product_id'].to_numpy(dtype=np.int64)
            if (np.any(g<0) or np.any(g>=qn) or np.any(g[1:]<g[:-1])
                    or np.any((g[1:]==g[:-1])&(it[1:]<=it[:-1]))
                    or (previous is not None and (int(g[0]),int(it[0]))<=previous)):
                raise ValueError('Model row ordering/group/key boundary invalid')
            previous=(int(g[-1]),int(it[-1]))
            x[cursor:stop]=frame[names].to_numpy(dtype=np.float32,na_value=np.nan)
            if np.isinf(x[cursor:stop]).any():raise ValueError('Infinite feature after float32 conversion')
            groups[cursor:stop]=g;items[cursor:stop]=it;y[cursor:stop]=frame['y'].to_numpy(dtype=np.int8)
            if mixed:
                for j,name in enumerate(m.NOMINAL):
                    encoded=[]
                    for value in frame[name]:
                        if not isinstance(value,str) or not(value.startswith('value:') or value in {'state:missing','state:ambiguous'}):
                            raise ValueError('Invalid nominal namespace/type')
                        if value not in cache:cache[value]=value.encode('utf8')
                        encoded.append(cache[value])
                    categorical[cursor:stop,j]=encoded
                validate_metadata_arrays(x[cursor:stop,len(base_names):],categorical[cursor:stop])
            cursor=stop;chunks+=1;maximum_chunk=max(maximum_chunk,size);check()
        if cursor!=n:raise ValueError('Model result did not cover preallocated rows exactly')
        result=ModelData(queries,groups,items,x,y,names,categorical,list(m.NOMINAL) if mixed else [],
            dict(rows=n,queries=qn,estimated_matrix_bytes=estimate,chunks=chunks,max_chunk_rows=maximum_chunk,
                 chunk_vectors=chunk_vectors,utf8_cached_values=len(cache),full_target_rows=yn,
                 label_independent_sampling=True,fit_attempt_count=0))
        b.group_accounting(result);check()
        return result
    finally:con.close()
