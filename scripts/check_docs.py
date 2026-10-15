#!/usr/bin/env python3
"""Check local Markdown links, fragments, README roles and SVG references without private inputs."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r'!?\[[^\]]*\]\(([^\s)]+)\)')
# Local environments and generated output at the checkout root are not documentation.
SKIP_ROOT = {'.git', '.venv', 'build', 'dist', '.pytest_cache'}
count = 0
for path in sorted(ROOT.rglob('*.md')):
    parts = path.relative_to(ROOT).parts
    if parts[0] in SKIP_ROOT or any(p.endswith('.egg-info') for p in parts):
        continue
    body = path.read_text()
    for target in LINK.findall(body):
        url = urlsplit(target)
        if url.scheme in ('https','http'):
            continue
        assert not url.scheme and not target.startswith('/'), (path.name, target)
        dest = (path.parent/unquote(url.path)).resolve() if url.path else path
        assert dest.is_relative_to(ROOT) and (dest.is_file() or dest.is_dir()), (path.name, target)
        if url.fragment:
            heads = re.findall(r'^#+\s+(.+)$',dest.read_text(),re.M)
            slugs = [re.sub(r'[^\w\s-]','',h.lower()).replace(' ','-') for h in heads]
            assert unquote(url.fragment) in slugs, (path.name,target)
        count += 1
for path in (ROOT/'docs/figures').glob('*.svg'):
    tree = ET.parse(path)
    assert tree.getroot().tag == '{http://www.w3.org/2000/svg}svg'
    for element in tree.iter():
        assert element.tag.rsplit('}',1)[-1] not in ('script','image','foreignObject')
        assert not any(k.rsplit('}',1)[-1] == 'href' for k in element.attrib)
# GitHub landing page embeds both public figures; the package description stands alone.
readme = (ROOT/'README.md').read_text()
for figure in ('docs/figures/total-input.svg', 'docs/figures/uncached-input.svg'):
    assert re.search(r'!\[[^\]]+\]\(' + re.escape(figure) + r'\)', readme), f'README must embed {figure}'
assert tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['readme'] == 'PYPI_README.md'
pypi = (ROOT/'PYPI_README.md').read_text()
assert not [t for t in LINK.findall(pypi) if not t.startswith('https://')], 'PyPI README needs absolute https links only'
assert '![' not in pypi and '<img' not in pypi, 'PyPI README must not depend on images'
print(f'Documentation: {count} local links/fragments, two self-contained SVGs, README figures and a self-contained PyPI README passed.')
