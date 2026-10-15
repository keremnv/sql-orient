"""Delivery contracts: exact statement rows, caps, encoding and read-only access."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from sql_orient import build, sql

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / 'tests/fixtures/mini'
THREE = 'WITH x(n) AS (VALUES(1),(2),(3)) SELECT n FROM x ORDER BY n'
CLI_FORMATS = {'cli-default': (), 'cli-tsv': ('--format', 'tsv'),
               'cli-json': ('--format', 'json')}


@pytest.fixture(params=['run', 'run_bounded', *CLI_FORMATS])
def entrypoint(request):
    return request.param


def assert_denied(entrypoint, db, query, params=()):
    if entrypoint in CLI_FORMATS:
        assert params == ()  # The CLI has no parameter-binding flags.
        process = cli(db, query, *CLI_FORMATS[entrypoint])
        assert process.returncode == 1 and process.stdout == b''
        assert process.stderr.startswith(b'python -m sql_orient: error: SQL execution failed: ')
        assert b'not authorized' in process.stderr or b'authorization denied' in process.stderr
        assert b'Traceback' not in process.stderr
    else:
        with pytest.raises(sqlite3.Error, match='not authorized|authorization denied') as error:
            getattr(sql, entrypoint)(db, query, params)
        # Function denial uses SQLITE_ERROR; ordinary denied actions use AUTH.
        if hasattr(error.value, 'sqlite_errorcode'):
            assert error.value.sqlite_errorcode in (sqlite3.SQLITE_AUTH, sqlite3.SQLITE_ERROR)


def assert_read(entrypoint, db, query, columns, rows):
    if entrypoint == 'run':
        assert sql.run(db, query) == (columns, rows)
        return
    if entrypoint == 'run_bounded':
        decoded = result(db, query)
    else:
        process = cli(db, query, *CLI_FORMATS[entrypoint])
        assert process.returncode == 0 and not process.stderr
        if entrypoint != 'cli-json':
            expected = '\t'.join(columns) + '\n'
            expected += ''.join('\t'.join('' if v is None else str(v) for v in row) + '\n'
                                for row in rows)
            assert process.stdout == expected.encode('utf-8')
            return
        decoded = json.loads(process.stdout)
    assert decoded['columns'] == columns and decoded['rows'] == [list(row) for row in rows]
    assert decoded['delivery']['sql_result_exhausted']
    assert decoded['execution']['completion'] == 'observed'


@pytest.fixture
def db_path(tmp_path, request):
    path = tmp_path / 'mini.db'
    scip = str(MINI / 'scip.json') if getattr(request, 'param', True) else None
    build.build(str(MINI / 'repo'), str(MINI / 'graph.json'), scip, str(path))
    return str(path)


def result(db, query, **limits):
    encoded = sql.run_bounded(db, query, **limits)
    decoded = json.loads(encoded)
    assert encoded.endswith(b'\n') and len(encoded) <= limits.get('max_bytes', sql.DEFAULT_MAX_BYTES)
    assert len(decoded['rows']) == decoded['delivery']['rows_emitted']
    assert decoded['delivery']['more_rows'] == (not decoded['delivery']['sql_result_exhausted'])
    assert set(decoded['claims'].values()) == {'unknown'}
    return decoded


def cli(db, query=None, *flags, env=None):
    args = [sys.executable, '-m', 'sql_orient', 'sql', '--db', db]
    if query is not None:
        args += ['--query', query]
    return subprocess.run(args + list(flags), capture_output=True, cwd=ROOT,
                          env=dict(os.environ, PYTHONPATH=str(ROOT / 'src'), **(env or {})))


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_legacy_cli_and_api_unchanged(db_path):
    query = "SELECT 'alpha' AS name, NULL AS missing UNION ALL SELECT 'beta', ''"
    columns, rows = sql.run(db_path, query)
    assert columns == ['name', 'missing'] and rows == [('alpha', None), ('beta', '')]
    for flags in [(), ('--format', 'tsv')]:
        process = cli(db_path, query, *flags)
        assert process.returncode == 0 and process.stdout == b'name\tmissing\nalpha\t\nbeta\t\n'
        assert not process.stderr


def test_small_result_exhausted(db_path):
    decoded = result(db_path, THREE)
    assert decoded['rows'] == [[1], [2], [3]]
    assert decoded['execution']['completion'] == 'observed'
    assert decoded['delivery']['sql_result_exhausted']
    assert decoded['delivery']['limit_reason'] is None


@pytest.mark.parametrize('cap', [0, 1, 2, 3, 5])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_row_caps_and_exact_boundary(db_path, cap):
    decoded = result(db_path, THREE, max_rows=cap)
    assert decoded['rows'] == [[1], [2], [3]][:cap]
    partial = cap < 3
    assert decoded['delivery']['more_rows'] == partial
    assert decoded['delivery']['limit_reason'] == ('max_rows' if partial else None)
    assert decoded['execution']['completion'] == ('unknown' if partial else 'observed')


def test_empty_is_exact_sql_result_not_source_claim(db_path):
    decoded = result(db_path, "SELECT id FROM g_nodes WHERE id='missing'", max_rows=0)
    assert decoded['columns'] == ['id'] and decoded['rows'] == []
    assert decoded['delivery']['sql_result_exhausted']
    assert decoded['claims']['stored_fact_coverage'] == 'unknown'
    assert decoded['claims']['source_correctness'] == 'unknown'


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_explicit_sql_limit_exhaustion_is_not_intent_completeness(db_path):
    decoded = result(db_path, THREE + ' LIMIT 2', max_rows=2)
    assert decoded['rows'] == [[1], [2]]
    assert decoded['delivery']['sql_result_exhausted']
    assert decoded['claims']['logical_query_completeness'] == 'unknown'
    assert len(sql.run(db_path, THREE)[1]) == 3


def test_homonymous_definitions_and_order_not_collapsed(db_path):
    query = "SELECT id,label FROM g_nodes WHERE label='.m()' ORDER BY id"
    decoded = result(db_path, query)
    assert len(decoded['rows']) == 2
    assert decoded['rows'][0][1] == decoded['rows'][1][1] == '.m()'
    assert decoded['rows'][0][0] != decoded['rows'][1][0]
    assert decoded == result(db_path, query)


@pytest.mark.parametrize('cap', [600, 800, 1200])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_byte_cap_preserves_prefix_and_truthful_counts(db_path, cap):
    query = "SELECT id,label,attrs FROM g_nodes ORDER BY id"
    decoded = result(db_path, query, max_rows=100, max_bytes=cap)
    columns, all_rows = sql.run(db_path, query)
    count = decoded['delivery']['rows_emitted']
    assert decoded['columns'] == columns
    assert decoded['rows'] == [list(r) for r in all_rows[:count]]
    assert decoded['delivery']['more_rows'] == (count < len(all_rows))
    assert decoded['delivery']['limit_reason'] == 'max_bytes'


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_large_single_row_withheld_but_execution_observed(db_path):
    decoded = result(db_path, "SELECT printf('%1000000s','x') AS big", max_bytes=1200)
    assert decoded['rows'] == []
    assert decoded['delivery']['more_rows'] and not decoded['delivery']['sql_result_exhausted']
    assert decoded['delivery']['limit_reason'] == 'max_bytes'
    assert decoded['execution']['completion'] == 'observed'


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_exact_utf8_byte_boundary(db_path):
    query = "SELECT 'é' || printf('%100s','x') AS value"
    cap = 2000
    for _ in range(5):  # echoed cap's digit count affects envelope length
        cap = len(sql.run_bounded(db_path, query, max_bytes=cap))
    body = sql.run_bounded(db_path, query, max_bytes=cap)
    assert len(body) == cap and json.loads(body)['delivery']['sql_result_exhausted']
    short = result(db_path, query, max_bytes=cap - 1)
    assert short['rows'] == [] and short['delivery']['limit_reason'] == 'max_bytes'


def test_utf8_special_characters_nulls_duplicate_columns_and_params(db_path):
    text = 'é 😀 tab\t line\n slash\\ quote" nul\0'
    query = 'SELECT ? AS "same", NULL AS "same", ? AS "é\tname"'
    body = sql.run_bounded(db_path, query, (text, ''), max_bytes=2000)
    decoded = json.loads(body)
    assert decoded['columns'] == ['same', 'same', 'é\tname']
    assert decoded['rows'] == [[text, None, '']]
    assert b'\xc3\xa9' in body and b'\xf0\x9f\x98\x80' in body
    assert len(body.splitlines()) == 1
    assert len(body) <= 2000


def test_json_cli_utf8_independent_of_text_stdout_encoding(db_path, tmp_path):
    query_file = tmp_path / 'query.sql'
    query_file.write_text("SELECT 'é 😀' AS value", encoding='utf-8')
    process = cli(db_path, None, '--file', str(query_file), '--format', 'json',
                  env={'PYTHONIOENCODING':'ascii'})
    assert process.returncode == 0
    assert json.loads(process.stdout)['rows'] == [['é 😀']]


@pytest.mark.parametrize('query', ["SELECT x'0001'", 'SELECT 1e999'])
def test_unrepresentable_json_values_fail_without_partial_stdout(db_path, query):
    with pytest.raises(sql.DeliveryError, match='serialization failed'):
        sql.run_bounded(db_path, query)
    process = cli(db_path, query, '--format', 'json')
    assert process.returncode == 1 and process.stdout == b''
    assert b'serialization failed' in process.stderr


def test_metadata_or_column_names_cannot_fit_explicit_error(db_path):
    for query, cap in [('SELECT 1', 1), ('SELECT 1 AS "' + 'é'*2000 + '"', 1200)]:
        process = cli(db_path, query, '--format', 'json', '--max-bytes', str(cap))
        assert process.returncode == 1 and process.stdout == b''
        assert b'byte cap' in process.stderr


@pytest.mark.parametrize('flags', [('--max-rows','1'), ('--format','json','--max-rows','-1'),
                                  ('--format','json','--max-bytes','0')])
def test_bad_cli_caps_fail_explicitly(db_path, flags):
    process = cli(db_path, 'SELECT 1', *flags)
    assert process.returncode == 2 and process.stdout == b''


@pytest.mark.parametrize('limits', [{'max_rows':1.5}, {'max_bytes':True},
                                    {'max_rows':-1}, {'max_bytes':0}])
def test_api_caps_are_validated(db_path, limits):
    with pytest.raises(sql.DeliveryError):
        sql.run_bounded(db_path, 'SELECT 1', **limits)


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_sql_failure_distinct_from_successful_partial_delivery(db_path):
    process = cli(db_path, 'SELECT missing FROM missing', '--format', 'json')
    assert process.returncode == 1 and process.stdout == b''
    assert b'SQL execution failed' in process.stderr
    partial = cli(db_path, THREE, '--format', 'json', '--max-rows', '1')
    assert partial.returncode == 0 and json.loads(partial.stdout)['delivery']['more_rows']


@pytest.mark.parametrize('query', ['', '-- comments only'])
def test_no_statement_is_not_reported_as_an_empty_sql_result(db_path, query):
    process = cli(db_path, query, '--format', 'json')
    assert process.returncode == 1 and process.stdout == b''
    assert b'row-producing' in process.stderr


def test_unknown_execution_completion_does_not_hide_later_error_claim(db_path, monkeypatch):
    original = sql._connect_read_only

    def connect(path):
        db = original(path)

        def fail_later(value):
            if value == 5:
                raise ValueError('late failure')
            return value

        db.create_function('fail_later', 1, fail_later)
        return db

    monkeypatch.setattr(sql, '_connect_read_only', connect)
    query = 'WITH x(n) AS (VALUES(1),(2),(3),(4),(5),(6)) SELECT fail_later(n) FROM x'
    decoded = result(db_path, query, max_rows=1)
    assert decoded['rows'] == [[1]] and decoded['execution']['completion'] == 'unknown'
    with pytest.raises(sqlite3.OperationalError, match='user-defined function'):
        sql.run_bounded(db_path, query, max_rows=10)


def test_new_path_never_fetchalls_or_scans_remaining_rows(db_path, monkeypatch):
    original = sqlite3.connect
    fetched = []

    class Cursor(sqlite3.Cursor):
        def fetchall(self):
            raise AssertionError('new path must not fetchall')

        def fetchone(self):
            fetched.append(1)
            return super().fetchone()

    class Connection(sqlite3.Connection):
        def execute(self, *args):
            return self.cursor(Cursor).execute(*args)

    monkeypatch.setattr(sql.sqlite3, 'connect', lambda *a, **k: original(*a, **k, factory=Connection))
    decoded = result(db_path, THREE, max_rows=1)
    assert len(fetched) == 2 and decoded['delivery']['rows_emitted'] == 1
    fetched.clear()
    decoded = result(db_path,
                     "WITH x(n) AS (VALUES(1),(2),(3)) SELECT printf('%1000000s',n) FROM x",
                     max_bytes=1200)
    # The rejected candidate and its lookahead are both fetched. This is a
    # delivery cap, not a promise to fetch only emitted rows or cap row memory.
    assert len(fetched) == 2 and decoded['delivery']['rows_emitted'] == 0
    assert decoded['execution']['completion'] == 'unknown'


def test_read_only_and_no_unexpected_files_or_database_writes(db_path, tmp_path):
    path = Path(db_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    unwanted = tmp_path / 'unwanted.db'
    queries = ['DELETE FROM g_nodes', 'CREATE TABLE evil(x)', 'PRAGMA query_only=OFF',
               'PRAGMA user_version=1', f"ATTACH DATABASE '{unwanted}' AS other",
               f"VACUUM INTO '{unwanted}'", 'SELECT 1; SELECT 2', 'BEGIN',
               "SELECT load_extension('missing')"]
    for query in queries:
        with pytest.raises(sqlite3.Error):
            sql.run_bounded(db_path, query)
    assert result(db_path, 'PRAGMA table_info(g_nodes)')['delivery']['sql_result_exhausted']
    assert result(db_path, 'PRAGMA TABLE_INFO(g_nodes)')['delivery']['sql_result_exhausted']
    assert result(db_path, 'PRAGMA user_version')['rows'] == [[0]]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not unwanted.exists() and not Path(db_path+'-journal').exists()


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_uniform_attach_denial_replaces_historical_legacy_probe(db_path, tmp_path, entrypoint):
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    destination = tmp_path / 'attached.db'
    assert_denied(entrypoint, db_path, f"ATTACH DATABASE '{destination}' AS other")
    assert not destination.exists()
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_filename_uri_characters(db_path, tmp_path, entrypoint):
    target = tmp_path / 'é ? # %.db'
    shutil.copyfile(db_path, target)
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    assert_read(entrypoint, str(target), 'SELECT COUNT(*) AS n FROM g_nodes', ['n'], [(15,)])
    assert sql.run(target, 'SELECT COUNT(*) FROM g_nodes') == (['COUNT(*)'], [(15,)])
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('api', ['run', 'run_bounded'])
@pytest.mark.parametrize('named', [False, True])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_parameterized_attach_denied(db_path, tmp_path, api, named):
    destination = tmp_path / 'bound attachment.db'
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    placeholder = ':destination' if named else '?'
    params = {'destination': str(destination)} if named else (str(destination),)
    assert_denied(api, db_path, f'ATTACH DATABASE {placeholder} AS other', params)
    assert not destination.exists()
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize('query', [
    'DETACH DATABASE other',
    'DELETE FROM g_nodes', 'DELETE FROM g_nodes WHERE 0',
    "INSERT INTO g_nodes(id) VALUES ('new')", "UPDATE g_nodes SET label='changed'",
    'CREATE TABLE evil(x)', 'CREATE TEMP TABLE evil(x)',
    'CREATE INDEX evil ON g_nodes(label)', 'DROP TABLE g_nodes', 'DROP INDEX i_occ_sym',
    'ALTER TABLE g_nodes ADD COLUMN evil TEXT', 'EXPLAIN DELETE FROM g_nodes',
    'PRAGMA query_only=OFF', 'PRAGMA query_only=ON', 'PRAGMA user_version=1',
    'PRAGMA journal_mode=WAL', 'PRAGMA cache_size', 'PRAGMA cache_size=1',
    'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT other', 'RELEASE other',
    'VACUUM', "SELECT load_extension('missing')", "SELECT LoAd_ExTeNsIoN('missing')",
])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_uniform_mutation_and_permission_denial(db_path, entrypoint, query):
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    assert_denied(entrypoint, db_path, query)
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before
    assert not Path(db_path + '-journal').exists()
    assert sql.run(db_path, 'SELECT COUNT(*) FROM g_nodes')[1] == [(15,)]


@pytest.mark.parametrize('query', ["SELECT fts3_tokenizer('simple')", "SELECT FTS3_Tokenizer('simple')",
                                   "SELECT fts3_tokenizer('x', zeroblob(8))"])
def test_fts3_tokenizer_pointer_function_denied_where_available(db_path, entrypoint, query):
    probe = sqlite3.connect(':memory:')
    try:
        available = probe.execute("SELECT 1 FROM pragma_function_list WHERE name='fts3_tokenizer'").fetchone()
    finally:
        probe.close()
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    if available:
        assert_denied(entrypoint, db_path, query)
    elif entrypoint in CLI_FORMATS:
        assert b'no such function' in cli(db_path, query, *CLI_FORMATS[entrypoint]).stderr
    else:
        with pytest.raises(sqlite3.OperationalError, match='no such function'):
            getattr(sql, entrypoint)(db_path, query)
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize('api', ['run', 'run_bounded'])
def test_fts3_tokenizer_denied_by_name_on_every_build(db_path, api, monkeypatch):
    # Register a stand-in so the policy is exercised even where SQLite omits FTS3.
    original = sqlite3.connect
    def connect(*args, **kwargs):
        db = original(*args, **kwargs)
        db.create_function('fts3_tokenizer', -1, lambda *values: 'pointer')
        return db
    monkeypatch.setattr(sql.sqlite3, 'connect', connect)
    with pytest.raises(sqlite3.Error, match='not authorized'):
        getattr(sql, api)(db_path, "SELECT fts3_tokenizer('simple')")
    assert sql.run(db_path, 'SELECT 1')[1] == [(1,)]


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_vacuum_into_cannot_create_output(db_path, tmp_path, entrypoint):
    destination = tmp_path / 'vacuum.db'
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    assert_denied(entrypoint, db_path, f"VACUUM INTO '{destination}'")
    assert not destination.exists() and not Path(db_path + '-journal').exists()
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize('query,columns,rows', [
    (THREE, ['n'], [(1,), (2,), (3,)]),
    ('VALUES(1),(1),(2)', ['column1'], [(1,), (1,), (2,)]),
    ('WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<3) '
     'SELECT n FROM x ORDER BY n', ['n'], [(1,), (2,), (3,)]),
    ("SELECT target FROM g_edges WHERE source='mod_a_alpha'", ['target'], [('mod_a_helper',)]),
    ("SELECT n.id FROM g_edges e JOIN g_nodes n ON n.id=e.source "
     "WHERE e.target='mod_a_alpha' ORDER BY e.id", ['id'], [('mod_b_beta',), ('mod_b_beta',)]),
    ("SELECT a.source,b.target FROM g_edges a JOIN g_edges b ON a.target=b.source "
     "WHERE a.relation='calls' AND b.relation='calls' ORDER BY a.id,b.id",
     ['source', 'target'], [('mod_b_beta', 'mod_a_helper'), ('mod_b_beta', 'mod_a_helper')]),
    ("SELECT o.doc,o.line1,o.col0 FROM links l JOIN s_occurrences o ON o.symbol=l.s_symbol "
     "WHERE l.g_id='mod_a_alpha' AND o.doc='mod_b.py' AND o.line1=6 ORDER BY o.id",
     ['doc', 'line1', 'col0'], [('mod_b.py', 6, 11)]),
    ("SELECT value FROM meta WHERE key='codeindex.schema_version'", ['value'], [('2',)]),
    ("SELECT name FROM sqlite_schema WHERE type='table' AND name='g_nodes'", ['name'], [('g_nodes',)]),
    ("SELECT name FROM pragma_table_info('g_nodes') ORDER BY cid", ['name'],
     [(name,) for name in ('id', 'label', 'source_file', 'source_location', 'file_type', 'community', 'attrs')]),
    ('PRAGMA query_only', ['query_only'], [(1,)]),
    ('PRAGMA user_version', ['user_version'], [(0,)]),
    ("SELECT 'ATTACH; DROP load_extension' AS 'DROP'; -- ; ATTACH", ['DROP'], [('ATTACH; DROP load_extension',)]),
    ("SELECT NULL AS same,'' AS same UNION ALL SELECT NULL,''", ['same', 'same'], [(None, ''), (None, '')]),
    ('SELECT 1 AS n WHERE 0', ['n'], []),
])
def test_permitted_read_populations_across_entrypoints(db_path, entrypoint, query, columns, rows):
    assert_read(entrypoint, db_path, query, columns, rows)


@pytest.mark.parametrize('query', [
    'PRAGMA table_info(g_nodes)', 'PRAGMA TABLE_XINFO(g_nodes)', 'PRAGMA index_list(g_nodes)',
    'PRAGMA index_info(i_edge_tgt)', 'PRAGMA database_list', 'PRAGMA quick_check',
    'EXPLAIN SELECT id FROM g_nodes',
])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_schema_and_explain_inspection_across_entrypoints(db_path, entrypoint, query):
    # Compare SQLite-native fixture inspection, including engine-dependent EXPLAIN opcodes.
    with sqlite3.connect(db_path) as db:
        cur = db.execute(query)
        columns, rows = [d[0] for d in cur.description], cur.fetchall()
    assert rows
    assert_read(entrypoint, db_path, query, columns, rows)


@pytest.mark.parametrize('api', ['run', 'run_bounded'])
@pytest.mark.parametrize('named', [False, True])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_native_parameter_and_value_compatibility(db_path, api, named):
    query = 'SELECT :value AS same,:missing AS same' if named else 'SELECT ? AS same,? AS same'
    params = {'value': 'é 😀', 'missing': None} if named else ('é 😀', None)
    output = getattr(sql, api)(db_path, query, params)
    if api == 'run':
        assert output == (['same', 'same'], [('é 😀', None)])
        assert sql.run(db_path, "SELECT x'0001',1e999")[1] == [(b'\x00\x01', float('inf'))]
    else:
        decoded = json.loads(output)
        assert decoded['columns'] == ['same', 'same'] and decoded['rows'] == [['é 😀', None]]
    with pytest.raises(sqlite3.ProgrammingError):
        getattr(sql, api)(db_path, query, ())


@pytest.mark.parametrize('query', ['', '  \n ', '-- comments only', '/* comment */', ';'])
def test_empty_statement_legacy_and_json_distinction(db_path, entrypoint, query):
    if entrypoint == 'run':
        assert sql.run(db_path, query) == ([], [])
    elif entrypoint == 'run_bounded':
        with pytest.raises(sql.DeliveryError, match='row-producing'):
            sql.run_bounded(db_path, query)
    else:
        process = cli(db_path, query, *CLI_FORMATS[entrypoint])
        assert process.stdout == b''
        if entrypoint == 'cli-json':
            assert process.returncode == 1 and b'row-producing' in process.stderr
        else:
            assert process.returncode == 0 and not process.stderr


def test_missing_object_drop_is_engine_noop_not_text_blacklist(db_path, entrypoint):
    query = 'DROP TABLE IF EXISTS absent'
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    # Engine versions may request an authorization action even for a no-op.
    try:
        assert sql.run(db_path, query) == ([], [])
    except sqlite3.DatabaseError as error:
        assert 'not authorized' in str(error)
        if hasattr(error, 'sqlite_errorcode'):
            assert error.sqlite_errorcode == sqlite3.SQLITE_AUTH
        assert_denied(entrypoint, db_path, query)
    else:
        test_empty_statement_legacy_and_json_distinction(db_path, entrypoint, query)
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize('query', ['SELECT missing FROM missing', 'SELEC 1', 'SELECT ?',
                                  'SELECT 1; SELECT 2',
                                  'SELECT 1 UNION ALL SELECT abs(-9223372036854775808)'])
def test_sql_and_binding_failures_across_entrypoints(db_path, entrypoint, query):
    if entrypoint in CLI_FORMATS:
        process = cli(db_path, query, *CLI_FORMATS[entrypoint])
        assert process.returncode == 1 and process.stdout == b''
        assert process.stderr.startswith(b'python -m sql_orient: error: SQL execution failed: ')
        assert b'Traceback' not in process.stderr
    else:
        with pytest.raises(sqlite3.Error):
            getattr(sql, entrypoint)(db_path, query)


@pytest.mark.parametrize('api', ['run', 'run_bounded'])
def test_multiple_statement_error_preserves_native_diagnostic_and_cause(db_path, api):
    query = 'SELECT 1; SELECT 2'
    with sqlite3.connect(db_path) as native:
        with pytest.raises((sqlite3.Error, sqlite3.Warning)) as original:
            native.execute(query)
    with pytest.raises(sqlite3.Error) as normalized:
        getattr(sql, api)(db_path, query)
    assert str(normalized.value) == str(original.value)
    if isinstance(original.value, sqlite3.Warning):
        assert isinstance(normalized.value, sqlite3.ProgrammingError)
        assert isinstance(normalized.value.__cause__, sqlite3.Warning)
        assert str(normalized.value.__cause__) == str(original.value)
    else:
        assert type(normalized.value) is type(original.value)
        assert normalized.value.__cause__ is None


def test_missing_database_is_controlled_failure_without_creation(tmp_path, entrypoint):
    path = tmp_path / 'missing.db'
    if entrypoint in CLI_FORMATS:
        process = cli(str(path), 'SELECT 1', *CLI_FORMATS[entrypoint])
        assert process.returncode == 1 and process.stdout == b''
        assert b'SQL execution failed' in process.stderr
    else:
        with pytest.raises(sqlite3.OperationalError):
            getattr(sql, entrypoint)(str(path), 'SELECT 1')
    assert not path.exists()


@pytest.mark.parametrize('flags', [(), ('--format', 'tsv'), ('--format', 'json')])
@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_cli_query_file_uses_same_permission_policy(db_path, tmp_path, flags):
    destination = tmp_path / 'attached.db'
    query_file = tmp_path / 'é query.sql'
    query_file.write_text(f"ATTACH DATABASE '{destination}' AS other", encoding='utf-8')
    before = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()
    process = cli(db_path, None, '--file', str(query_file), *flags)
    assert process.returncode == 1 and process.stdout == b''
    assert b'SQL execution failed: not authorized' in process.stderr
    assert not destination.exists()
    query_file.write_text("SELECT 'é' AS value", encoding='utf-8')
    process = cli(db_path, None, '--file', str(query_file), *flags)
    assert process.returncode == 0 and not process.stderr
    if flags == ('--format', 'json'):
        assert json.loads(process.stdout)['rows'] == [['é']]
    else:
        assert process.stdout == 'value\né\n'.encode('utf-8')
    assert hashlib.sha256(Path(db_path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize('db_path', [False], indirect=True, ids=['graphify-only'])
@pytest.mark.parametrize('query,columns,rows', [
    ("SELECT target FROM g_edges WHERE source='mod_a_alpha'", ['target'], [('mod_a_helper',)]),
    ("SELECT n.id FROM g_edges e JOIN g_nodes n ON n.id=e.source "
     "WHERE e.target='mod_a_alpha' ORDER BY e.id", ['id'], [('mod_b_beta',), ('mod_b_beta',)]),
    ("SELECT a.source,b.target FROM g_edges a JOIN g_edges b ON a.target=b.source "
     "WHERE a.relation='calls' AND b.relation='calls' ORDER BY a.id,b.id",
     ['source', 'target'], [('mod_b_beta', 'mod_a_helper'), ('mod_b_beta', 'mod_a_helper')]),
    ('SELECT doc,line1 FROM s_occurrences', ['doc', 'line1'], []),
    ('SELECT COUNT(*) AS n FROM s_occurrences', ['n'], [(0,)]),
    ('SELECT l.s_symbol FROM g_nodes n JOIN links l ON n.id=l.g_id', ['s_symbol'], []),
])
def test_structural_only_query_populations(db_path, entrypoint, query, columns, rows):
    assert_read(entrypoint, db_path, query, columns, rows)


@pytest.mark.parametrize('db_path', [True, False], indirect=True, ids=['paired', 'graphify-only'])
def test_zero_match_does_not_conflate_producer_availability(db_path, request):
    meta = dict(sql.run(db_path, 'SELECT key,value FROM meta')[1])
    query = "SELECT doc,line1 FROM s_occurrences WHERE symbol='nonexistent symbol'"
    assert sql.run(db_path, query) == (['doc', 'line1'], [])
    decoded = result(db_path, query)
    assert decoded['columns'] == ['doc', 'line1'] and decoded['rows'] == []
    assert decoded['delivery']['sql_result_exhausted']
    assert decoded['claims']['stored_fact_coverage'] == decoded['claims']['source_correctness'] == 'unknown'
    count = sql.run(db_path, 'SELECT COUNT(*) FROM s_occurrences')[1][0][0]
    expected = ('indexed', 'completed', 28) if request.node.callspec.params['db_path'] else ('not-supplied', 'not-run', 0)
    assert (meta['scip.status'], meta['link.status'], count) == expected
    if meta['scip.status'] == 'not-supplied':
        assert meta['build.mode'] == 'graphify-only'
        # An outer join still exposes all Graphify nodes; it is not an unmatched census.
        assert sql.run(db_path, 'SELECT COUNT(*) FROM g_nodes n LEFT JOIN links l ON n.id=l.g_id '
                       'WHERE l.g_id IS NULL')[1] == [(15,)]
        assert meta['link.unmatched'] == '0'
