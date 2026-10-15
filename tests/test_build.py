"""Unit tests on the tiny synthetic fixture (no external artifacts)."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from sql_orient import build as buildmod
from sql_orient import linkage, scip as scipmod
from sql_orient import sql as sqlmod

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'mini')
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def preserved_public_inputs():
    paths = [Path(FIX) / name for name in ('graph.json', 'scip.json')]
    before = [p.read_bytes() for p in paths]
    yield
    assert [p.read_bytes() for p in paths] == before


def mini_build(path, with_scip):
    return buildmod.build(os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json'),
                          os.path.join(FIX, 'scip.json') if with_scip else None, str(path))


def assert_mode(path, diag, with_scip):
    meta = dict(sqlmod.run(str(path), 'SELECT key,value FROM meta')[1])
    if diag is not None:
        assert diag['meta'] == meta
    assert meta['build.mode'] == ('graphify+scip' if with_scip else 'graphify-only')
    assert meta['scip.status'] == ('indexed' if with_scip else 'not-supplied')
    assert meta['link.status'] == ('completed' if with_scip else 'not-run')
    assert meta['codeindex.version'] == '0.2.0'
    assert meta['codeindex.schema_version'] == '2'
    assert meta['scip.coordinate_normalization_version'] == '1'
    assert meta['graph.sha256'] == buildmod.sha256_file(os.path.join(FIX, 'graph.json'))
    assert meta['repo.source_identity_status'] == meta['inputs.source_alignment_status'] == 'unverified'
    counts = sqlmod.run(str(path), 'SELECT (SELECT COUNT(*) FROM g_nodes),'
                        '(SELECT COUNT(*) FROM g_edges),(SELECT COUNT(*) FROM s_documents),'
                        '(SELECT COUNT(*) FROM s_occurrences),(SELECT COUNT(*) FROM s_symbols),'
                        '(SELECT COUNT(*) FROM links)')[1]
    assert counts == [(15, 7, 2, 28, 2, 13) if with_scip else (15, 7, 0, 0, 0, 0)]
    if with_scip:
        assert meta['scip.path'] == os.path.abspath(os.path.join(FIX, 'scip.json'))
        assert meta['scip.sha256'] == buildmod.sha256_file(os.path.join(FIX, 'scip.json'))
        assert meta['link.decl_matched'] == '11' and meta['link.file_matched'] == '2'
    else:
        assert all(meta[key] == '' for key in ('scip.path', 'scip.sha256', 'scip.tool',
                                             'scip.tool_version', 'scip.project_root'))
        assert meta['scip.packages'] == '[]'
        assert meta['import.s_documents'] == meta['import.s_occurrences'] == '0'
        for key in ('decl_matched', 'file_matched', 'unmatched', 'ambiguous', 'skipped_nondecl'):
            assert meta['link.' + key] == '0'
            if diag is not None:
                assert type(diag[key]) is int and diag[key] == 0
        if diag is not None:
            assert diag['unmatched_ids'] == []


@pytest.mark.parametrize('with_scip', [False, True], ids=['graphify-only', 'paired'])
@pytest.mark.parametrize('style', ['positional', 'revision-positional', 'keyword'])
def test_build_call_compatibility_and_metadata(tmp_path, with_scip, style):
    path = tmp_path / 'index.db'
    repo, graph = os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json')
    scip = os.path.join(FIX, 'scip.json') if with_scip else None
    if style == 'positional':
        diag = buildmod.build(repo, graph, scip, str(path))
    elif style == 'revision-positional':
        diag = buildmod.build(repo, graph, scip, str(path), 'public-fixture-claim')
        assert diag['meta']['repo.revision'] == 'public-fixture-claim'
        assert diag['meta']['repo.revision_status'] == 'supplied-by-caller'
    else:
        diag = buildmod.build(repo=repo, graph_path=graph, scip_path=scip,
                              db_path=str(path), revision=None)
    assert_mode(path, diag, with_scip)


def test_three_positional_arguments_are_not_reinterpreted(tmp_path):
    target = tmp_path / 'index.db'
    with pytest.raises(TypeError, match='db_path'):
        buildmod.build(os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json'), str(target))
    assert not target.exists()


@pytest.mark.parametrize('with_scip', [False, True], ids=['graphify-only', 'paired'])
def test_cli_construction_modes(tmp_path, with_scip):
    path = tmp_path / 'é ? # %.db'
    args = [sys.executable, '-m', 'sql_orient', 'build', '--repo', os.path.join(FIX, 'repo'),
            '--graph', os.path.join(FIX, 'graph.json'), '--db', str(path)]
    if with_scip:
        args += ['--scip', os.path.join(FIX, 'scip.json')]
    process = subprocess.run(args, capture_output=True, cwd=ROOT,
                             env=dict(os.environ, PYTHONPATH=str(ROOT / 'src'),
                                      PYTHONDONTWRITEBYTECODE='1'))
    assert process.returncode == 0 and not process.stderr
    assert_mode(path, None, with_scip)
    assert sqlmod.run(str(path), "SELECT source FROM g_edges WHERE target='mod_a_alpha' "
                     'ORDER BY id')[1] == [('mod_b_beta',), ('mod_b_beta',)]


def test_structural_mode_has_no_semantic_work(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('SCIP work must not run when no input was supplied')

    for name in ('load_index', 'package_versions', 'link_all', 'decode_range'):
        monkeypatch.setattr(buildmod, name, forbidden)
    monkeypatch.setattr(scipmod.shutil, 'which', lambda _: None)
    original_hash = buildmod.sha256_file
    def graph_hash_only(path):
        assert path == os.path.join(FIX, 'graph.json')
        return original_hash(path)
    monkeypatch.setattr(buildmod, 'sha256_file', graph_hash_only)
    path = tmp_path / 'structural.db'
    diag = mini_build(path, False)
    assert_mode(path, diag, False)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['structural.db']


def test_identical_structural_rows_and_schema_between_modes(tmp_path):
    structural, paired = tmp_path / 'structural.db', tmp_path / 'paired.db'
    mini_build(structural, False)
    mini_build(paired, True)
    for query in ('SELECT * FROM g_nodes ORDER BY id', 'SELECT * FROM g_edges ORDER BY id',
                  'SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name'):
        assert sqlmod.run(str(structural), query) == sqlmod.run(str(paired), query)
    graph = json.loads((Path(FIX) / 'graph.json').read_text())
    nodes = {row[0]: row for row in sqlmod.run(str(structural), 'SELECT * FROM g_nodes')[1]}
    for node in graph['nodes']:
        assert nodes[node['id']][1:6] == tuple(node.get(k) for k in
                                              ('label', 'source_file', 'source_location', 'file_type', 'community'))
        assert json.loads(nodes[node['id']][-1]) == {k:v for k,v in node.items() if k not in buildmod.NODE_COLS}
    edges = sqlmod.run(str(structural), 'SELECT source,target,relation,context,source_file,source_location,attrs '
                       'FROM g_edges ORDER BY id')[1]
    for row, edge in zip(edges, graph['links']):
        assert row[:-1] == tuple(edge.get(k) for k in
                                 ('source', 'target', 'relation', 'context', 'source_file', 'source_location'))
        assert json.loads(row[-1]) == {k:v for k,v in edge.items() if k not in buildmod.EDGE_COLS}


def test_supplied_zero_document_index_is_indexed(tmp_path):
    # A real, explicitly supplied zero-population input, not a structural-mode workaround.
    index = json.loads((Path(FIX) / 'scip.json').read_text())
    index['documents'] = []
    supplied = tmp_path / 'supplied-zero-documents.json'
    supplied.write_text(json.dumps(index), encoding='utf-8')
    before = supplied.read_bytes()
    target = tmp_path / 'paired-zero.db'
    diag = buildmod.build(os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json'),
                          str(supplied), str(target))
    assert diag['meta']['build.mode'] == 'graphify+scip'
    assert diag['meta']['scip.status'] == 'indexed' and diag['meta']['link.status'] == 'completed'
    assert diag['meta']['scip.sha256'] == hashlib.sha256(before).hexdigest()
    assert diag['meta']['scip.path'] == str(supplied.resolve())
    assert diag['meta']['import.s_documents'] == diag['meta']['import.s_occurrences'] == '0'
    assert diag['unmatched'] == 13 and diag['skipped_nondecl'] == 2
    assert len(diag['unmatched_ids']) == 13
    assert sqlmod.run(str(target), 'SELECT COUNT(*) FROM s_symbols')[1] == [(0,)]
    assert supplied.read_bytes() == before


@pytest.mark.parametrize('with_scip', [False, True])
def test_mode_overwrite_refusal_precedes_input_loading(tmp_path, with_scip, monkeypatch):
    path = tmp_path / 'protected.db'
    mini_build(path, True)
    before = path.read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError('no input loading before overwrite refusal')
    monkeypatch.setattr(buildmod, 'load_index', forbidden)
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        buildmod.build(str(tmp_path), 'missing-graph.json', 'missing.scip' if with_scip else None, str(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize('with_scip', [False, True])
@pytest.mark.parametrize('problem', ['missing', 'malformed', 'null', 'duplicate'])
def test_graph_input_failure_and_cleanup(tmp_path, with_scip, problem, monkeypatch):
    graph = tmp_path / 'graph.json'
    if problem == 'malformed':
        graph.write_text('{')
    elif problem == 'null':
        graph.write_text('null')
    elif problem == 'duplicate':
        data = json.loads((Path(FIX) / 'graph.json').read_text())
        data['nodes'].append(data['nodes'][0])
        graph.write_text(json.dumps(data))
    before = graph.read_bytes() if graph.exists() else None
    path = tmp_path / 'failed.db'
    opened = []
    original_connect = sqlite3.connect
    def connect_output(name, *args, **kwargs):
        opened.append(name)
        return original_connect(name, *args, **kwargs)
    monkeypatch.setattr(buildmod.sqlite3, 'connect', connect_output)
    cause, message = {'missing': (FileNotFoundError, 'No such file'),
                      'malformed': (json.JSONDecodeError, 'invalid JSON at line'),
                      'null': (type(None), 'expected a JSON object'),
                      'duplicate': (sqlite3.IntegrityError, r'nodes\[16\]: UNIQUE')}[problem]
    with pytest.raises(RuntimeError, match='Graphify input .*' + message) as caught:
        buildmod.build(os.path.join(FIX, 'repo'), str(graph),
                       os.path.join(FIX, 'scip.json') if with_scip else None, str(path))
    assert isinstance(caught.value.__cause__, cause)
    assert opened == ([str(path)] if problem == 'duplicate' else [])
    assert not path.exists() and not Path(str(path) + '-journal').exists()
    assert (graph.read_bytes() if graph.exists() else None) == before


@pytest.mark.parametrize('problem', ['missing', 'malformed', 'unreadable', 'unsupported', 'null', 'empty-string'])
def test_explicit_bad_scip_never_falls_back(tmp_path, problem, monkeypatch):
    monkeypatch.setattr(scipmod.shutil, 'which', lambda _: None)
    supplied = tmp_path / 'supplied.json'
    if problem == 'malformed':
        supplied.write_text('{')
    elif problem == 'unreadable':
        supplied.mkdir()  # Not readable as a JSON file, even with privileged test execution.
    elif problem == 'unsupported':
        supplied = tmp_path / 'unsupported.scip'
        supplied.write_bytes(b'not a SCIP index')
    elif problem == 'null':
        supplied.write_text('null')
    value = '' if problem == 'empty-string' else str(supplied)
    before = supplied.read_bytes() if supplied.is_file() else None
    path = tmp_path / 'failed.db'
    with pytest.raises(RuntimeError, match='SCIP input'):
        buildmod.build(os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json'), value, str(path))
    assert not path.exists() and not Path(str(path) + '-journal').exists()
    assert (supplied.read_bytes() if supplied.is_file() else None) == before


@pytest.mark.parametrize('problem', ['missing', 'malformed', 'null'])
def test_cli_explicit_bad_scip_fails_without_output(tmp_path, problem):
    supplied = tmp_path / 'supplied.json'
    if problem != 'missing':
        supplied.write_text('{' if problem == 'malformed' else 'null')
    before = supplied.read_bytes() if supplied.exists() else None
    path = tmp_path / 'failed.db'
    process = subprocess.run(
        [sys.executable, '-m', 'sql_orient', 'build', '--repo', os.path.join(FIX, 'repo'),
         '--graph', os.path.join(FIX, 'graph.json'), '--scip', str(supplied), '--db', str(path)],
        capture_output=True, cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1'))
    assert process.returncode == 1 and process.stdout == b''
    assert process.stderr.startswith(b'python -m sql_orient: error: SCIP input ')
    assert str(supplied).encode() in process.stderr and b'Traceback' not in process.stderr
    assert not path.exists() and not Path(str(path) + '-journal').exists()
    assert (supplied.read_bytes() if supplied.exists() else None) == before


@pytest.mark.parametrize('case', ['observed', 'caller-match', 'unknown', 'supplied', 'nested', 'mismatch', 'dirty'])
def test_structural_revision_and_alignment_contract(tmp_path, case):
    repo = tmp_path / 'repo'
    head = None
    if case in ('observed', 'caller-match', 'mismatch', 'dirty', 'nested'):
        head = source_checkout(repo)
        if case == 'nested':
            repo = repo / 'export'
            repo.mkdir()
            head = None
        elif case == 'dirty':
            (repo / 'source.py').write_text('VALUE = 2\n')
    else:
        repo.mkdir()
    revision = head if case == 'caller-match' else ('other-revision' if case in ('supplied', 'mismatch') else None)
    path = tmp_path / 'index.db'
    if case == 'mismatch':
        with pytest.raises(RuntimeError, match='revision mismatch'):
            buildmod.build(str(repo), os.path.join(FIX, 'graph.json'), None, str(path), revision)
        assert not path.exists()
        return
    diag = buildmod.build(str(repo), os.path.join(FIX, 'graph.json'), None, str(path), revision)
    meta = diag['meta']
    status = {'observed':'observed-git-head', 'caller-match':'caller-matches-git-head',
              'unknown':'unknown', 'supplied':'supplied-by-caller', 'nested':'unknown',
              'dirty':'observed-git-head'}[case]
    assert meta['repo.revision_status'] == status
    assert meta['repo.revision'] == (revision or head or '')
    assert meta['repo.git_head'] == (head or '')
    assert_mode(path, diag, False)


@pytest.fixture()
def db_path(tmp_path):
    out = str(tmp_path / 'mini.db')
    buildmod.build(os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json'),
                   os.path.join(FIX, 'scip.json'), out)
    return out


def connect(db_path):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return db


def test_counts_preserved(db_path):
    db = connect(db_path)
    assert db.execute('SELECT COUNT(*) FROM g_nodes').fetchone()[0] == 15
    assert db.execute('SELECT COUNT(*) FROM g_edges').fetchone()[0] == 7
    assert db.execute('SELECT COUNT(*) FROM s_documents').fetchone()[0] == 2
    assert db.execute('SELECT COUNT(*) FROM s_occurrences').fetchone()[0] == 28
    assert db.execute('SELECT COUNT(*) FROM s_symbols').fetchone()[0] == 2


def test_edge_multiplicity_and_direction(db_path):
    db = connect(db_path)
    n = db.execute("SELECT COUNT(*) FROM g_edges WHERE source='mod_b_beta'"
                   " AND target='mod_a_alpha' AND relation='calls'").fetchone()[0]
    assert n == 2
    n = db.execute("SELECT COUNT(*) FROM g_edges WHERE source='mod_a_alpha'"
                   " AND target='mod_b_beta'").fetchone()[0]
    assert n == 0


def test_scip_roles_ranges_locals(db_path):
    db = connect(db_path)
    assert db.execute('SELECT roles FROM s_occurrences WHERE doc=? AND line1=? AND col0=?',
                      ('mod_b.py', 2, 18)).fetchone()[0] == 10
    assert db.execute("SELECT COUNT(*) FROM s_occurrences WHERE symbol LIKE 'local %'").fetchone()[0] == 6
    row = db.execute("SELECT enc_line0,enc_col0,enc_line1,enc_col1 FROM s_occurrences"
                     " WHERE symbol LIKE '%/K#' AND roles=1").fetchone()
    assert tuple(row) == (12, 0, 14, 16)
    row = db.execute("SELECT documentation FROM s_symbols WHERE symbol LIKE '%/alpha().'"
                     ).fetchone()[0]
    assert 'def alpha' in row
    row = db.execute("SELECT relationships FROM s_symbols WHERE symbol LIKE '%/J#'").fetchone()[0]
    assert 'is_implementation' in row and '/K#' in row


def test_linkage_matches(db_path):
    db = connect(db_path)
    assert db.execute("SELECT COUNT(*) FROM links WHERE rule='decl:file+line+name'").fetchone()[0] == 11
    assert db.execute("SELECT COUNT(*) FROM links WHERE rule='file:path'").fetchone()[0] == 2
    km = db.execute("SELECT s_symbol FROM links WHERE g_id='mod_a_k_m'").fetchone()[0]
    jm = db.execute("SELECT s_symbol FROM links WHERE g_id='mod_a_j_m'").fetchone()[0]
    assert km != jm and km.endswith('/K#m().') and jm.endswith('/J#m().')
    inner = db.execute("SELECT s_symbol FROM links WHERE g_id='mod_a_outer_inner'").fetchone()[0]
    assert inner.endswith('/outer().inner().')
    deco = db.execute("SELECT s_symbol FROM links WHERE g_id='mod_a_decorated'").fetchone()[0]
    assert deco.endswith('/decorated().')
    assert db.execute("SELECT COUNT(*) FROM links WHERE s_symbol LIKE '%CONSTANT%'").fetchone()[0] == 0


def test_unmatched_and_skipped_reported(tmp_path):
    out = str(tmp_path / 'mini.db')
    diag = buildmod.build(os.path.join(FIX, 'repo'), os.path.join(FIX, 'graph.json'),
                          os.path.join(FIX, 'scip.json'), out)
    assert diag['decl_matched'] == 11 and diag['file_matched'] == 2
    assert diag['unmatched'] == 0 and diag['ambiguous'] == 0
    assert diag['skipped_nondecl'] == 2  # rationale + location-less stub


def test_ambiguous_stays_unlinked():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE g_nodes(id TEXT, label TEXT, source_file TEXT, source_location TEXT, file_type TEXT, attrs TEXT)')
    db.execute('CREATE TABLE s_occurrences(doc TEXT, line1 INTEGER, symbol TEXT, roles INTEGER)')
    db.execute('CREATE TABLE links(g_id TEXT PRIMARY KEY, s_symbol TEXT, s_doc TEXT, rule TEXT)')
    db.execute("INSERT INTO g_nodes VALUES ('a_f','f()','a.py','L1','code','{}')")
    db.execute("INSERT INTO s_occurrences VALUES ('a.py',1,'a b c d p/f().',1)")
    db.execute("INSERT INTO s_occurrences VALUES ('a.py',1,'a b c d p/f().',1)")
    diag = linkage.link_all(db)
    assert diag['ambiguous'] == 1
    assert db.execute('SELECT COUNT(*) FROM links').fetchone()[0] == 0


def test_descriptor_grammar():
    assert scipmod.parse_definition_symbol('local 3') is None
    assert scipmod.parse_definition_symbol('a b c d `p`/f().(x)') is None
    assert scipmod.parse_definition_symbol('a b c d `p`/K#m().') == ('p/K#', 'm', '().')
    assert scipmod.parse_definition_symbol('a b c d `p`/o().i().') == ('p/o().', 'i', '().')
    assert scipmod.parse_definition_symbol('a b c d p/C#') == ('p', 'C', '#')


def revision_build(repo, db_path, revision=None):
    return buildmod.build(str(repo), os.path.join(FIX, 'graph.json'),
                          os.path.join(FIX, 'scip.json'), str(db_path), revision)


def source_checkout(path):
    path.mkdir()
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    (path / 'source.py').write_text('VALUE = 1\n')
    subprocess.run(['git', '-C', str(path), 'add', 'source.py'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'source'], check=True)
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


def test_standalone_checkout_head_is_observed_not_source_verified(tmp_path):
    repo = tmp_path / 'repo'
    head = source_checkout(repo)
    meta = revision_build(repo, tmp_path / 'a.db')['meta']
    assert meta['repo.revision'] == meta['repo.git_head'] == head
    assert meta['repo.revision_status'] == 'observed-git-head'
    assert meta['repo.source_identity_status'] == 'unverified'
    assert meta['inputs.source_alignment_status'] == 'unverified'
    meta = revision_build(repo, tmp_path / 'b.db', head)['meta']
    assert meta['repo.revision_status'] == 'caller-matches-git-head'
    assert meta['repo.source_identity_status'] == 'unverified'


def test_nested_source_does_not_inherit_enclosing_git_head(tmp_path):
    outer = tmp_path / 'outer'
    source_checkout(outer)
    snapshot = outer / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'source.py').write_text('DIFFERENT = True\n')
    assert buildmod.git_head(str(snapshot)) is None
    meta = revision_build(snapshot, tmp_path / 'a.db')['meta']
    assert meta['repo.revision'] == meta['repo.git_head'] == ''
    assert meta['repo.revision_status'] == 'unknown'
    meta = revision_build(snapshot, tmp_path / 'b.db', 'upstream-parent')['meta']
    assert meta['repo.revision'] == 'upstream-parent'
    assert meta['repo.revision_status'] == 'supplied-by-caller'


def test_caller_revision_for_non_git_snapshot_is_a_claim(tmp_path):
    repo = tmp_path / 'export'
    repo.mkdir()
    meta = revision_build(repo, tmp_path / 'a.db', 'upstream-parent')['meta']
    assert meta['repo.revision'] == 'upstream-parent'
    assert meta['repo.revision_status'] == 'supplied-by-caller'
    assert meta['repo.git_head'] == ''
    assert meta['repo.source_identity_status'] == 'unverified'


def test_genuine_checkout_revision_mismatch_is_rejected(tmp_path):
    repo = tmp_path / 'repo'
    source_checkout(repo)
    with pytest.raises(RuntimeError, match='mismatch'):
        revision_build(repo, tmp_path / 'a.db', 'other-rev')
    assert not (tmp_path / 'a.db').exists()


def test_unknown_revision_without_reliable_head(tmp_path):
    repo = tmp_path / 'export'
    repo.mkdir()
    meta = revision_build(repo, tmp_path / 'a.db')['meta']
    assert meta['repo.revision'] == ''
    assert meta['repo.revision_status'] == 'unknown'
    # An unborn checkout is also not a reliable revision.
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    assert buildmod.git_head(str(repo)) is None


def test_dirty_source_and_independent_producers_are_not_verified(tmp_path):
    repo = tmp_path / 'repo'
    head = source_checkout(repo)
    (repo / 'source.py').write_text('VALUE = 2\n')
    meta = revision_build(repo, tmp_path / 'a.db', head)['meta']
    assert meta['repo.revision_status'] == 'caller-matches-git-head'
    assert meta['repo.source_identity_status'] == 'unverified'
    assert meta['inputs.source_alignment_status'] == 'unverified'
    assert meta['graph.sha256'] == buildmod.sha256_file(os.path.join(FIX, 'graph.json'))
    assert meta['scip.sha256'] == buildmod.sha256_file(os.path.join(FIX, 'scip.json'))


def test_sql_read_only(db_path):
    cols, rows = sqlmod.run(db_path, 'SELECT COUNT(*) FROM g_nodes')
    assert rows == [(15,)]
    with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
        sqlmod.run(db_path, 'DELETE FROM g_nodes')
    with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
        sqlmod.run(db_path, 'CREATE TABLE evil(x)')


def test_composed_query(db_path):
    cols, rows = sqlmod.run(
        db_path,
        "SELECT e.source_location, o.col0 FROM g_edges e "
        "JOIN links l ON l.g_id = e.target "
        "JOIN s_occurrences o ON o.symbol = l.s_symbol "
        "WHERE e.target='mod_a_alpha' AND e.relation='calls' "
        "AND o.doc = e.source_file "
        "AND o.line1 = CAST(SUBSTR(e.source_location, 2) AS INT)")
    assert len(rows) == 2  # both duplicate call edges corroborated at mod_b.py:6
    assert all(r[0] == 'L6' and r[1] == 11 for r in rows)
