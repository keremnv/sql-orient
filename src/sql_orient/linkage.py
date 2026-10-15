"""Identity linkage between Graphify declaration nodes and SCIP definitions.

Shared declarations join on
`source file + declaration line + declaration name`; files join on
`source path`. No fuzzy matching: ambiguous or unparseable identities
stay unlinked and are reported in the returned diagnostics.
"""
from __future__ import annotations

import re
import sqlite3

RULE_DECL = 'decl:file+line+name'
RULE_FILE = 'file:path'

LOC_RE = re.compile(r'L(\d+)$')


def graphify_kind(label: str, attrs: dict) -> str:
    if label.endswith('.py'):
        return 'file'
    if attrs.get('_callable_class'):
        return 'class'
    if label.startswith('.'):
        return 'method'
    if label.endswith('()'):
        return 'func'
    return 'other'


def graphify_name(label: str) -> str:
    s = label[1:] if label.startswith('.') else label
    return s[:-2] if s.endswith('()') else s


def link_all(db: sqlite3.Connection) -> dict:
    """Populate `links` from the imported facts. Returns diagnostics counts."""
    from .scip import parse_definition_symbol

    sdefs: dict[tuple[str, int, str], list[str]] = {}
    for doc, line1, sym in db.execute(
            'SELECT doc, line1, symbol FROM s_occurrences WHERE roles & 1 != 0'):
        parsed = parse_definition_symbol(sym)
        if parsed is not None:
            sdefs.setdefault((doc, line1, parsed[1]), []).append(sym)

    diag = {'decl_matched': 0, 'file_matched': 0, 'unmatched': 0,
            'ambiguous': 0, 'skipped_nondecl': 0, 'unmatched_ids': []}
    rows = db.execute(
        'SELECT id, label, source_file, source_location, file_type, attrs FROM g_nodes'
    ).fetchall()
    import json as _json
    for gid, label, path, loc, ftype, attrs_json in rows:
        attrs = _json.loads(attrs_json or '{}')
        if ftype in ('rationale', 'concept') or not path:
            diag['skipped_nondecl'] += 1
            continue
        if graphify_kind(label, attrs) == 'file':
            mod = db.execute(
                "SELECT symbol FROM s_occurrences WHERE doc=? AND roles & 1 != 0"
                " AND symbol LIKE '%/__init__:%' LIMIT 1", (path,)).fetchone()
            if mod is not None:
                db.execute('INSERT INTO links VALUES (?,?,?,?)', (gid, mod[0], path, RULE_FILE))
                diag['file_matched'] += 1
            else:
                diag['unmatched'] += 1
                diag['unmatched_ids'].append(gid)
            continue
        if graphify_kind(label, attrs) == 'other':
            diag['skipped_nondecl'] += 1
            continue
        m = LOC_RE.match(loc or '')
        if not m:
            diag['unmatched'] += 1
            diag['unmatched_ids'].append(gid)
            continue
        cands = sdefs.get((path, int(m.group(1)), graphify_name(label)), [])
        if len(cands) == 1:
            db.execute('INSERT INTO links VALUES (?,?,?,?)', (gid, cands[0], path, RULE_DECL))
            diag['decl_matched'] += 1
        elif len(cands) > 1:
            diag['ambiguous'] += 1
        else:
            diag['unmatched'] += 1
            diag['unmatched_ids'].append(gid)
    return diag
