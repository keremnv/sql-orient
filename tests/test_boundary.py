"""Public-boundary scan in a Git-initialized checkout, as created by CI checkout."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT/'scripts/check_boundary.py'
SPEC = importlib.util.spec_from_file_location('boundary_scan', SCANNER)
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)

# Assembled at runtime so this module never contains the values it injects.
PERSONAL_PATH = '/' + 'home' + '/alice/project'
EMAIL = 'alice' + '@' + 'example.org'
PRIVATE_NAME = 'acme' + '-private-' + 'research'
GIT_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)


def run(*args):
    return subprocess.run([sys.executable, str(SCANNER), *map(str, args)],
                          capture_output=True, text=True)


def git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, env=GIT_ENV, capture_output=True)


@pytest.fixture
def checkout(tmp_path):
    """Distributable files plus root Git metadata and an index; no commit is created."""
    root = tmp_path/'checkout'
    for name, raw in scan.source_files(ROOT):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    git(root, 'init', '-q')
    git(root, 'add', '-A')
    assert (root/'.git/index').is_file()
    return root


def test_clean_git_initialized_checkout_passes(checkout):
    names = [name for name, _ in scan.source_files(checkout)]
    assert '.github/workflows/ci.yml' in names and '.gitignore' in names
    assert not any(name == '.git' or name.startswith('.git/') for name in names)
    proc = run(checkout)
    assert proc.returncode == 0, proc.stdout
    assert 'BLOCKED' not in proc.stdout and 'scan passed' in proc.stdout


@pytest.mark.parametrize('name, payload, rule', [
    ('README.md', PERSONAL_PATH, 'personal-path'),
    ('src/sql_orient/sql.py', '# ' + EMAIL, 'email'),
    ('.github/workflows/ci.yml', '# ' + PERSONAL_PATH, 'personal-path'),
    ('.gitignore', '# ' + EMAIL, 'email'),
])
def test_injected_identifier_in_tracked_file_fails(checkout, name, payload, rule):
    with open(checkout/name, 'a', encoding='utf-8') as fh:
        fh.write('\n' + payload + '\n')
    git(checkout, 'add', '-A')
    proc = run(checkout)
    assert proc.returncode == 1
    assert f'BLOCKED {rule}: {name}' in proc.stdout
    assert payload.lstrip('# ') not in proc.stdout + proc.stderr


def test_git_metadata_below_the_root_stays_forbidden(checkout):
    nested = checkout/'tests/fixtures/vendored/.git/config'
    nested.parent.mkdir(parents=True)
    nested.write_text('[core]\n')
    proc = run(checkout)
    assert proc.returncode == 1
    assert 'BLOCKED forbidden-path: tests/fixtures/vendored/.git/config' in proc.stdout


def test_external_patterns_file_extends_rules(checkout, tmp_path):
    patterns = tmp_path/'patterns.txt'
    patterns.write_text('# deployment-specific identifiers\n' + PRIVATE_NAME + '\n')
    assert run(checkout, '--patterns', patterns).returncode == 0
    with open(checkout/'docs/scip.md', 'a', encoding='utf-8') as fh:
        fh.write(PRIVATE_NAME + '\n')
    proc = run(checkout, '--patterns', patterns)
    assert proc.returncode == 1
    assert 'BLOCKED patterns.txt:2: docs/scip.md' in proc.stdout
    assert PRIVATE_NAME not in proc.stdout + proc.stderr


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_archive_members_are_still_scanned(tmp_path, kind):
    body = ('# ' + EMAIL + '\n').encode()
    if kind == 'wheel':
        path = tmp_path/'demo-0-py3-none-any.whl'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('demo/__init__.py', body)
        member = 'demo/__init__.py'
    else:
        path = tmp_path/'demo-0.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo('demo-0/src/demo/__init__.py')
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
        member = 'demo-0/src/demo/__init__.py'
    proc = run(path)
    assert proc.returncode == 1 and f'BLOCKED email: {member}' in proc.stdout
