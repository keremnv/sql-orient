# sql_orient

Graphify extracts code relationships externally. sql_orient imports its JSON exports into SQLite and provides read-only SQL querying. Optional SCIP facts add symbol occurrences and explicit identity links. This is an early-stage project, version 0.2.0. It is not released on PyPI; install it from a source checkout.

[Graphify](https://github.com/Graphify-Labs/graphify) is an independent upstream project ([license](https://github.com/Graphify-Labs/graphify/blob/HEAD/LICENSE)). Run it separately to obtain `graph.json`. It is not bundled or a required runtime dependency. No affiliation or endorsement is implied. sql_orient does not extract a graph, validate source truth or ensure complete relationships.

## Install from a source checkout

Python 3.10 or later with SQLite is required. Clone or download the source repository, then from its root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

## Quickstart with the synthetic fixture

The quickstart inputs, `tests/fixtures/mini/` and `examples/callers.sql`, are part of the source repository and source distribution. They are not installed with the wheel. From the checkout root:

```sh
sql-orient build --repo tests/fixtures/mini/repo --graph tests/fixtures/mini/graph.json --db mini.db
sql-orient sql --db mini.db --file examples/callers.sql
```

Expected TSV output (duplicate relationships are preserved):

```text
caller	relation	target
beta()	calls	alpha()
beta()	calls	alpha()
```

The fixture is synthetic and requires neither Graphify nor a decoder.

## Using the installed command

After installation, `sql-orient` (or `python -m sql_orient`) works from any directory with your own source snapshot and its external Graphify export:

```sh
sql-orient build --repo path/to/source --graph path/to/graph.json --db project.db
sql-orient sql --db project.db --query 'SELECT relation, COUNT(*) AS n FROM g_edges GROUP BY relation ORDER BY n DESC'
```

Existing output databases are never overwritten. Malformed inputs fail with a one-line error and leave no database. Imported metadata records absolute input paths and producer claims; treat databases as potentially sensitive before sharing.

## SQL and bounded JSON

`sql-orient sql --db mini.db --query 'SELECT COUNT(*) AS n FROM g_nodes' --format json --max-rows 100 --max-bytes 65536`

The API and CLI permit read-only statements and selected inspection pragmas. Mutation, attachment, transactions and extension loading are denied. TSV is uncapped; JSON bounds delivered rows and total UTF-8 bytes including metadata. The JSON reports cursor exhaustion separately from execution completion. Caps do not bound SQLite work or individual row memory. An exhausted SQL result establishes neither graph completeness nor source correctness. A partial result can hide errors later in the cursor.

## Optional SCIP

`sql-orient build --repo tests/fixtures/mini/repo --graph tests/fixtures/mini/graph.json --scip tests/fixtures/mini/scip.json --db paired.db`

JSON uses the supported `scip print --json` field conventions. Binary input requires an external compatible `scip` decoder on PATH that passes the typed-range and position-encoding capability probe. Graphify-only construction performs no SCIP work. Links use exact path, declaration line and name matching; they do not validate graph edges. The source repository's `docs/scip.md`, `docs/schema.md` and `docs/sql.md` give details.

## Evidence and limitations

One selected Dulwich task, 12 blocks and three arms produced these descriptive amended-set observations (mean input tokens per session):

| Metric | Source-only | Native Graphify | sql_orient |
|---|---:|---:|---:|
| Total input | 1,721,255 | 1,637,750 | 1,449,205 |
| Uncached input | 94,141 | 104,438 | 88,779 |

All 36 amended-set patches passed frozen checks. Thirty of the 36 preregistered sessions completed; six that failed for environment reasons were each replaced once under a post-hoc, owner-authorized amendment, in two rounds. Two of the six had first been retained as agent watchdog timeouts and were reclassified as network failures after their captures were reviewed. The preregistered comparison remains unidentified. The nominal 95% t-interval (11 degrees of freedom) for the mean within-block paired difference in total input, sql_orient minus Native Graphify, includes zero. Uncached-input findings are post hoc and exploratory. No general efficiency, causal attribution or monetary-savings claim is established.

Graphify source facts may be incomplete or inaccurate. Missing rows do not prove absence in source. SCIP references are not call edges, and supplied revisions do not certify alignment. Results on one task with one model and agent harness do not establish performance on other projects, models or producer versions.

The source repository includes a sanitized numerical evidence file, `evidence/d1.json`, deterministic SVG figures in `docs/figures/`, a standard-library renderer and `docs/evidence.md`. `python scripts/render_evidence.py --check` reproduces displayed calculations and figures, not the underlying agent experiments. No full sessions, patches or studied source are included.

## License and contributions

Copyright 2026 keremnv. sql_orient project material is licensed under Apache-2.0; see `LICENSE` and `NOTICE`. External projects, including Graphify and SCIP, are owned by their respective authors and retain their own licenses; see `ATTRIBUTION.md`. Contribution guidance is in `CONTRIBUTING.md`.
