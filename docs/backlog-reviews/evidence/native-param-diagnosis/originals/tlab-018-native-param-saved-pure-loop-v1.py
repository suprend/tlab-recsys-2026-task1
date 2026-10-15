"""Minimised exact protected verifier replay from the one saved parameter capture."""
import ast
import hashlib
import json
import math
from pathlib import Path
import struct
import types

CAPTURE=Path('/tmp/tlab-018-native-param-diagnostic-20261015-once/capture.json')
PREDICTIONS=Path('/Users/mdpospelov/tlab-recsys-2026/scripts/heldout_predictions.py')
PREDICTIONS_SHA='e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b'
CONTRACT=Path('/Users/mdpospelov/tlab-recsys-2026/scripts/heldout_contract.py')
CONTRACT_SHA='fc50d11d3b6dfdc2906522472f5b66138424bc4586e7833b43c6fc4e6c4f1abc'


def exact(path,sha):
    raw=path.read_bytes()
    assert 0<len(raw)<=262144 and hashlib.sha256(raw).hexdigest()==sha
    return raw


def tight_red(call):
    try:call()
    except ValueError as error:
        assert str(error)=='Native effective parameter differs'
        return dict(type=type(error).__name__,message=str(error),same_original_symptom=True)
    raise AssertionError('Original bug did not reproduce')


def main():
    raw=CAPTURE.read_bytes();assert len(raw)<=262144
    capture=json.loads(raw);spec=capture['expected_spec'];params=capture['actual_params']
    contract=types.ModuleType('saved_pure_original_contract')
    exec(compile(exact(CONTRACT,CONTRACT_SHA),str(CONTRACT),'exec',dont_inherit=True),contract.__dict__)
    source=ast.parse(exact(PREDICTIONS,PREDICTIONS_SHA),filename=str(PREDICTIONS))
    nodes=[node for node in source.body if isinstance(node,ast.FunctionDef) and node.name in {'_same','verify_model'}]
    assert [node.name for node in nodes]==['_same','verify_model']
    original=types.ModuleType('saved_pure_original_verifier');original.__dict__.update(h=contract,math=math,struct=struct)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(PREDICTIONS),'exec',dont_inherit=True),original.__dict__)
    class SavedModel:
        tree_count_=capture['native_metadata']['tree_count']
        feature_names_=capture['native_metadata']['feature_names']
        def get_cat_feature_indices(self):return capture['native_metadata']['cat_features']
        def get_text_feature_indices(self):return capture['native_metadata']['text_features']
        def get_embedding_feature_indices(self):return capture['native_metadata']['embedding_features']
        def get_all_params(self):return params
    result=dict(version=1,scope='saved_params_pure_minimisation_only_no_fix',
        capture_sha256=hashlib.sha256(raw).hexdigest(),native_imports=0,native_loads=0,
        predictions=0,fits=0,source_Y_opens=0,protected_code_sha256=PREDICTIONS_SHA,
        original_verify_model=tight_red(lambda:original.verify_model(SavedModel(),spec)),
        full_parameter_dict=tight_red(lambda:original._same(spec['effective_parameters'],params)),
        minimal_single_scalar=tight_red(lambda:original._same(spec['effective_parameters']['bayesian_matrix_reg'],
            params['bayesian_matrix_reg'],('bayesian_matrix_reg',))),
        minimal_input=dict(path=['bayesian_matrix_reg'],expected=spec['effective_parameters']['bayesian_matrix_reg'],
            actual=params['bayesian_matrix_reg']),fix_applied=False)
    out=Path('/tmp/tlab-018-native-param-saved-pure-loop-v1-results.json')
    with out.open('x') as handle:json.dump(result,handle,indent=2)
    print('RED_REPRODUCED three exact protected-code seams; minimum one float pair; native loads0')


if __name__=='__main__':main()
