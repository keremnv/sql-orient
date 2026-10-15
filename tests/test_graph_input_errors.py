"""Malformed Graphify exports fail with one actionable line and no output database."""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import pytest
from sql_orient import build

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/mini'
NODE = {'id': 'n1', 'label': 'f()', 'source_file': 'mod_a.py', 'source_location': 'L1'}


@pytest.mark.parametrize('payload, reason, cause', [
    (None, 'No such file', FileNotFoundError),
    (b'{', 'invalid JSON at line', json.JSONDecodeError),
    (b'\xff', 'not valid UTF-8', UnicodeDecodeError),
    (b'null', 'expected a JSON object', type(None)),
    (b'[]', 'expected a JSON object', type(None)),
    (b'{"nodes":null}', 'nodes must be an array of objects', type(None)),
    (b'{"nodes":[1]}', 'nodes must be an array of objects', type(None)),
    (b'{"nodes":[],"links":{}}', 'links must be an array of objects', type(None)),
    (json.dumps({'nodes': [NODE, NODE]}).encode(), r'nodes[2]: UNIQUE', sqlite3.IntegrityError),
    (json.dumps({'nodes': [dict(NODE, source_file={'x': 1})]}).encode(), 'nodes[1]:', sqlite3.Error),
    (json.dumps({'nodes': [NODE], 'links': [{'source': 'n1', 'target': 'n1', 'context': {'x': 1}}]}).encode(),
     'links[1]:', sqlite3.Error),
    (json.dumps({'nodes': [NODE], 'edges': [{'source': 'n1', 'target': 'n1', 'context': {'x': 1}}]}).encode(),
     'edges[1]:', sqlite3.Error),
    (b'{"hyperedges":5}', 'hyperedges must be an array', type(None)),
    (b'{"graph":[]}', 'graph must be an object', type(None)),
])
def test_invalid_graph_programmatic_and_cli(tmp_path, payload, reason, cause):
    supplied = tmp_path/'graph.json'
    if payload is not None:
        supplied.write_bytes(payload)
    target = tmp_path/'failed.db'
    with pytest.raises(RuntimeError) as caught:
        build.build(str(FIX/'repo'), str(supplied), None, str(target))
    assert str(supplied) in str(caught.value) and reason in str(caught.value)
    assert isinstance(caught.value.__cause__, cause)
    proc = subprocess.run([sys.executable, '-m', 'sql_orient', 'build', '--repo', str(FIX/'repo'),
                           '--graph', str(supplied), '--db', str(target)],
                          capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT/'src')))
    assert proc.returncode == 1 and proc.stdout == b''
    assert b'Traceback' not in proc.stderr
    assert reason.encode() in proc.stderr and len(proc.stderr.splitlines()) == 1
    assert not list(tmp_path.glob('failed.db*'))
    assert (supplied.read_bytes() if payload is not None else None) == payload


@pytest.mark.parametrize('scip', [False, True], ids=['graphify-only', 'paired'])
@pytest.mark.parametrize('graph, reason', [
    ({'nodes': [NODE], 'hyperedges': 5}, 'hyperedges must be an array'),
    ({'nodes': [NODE], 'hyperedges': None}, 'hyperedges must be an array'),
    ({'nodes': [NODE], 'hyperedges': {'a': 1}}, 'hyperedges must be an array'),
    ({'nodes': [NODE], 'hyperedges': 'ab'}, 'hyperedges must be an array'),
    ({'nodes': [NODE], 'graph': []}, 'graph must be an object'),
    ({'nodes': [NODE], 'graph': None}, 'graph must be an object'),
    ({'nodes': [NODE], 'graph': 'x'}, 'graph must be an object'),
    ({'nodes': [NODE, dict(NODE, id='n2', label=None)]}, 'nodes[2].label must be a string'),
    ({'nodes': [{k: v for k, v in NODE.items() if k != 'label'}]}, 'nodes[1].label must be a string'),
    ({'nodes': [dict(NODE, label=5)]}, 'nodes[1].label must be a string'),
])
def test_structural_type_errors_in_both_build_modes(tmp_path, graph, reason, scip):
    supplied = tmp_path/'graph.json'
    supplied.write_text(json.dumps(graph))
    target = tmp_path/'failed.db'
    extra = ['--scip', str(FIX/'scip.json')] if scip else []
    with pytest.raises(RuntimeError, match='Graphify input .*' + re.escape(reason)) as caught:
        build.build(str(FIX/'repo'), str(supplied), str(FIX/'scip.json') if scip else None, str(target))
    assert caught.value.__cause__ is None
    proc = subprocess.run([sys.executable, '-m', 'sql_orient', 'build', '--repo', str(FIX/'repo'),
                           '--graph', str(supplied), *extra, '--db', str(target)],
                          capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT/'src')))
    assert proc.returncode == 1 and proc.stdout == b'' and b'Traceback' not in proc.stderr
    assert reason.encode() in proc.stderr and len(proc.stderr.splitlines()) == 1
    assert not list(tmp_path.glob('failed.db*'))


def test_valid_optional_members_and_fixture_export_unchanged(tmp_path):
    fixture = json.loads((FIX/'graph.json').read_text())
    supplied = tmp_path/'graph.json'
    supplied.write_text(json.dumps(dict(fixture, hyperedges=[{'nodes': ['a', 'b']}], graph={})))
    diag = build.build(str(FIX/'repo'), str(supplied), str(FIX/'scip.json'), str(tmp_path/'ok.db'))
    assert diag['meta']['graph.hyperedges'] == '1' and diag['hyperedges_ignored'] == 1
    assert diag['meta']['import.g_nodes'] == str(len(fixture['nodes']))


def test_valid_graph_without_optional_arrays_still_builds(tmp_path):
    supplied = tmp_path/'graph.json'
    supplied.write_text('{}')
    diag = build.build(str(FIX/'repo'), str(supplied), None, str(tmp_path/'empty.db'))
    assert diag['meta']['import.g_nodes'] == '0' and diag['meta']['import.g_edges'] == '0'
