# SQLite schema 2

The importer creates `meta`, `g_nodes`, `g_edges`, `s_documents`, `s_occurrences`, `s_symbols` and `links`. Inspect columns with `PRAGMA table_info(g_nodes)` or another table name. Node IDs are producer identities; edge IDs preserve input order and duplicate edges. Extra fields are JSON in `attrs`; symbol documentation and relationships are stored as JSON text.

Historical `codeindex.version` and `codeindex.schema_version` metadata keys remain database API contracts. Schema version is 2; coordinate normalization version is 1. There is no compatibility Python package or command. Old databases are queried without rewriting their schema or correcting historical coordinates.

Occurrence `line1`/`end_line1` are one based; columns retain producer units and are zero based. Enclosing endpoints remain zero based. Raw ranges and extra producer fields are preserved. Inspect `s_documents.position_encoding` before interpreting columns.

`meta` includes source paths, input hashes, observed Git HEAD when available, caller revision claims and mode/status fields. These do not establish source/input alignment. Graphify-only mode keeps empty semantic tables and reports `not-supplied`/`not-run`; zero rows have a different meaning from an indexed absence.
