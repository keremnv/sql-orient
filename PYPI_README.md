# sql_orient

**Query extracted code relationships with read-only SQL. Give developers and coding agents explicit, bounded context.**

sql_orient imports a [Graphify](https://github.com/Graphify-Labs/graphify) code graph (`graph.json`) into SQLite. You then choose relationship direction, predicates, joins, columns and ordering with SQL, instead of relying on a tool's own selection and rendering. Rows keep the producer's source file and line, so answers point back to code that still needs checking. Optional SCIP input adds symbol identities and occurrence sites.

Version 0.2.0 is an early-stage release candidate. Graphify is an independent project; it is not bundled, not a runtime dependency, and no affiliation or endorsement is implied.

## Usage

Python 3.10 or later; no runtime dependencies. Produce `graph.json` with Graphify for a source snapshot; both its clustered (`links`) and raw `--no-cluster` (`edges`) exports are accepted. Then:

```sh
sql-orient build --repo path/to/source --graph path/to/graph.json --db project.db
sql-orient sql --db project.db --query "SELECT s.label AS caller, t.label AS callee, e.source_file, e.source_location FROM g_edges e JOIN g_nodes s ON s.id = e.source JOIN g_nodes t ON t.id = e.target WHERE e.relation = 'calls' ORDER BY e.source_file, e.id"
sql-orient sql --db project.db --query "SELECT id, label FROM g_nodes ORDER BY id" --format json --max-rows 100 --max-bytes 65536
```

`python -m sql_orient` is equivalent. Tables: `g_nodes`, `g_edges`, `meta`, and the optional SCIP tables `s_documents`, `s_occurrences`, `s_symbols` and `links`. Existing databases are never overwritten, and malformed inputs fail with a one-line error and leave no database.

The CLI and Python APIs (`sql_orient.sql.run`, `sql_orient.sql.run_bounded`) only run read-only SQL: an SQLite authorizer rejects writes, `ATTACH`, transactions and extension loading. Bounded JSON caps delivered rows and bytes and reports withheld rows; it does not cap query execution and is not a sandbox for untrusted queries.

A runnable synthetic fixture, example queries and full guides are in the source distribution and source repository; they are not installed with the wheel.

## Limitations

Imported facts are only as good as the producer: relationships may be coarse, inferred, missing or wrong. Missing rows do not prove absence in source. Hyperedges are counted, not imported. SCIP links are identity links; they neither validate Graphify edges nor verify calls. Databases are snapshots, and recorded revisions are not certified.

## Evidence (one task, descriptive)

One selected Dulwich task was run in 12 blocks with three arms, using Graphify 0.9.86. Mean input tokens per session in the amended set:

| Metric | Source-only | Native Graphify | sql_orient |
|---|---:|---:|---:|
| Total input | 1,721,255 | 1,637,750 | 1,449,205 |
| Uncached input | 94,141 | 104,438 | 88,779 |

All 36 amended-set patches passed frozen checks. Six environment-failed sessions were replaced once each in two post-hoc rounds, and the preregistered comparison remains unidentified. The nominal 95% t-interval (11 degrees of freedom) for the mean within-block paired difference in total input, sql_orient minus Native Graphify, runs from -426,147 to +49,057 and includes zero. Uncached-input comparisons are exploratory. One task with one model and agent harness establishes no general efficiency, causal or monetary advantage. The published figures reproduce the displayed calculations, not the underlying experiments.

## License

Copyright 2026 keremnv. Licensed under Apache-2.0; see the LICENSE, NOTICE and ATTRIBUTION.md files included in the distribution. Graphify and SCIP remain owned and licensed by their respective authors.

Source repository: https://github.com/keremnv/sql-orient
