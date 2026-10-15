"""Graphify stores relationships under `links` (clustered writer) or `edges` (raw --no-cluster writer)."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sql_orient import build, sql

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/mini'
FIXTURE = json.loads((FIX / 'graph.json').read_text())
CALLERS = (ROOT / 'examples/callers.sql').read_text()
RELATIONSHIPS = (ROOT / 'examples/relationships.sql').read_text()
NODE = {'id': 'n1', 'label': 'f()', 'source_file': 'mod_a.py', 'source_location': 'L1'}


def raw_export(graph):
    """Shape of a raw --no-cluster export: `edges`, no clustering metadata, token counters."""
    raw = {k: v for k, v in graph.items() if k not in ('links', 'graph', 'directed', 'multigraph')}
    return dict(raw, edges=graph['links'], input_tokens=0, output_tokens=0)


def write(tmp_path, name, graph):
    path = tmp_path / name
    path.write_text(json.dumps(graph))
    return path


def snapshot(db):
    rows = lambda query: sql.run(db, query)[1]
    return {'nodes': rows('SELECT * FROM g_nodes ORDER BY id'), 'edges': rows('SELECT * FROM g_edges ORDER BY id'),
            'links': rows('SELECT * FROM links ORDER BY g_id'), 'callers': rows(CALLERS),
            'relationships': rows(RELATIONSHIPS)}


@pytest.mark.parametrize('scip', [False, True], ids=['graphify-only', 'paired'])
def test_edges_key_imports_identically_to_links(tmp_path, scip):
    supplied_scip = str(FIX / 'scip.json') if scip else None
    clustered = build.build(str(FIX / 'repo'), str(write(tmp_path, 'links.json', FIXTURE)),
                            supplied_scip, str(tmp_path / 'links.db'))
    raw = build.build(str(FIX / 'repo'), str(write(tmp_path, 'edges.json', raw_export(FIXTURE))),
                      supplied_scip, str(tmp_path / 'edges.db'))
    # Identity, input order, direction, duplicates, attributes and provenance all survive.
    assert snapshot(str(tmp_path / 'edges.db')) == snapshot(str(tmp_path / 'links.db'))
    assert raw['meta']['import.g_edges'] == clustered['meta']['import.g_edges'] == '7'
    assert [raw[k] for k in ('decl_matched', 'file_matched', 'unmatched', 'ambiguous')] == \
           [clustered[k] for k in ('decl_matched', 'file_matched', 'unmatched', 'ambiguous')]
    assert sql.run(str(tmp_path / 'edges.db'), RELATIONSHIPS)[1] == [
        ('incoming', 'beta()', 'calls', 'alpha()', 'mod_b.py', 'L6'),
        ('incoming', 'beta()', 'calls', 'alpha()', 'mod_b.py', 'L6'),
        ('outgoing', 'alpha()', 'calls', 'helper()', 'mod_a.py', 'L6')]
    assert raw['meta']['graph.graphify_version'] == ''  # Raw exports carry no producer version.


def test_identical_links_and_edges_are_imported_once(tmp_path):
    graph = dict(FIXTURE, edges=FIXTURE['links'])
    diag = build.build(str(FIX / 'repo'), str(write(tmp_path, 'both.json', graph)), None, str(tmp_path / 'both.db'))
    assert diag['meta']['import.g_edges'] == '7'


def test_empty_edges_array_is_valid(tmp_path):
    diag = build.build(str(FIX / 'repo'), str(write(tmp_path, 'g.json', {'nodes': [NODE], 'edges': []})),
                       None, str(tmp_path / 'g.db'))
    assert diag['meta']['import.g_edges'] == '0'


LINK = {'source': 'n1', 'target': 'n1', 'relation': 'calls'}


@pytest.mark.parametrize('graph, reason', [
    (dict(FIXTURE, edges=[]), 'links and edges both present but differ'),
    (dict(FIXTURE, edges=FIXTURE['links'][:-1]), 'links and edges both present but differ'),
    (dict(FIXTURE, edges=FIXTURE['links'][::-1]), 'links and edges both present but differ'),
    ({'nodes': [NODE], 'edges': {}}, 'edges must be an array of objects'),
    ({'nodes': [NODE], 'edges': [1]}, 'edges must be an array of objects'),
    ({'nodes': [NODE], 'edges': [{'target': 'n1'}]}, 'edges[1].source must be a string'),
    ({'nodes': [NODE], 'edges': [LINK, dict(LINK, target=5)]}, 'edges[2].target must be a string'),
    ({'nodes': [NODE], 'edges': [dict(LINK, relation=['calls'])]}, 'edges[1].relation must be a string'),
    ({'nodes': [NODE], 'links': [dict(LINK, source=None)]}, 'links[1].source must be a string'),
])
@pytest.mark.parametrize('scip', [False, True], ids=['graphify-only', 'paired'])
def test_conflicting_or_malformed_edge_arrays_fail_cleanly(tmp_path, graph, reason, scip):
    supplied = write(tmp_path, 'graph.json', graph)
    target = tmp_path / 'failed.db'
    extra = ['--scip', str(FIX / 'scip.json')] if scip else []
    with pytest.raises(RuntimeError, match='Graphify input') as caught:
        build.build(str(FIX / 'repo'), str(supplied), str(FIX / 'scip.json') if scip else None, str(target))
    assert reason in str(caught.value)
    proc = subprocess.run([sys.executable, '-m', 'sql_orient', 'build', '--repo', str(FIX / 'repo'),
                           '--graph', str(supplied), *extra, '--db', str(target)],
                          capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')))
    assert proc.returncode == 1 and proc.stdout == b'' and b'Traceback' not in proc.stderr
    assert reason.encode() in proc.stderr and len(proc.stderr.splitlines()) == 1
    assert not list(tmp_path.glob('failed.db*'))
