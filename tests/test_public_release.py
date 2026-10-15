"""Public release gate is independent of version and covers upload artifacts."""
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release_gate', ROOT/'scripts/check_public_release.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


@pytest.mark.parametrize('version', ['0.2.0', '0.3.0rc1', '1.0.0', '2.0.0'])
@pytest.mark.parametrize('kind', ['source', 'wheel', 'sdist'])
@pytest.mark.parametrize('alias', ['package', 'command', 'neither'])
def test_any_version_alias_in_source_or_upload_is_blocked(tmp_path, version, kind, alias):
    command = '\ncodeindex = "sql_orient.__main__:codeindex_main"' if alias == 'command' else ''
    project = f'[project]\nname="sql-orient"\nversion="{version}"\n[project.scripts]\nsql-orient="sql_orient.__main__:main"{command}\n'
    contents = {'pyproject.toml': project.encode(), 'src/sql_orient/__init__.py': b''}
    if alias == 'package': contents['src/codeindex/__init__.py'] = b''
    if kind == 'source':
        for name, body in contents.items():
            path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
        validate = lambda: gate.validate_source(tmp_path)
    elif kind == 'wheel':
        path = tmp_path/f'sql_orient-{version}-py3-none-any.whl'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(f'sql_orient-{version}.dist-info/METADATA', f'Name: sql-orient\nVersion: {version}\n')
            archive.writestr(f'sql_orient-{version}.dist-info/entry_points.txt', '[console_scripts]\nsql-orient=sql_orient.__main__:main'+command)
            if alias == 'package': archive.writestr('codeindex/__init__.py', '')
        validate = lambda: gate.validate_artifact(path)
    else:
        path = tmp_path/f'sql_orient-{version}.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, body in contents.items():
                member = tarfile.TarInfo(f'sql_orient-{version}/'+name);member.size=len(body)
                archive.addfile(member, io.BytesIO(body))
        validate = lambda: gate.validate_artifact(path)
    if alias == 'neither': validate()
    else:
        with pytest.raises(ValueError, match='before ANY public release'): validate()


def test_actual_public_checkout_passes():
    proc = subprocess.run([sys.executable, str(ROOT/'scripts/check_public_release.py'), str(ROOT)], capture_output=True)
    assert proc.returncode == 0 and not proc.stderr
    assert b'Alias-removal gate passed' in proc.stdout


@pytest.mark.parametrize('kind', ['source', 'wheel', 'sdist'])
def test_gui_alias_entry_point_is_also_blocked(tmp_path, kind):
    project = '[project]\nname="sql-orient"\nversion="0.2.0"\n[project.gui-scripts]\ncodeindex="sql_orient.__main__:codeindex_main"\n'
    if kind == 'source':
        (tmp_path/'pyproject.toml').write_text(project)
        validate = lambda: gate.validate_source(tmp_path)
    elif kind == 'wheel':
        path = tmp_path/'sql_orient-0.2.0-py3-none-any.whl'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('sql_orient-0.2.0.dist-info/METADATA', 'Name: sql-orient\nVersion: 0.2.0\n')
            archive.writestr('sql_orient-0.2.0.dist-info/entry_points.txt', '[gui_scripts]\ncodeindex=sql_orient.__main__:codeindex_main')
        validate = lambda: gate.validate_artifact(path)
    else:
        path = tmp_path/'sql_orient-0.2.0.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            body = project.encode()
            member = tarfile.TarInfo('sql_orient-0.2.0/pyproject.toml'); member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
        validate = lambda: gate.validate_artifact(path)
    with pytest.raises(ValueError, match='codeindex entry point'):
        validate()


@pytest.mark.parametrize('kind', ['source','wheel','sdist'])
def test_internal_module_shim_is_blocked(tmp_path, kind):
    project = '[project]\nname="sql-orient"\nversion="0.2.0"\n'
    shim = b'def codeindex_main():\n    pass\n'
    if kind == 'source':
        (tmp_path/'pyproject.toml').write_text(project)
        module=tmp_path/'src/sql_orient/__main__.py'
        module.parent.mkdir(parents=True)
        module.write_bytes(shim)
        validate=lambda:gate.validate_source(tmp_path)
    elif kind == 'wheel':
        path=tmp_path/'sql_orient-0.2.0-py3-none-any.whl'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('sql_orient-0.2.0.dist-info/METADATA','Name: sql-orient\nVersion: 0.2.0\n')
            archive.writestr('sql_orient/__main__.py',shim)
        validate=lambda:gate.validate_artifact(path)
    else:
        path=tmp_path/'sql_orient-0.2.0.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            for name,body in [('pyproject.toml',project.encode()),('src/sql_orient/__main__.py',shim)]:
                member=tarfile.TarInfo('sql_orient-0.2.0/'+name)
                member.size=len(body)
                archive.addfile(member,io.BytesIO(body))
        validate=lambda:gate.validate_artifact(path)
    with pytest.raises(ValueError,match='module shim'):
        validate()
