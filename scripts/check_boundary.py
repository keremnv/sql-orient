#!/usr/bin/env python3
"""Limited public-boundary scan. Reports rule and filename, never matched values.

Covers source text and every regular wheel/sdist member, including SVG metadata.
Deployment-specific identifiers (for example private repository or directory
names) belong in a --patterns file kept outside the distribution.
This is neither a complete security audit nor legal clearance.
"""
import argparse
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

# Rules assembled to avoid matching the scanner's own literals.
RULES = {
    'personal-path': re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+|[A-Z]:\\Users\\'),
    'email': re.compile(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    'credential': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)'),
    'internal-host': re.compile(r'\b(?:[A-Za-z0-9-]+\.)+(?:internal|corp|local)\b'),
}
FORBIDDEN = {'.git','.env','.DS_Store','id_rsa','id_ed25519'}
# Generated outputs at the checkout root, scanned via archives separately; local environments aren't distribution inputs.
ROOT_GENERATED = {'build','dist','.venv','.pytest_cache'}


def source_files(root):
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        # Only the checkout's own Git metadata is skipped; a .git anywhere else stays forbidden.
        if rel.parts[0] == '.git' or rel.parts[0] in ROOT_GENERATED:
            continue
        if '__pycache__' in rel.parts or any(part.endswith('.egg-info') for part in rel.parts):
            continue
        if p.is_symlink():
            raise ValueError(f'symlink: {rel}')
        if p.is_file():
            yield rel.as_posix(), p.read_bytes()


def members(path):
    if path.is_dir():
        yield from source_files(path)
    elif path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            for n in archive.namelist():
                if not n.endswith('/'):
                    yield n, archive.read(n)
    elif path.name.endswith('.tar.gz'):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError('archive link: '+member.name)
                if member.isfile():
                    yield member.name, archive.extractfile(member).read()
    else:
        raise ValueError('expected source directory, wheel or sdist')


def load_patterns(path):
    """One regular expression per line; blank lines and # comments are ignored."""
    rules = {}
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if line.strip() and not line.lstrip().startswith('#'):
            rules[f'{path.name}:{number}'] = re.compile(line.strip())
    return rules


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',nargs='+',type=Path)
    parser.add_argument('--patterns', type=Path, action='append', default=[],
                        help='extra deployment-specific regex file, kept outside the distribution')
    args = parser.parse_args(argv)
    rules = dict(RULES)
    for path in args.patterns:
        rules.update(load_patterns(path))
    failures=[]
    for path in args.inputs:
        count=0
        for name, raw in members(path):
            count+=1
            parts=PurePosixPath(name).parts
            if FORBIDDEN.intersection(parts) or '..' in parts or name.startswith('/'):
                failures.append((name,'forbidden-path'))
            try:
                text=raw.decode('utf-8')
            except UnicodeDecodeError:
                failures.append((name,'unreviewed-binary'))
                continue
            for rule, pattern in rules.items():
                matches = pattern.findall(text)
                if rule == 'email':
                    # Reserved synthetic identity used only in temporary Git test repositories.
                    matches = [m for m in matches if m != 'test@example.invalid']
                if matches:
                    failures.append((name,rule))
        print(f'{path.name}: scanned {count} files/members')
    for name,rule in failures:
        print(f'BLOCKED {rule}: {name}')
    if failures:
        raise SystemExit(1)
    print('Limited automated public-boundary scan passed; manual provenance review is also required.')


if __name__ == '__main__':
    main()
