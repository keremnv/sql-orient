"""SCIP coordinate behavior tested with independently specified synthetic inputs."""
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from sql_orient import __version__, build, scip, sql

ROOT = Path(__file__).resolve().parents[1]


def import_documents(tmp_path, documents):
    graph = tmp_path / 'graph.json'
    index = tmp_path / 'index.json'
    graph.write_text('{"nodes":[],"links":[]}')
    index.write_text(json.dumps({'documents': documents}))
    target = tmp_path / 'result.db'
    before = (graph.read_bytes(), index.read_bytes())
    try:
        result = build.build(str(tmp_path), str(graph), str(index), str(target))
    finally:
        assert before == (graph.read_bytes(), index.read_bytes())
    return target, result


def occurrence(**fields):
    return {'symbol': 'local 0', 'symbol_roles': 9, **fields}


def import_occurrence(tmp_path, fields, **document_fields):
    return import_documents(tmp_path, [{
        'relative_path': 'sample.py', 'occurrences': [occurrence(**fields)], **document_fields}])


@pytest.mark.parametrize('field', ['range', 'enclosing_range'])
@pytest.mark.parametrize('encoded,expected', [
    ([7, 2, 5], (7, 2, 7, 5)),
    ([7, 2, 9, 4], (7, 2, 9, 4)),
    ([7, 0, 9], (7, 0, 7, 9)),
    ([6, 0, 10, 3], (6, 0, 10, 3)),
    ([7, 2, 7, 5], (7, 2, 7, 5)),
    ([0, 0, 0], (0, 0, 0, 0)),
    ([0, 0, 0, 0], (0, 0, 0, 0)),
    ([7, 2, 9, 0], (7, 2, 9, 0)),  # Half-open end at next line's column zero.
])
def test_legacy_encodings_independently(field, encoded, expected):
    assert scip.decode_range({field: encoded}, field, context='sample.py') == expected


@pytest.mark.parametrize('field,single,multi,wrapper,variants', [
    ('range', 'single_line_range', 'multi_line_range', 'TypedRange',
     ('SingleLineRange', 'MultiLineRange')),
    ('enclosing_range', 'single_line_enclosing_range', 'multi_line_enclosing_range',
     'TypedEnclosingRange', ('SingleLineEnclosingRange', 'MultiLineEnclosingRange')),
])
@pytest.mark.parametrize('wrapped', [False, True])
@pytest.mark.parametrize('multiline,value,expected', [
    (False, {'line': 7, 'start_character': 2, 'end_character': 5}, (7, 2, 7, 5)),
    (False, {}, (0, 0, 0, 0)),
    (False, {'end_character': 5}, (0, 0, 0, 5)),
    (True, {'start_line': 7, 'start_character': 2, 'end_line': 9, 'end_character': 4},
     (7, 2, 9, 4)),
    (True, {'start_line': 7, 'start_character': 2, 'end_line': 7, 'end_character': 5},
     (7, 2, 7, 5)),
    (True, {}, (0, 0, 0, 0)),
])
def test_typed_encodings_and_protobuf_defaults(field, single, multi, wrapper, variants,
                                              wrapped, multiline, value, expected):
    typed = {wrapper: {variants[int(multiline)]: value}} if wrapped else {
        multi if multiline else single: value}
    assert scip.decode_range(typed, field, context='sample.py') == expected


@pytest.mark.parametrize('rng,enc,expected', [
    ([7, 2, 5], [7, 0, 9], (8, 8, 2, 5, 7, 0, 7, 9)),
    ([7, 2, 9, 4], [6, 0, 10, 3], (8, 10, 2, 4, 6, 0, 10, 3)),
    ([7, 2, 5], [6, 0, 10, 3], (8, 8, 2, 5, 6, 0, 10, 3)),
    ([7, 2, 9, 0], [6, 0, 10, 3], (8, 10, 2, 0, 6, 0, 10, 3)),
    ([0, 0, 0], [0, 0, 0, 0], (1, 1, 0, 0, 0, 0, 0, 0)),
])
def test_database_conventions_mixed_shapes_and_raw_arrays(tmp_path, rng, enc, expected):
    path, diag = import_occurrence(tmp_path, {'range': rng, 'enclosing_range': enc, 'extra': {'x': 1}})
    _, rows = sql.run(str(path), 'SELECT line1,end_line1,col0,col1,enc_line0,enc_col0,'
                     'enc_line1,enc_col1 FROM s_occurrences')
    assert rows == [expected]
    _, rows = sql.run(str(path), 'SELECT range_raw,enc_raw,attrs,symbol,roles FROM s_occurrences')
    assert json.loads(rows[0][0]) == rng and json.loads(rows[0][1]) == enc
    assert json.loads(rows[0][2]) == {'extra': {'x': 1}}
    assert rows[0][3:] == ('local 0', 9)
    assert diag['meta']['codeindex.version'] == __version__ == '0.2.0'
    assert diag['meta']['codeindex.schema_version'] == '2'
    assert diag['meta']['scip.coordinate_normalization_version'] == '1'


@pytest.mark.parametrize('fields,raw', [({}, None), ({'enclosing_range': None}, 'null'),
                                      ({'enclosing_range': []}, '[]')])
def test_missing_enclosing_normalizes_null_but_preserves_presence(tmp_path, fields, raw):
    path, _ = import_occurrence(tmp_path, {'range': [0, 0, 0], **fields})
    _, rows = sql.run(str(path), 'SELECT enc_line0,enc_col0,enc_line1,enc_col1,enc_raw '
                     'FROM s_occurrences')
    assert rows == [(None, None, None, None, raw)]


@pytest.mark.parametrize('fields', [
    {'single_line_range': {'line': 7, 'start_character': 2, 'end_character': 5}},
    {'range': [7, 2, 5], 'single_line_range': {'line': 7, 'start_character': 2, 'end_character': 5}},
    {'range': [7, 2, 7, 5], 'multi_line_range': {
        'start_line': 7, 'start_character': 2, 'end_line': 7, 'end_character': 5}},
    {'range': [], 'TypedRange': {'SingleLineRange': {
        'line': 7, 'start_character': 2, 'end_character': 5}}},
])
def test_typed_precedence_equivalence_and_exact_raw_fields(tmp_path, fields):
    fields = {**fields, 'TypedEnclosingRange': {'SingleLineEnclosingRange': {
        'line': 7, 'end_character': 9}}, 'producer_extra': [1, 2]}
    original = json.loads(json.dumps(fields))
    path, _ = import_occurrence(tmp_path, fields)
    _, rows = sql.run(str(path), 'SELECT line1,end_line1,col0,col1,range_raw,enc_raw,attrs '
                     'FROM s_occurrences')
    assert rows[0][:4] == (8, 8, 2, 5)
    assert rows[0][4] == (json.dumps(fields['range']) if 'range' in fields else None)
    assert rows[0][5] is None
    assert json.loads(rows[0][6]) == {k: v for k, v in fields.items() if k != 'range'}
    assert fields == original


@pytest.mark.parametrize('field', ['range', 'enclosing_range'])
@pytest.mark.parametrize('value', [[1], [1, 2], [1, 2, 3, 4, 5], '123', {}, True, 3,
                                  [0, 0, '1'], [0, 0, 1.0], [0, False, 1], [0, 0, None],
                                  [-1, 0, 1], [0, -1, 1], [0, 0, -1],
                                  [7, 5, 2], [7, 2, 6, 100], [0, 0, 2147483648]])
def test_invalid_legacy_ranges_fail_without_output(tmp_path, field, value):
    fields = {'range': [7, 2, 5], 'enclosing_range': [7, 0, 9], field: value}
    with pytest.raises(RuntimeError, match=f"sample.py.*occurrence 1.*{field}:"):
        import_occurrence(tmp_path, fields)
    assert not list(tmp_path.glob('result.db*'))


@pytest.mark.parametrize('value', [None, [], False, 'bad', 1, {'line': None},
                                  {'line': -1}, {'line': 1.0}, {'line': True},
                                  {'line': 2147483648}, {'start_character': 5},
                                  {'startCharacter': 2}, {'end_character': 1, 'extra': 2}])
@pytest.mark.parametrize('field,key', [('range', 'single_line_range'),
                                     ('enclosing_range', 'single_line_enclosing_range')])
def test_invalid_typed_messages_fail_without_output(tmp_path, value, field, key):
    fields = {'range': [7, 2, 5]} if field == 'enclosing_range' else {}
    with pytest.raises(RuntimeError, match=f"sample.py.*occurrence 1.*{field}:"):
        import_occurrence(tmp_path, {**fields, key: value})
    assert not (tmp_path / 'result.db').exists()


@pytest.mark.parametrize('fields,field', [
    ({'range': [7, 2, 5], 'single_line_range': {'line': 7, 'end_character': 9}}, 'range'),
    ({'range': [7, 2, 5], 'enclosing_range': [7, 0, 9],
      'single_line_enclosing_range': {'line': 7, 'end_character': 10}}, 'enclosing_range'),
    ({'single_line_range': {}, 'multi_line_range': {}}, 'range'),
    ({'range': [0, 0, 0], 'single_line_enclosing_range': {},
      'multi_line_enclosing_range': {}}, 'enclosing_range'),
    ({'TypedRange': {'SingleLineRange': {}, 'MultiLineRange': {}}}, 'range'),
    ({'range': [0, 0, 0], 'TypedEnclosingRange': {
        'SingleLineEnclosingRange': {}, 'MultiLineEnclosingRange': {}}}, 'enclosing_range'),
    ({'single_line_range': {}, 'TypedRange': {'SingleLineRange': {}}}, 'range'),
    ({'TypedRange': {}}, 'range'),
    ({'TypedRange': {'FutureRange': {}}}, 'range'),
    ({'range': [7, 2, 5], 'singleLineRange': {}}, 'range'),
    ({'range': [7, 2, 5], 'typed_range': {}}, 'range'),
    ({'range': [7, 2, 5], 'enclosingRange': [7, 0, 9]}, 'enclosing_range'),
    ({'range': [7, 2, 5], 'enclosing_range': [7, 3, 9]}, 'enclosing_range'),
    ({'range': [7, 2, 5], 'enclosing_range': [7, 0, 4]}, 'enclosing_range'),
    ({'range': [7, 2, 9, 4], 'enclosing_range': [7, 0, 9]}, 'enclosing_range'),
])
def test_conflicts_oneofs_unsupported_formats_and_containment(tmp_path, fields, field):
    with pytest.raises(RuntimeError, match=f"sample.py.*occurrence 1.*{field}:"):
        import_occurrence(tmp_path, fields)
    assert not (tmp_path / 'result.db').exists()


@pytest.mark.parametrize('field,key', [('range', 'multi_line_range'),
                                     ('enclosing_range', 'multi_line_enclosing_range')])
@pytest.mark.parametrize('value', [
    {'start_line': 7, 'end_line': 6, 'end_character': 100},
    {'start_line': 7, 'start_character': 5, 'end_line': 7, 'end_character': 2},
    {'start_line': 7},  # Omitted end defaults to zero, making this reversed.
    {'end_line': -1}, {'end_character': True}, {'start_character': '2'},
])
def test_multiline_typed_invalid_coordinates_independently(tmp_path, field, key, value):
    fields = {'range': [7, 2, 5]} if field == 'enclosing_range' else {}
    with pytest.raises(RuntimeError, match=f"sample.py.*occurrence 1.*{field}:"):
        import_occurrence(tmp_path, {**fields, key: value})
    assert not (tmp_path / 'result.db').exists()


@pytest.mark.parametrize('fields', [{}, {'range': None}, {'range': []},
                                  {'TypedRange': None}, {'range': [], 'TypedRange': None}])
def test_missing_occurrence_coordinates_are_rejected(tmp_path, fields):
    with pytest.raises(RuntimeError, match='range: missing occurrence range'):
        import_occurrence(tmp_path, fields)
    assert not (tmp_path / 'result.db').exists()


@pytest.mark.parametrize('encoding,column', [(1, 4), (2, 2), (3, 1), (0, 2), (None, 2), (99, 2)])
def test_declared_document_units_preserved_without_unicode_conversion(tmp_path, encoding, column):
    # On "😇x", x starts at UTF-8 byte 4, UTF-16 unit 2, UTF-32 unit 1.
    path, _ = import_occurrence(tmp_path, {'range': [0, column, column + 1]},
                                position_encoding=encoding, text='😇x')
    _, rows = sql.run(str(path), 'SELECT position_encoding FROM s_documents')
    assert rows == [(encoding,)]
    _, rows = sql.run(str(path), 'SELECT col0,col1 FROM s_occurrences')
    assert rows == [(column, column + 1)]


def test_absent_position_encoding_stays_unknown(tmp_path):
    path, _ = import_occurrence(tmp_path, {'range': [0, 0, 0]})
    assert sql.run(str(path), 'SELECT position_encoding FROM s_documents')[1] == [(None,)]


@pytest.mark.parametrize('metadata', [{'position_encoding': True}, {'position_encoding': 1.0},
                                      {'position_encoding': 'UTF16CodeUnitOffsetFromLineStart'},
                                      {'position_encoding': 2147483648}, {'positionEncoding': 2}])
def test_unsupported_encoding_representation_rejects(tmp_path, metadata):
    with pytest.raises(RuntimeError, match='sample.py.*position_encoding:'):
        import_occurrence(tmp_path, {'range': [0, 0, 0]}, **metadata)
    assert not (tmp_path / 'result.db').exists()


def test_typed_mini_index_preserves_symbol_role_and_link_populations(tmp_path):
    mini = ROOT / 'tests/fixtures/mini'
    index = json.loads((mini / 'scip.json').read_text())
    for doc in index['documents']:
        for occ in doc['occurrences']:
            # This fixture uses single-line legacy occurrences. Build an
            # equivalent spec-shaped producer input without our decoder.
            line, start, end = occ.pop('range')
            occ['single_line_range'] = {'line': line, 'start_character': start,
                                        'end_character': end}
    path = tmp_path / 'typed-mini.json'
    path.write_text(json.dumps(index))
    target = tmp_path / 'typed-mini.db'
    diag = build.build(str(mini / 'repo'), str(mini / 'graph.json'), str(path), str(target))
    assert diag['decl_matched'] == 11 and diag['file_matched'] == 2
    assert diag['ambiguous'] == diag['unmatched'] == 0
    assert sql.run(str(target), 'SELECT COUNT(*) FROM s_occurrences')[1] == [(28,)]
    assert sql.run(str(target), 'SELECT COUNT(*) FROM s_symbols')[1] == [(2,)]
    assert sql.run(str(target), 'SELECT roles FROM s_occurrences WHERE doc=\'mod_b.py\' '
                   'AND line1=2 AND col0=18')[1] == [(10,)]
    assert sql.run(str(target), "SELECT s_symbol FROM links WHERE g_id='mod_a_outer_inner'")[1][0][0].endswith(
        '/outer().inner().')


def test_old_database_coordinates_schema_meta_and_read_only_interfaces_unchanged(tmp_path):
    path = tmp_path / 'legacy.db'
    # Actual legacy column layout/defective values, specified without invoking the new importer.
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);'
                        'CREATE TABLE s_documents(path TEXT PRIMARY KEY);'
                        'CREATE TABLE s_occurrences(id INTEGER PRIMARY KEY,doc TEXT,line1 INTEGER,'
                        'col0 INTEGER,col1 INTEGER,symbol TEXT,roles INTEGER,enc_line0 INTEGER,'
                        'enc_col0 INTEGER,enc_line1 INTEGER,enc_col1 INTEGER,range_raw TEXT,'
                        'enc_raw TEXT,attrs TEXT);')
        db.execute("INSERT INTO meta VALUES ('codeindex.version','0.1.0')")
        db.execute("INSERT INTO s_documents VALUES ('sample.py')")
        db.execute('INSERT INTO s_occurrences VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('sample.py', 72, 51, 73, 'local 0', 8, 43, 4, 47, None,
                    '[71, 51, 73, 5]', '[43, 4, 47]', '{}'))
    before = path.read_bytes()
    schema = sql.run(str(path), 'PRAGMA table_info(s_occurrences)')
    meta = sql.run(str(path), 'SELECT * FROM meta ORDER BY key')
    query = 'SELECT line1,col0,col1,enc_line1,enc_col1 FROM s_occurrences'
    assert sql.run(str(path), query)[1] == [(72, 51, 73, 47, None)]
    assert json.loads(sql.run_bounded(str(path), query))['rows'] == [[72, 51, 73, 47, None]]
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        build.build(str(tmp_path), 'missing.json', 'missing.scip', str(path))
    assert schema == sql.run(str(path), 'PRAGMA table_info(s_occurrences)')
    assert meta == sql.run(str(path), 'SELECT * FROM meta ORDER BY key')
    assert path.read_bytes() == before


def test_new_database_overwrite_also_refused(tmp_path):
    path, _ = import_occurrence(tmp_path, {'range': [7, 2, 9, 4]})
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        build.build(str(tmp_path), 'missing.json', 'missing.json', str(path))
    assert path.read_bytes() == before


def test_incapable_binary_cli_is_rejected_before_decoding_input(tmp_path, monkeypatch):
    original = tmp_path / 'input.scip'
    original.write_bytes(b'preserved input')
    calls = []
    monkeypatch.setattr(scip.shutil, 'which', lambda _: 'old-scip')

    def old_cli(argv, **kwargs):
        calls.append(argv)
        assert argv[-1] != str(original)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'documents': [{
            'relative_path': 'probe.py', 'position_encoding': 2, 'occurrences': [{}, {}]}]}))

    monkeypatch.setattr(scip.subprocess, 'run', old_cli)
    with pytest.raises(RuntimeError, match='capability check'):
        scip.load_index(str(original))
    assert len(calls) == 1 and original.read_bytes() == b'preserved input'
    assert not Path(calls[0][-1]).exists()  # Probe cleaned up on failure.


@pytest.mark.parametrize('payload', [
    {'documents': [{'occurrences': []}]}, {'documents': []}, {}, None,
    {'documents': [{'position_encoding': 2, 'occurrences': [{}, {}]}]},
    {'documents': [0]}, {'documents': ['bad']},
    {'documents': [{'position_encoding': 2, 'occurrences': {}}]},
])
def test_malformed_capability_probe_receipts_reject(payload, monkeypatch):
    monkeypatch.setattr(scip.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout=json.dumps(payload)))
    with pytest.raises(RuntimeError, match='capability check'):
        scip._check_decoder('fake-scip')


def test_json_input_does_not_require_or_launch_cli(tmp_path, monkeypatch):
    path = tmp_path / 'index.json'
    expected = {'documents': [{'relative_path': 'sample.py', 'occurrences': []}]}
    path.write_text(json.dumps(expected))
    def unexpected(*args, **kwargs):
        pytest.fail('JSON input must not invoke external decoding')
    monkeypatch.setattr(scip.shutil, 'which', unexpected)
    monkeypatch.setattr(scip.subprocess, 'run', unexpected)
    assert scip.load_index(str(path)) == expected
