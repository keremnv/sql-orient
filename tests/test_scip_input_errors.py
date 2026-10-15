"""Expected input errors stay actionable; programming failures remain visible."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sql_orient import build, scip

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/mini'


@pytest.mark.parametrize('payload, reason, cause', [
    (b'', 'file is empty', ValueError),
    (b'  \n ', 'invalid JSON at line', json.JSONDecodeError),
    (b'{', 'invalid JSON at line', json.JSONDecodeError),
    (b'\xff', 'not valid UTF-8', UnicodeDecodeError),
    (b'null', 'index: expected a JSON object', ValueError),
    (b'[]', 'index: expected a JSON object', ValueError),
    (b'{"documents":null}', 'documents: expected an array', ValueError),
    (b'{"documents":[null]}', 'documents[1]: expected a JSON object', ValueError),
    (b'{"documents":[{"relative_path":"x","occurrences":[null]}]}', 'occurrences[1]', ValueError),
    (b'{"metadata":null}', 'metadata: expected a JSON object', ValueError),
    (b'{"documents":[{"relative_path":"x","occurrences":[{"range":[0,0,1],"symbol":null}]}]}', 'symbol: expected a string', ValueError),
    (b'{"documents":[{"relative_path":"x","occurrences":[{"range":[0,2,1]}]}]}', 'end precedes start', RuntimeError),
])
def test_invalid_json_input_programmatic_and_cli(tmp_path, payload, reason, cause):
    supplied = tmp_path/'bad.json'
    supplied.write_bytes(payload)
    target = tmp_path/'failed.db'
    with pytest.raises(RuntimeError) as caught:
        build.build(str(FIX/'repo'), str(FIX/'graph.json'), str(supplied), str(target))
    assert str(supplied) in str(caught.value) and reason in str(caught.value)
    assert isinstance(caught.value.__cause__, cause)
    for module in ('sql_orient',):
        proc = subprocess.run([sys.executable, '-m', module, 'build', '--repo', str(FIX/'repo'),
                               '--graph', str(FIX/'graph.json'), '--scip', str(supplied), '--db', str(target)],
                              capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT/'src')))
        assert proc.returncode == 1 and proc.stdout == b''
        assert b'Traceback' not in proc.stderr
        assert str(supplied).encode() in proc.stderr and reason.encode() in proc.stderr
        assert len(proc.stderr.splitlines()) == 1
    assert not list(tmp_path.glob('failed.db*'))  # No database or sidecars; no fallback.
    assert supplied.read_bytes() == payload


@pytest.mark.parametrize('suffix, empty', [('.json', False), ('.scip', False), ('.scip', True)])
def test_missing_or_empty_input_precedes_decoder_discovery(tmp_path, monkeypatch, suffix, empty):
    supplied = tmp_path/('input'+suffix)
    if empty: supplied.write_bytes(b'')
    def unexpected(*args):
        raise AssertionError('decoder discovery must not run for a missing or empty input')
    monkeypatch.setattr(scip.shutil, 'which', unexpected)
    with pytest.raises(RuntimeError) as caught:
        scip.load_index(str(supplied))
    assert str(supplied) in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError if empty else FileNotFoundError)


@pytest.mark.parametrize('response, reason, cause', [
    (SimpleNamespace(returncode=1, stderr='bad\nprotobuf', stdout=''), 'bad protobuf', None),
    (SimpleNamespace(returncode=0, stderr='', stdout=''), 'invalid JSON', json.JSONDecodeError),
    (SimpleNamespace(returncode=0, stderr='', stdout='null'), 'expected a JSON object', ValueError),
    (FileNotFoundError('decoder disappeared'), 'decoder disappeared', FileNotFoundError),
])
def test_expected_binary_decoder_failures(tmp_path, monkeypatch, response, reason, cause):
    supplied = tmp_path/'bad.scip'; supplied.write_bytes(b'invalid protobuf')
    target = tmp_path/'failed.db'
    monkeypatch.setattr(scip.shutil, 'which', lambda _: 'fake-scip')
    monkeypatch.setattr(scip, '_check_decoder', lambda _: None)
    def decode(*args, **kwargs):
        if isinstance(response, Exception): raise response
        return response
    monkeypatch.setattr(scip.subprocess, 'run', decode)
    with pytest.raises(RuntimeError) as caught:
        build.build(str(FIX/'repo'), str(FIX/'graph.json'), str(supplied), str(target))
    assert str(supplied) in str(caught.value) and reason in str(caught.value)
    if cause: assert isinstance(caught.value.__cause__, cause)
    assert not list(tmp_path.glob('failed.db*'))


def test_programming_error_is_not_reclassified(tmp_path, monkeypatch):
    supplied = tmp_path/'valid.json'; supplied.write_text('{"documents":[]}')
    def bug(index): raise TypeError('unexpected implementation bug')
    monkeypatch.setattr(scip, '_validate_index', bug)
    with pytest.raises(TypeError, match='implementation bug'):
        build.build(str(FIX/'repo'), str(FIX/'graph.json'), str(supplied), str(tmp_path/'failed.db'))
    assert not list(tmp_path.glob('failed.db*'))
