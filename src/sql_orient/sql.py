"""Read-only SQL access to a sql_orient database."""
from __future__ import annotations

import sqlite3
import json
from urllib.parse import quote


DEFAULT_MAX_ROWS = 100
DEFAULT_MAX_BYTES = 65536


class DeliveryError(RuntimeError):
    """A valid, truthful JSON response cannot be produced under the contract."""


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    db = sqlite3.connect(f'file:{quote(db_path, safe="/")}?mode=ro', uri=True)
    db.execute('PRAGMA query_only = ON')

    # query_only/mode=ro protect table data but ATTACH can still create files.
    # Use SQLite's authorizer, not SQL parsing, to reject side-effecting forms.
    inspection = {'table_info', 'table_xinfo', 'table_list', 'index_info',
                  'index_xinfo', 'index_list', 'foreign_key_list', 'foreign_key_check',
                  'integrity_check', 'quick_check', 'database_list',
                  'compile_options', 'collation_list'}
    settings = {'query_only', 'user_version', 'application_id', 'schema_version',
                'data_version', 'page_count', 'freelist_count', 'page_size',
                'encoding', 'journal_mode', 'auto_vacuum'}
    # fts3_tokenizer() returns or accepts raw tokenizer pointers; builds compiled with
    # SQLITE_ENABLE_FTS3_TOKENIZER enable the pointer-registering form.
    denied_functions = {'load_extension', 'fts3_tokenizer'}

    def authorize(action, name, argument, database, trigger):
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (argument or '').lower() not in denied_functions:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA:
            name = (name or '').lower()
            if name in inspection or (name in settings and argument is None):
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    db.set_authorizer(authorize)
    return db


def _execute(db: sqlite3.Connection, query: str, params: tuple) -> sqlite3.Cursor:
    """Keep execution failures in sqlite3.Error across Python versions."""
    try:
        return db.execute(query, params)
    except sqlite3.Warning as exc:
        # Python 3.10 reports multiple statements outside the Error hierarchy.
        raise sqlite3.ProgrammingError(str(exc)) from exc


def _json_bytes(value, limit: int | None = None) -> bytes | None:
    """Compact UTF-8 JSON, stopping serialization if it cannot fit the budget."""
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    chunks = []
    size = 0
    try:
        for chunk in encoder.iterencode(value):
            if limit is not None and len(chunk) > limit - size:
                return None  # UTF-8 needs at least one byte per character.
            encoded = chunk.encode('utf-8')
            size += len(encoded)
            if limit is not None and size > limit:
                return None
            chunks.append(encoded)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DeliveryError(f'JSON serialization failed: {exc}') from exc
    return b''.join(chunks)


def _document(columns: bytes, rows: list[bytes], *, completion: str, more: bool,
              reason: str | None, max_rows: int, max_bytes: int) -> bytes:
    metadata = _json_bytes({
        'execution': {'completion': completion},
        'delivery': {'rows_emitted': len(rows), 'sql_result_exhausted': not more,
                     'more_rows': more, 'limit_reason': reason,
                     'max_rows': max_rows, 'max_bytes': max_bytes},
        'claims': {'logical_query_completeness': 'unknown',
                   'stored_fact_coverage': 'unknown', 'source_correctness': 'unknown',
                   'model_delivery': 'unknown'},
        'caveat': 'Producer/revision claims in meta are not verified here; check current source.',
    })
    return (b'{"columns":' + columns + b',"rows":[' + b','.join(rows) + b'],'
            + metadata[1:] + b'\n')


def run_bounded(db_path: str, query: str, params: tuple = (), *,
                max_rows: int = DEFAULT_MAX_ROWS,
                max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    """Return one capped UTF-8 JSON line; no SQL rewriting or generic pagination.

    Exhaustion describes delivered rows of this exact statement, not intent,
    extraction coverage or source truth. A selected prefix may hide later SQL
    errors: execution completion stays unknown unless end-of-cursor is observed.
    At most one lookahead row is kept; individual rows/SQLite work are not capped.
    Errors occur before stdout is written. Both APIs share the SQL authorizer;
    legacy run() retains its uncapped (columns, rows) result format.
    """
    if type(max_rows) is not int or type(max_bytes) is not int:
        raise DeliveryError('max_rows and max_bytes must be integers')
    if max_rows < 0 or max_bytes < 1:
        raise DeliveryError('max_rows must be nonnegative and max_bytes positive')
    db = _connect_read_only(db_path)
    try:
        cur = _execute(db, query, params)
        if cur.description is None:
            raise DeliveryError('JSON delivery requires a row-producing read-only statement')
        columns = _json_bytes([d[0] for d in cur.description], max_bytes)
        if columns is None:
            raise DeliveryError('byte cap cannot fit JSON column names and metadata')
        rows = []
        completion = 'unknown'
        reason = None
        row = cur.fetchone()
        if row is None:
            completion = 'observed'
        while row is not None:
            if len(rows) == max_rows:
                reason = 'max_rows'
                break
            following = cur.fetchone()
            if following is None:
                completion = 'observed'
            encoded = _json_bytes(list(row), max_bytes)
            if encoded is None:
                reason = 'max_bytes'
                break
            # Reserve truthful partial metadata while another row exists. Its
            # longest state uses observed completion (a later oversized last row).
            candidate = _document(columns, rows + [encoded], completion='observed',
                                  more=following is not None,
                                  reason='max_bytes' if following is not None else None,
                                  max_rows=max_rows, max_bytes=max_bytes)
            if len(candidate) > max_bytes:
                reason = 'max_bytes'
                break
            rows.append(encoded)
            row = following
        result = _document(columns, rows, completion=completion, more=reason is not None,
                           reason=reason, max_rows=max_rows, max_bytes=max_bytes)
        if len(result) > max_bytes:
            raise DeliveryError('byte cap cannot fit truthful JSON metadata; no result emitted')
        return result
    finally:
        db.close()


def run(db_path: str, query: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    """Execute one read-only statement. Returns (columns, rows)."""
    db = _connect_read_only(str(db_path))
    try:
        cur = _execute(db, query, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall()
    finally:
        db.close()
