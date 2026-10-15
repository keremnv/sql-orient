"""sql-orient command line: build databases, run read-only SQL."""
from __future__ import annotations

import argparse
import json
import sys


def cmd_build(args: argparse.Namespace) -> int:
    from .build import build
    diag = build(args.repo, args.graph, args.scip, args.db, revision=args.revision)
    print(json.dumps({k: v for k, v in diag.items() if k != 'meta'}, indent=1)[:2000])
    print('meta:', json.dumps(diag['meta'], indent=1)[:2000])
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    import sqlite3
    from .sql import DEFAULT_MAX_BYTES, DEFAULT_MAX_ROWS, run, run_bounded
    query = args.query
    if args.file:
        with open(args.file, encoding='utf-8') as fh:
            query = fh.read()
    try:
        if args.format == 'json':
            body = run_bounded(args.db, query,
                               max_rows=DEFAULT_MAX_ROWS if args.max_rows is None else args.max_rows,
                               max_bytes=DEFAULT_MAX_BYTES if args.max_bytes is None else args.max_bytes)
        else:
            cols, rows = run(args.db, query)
    except sqlite3.Error as exc:
        raise RuntimeError(f'SQL execution failed: {exc}') from exc
    if args.format == 'json':
        sys.stdout.buffer.write(body)
        return 0
    if cols:
        print('\t'.join(cols))
    for row in rows:
        print('\t'.join('' if v is None else str(v) for v in row))
    return 0


def main(argv: list[str] | None = None, prog: str = 'sql-orient') -> int:
    ap = argparse.ArgumentParser(prog=prog)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='import Graphify and optional SCIP into a new database')
    b.add_argument('--repo', required=True)
    b.add_argument('--graph', required=True)
    b.add_argument('--scip', help='optional SCIP input; omit for Graphify-only construction')
    b.add_argument('--db', required=True)
    b.add_argument('--revision', default=None)
    b.set_defaults(func=cmd_build)
    s = sub.add_parser('sql', help='run one read-only SQL statement')
    s.add_argument('--db', required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument('--query')
    g.add_argument('--file')
    s.add_argument('--format', choices=('tsv', 'json'), default='tsv',
                   help='default uncapped TSV, or bounded UTF-8 JSON')
    s.add_argument('--max-rows', type=int, help='JSON row cap (default 100; zero allowed)')
    s.add_argument('--max-bytes', type=int, help='JSON stdout byte cap including metadata/newline (default 65536)')
    s.set_defaults(func=cmd_sql)
    args = ap.parse_args(argv)
    if args.cmd == 'sql':
        if args.format != 'json' and (args.max_rows is not None or args.max_bytes is not None):
            ap.error('--max-rows and --max-bytes require --format json')
        if args.max_rows is not None and args.max_rows < 0:
            ap.error('--max-rows must be nonnegative')
        if args.max_bytes is not None and args.max_bytes < 1:
            ap.error('--max-bytes must be positive')
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f'{prog}: error: {exc}', file=sys.stderr)
        return 1



if __name__ == '__main__':
    sys.exit(main(prog='python -m sql_orient'))
