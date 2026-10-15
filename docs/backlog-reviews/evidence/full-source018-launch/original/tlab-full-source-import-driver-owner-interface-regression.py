"""Pure interface regression from exact accepted owner AST; never imports owner."""
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

OWNER=Path('/Users/mdpospelov/tlab-recsys-2026/scripts/run_source_import.py')
OWNER_SHA='5df50bb2577b4515c5d80a5eaf4a6f2bf18abe344039d1cd22a51a872e1c7653'
PROJECT=OWNER.parent.parent


def accepted_local():
    raw=OWNER.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=OWNER_SHA:
        raise ValueError('Accepted owner source changed')
    tree=ast.parse(raw,str(OWNER))
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {'need','local'}]
    if {node.name for node in nodes}!={'need','local'}:
        raise ValueError('Accepted owner interface fragment missing')
    namespace={'ROOT':PROJECT}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(OWNER),'exec',dont_inherit=True),namespace)
    return namespace['local']


def probe(source):
    module=ModuleType('interface_candidate_not_main')
    module.__file__=str(source)
    sys.modules[module.__name__]=module
    raw=Path(source).read_bytes()
    exec(compile(raw,str(source),'exec',dont_inherit=True),module.__dict__)
    argv=module.command()
    argument=argv[argv.index('--request')+1]
    local=accepted_local()
    with patch.object(Path,'resolve',lambda self:self),patch.object(Path,'is_symlink',return_value=False):
        result=local(argument,existing=False)
    if result!=module.REQUEST:
        raise AssertionError('Accepted local did not resolve fixed staged request')
    return dict(status='PASS_actual_accepted_owner_local_AST',candidate=str(source),
                candidate_sha256=hashlib.sha256(raw).hexdigest(),owner_sha256=OWNER_SHA,
                request_cli_argument=argument,existing=False,
                filesystem_observation_mocked=True,owner_imported=False,owner_launched=False)


if __name__=='__main__':
    print(json.dumps(probe(Path(sys.argv[1])),sort_keys=True))
