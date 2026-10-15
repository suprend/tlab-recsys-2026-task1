"""Frozen, label-blind daily inference core; no execution or target capability.

The measured caller authenticates files/source/choice, loads the exact CBMs and
owns claims, serialization, independent replay and complete resource lifetime.
This module opens no model itself, accepts no Y and performs no fitting.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import math
import hashlib
import struct

import numpy as np
from scripts import heldout_contract as h
from scripts import inference_data


@dataclass
class FrozenScores:
    queries: list
    calendar_maturity: np.ndarray
    group: np.ndarray
    items: np.ndarray
    scores: np.ndarray
    feature_names: list
    model: dict
    source_acceptance: dict
    preparation: dict


def _bayesian_serialized_alias(expected, actual, path):
    """Only the observed Bayesian float32-to-ten-digit metadata alias.

    This is an observed representation, not a claim about a documented native
    format. The caller still authenticates the exact fixed model bytes/spec.
    Other keys, nested occurrences and arbitrary values in the same bin do not
    receive a wider tolerance.
    """
    if (path != ('bayesian_matrix_reg',) or type(expected) is not float
            or type(actual) is not float or not math.isfinite(expected)
            or not math.isfinite(actual)):
        return False
    try:
        canonical = struct.unpack('!f', struct.pack('!f', expected))[0]
        loaded = struct.unpack('!f', struct.pack('!f', actual))[0]
    except (OverflowError, struct.error):
        return False
    return (expected == canonical and loaded == canonical
            and actual == float(format(expected, '.10g')))


def _same(expected, actual, path=(), *, _scalar_alias=True):
    if type(expected) is dict:
        h.keys(actual,expected,'Native parameter schema')
        for key,value in expected.items():_same(value,actual[key],(*path,key),_scalar_alias=_scalar_alias)
    elif type(expected) is list:
        h.need(type(actual) is list and len(actual)==len(expected),'Native parameter sequence differs')
        for a,b in zip(expected,actual):_same(a,b,path,_scalar_alias=False)
    elif type(expected) is float:
        tolerance=max(1e-12,abs(expected)*1e-8) if path==('learning_rate',) else 1e-12
        h.need(type(actual) is float and math.isfinite(expected) and math.isfinite(actual)
               and (abs(expected-actual)<=tolerance or (_scalar_alias and _bayesian_serialized_alias(expected,actual,path))),
               'Native effective parameter differs')
    else:h.need(type(actual) is type(expected) and actual==expected,'Native parameter value/type differs')


def verify_model(model, spec):
    """Validate the loaded native state; byte identity remains caller-owned."""
    h.model(spec)
    expected=spec['effective_parameters']
    fixed=dict(loss_function='Logloss',iterations=300,depth=6,l2_leaf_reg=30,random_seed=2026,task_type='CPU',
        boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,
        leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,
        border_count=254,nan_mode='Min',rsm=1)
    for key,value in fixed.items():_same(value,expected.get(key),(key,))
    effective=struct.unpack('!f',struct.pack('!f',.05))[0]
    _same(effective,expected.get('learning_rate'),('learning_rate',))
    h.need(type(model.tree_count_) is int and model.tree_count_==300,'Frozen native tree count differs')
    h.need(model.feature_names_==spec['feature_names'],'Frozen native feature order differs')
    h.need(model.get_cat_feature_indices()==[] and model.get_text_feature_indices()==[]
           and model.get_embedding_feature_indices()==[],'Only numeric native models supported')
    _same(expected,model.get_all_params())


def _source_day(snapshot, anchor, lock):
    h.keys(snapshot,{'acceptance','days'},'Authenticated source snapshot');h.ref(snapshot['acceptance'])
    rows=snapshot['days'];h.need(type(rows) is list and len(rows)==7,'Exactly seven source dates required')
    days={}
    for row in rows:
        h.keys(row,{'anchor','queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count'},'Source day')
        day=row['anchor'];h.need(day in h.DAYS and day not in days,'Repeated/outside source date')
        for key in ['queries','candidates','base_features']:h.ref(row[key])
        h.integer(row['query_count'],0,2000,'Daily Q');h.integer(row['candidate_count'],0,row['query_count']*220,'Daily C')
        h.need(type(row['mature_query_count']) is int and row['mature_query_count']==row['query_count'],'Current calendar requires every Q mature')
        if lock['choice']=='B':h.need(row['extra_features'] is None,'B-only source must have no extras')
        else:h.ref(row['extra_features'])
        days[day]=row
    h.need(set(days)==set(h.DAYS) and anchor in days,'Incomplete/outside source calendar')
    return deepcopy(days[anchor])


def _validate_data(data, row, names, check):
    h.need(type(data) is inference_data.InferenceData and not hasattr(data,'y'),'Label-blind inference data required')
    h.need(type(data.queries) is list and len(data.queries)==row['query_count'] and data.feature_names==names,'Source Q/schema differs')
    qids=[];identities=set();anchor=h.utc(row['anchor']).replace(tzinfo=None)
    for q in data.queries:
        h.need(type(q) is tuple and len(q)==3,'Query must have exactly qid/user/anchor, no target')
        qid,user,when=q
        h.need(type(qid) is str and qid and type(user) is int and -2**63<=user<2**63
               and type(when) is datetime and when==anchor,'Query identity/calendar differs')
        h.need((user,when) not in identities,'Duplicate user-day');identities.add((user,when));qids.append(qid)
    h.need(qids==sorted(set(qids)),'Exact canonical all-Q order required')
    n=row['candidate_count'];qn=len(qids)
    for array,dtype,shape in [(data.x,np.dtype('float32'),(n,len(names))),
            (data.group,np.dtype('int32'),(n,)),(data.items,np.dtype('int64'),(n,)),
            (data.calendar_maturity,np.dtype('bool'),(qn,))]:
        h.need(type(array) is np.ndarray and array.dtype==dtype and array.shape==shape,'Typed inference array/shape differs')
    h.need(data.calendar_maturity.all(),'All declared current queries must be mature')
    for start in range(0,n,65536):
        check();stop=min(n,start+65536);g=data.group[start:stop];items=data.items[start:stop]
        h.need(not np.isinf(data.x[start:stop]).any(),'Infinite inference values')
        h.need((g>=0).all() and (g<qn).all(),'Candidate group outside complete Q')
        left=max(0,start-1);gg=data.group[left:stop];ii=data.items[left:stop]
        h.need(((gg[1:]>gg[:-1])|((gg[1:]==gg[:-1])&(ii[1:]>ii[:-1]))).all(),'Candidate keys duplicate or unordered')
    counts=np.bincount(data.group,minlength=qn)
    h.need((counts<=220).all(),'Per-query candidate cap differs')
    check()


def _matrix_witness(x, check):
    value=hashlib.sha256()
    for start in range(0,len(x),65536):
        check();part=np.ascontiguousarray(x[start:start+65536]);value.update(memoryview(part).cast('B'))
    check();return value.hexdigest()


def score_day(anchor, lock, *, authenticated_choice, authenticated_source,
              load_model, load_data=None, check=lambda:None):
    """Return exact B/W keyed raw scores, retaining all Q and empty C.

    load_model(ref) MUST return the caller-authenticated native object. Core has
    no default file opener, writer, CLI, Y reference, fit or Pool. Source and code
    authenticity plus resource supervision are external obligations.
    """
    check();locked=h.validate_lock(lock,authenticated_choice=authenticated_choice)
    source=deepcopy(authenticated_source);row=_source_day(source,anchor,locked)
    h.need(callable(load_model),'Explicit authenticated model loader required')
    loader=inference_data.load_inference_data if load_data is None else load_data
    h.need(callable(loader),'Explicit inference loader must be callable');result={}
    for role in ['B','W']:
        if role=='W' and locked['choice']=='B':result['W']=result['B'];continue
        check();spec=locked['models'][role];model=load_model(deepcopy(spec['model']));check();verify_model(model,spec)
        extras=spec['feature_names'][41:]
        data=loader([row['queries']['path']],[row['base_features']['path']],
            expected_feature_names=list(spec['feature_names']),
            extra_feature_paths=[row['extra_features']['path']] if extras else None,
            extra_feature_names=list(extras),max_queries=2000,max_rows=440000,check=check)
        check();_validate_data(data,row,spec['feature_names'],check)
        snapshot=dict(queries=deepcopy(data.queries),calendar=data.calendar_maturity.copy(),
            group=data.group.copy(),items=data.items.copy(),preparation=deepcopy(data.preparation))
        witness=_matrix_witness(data.x,check)
        if row['candidate_count']:
            raw=model.predict(data.x,prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2)
        else:raw=np.empty(0,dtype=np.float64)
        check();verify_model(model,spec);_validate_data(data,row,spec['feature_names'],check)
        h.need(data.queries==snapshot['queries'] and np.array_equal(data.calendar_maturity,snapshot['calendar'])
            and np.array_equal(data.group,snapshot['group']) and np.array_equal(data.items,snapshot['items'])
            and data.preparation==snapshot['preparation'],'Inference snapshot changed during native call')
        h.need(_matrix_witness(data.x,check)==witness,'Feature matrix changed during native call')
        h.need(type(raw) is np.ndarray and raw.dtype==np.dtype('float64') and raw.shape==(row['candidate_count'],)
               and np.isfinite(raw).all(),'Exact finite native float64 score vector required')
        scores=FrozenScores(snapshot['queries'],snapshot['calendar'],snapshot['group'],snapshot['items'],raw.copy(),
            list(spec['feature_names']),deepcopy(spec['model']),deepcopy(source['acceptance']),snapshot['preparation'])
        if role=='W':
            b=result['B'];h.need(scores.queries==b.queries and np.array_equal(scores.calendar_maturity,b.calendar_maturity)
                and np.array_equal(scores.group,b.group) and np.array_equal(scores.items,b.items),'B/W source query/key domains differ')
        result[role]=scores;del data,model;check()
    return dict(anchor=anchor,source_day=row,source_acceptance=source['acceptance'],predictions=result,
                fit_attempt_count=0,outcome_relations_opened=0,
                native_prediction_calls=0 if row['candidate_count']==0 else 1 if locked['choice']=='B' else 2,
                proof='caller_authenticated_source_and_model_bytes_independent_output_replay_still_required')
