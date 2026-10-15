# Read-only SQL

Use `sql-orient sql --db PATH --query SQL` or `--file FILE`. The default TSV returns all rows; `--format json` defaults to 100 rows and 65536 UTF-8 bytes. Explicit `ORDER BY` is needed for stable ordering. Use joins and predicates to select relationships; see [callers](../examples/callers.sql) and [relationships in both directions with provenance](../examples/relationships.sql).

Python APIs: `sql_orient.sql.run(path, query, params=())` returns columns and tuples; `run_bounded(path, query, params=(), max_rows=100, max_bytes=65536)` returns JSON bytes. Native parameter binding is supported by the APIs. JSON cannot serialize blobs or non-finite floats. A cap too small for truthful metadata raises an error without partial stdout.

Read-only URI mode, query_only and SQLite authorization reject writes, ATTACH/DETACH, transactions, extension loading and the pointer-based `fts3_tokenizer()` function. Selected schema inspection pragmas and other built-in SQL functions remain available; which functions exist depends on the local SQLite build. This is not a general-purpose or resource sandbox for untrusted queries. Row/byte caps bound delivery, not execution time, intermediate SQLite storage or row size. Exhaustion applies to the exact SQL result only; coverage and source correctness remain unknown.
