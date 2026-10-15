"""Build a sql_orient SQLite database from Graphify and optional SCIP inputs."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import subprocess

from . import __version__
from .linkage import link_all
from .scip import decode_range, load_index, package_versions

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE g_nodes(id TEXT PRIMARY KEY, label TEXT, source_file TEXT,
  source_location TEXT, file_type TEXT, community INTEGER, attrs TEXT);
CREATE TABLE g_edges(id INTEGER PRIMARY KEY, source TEXT, target TEXT,
  relation TEXT, context TEXT, source_file TEXT, source_location TEXT, attrs TEXT);
CREATE TABLE s_documents(path TEXT PRIMARY KEY, position_encoding INTEGER);
CREATE TABLE s_occurrences(id INTEGER PRIMARY KEY, doc TEXT, line1 INTEGER,
  end_line1 INTEGER, col0 INTEGER, col1 INTEGER, symbol TEXT, roles INTEGER,
  enc_line0 INTEGER, enc_col0 INTEGER, enc_line1 INTEGER, enc_col1 INTEGER,
  range_raw TEXT, enc_raw TEXT, attrs TEXT);
CREATE TABLE s_symbols(id INTEGER PRIMARY KEY, doc TEXT, symbol TEXT,
  documentation TEXT, relationships TEXT);
CREATE INDEX i_sym ON s_symbols(doc, symbol);
CREATE TABLE links(g_id TEXT PRIMARY KEY, s_symbol TEXT, s_doc TEXT, rule TEXT);
CREATE INDEX i_occ_sym ON s_occurrences(symbol, roles);
CREATE INDEX i_occ_doc ON s_occurrences(doc, line1);
CREATE INDEX i_edge_tgt ON g_edges(target, relation);
CREATE INDEX i_edge_src ON g_edges(source, relation);
CREATE INDEX i_node_file ON g_nodes(source_file, source_location);
"""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git_head(repo: str) -> str | None:
    """Observe HEAD only when repo itself is a Git worktree root.

    Git searches parent directories by default. A nested source export is
    not the enclosing project's checkout, and HEAD never certifies source
    bytes or the provenance of independently supplied index inputs.
    """
    try:
        root = subprocess.run(['git', '-C', repo, 'rev-parse', '--show-toplevel'],
                              capture_output=True, text=True, timeout=30)
        if root.returncode != 0 or os.path.realpath(root.stdout.strip()) != os.path.realpath(repo):
            return None
        proc = subprocess.run(['git', '-C', repo, 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


NODE_COLS = {'id', 'label', 'source_file', 'source_location', 'file_type', 'community'}
EDGE_COLS = {'source', 'target', 'relation', 'context', 'source_file', 'source_location'}
OCC_COLS = {'range', 'symbol', 'symbol_roles', 'enclosing_range'}


def load_graph(path: str) -> dict:
    """Load Graphify JSON; expected input failures are RuntimeErrors with chained causes."""
    hint = 'supply a valid Graphify graph.json export'
    try:
        with open(path, encoding='utf-8') as fh:
            graph = json.load(fh)
    except OSError as exc:
        raise RuntimeError(f'Graphify input {path!r}: {exc.strerror}; {hint}') from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Graphify input {path!r}: invalid JSON at line {exc.lineno}, '
                           f'column {exc.colno}: {exc.msg}; {hint}') from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError(f'Graphify input {path!r}: JSON input is not valid UTF-8; {hint}') from exc
    if not isinstance(graph, dict):
        raise RuntimeError(f'Graphify input {path!r}: expected a JSON object; {hint}')
    for key in ('nodes', 'links'):
        items = graph.get(key, [])
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise RuntimeError(f'Graphify input {path!r}: {key} must be an array of objects; {hint}')
    # Optional members, when present, must keep their Graphify types; hyperedges are only counted.
    if not isinstance(graph.get('graph', {}), dict):
        raise RuntimeError(f'Graphify input {path!r}: graph must be an object; {hint}')
    if not isinstance(graph.get('hyperedges', []), list):
        raise RuntimeError(f'Graphify input {path!r}: hyperedges must be an array; {hint}')
    for number, node in enumerate(graph.get('nodes', []), 1):
        if not isinstance(node.get('label'), str):  # Linkage classifies declarations by label.
            raise RuntimeError(f'Graphify input {path!r}: nodes[{number}].label must be a string; {hint}')
    return graph


def build(repo: str, graph_path: str, scip_path: str | None, db_path: str,
          revision: str | None = None) -> dict:
    """Import inputs into a fresh database; None skips SCIP and linkage."""
    if os.path.exists(db_path):
        raise RuntimeError(f'refusing to overwrite existing database: {db_path}')
    graph = load_graph(graph_path)
    has_scip = scip_path is not None
    index = load_index(scip_path) if has_scip else None

    head = git_head(repo)
    if revision is not None and head is not None and revision != head:
        raise RuntimeError(
            f'revision mismatch: caller supplied {revision} but {repo} is at {head}')
    if revision is not None:
        rev_status = 'supplied-by-caller' if head is None else 'caller-matches-git-head'
        rev_value = revision
    elif head is not None:
        rev_status, rev_value = 'observed-git-head', head
    else:
        rev_status, rev_value = 'unknown', ''

    db = sqlite3.connect(db_path)
    try:
        db.executescript(SCHEMA)
        item = 'nodes', 0
        try:
            for number, node in enumerate(graph.get('nodes', []), 1):
                item = 'nodes', number
                rest = {k: v for k, v in node.items() if k not in NODE_COLS}
                db.execute('INSERT INTO g_nodes VALUES (?,?,?,?,?,?,?)',
                           (node.get('id'), node.get('label'), node.get('source_file'),
                            node.get('source_location'), node.get('file_type'),
                            node.get('community'), json.dumps(rest, sort_keys=True)))
            for number, link in enumerate(graph.get('links', []), 1):
                item = 'links', number
                rest = {k: v for k, v in link.items() if k not in EDGE_COLS}
                db.execute('INSERT INTO g_edges(source,target,relation,context,source_file,'
                           'source_location,attrs) VALUES (?,?,?,?,?,?,?)',
                           (link.get('source'), link.get('target'), link.get('relation'),
                            link.get('context'), link.get('source_file'), link.get('source_location'),
                            json.dumps(rest, sort_keys=True)))
        except sqlite3.Error as exc:
            # Duplicate node IDs or non-scalar column values in the producer export.
            raise RuntimeError(f'Graphify input {graph_path!r}: {item[0]}[{item[1]}]: {exc}; '
                               'supply a valid Graphify graph.json export') from exc
        for doc in (index.get('documents', []) if has_scip else ()):
            path = doc.get('relative_path')
            encoding = doc.get('position_encoding')
            db.execute('INSERT INTO s_documents VALUES (?,?)', (path, encoding))
            for number, occ in enumerate(doc.get('occurrences', []), 1):
                context = f'SCIP document {path!r} occurrence {number}'
                rng = decode_range(occ, 'range', context=context)
                enc = decode_range(occ, 'enclosing_range', context=context)
                enc = enc if enc is not None else (None,) * 4
                rest = {k: v for k, v in occ.items() if k not in OCC_COLS}
                db.execute('INSERT INTO s_occurrences(doc,line1,end_line1,col0,col1,symbol,roles,'
                           'enc_line0,enc_col0,enc_line1,enc_col1,range_raw,enc_raw,attrs)'
                           ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (path, rng[0] + 1, rng[2] + 1,
                            rng[1], rng[3], occ.get('symbol'), occ.get('symbol_roles'),
                            enc[0], enc[1], enc[2], enc[3],
                            json.dumps(occ['range']) if 'range' in occ else None,
                            json.dumps(occ['enclosing_range']) if 'enclosing_range' in occ else None,
                            json.dumps(rest, sort_keys=True)))
            for info in doc.get('symbols', []):
                db.execute('INSERT INTO s_symbols(doc,symbol,documentation,relationships)'
                           ' VALUES (?,?,?,?)',
                           (path, info.get('symbol'),
                            json.dumps(info.get('documentation')) if info.get('documentation') is not None else None,
                            json.dumps(info.get('relationships')) if info.get('relationships') is not None else None))
        diag = link_all(db) if has_scip else {
            'decl_matched': 0, 'file_matched': 0, 'unmatched': 0,
            'ambiguous': 0, 'skipped_nondecl': 0, 'unmatched_ids': []}
        gmeta = graph.get('graph', {}) if isinstance(graph.get('graph'), dict) else {}
        tinfo = index.get('metadata', {}).get('tool_info', {}) if has_scip else {}
        hyper = graph.get('hyperedges', [])
        # Historical key names; kept unchanged across the package rename (schema 2).
        meta = {
            'codeindex.version': __version__,
            'codeindex.schema_version': '2',
            'scip.coordinate_normalization_version': '1',
            'build.mode': 'graphify+scip' if has_scip else 'graphify-only',
            'scip.status': 'indexed' if has_scip else 'not-supplied',
            'link.status': 'completed' if has_scip else 'not-run',
            'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'repo.path': os.path.abspath(repo),
            'repo.revision': rev_value,
            'repo.revision_status': rev_status,
            'repo.git_head': head or '',
            'repo.source_identity_status': 'unverified',
            'inputs.source_alignment_status': 'unverified',
            'graph.path': os.path.abspath(graph_path),
            'graph.sha256': sha256_file(graph_path),
            'graph.graphify_version': str(gmeta.get('graphify_version', '')),
            'graph.schema_version': str(gmeta.get('schema_version', '')),
            'graph.hyperedges': str(len(hyper)),
            'scip.path': os.path.abspath(scip_path) if has_scip else '',
            'scip.sha256': sha256_file(scip_path) if has_scip else '',
            'scip.tool': str(tinfo.get('name', '')),
            'scip.tool_version': str(tinfo.get('version', '')),
            'scip.project_root': str(index.get('metadata', {}).get('project_root', '')) if has_scip else '',
            'scip.packages': json.dumps(package_versions(index)) if has_scip else '[]',
            'import.g_nodes': str(db.execute('SELECT COUNT(*) FROM g_nodes').fetchone()[0]),
            'import.g_edges': str(db.execute('SELECT COUNT(*) FROM g_edges').fetchone()[0]),
            'import.s_documents': str(db.execute('SELECT COUNT(*) FROM s_documents').fetchone()[0]),
            'import.s_occurrences': str(db.execute('SELECT COUNT(*) FROM s_occurrences').fetchone()[0]),
            'link.decl_matched': str(diag['decl_matched']),
            'link.file_matched': str(diag['file_matched']),
            'link.unmatched': str(diag['unmatched']),
            'link.ambiguous': str(diag['ambiguous']),
            'link.skipped_nondecl': str(diag['skipped_nondecl']),
        }
        db.executemany('INSERT INTO meta VALUES (?,?)', list(meta.items()))
        db.commit()
    except Exception:
        db.close()
        os.remove(db_path)
        raise
    db.close()
    diag['meta'] = meta
    if hyper:
        diag['hyperedges_ignored'] = len(hyper)
    return diag
