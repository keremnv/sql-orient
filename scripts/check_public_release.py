#!/usr/bin/env python3
"""Reject codeindex compatibility aliases before ANY public sql-orient release.

Usage: python scripts/check_public_release.py PROJECT_DIR WHEEL SDIST ...
Read-only validation, never publication. Python 3.11+ or tomli on Python 3.10.
This gate checks alias removal; license, visibility and privacy are owner decisions.
"""
from __future__ import annotations
import argparse
import ast
import configparser
from email.parser import Parser
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import zipfile

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def _project_name(name):
    if re.sub(r'[-_.]+', '-', name).lower() != 'sql-orient':
        raise ValueError(f'expected sql-orient project metadata, got {name!r}')


def _alias_paths(names):
    return [n for n in names if any(part in ('codeindex', 'codeindex.py') for part in PurePosixPath(n).parts)]


def _scripts(scripts):
    return [name for name, target in scripts.items()
            if name == 'codeindex' or 'codeindex' in target]


def _reject(packages, commands):
    reasons = []
    if packages: reasons.append('codeindex package: '+', '.join(sorted(packages)[:3]))
    if commands: reasons.append('codeindex entry point: '+', '.join(sorted(commands)))
    if reasons:
        raise ValueError('; '.join(reasons)+'. Remove the compatibility package and command before ANY public release, regardless of version.')


def _module_shims(name, raw):
    if not name.endswith('.py'):
        return
    tree = ast.parse(raw, filename=name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and 'codeindex' in node.name.lower():
            raise ValueError('codeindex module shim: '+name)
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or '']
        else:
            modules = []
        if any(m == 'codeindex' or m.startswith('codeindex.') for m in modules):
            raise ValueError('codeindex import shim: '+name)


def validate_source(root):
    project = tomllib.loads((root/'pyproject.toml').read_text())['project']
    _project_name(project['name'])
    paths = [p.relative_to(root).as_posix() for p in (root/'src').rglob('*')]
    for path in (root/'src').rglob('*.py'):
        _module_shims(path.name, path.read_bytes())
    _reject(_alias_paths(paths), _scripts(project.get('scripts', {}) | project.get('gui-scripts', {})))


def validate_artifact(path):
    """Inspect archive contents without importing code or extracting files."""
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            metadata = [n for n in names if n.endswith('.dist-info/METADATA')]
            if len(metadata) != 1: raise ValueError('wheel needs exactly one METADATA file')
            _project_name(Parser().parsestr(archive.read(metadata[0]).decode())['Name'] or '')
            commands = []
            for name in names:
                if name.endswith('.dist-info/entry_points.txt'):
                    entry = configparser.ConfigParser(interpolation=None)
                    entry.read_string(archive.read(name).decode())
                    for section in ('console_scripts', 'gui_scripts'):
                        if section in entry: commands += _scripts(entry[section])
            for name in names:
                if name.startswith('sql_orient/'):
                    _module_shims(name, archive.read(name))
            _reject(_alias_paths(names), commands)
    elif path.name.endswith('.tar.gz'):
        with tarfile.open(path, 'r:gz') as archive:
            names = archive.getnames()
            roots = {PurePosixPath(n).parts[0] for n in names}
            if len(roots) != 1: raise ValueError('sdist needs exactly one project root')
            root = roots.pop()
            member = archive.extractfile(root+'/pyproject.toml')
            if member is None: raise ValueError('sdist needs pyproject.toml')
            project = tomllib.loads(member.read().decode())['project']
            _project_name(project['name'])
            for name in names:
                if '/src/sql_orient/' in name and name.endswith('.py'):
                    _module_shims(name, archive.extractfile(name).read())
            _reject(_alias_paths(names), _scripts(project.get('scripts', {}) | project.get('gui-scripts', {})))
    else:
        raise ValueError('expected a project directory, .whl or .tar.gz sdist')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('inputs', type=Path, nargs='+')
    args = ap.parse_args(argv)
    for path in args.inputs:
        try:
            validate_source(path) if path.is_dir() else validate_artifact(path)
        except (ValueError, OSError, KeyError, zipfile.BadZipFile, tarfile.TarError, configparser.Error) as exc:
            print(f'Public release BLOCKED: {path}: {exc}', file=sys.stderr)
            return 1
        print(f'Alias-removal gate passed: {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
