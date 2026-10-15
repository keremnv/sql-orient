# sql_orient

**Query code relationships with SQL. Give agents structured, bounded context.**

sql_orient imports [Graphify](https://github.com/Graphify-Labs/graphify) code graphs
into SQLite, so developers and coding agents can ask explicit questions about
callers, dependencies and cross-file connections. SQL controls which stored
relationships and columns come back; optional JSON caps make output size visible
and controllable. It uses Graphify's extracted facts and preserves their
provenance, so consequential answers still need checking against source.

[Results](#observed-input-tokens) · [Retrieval mechanism](#why-the-output-differs) ·
[Quickstart](#quickstart) · [Evidence and limits](#what-the-evidence-supports) ·
[Technical reference](#technical-reference)

## Observed input tokens

In one selected Dulwich bug-fix task, sql_orient used less mean cumulative input
than either native Graphify or source-only work. The study called sql_orient
**CodeSQL**: B0 is source-only, G0 is native Graphify **0.9.86**, and G1 is
sql_orient. Each of 12 blocks contained one session per arm.

![Source-only: 1,721,255; Native Graphify: 1,637,750; sql_orient: 1,449,205 mean tokens per session. 12 sessions per arm. All 36 patches passed · 12/12 per arm 6 failures replaced in two rounds; descriptive. Graphify comparison: 426k fewer to 49k more. Includes no difference; broader gains unproven.](docs/figures/total-input.svg)

**Indexed-interface comparison:** sql_orient used **11.5% less** mean input than native
Graphify. **Secondary source-only comparison:** it used **15.8% less** than
source-only. **All 36 patches passed the frozen checks: 12/12 per arm.**

**How to read this result.** Six original sessions failed because of quota,
provider capacity or network loss. They were replaced once each after the fixed
sequence, under owner authorization, in two rounds: four in the first, and two
more after sessions first treated as agent watchdog timeouts were reclassified
as network failures from their captures. These bars describe that **amended set**;
the original preregistered token comparison remains unidentified because its
usage records are incomplete. The amended sql_orient–Graphify interval runs
from approximately **426k fewer to 49k more tokens per session**, including no
difference. The interval is a nominal 95% t-interval with 11 degrees of freedom for the mean within-block paired difference.
It is a small-sample summary, not a reliable guarantee.
**No general token-efficiency effect is established.**
[Original versus amended results](docs/evidence.md#original-versus-amended-results).

## Observed uncached input

Total input counts the context submitted across **all model calls**, including
context sent repeatedly. Cached input is the subset reported as cache hits;
**uncached input = total input − cached input**. A smaller total can therefore
coexist with more uncached input. Cache-hit share describes a proportion, while
uncached input describes an absolute amount.

**Exploratory observation:** this metric and these comparisons were selected
after examining multiple results. They are not a preregistered confirmation,
even where the pattern is consistent across blocks.

![Source-only: 94,141; Native Graphify: 104,438; sql_orient: 88,779 mean tokens per session. 12 sessions per arm. Exploratory: chosen after seeing results sql_orient lower than Graphify in 11/12 blocks. Uncached = total input minus cached input. Not a preregistered confirmation or money saved.](docs/figures/uncached-input.svg)

By arm means, Graphify used **10.9% more uncached input** than source-only;
sql_orient used **15.0% less than Graphify**, and was lower in **11/12 blocks**.

| Recorded cached share | Source-only | Native Graphify | sql_orient |
|---|---:|---:|---:|
| Mean session cache-hit share | 94.4% | 93.4% | 93.7% |

sql_orient's strongest cache-related observation is **lower absolute uncached
input than Graphify**. It did not improve cache-hit share over source-only.
Against source-only, sql_orient's uncached mean was slightly lower, but it was
lower in only 5/12 blocks; this does not establish a consistent advantage over
source-only work. These token counts are not monetary savings.
[Exploratory comparisons and definitions](docs/evidence.md#exploratory-d1-metrics).

## Why the output differs

Both indexed interfaces start with the same Graphify-produced facts. Native
Graphify chooses seeds and neighborhoods, then renders the selected graph. SQL
lets the consumer choose relationship direction, predicates, joins, columns and
ordering. A focused query can return just the relationships needed for the next
source inspection.

![query_graph displayed 196 nodes, no relationships, truncated. Native refinement delivered 11 relationships in 1,000 text bytes. SQL delivered 40 rows in 3,723 JSON bytes; labels and file provenance, no IDs. Separate sealed pair; different questions, not an equal-question comparison. Replication estimated carried index output: Graphify 100,151, sql_orient 25,797 tokens/session. Approximate post-hoc attribution.](docs/figures/retrieval-delivery.svg)

The example above summarizes **actual model-visible deliveries from the separate
D1 sealed pair**, before the 36-session replication. It shows response shapes
for different questions, not an equal-question benchmark. Native refinement was
compact and recovered relevant relationships. SQL returned labels and file
provenance; endpoint IDs were reconstructed by the evaluator, not delivered to
the model. `LIMIT 40` also means the returned rows do not prove graph coverage.
[Sealed-pair counts and definitions](docs/evidence.md#sealed-pair-retrieval-example).

In the replication's exploratory ledger, carried index output averaged about
**100,151 tokens/session for Graphify** and **25,797 for sql_orient**.
Carried test output also differed: approximately **137k versus 61k** tokens/session.
Retrieval output differences therefore do not fully explain total input use.

“Carried” output includes its repeated presence in later model inputs; these are
approximate contributions, not standalone query token counts. The post-hoc
ledger apportioned input increases by output size, with alignment fallbacks and
an over-attributed bundled native output. Smaller, more controllable retrieval
is a **plausible advantage**, but it does not causally explain the full session
difference. Test output, source reads and the number of later model calls also
varied. [Method and ledger definition](docs/evidence.md#exploratory-d1-metrics).

## What else matters in practice

- **Correctness did not distinguish the arms.** All amended-set patches passed
  the frozen checks. Source-only sessions also found relevant functions early;
  neither index showed a discovery advantage on this task. Passing this task's
  checks does not establish general patch quality.
- **Fewer calls, no clear speed advantage.** Mean model calls were 25.4 for
  source-only, 23.7 for Graphify and 22.1 for sql_orient. These are descriptive
  comparisons. Agent-session elapsed time showed no clear advantage, and captured
  inspection/discovery command output remained substantial in every arm; its byte
  count does not measure source-reading effort or actual model delivery.
- **Agents could author relationship SQL when instructed.** Every amended D1
  sql_orient session began with a working single-hop edge JOIN. Each ran one
  keyword-style query; this did not test multi-hop reasoning or spontaneous
  adoption. In separate optional-use pilots, there were **0/12** and **0/6**
  voluntary index operations among indexed sessions.
- **Access to stored facts is useful but conditional.** In selected B1 cases,
  focused analyst-written SQL exposed relationships that native rendering
  omitted. Native refinement also recovered relationships in other cases.
  Analyst-written queries demonstrate addressability, not an unfamiliar agent's
  formulation effort or avoided source reads.

Sources: [D1 exploratory metrics](docs/evidence.md#exploratory-d1-metrics) ·
[optional-use cohorts](docs/evidence.md#optional-use-cohorts) ·
[historical counterexamples and B1](docs/evidence.md#historical-counterexamples-and-b1).

## How it works

**Matching source snapshot + Graphify JSON → `sql-orient build` → SQLite →
read-only SQL → rows to verify in source.**

Run Graphify externally and supply its export (`nodes` plus `links`, or `edges`
from a raw `--no-cluster` export) alongside the source snapshot it describes.
sql_orient imports the graph into `g_nodes` and `g_edges`; it does not run or
repair the extractor. An optional external SCIP index adds symbol identities and
occurrence sites.

Graphify is an independent project and is not bundled with sql_orient. Its
[README](https://github.com/Graphify-Labs/graphify#readme) describes the setup:

1. In a terminal, install the `graphifyy` package, for example `uv tool install graphifyy` (or `pipx install graphifyy`).
2. In a terminal, run `graphify install` once to register Graphify with your AI coding assistant.
3. In the assistant (not the shell), type `/graphify .` to map the current project (Codex uses `$graphify`). Graphify writes `graphify-out/graph.json`.

Graphify's command-line help also documents a headless, code-only extraction that
needs no assistant or API key: `graphify extract path/to/source --code-only`
writes `path/to/source/graphify-out/graph.json`. sql_orient imports either edge
array and rejects a file whose `links` and `edges` differ; malformed inputs fail
with a one-line error and leave no database. Both export shapes were tested with
Graphify 0.9.86 and 0.9.91 on a small synthetic project; other versions are untested.

The database is a snapshot: nothing watches the source tree. Rebuild to a fresh
path after changes, and verify source alignment yourself. sql_orient's CLI and
Python APIs enforce read-only queries with an SQLite authorizer. Other SQLite
clients follow their own rules. The authorizer is not a general-purpose or
resource sandbox for untrusted queries.

## Quickstart

Python 3.10+ and Git are required. sql_orient is not released on PyPI; install it
from a source checkout. The fixture below needs neither Graphify nor a SCIP decoder.
Run every block in the same shell, starting outside an existing checkout.

```bash
git clone --branch main https://github.com/keremnv/sql-orient.git
cd sql-orient
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
sql-orient --help
```

### Usage

Build from the tracked mini fixture and query who calls `alpha()`:

```bash
DEMO="$(mktemp -d)"

sql-orient build \
  --repo tests/fixtures/mini/repo \
  --graph tests/fixtures/mini/graph.json \
  --db "$DEMO/graph.db"

CALLERS="
SELECT e.relation, s.id AS source_id, s.label AS source,
       t.id AS target_id, t.label AS target,
       e.source_file, e.source_location
FROM g_edges e
JOIN g_nodes s ON s.id = e.source
JOIN g_nodes t ON t.id = e.target
WHERE e.relation = 'calls' AND t.label = 'alpha()'
ORDER BY e.source_file, e.source_location, e.id"

sql-orient sql --db "$DEMO/graph.db" --query "$CALLERS"
```

The build imports **15 nodes and 7 edges**, prints JSON diagnostics and refuses
to overwrite an existing database. Default query output is tab-separated:

| relation | source_id | source | target_id | target | source_file | source_location |
|---|---|---|---|---|---|---|
| calls | mod_b_beta | beta() | mod_a_alpha | alpha() | mod_b.py | L6 |
| calls | mod_b_beta | beta() | mod_a_alpha | alpha() | mod_b.py | L6 |

The fixture deliberately stores one [source call](tests/fixtures/mini/repo/mod_b.py#L6)
twice; these are duplicate stored facts, not two execution paths. Select IDs to
avoid confusing identical labels, and use stable `ORDER BY` before `LIMIT`.

For bounded agent output:

```bash
sql-orient sql --db "$DEMO/graph.db" --query "$CALLERS" \
  --format json --max-rows 1
```

This emits one row and explicitly reports that more rows were withheld.
Caps bound output, not query execution cost or source completeness.
`python -m sql_orient` is equivalent to the console command. Fixtures are
checkout files, not installed package data.

To see relationship direction as well, [`examples/relationships.sql`](examples/relationships.sql)
labels every call touching `alpha()` as incoming or outgoing and keeps its file and line:

```bash
sql-orient sql --db "$DEMO/graph.db" --file examples/relationships.sql
```

| direction | source | relation | target | source_file | source_location |
|---|---|---|---|---|---|
| incoming | beta() | calls | alpha() | mod_b.py | L6 |
| incoming | beta() | calls | alpha() | mod_b.py | L6 |
| outgoing | alpha() | calls | helper() | mod_a.py | L6 |

## What the evidence supports

D1 offers a concrete observation about the cost of **required index consultation
on one task**, with ordinary source tools still available. The source-only
comparison also changes the instruction to consult an index, so it is secondary
to the comparison between indexed interfaces. Extraction, graph build and import
costs were excluded. All sessions used one Codex harness and model
(`gpt-6.1-sol`); later Graphify releases and other tasks or models are untested.
Replacements ran on a later date, so provider/model drift cannot be ruled out.

The favourable arm means coexist with counterexamples: Graphify used fewer
total input tokens in three D1 blocks, and sql_orient's uncached advantage over
source-only was inconsistent. Historical HTTPX work used more input with SQL;
both historical tenacity patches broke supported compatibility despite passing
a narrow bug oracle. Native refinement sometimes recovered useful navigation
where broad SQL lost selected rows at a cap. These are separate historical
observations, not additional D1 sessions or a unified benchmark. Those cases
matter when deciding whether this interface helps a particular workflow.

SQL exposes stored relationships; it does not make them true or complete.
Graphify facts may be coarse, inferred, missing or wrong. Missing rows are not
proof of missing source relationships, and a complete SQL result is not a
complete answer. Hyperedges are warned about and counted, not imported.
SCIP identity links do not validate Graphify edges, and references are not
verified calls. Query formulation, source corroboration and snapshot upkeep
remain part of the work. Multi-hop SQL is an available capability whose
end-to-end value was not tested by D1.

This repository includes sanitized aggregate evidence files and a
standard-library renderer; study protocols, identity manifests, corpus databases
and raw consumer captures are not published. Figure reproduction
(`python scripts/render_evidence.py --check`) checks the published summaries, not
a fresh reproduction of the agent sessions. Grading was mechanically blinded
against frozen checks, not independent human review; delivery does not establish
causal reliance.

[Evidence guide: populations, definitions and limitations](docs/evidence.md).

## Technical reference

Version 0.2.0 · import `sql_orient` · command/distribution `sql-orient` · schema 2 ·
Python 3.10+ · no runtime dependencies.

| Guide | Covers |
|---|---|
| [SQL guide](docs/sql.md) | CLI and Python APIs, bounded JSON delivery, caps versus SQL `LIMIT`, exhaustion and read-only enforcement |
| [Optional SCIP](docs/scip.md) | SCIP JSON and binary input, coordinates, external decoders and identity links |
| [Consumer schema](docs/schema.md) | Tables, metadata, Graphify `links`/`edges` import and snapshot lifecycle |
| [Evidence](docs/evidence.md) | Public evidence files, populations, definitions and figure reproduction |
| [Examples](examples/) | Runnable queries over the mini fixture |
| [Compatibility](docs/schema.md) | Historical `codeindex.*` metadata keys; there is no compatibility package or command |

Older databases are readable but are not migrated or repaired. The
examples run against the mini fixture; real use needs your own Graphify export.

## Status and licensing

Copyright 2026 keremnv. sql_orient is licensed under Apache-2.0; see
[LICENSE](LICENSE) and [NOTICE](NOTICE). Graphify and SCIP are independent
projects that retain their own licenses; see [ATTRIBUTION.md](ATTRIBUTION.md).
No affiliation or endorsement is implied. Version 0.2.0 is not released on PyPI.
Contribution guidance is in [CONTRIBUTING.md](CONTRIBUTING.md).
