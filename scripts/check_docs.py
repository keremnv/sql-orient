#!/usr/bin/env python3
"""Check local Markdown links, fragments and SVG references without private inputs."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
count = 0
for path in ROOT.rglob('*.md'):
    if any(p in ('build', 'dist') or p.endswith('.egg-info') for p in path.relative_to(ROOT).parts):
        continue
    body = path.read_text()
    for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)', body):
        url = urlsplit(target)
        if url.scheme in ('https','http'):
            continue
        assert not url.scheme and not target.startswith('/'), (path.name, target)
        dest = (path.parent/unquote(url.path)).resolve() if url.path else path
        assert dest.is_relative_to(ROOT) and dest.is_file(), (path.name, target)
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
readme = (ROOT/'README.md').read_text()
assert not re.findall(r'!?\[[^\]]*\]\((?!https?://)[^)]+\)',readme), 'PyPI README requires self-contained text or public URLs'
print(f'Documentation: {count} local links/fragments and two self-contained SVGs passed; README has no relative links.')
