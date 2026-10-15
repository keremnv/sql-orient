# Descriptive D1 evidence

Five sanitized files in [evidence/](../evidence/) support the README. Populations are identified separately and never pooled.

| File | Population | Status |
|---|---|---|
| [d1.json](../evidence/d1.json) | Owner-amended D1 set: 12 blocks × 3 arms, 36 sessions | Descriptive; preregistered comparison unidentified |
| [d1-exploratory.json](../evidence/d1-exploratory.json) | The same 36 amended sessions | Post hoc and exploratory |
| [d1-sealed-pair.json](../evidence/d1-sealed-pair.json) | Two separate sessions run before the replication | Illustrative; different questions |
| [optional-use.json](../evidence/optional-use.json) | Two separate optional-use cohorts | Separate studies; not D1 |
| [historical.json](../evidence/historical.json) | Separate V4 coding observations, V7 fixed checks and B1 investigations | Selected historical evidence; not D1 or a unified benchmark |

## Original versus amended results

[evidence/d1.json](../evidence/d1.json) contains only reviewed aggregate token sums, session and replacement counts, and a nominal interval with its definition from the preserved primary analysis. Totals were recomputed across amended blocks; uncached sums were recovered from the primary arm means times 12 and checked for exact whole-token sums. Every included numeric value was compared during preparation. Counts describe one selected Dulwich task, 12 blocks and three arms. Graphify version was 0.9.86; sql_orient was called CodeSQL in the experiment.

All 36 amended-set patches passed frozen checks. Of the 36 preregistered original sessions, 30 completed. Under a post-hoc amendment authorized by the owner, six sessions that failed for environment reasons were each replaced once, in two rounds. Round 1 replaced four (three quota failures and one provider-capacity failure). Two further sessions, one in the sql_orient arm and one in the Native Graphify arm, had been retained in round 1 as agent watchdog timeouts; review of their captures afterwards showed network/DNS loss, so they were reclassified as environment failures and replaced in round 2. Original records were kept, not overwritten. The preregistered comparison remains unidentified; amended-set results are descriptive.

The interval is a nominal 95% t-interval, with 11 degrees of freedom, for the mean within-block paired difference in total input tokens per session (sql_orient minus Native Graphify) across the 12 amended blocks: -426,147 to 49,057. It includes zero. Uncached-input findings are post hoc and exploratory. Results come from one selected task with one model and agent harness; no general efficiency, causal attribution or monetary-saving advantage is established.

## Exploratory D1 metrics

[evidence/d1-exploratory.json](../evidence/d1-exploratory.json) covers the same 36 amended sessions. Every value was selected after the results were seen and is descriptive only:

- **Mean session cache-hit share:** 94.4% source-only, 93.4% Native Graphify, 93.7% sql_orient. This is the mean over each arm's 12 sessions of cached divided by total input, not the ratio of arm means.
- **Paired blocks:** sql_orient's total input was lower than Native Graphify's in 9 of 12 blocks, so Graphify was lower in three. Its uncached input was lower than Graphify's in 11 of 12 and lower than source-only in 5 of 12.
- **Model calls and agent-session elapsed time:** mean calls were 25.4, 23.7 and 22.1. The elapsed interval starts immediately before launching the agent process and ends after process exit and output-capture thread drainage. It includes startup, tool execution, provider/network waiting and capture overhead, not just active computation. Preparation, graph extraction/import, grading and gaps between sessions are excluded. All arms and both replacement rounds use the same boundary. The amended set uses the six replacement durations in place of failed originals, without adding the originals' time; original failures remain in the private preregistered records. The nominal 95% t-intervals (11 degrees of freedom) for mean within-block relative change, A/B − 1, include zero for every pair of arms. For sql_orient versus Native Graphify the interval is approximately −16.5% to +9.7%; this establishes no clear elapsed-time advantage, not equivalent speed.
- **Captured inspection/discovery command output:** the private analysis labels this `source_output_bytes` and "source output read." It averages about 189,000 to 203,000 UTF-8 bytes per session. The collector sums each completed shell-command event's entire captured `aggregated_output` when its command text matches `sed`, `rg`, `cat`, `head`, `find` or `ls` at word boundaries. Repeats, listing output, failed-command diagnostics and mixed output count; a matching batch can include test output. Unmatched commands, standalone test commands without a match, direct MCP responses and separate patch events do not count. This is recorded command output, not unique source bytes, source files opened, reading effort or verified model-visible delivery. It covers the same 36 amended sessions, substituting replacements for failed originals.
- **Discovery timing:** for each of 7 tracked task functions, the median model call at which the function first appeared in non-index tool output was 2 to 4 for source-only and Native Graphify and 2 to 3 for sql_orient, so neither index showed a discovery advantage.
- **sql_orient queries:** each of the 12 amended sql_orient sessions ran exactly one CLI SQL query. Each was a single-hop edge JOIN with a keyword predicate, and each delivered rows to the model.
- **Carried output (approximate ledger):** carried index output was about 100,151 tokens per session for Graphify and 25,797 for sql_orient; carried test output was about 137,009 and 60,720. Each session's cumulative input is decomposed into later input increases times the calls that resend them, and increases are attributed to their producing actions in proportion to output size. Alignment fallbacks occur and one bundled native index output is over-attributed. This is a post-hoc approximation, not a causal decomposition.

## Sealed-pair retrieval example

[evidence/d1-sealed-pair.json](../evidence/d1-sealed-pair.json) summarizes model-visible delivery shapes from two separate D1 sessions run before the replication. They asked **different questions**, so this is not an equal-question benchmark.

- **Native Graphify:** `query_graph` displayed 196 nodes and 0 relationships, truncated. A following `get_neighbors` delivered 11 relationships in 1,000 bytes of text without truncation; 2 of them match the study's frozen task-relevance ledger.
- **sql_orient:** one SQL query (an edge JOIN with a keyword predicate and `LIMIT 40`) delivered 40 rows in 3,723 bytes of JSON. Each row had the source label, relation, target label and source file. Endpoint IDs were not delivered; the evaluator resolved them afterwards. Because of the `LIMIT`, an exhausted result did not prove complete graph coverage.

The verbatim questions, SQL text and delivered lines are not published.

## Optional-use cohorts

[evidence/optional-use.json](../evidence/optional-use.json) records two separate studies in which agents could use an index but were not required to. In an 18-session three-arm pilot, 0 of 12 indexed sessions made any index operation. In the V7 exploratory completion, 0 of 6 indexed sessions did. These are not D1 adoption rates and are not pooled.

## Historical counterexamples and B1

[evidence/historical.json](../evidence/historical.json) restores balancing observations from separate studies using Graphify 0.9.80. These selected cases are not additional D1 sessions, a unified benchmark, success-rate estimates or causal evidence.

- **V4 HTTPX:** one native-first session recorded 907,801 cumulative input tokens and one SQL-first session recorded 956,995. The native session was interrupted and resumed; its unique provider records include pre-failure input once. SQL used more recorded input in this case. Both patches passed the frozen acceptance checks.
- **V4 tenacity:** one patch per arm passed the narrow bug oracle, 1/1 each, yet both violated supported zero-wait compatibility. A separate retrospective diagnostic applied each final production patch with original tests and the unchanged frozen oracle overlay: both passed 0/2 compatibility checks. This diagnostic does not replace frozen grading; the original native broader-suite result also had test-overlay collection interference. These are agent-authored patch regressions, not defects attributed to the upstream project.
- **V7 fixed cross-file dispatch check:** evaluator-authored native reformulation exposed more relevant navigation candidates, and a direct path supplied module-mediated navigation. Broad structural SQL reached its 262,144-byte cap after 709 edge rows, before delivering any seed-node rows. These are different response populations, not a measured native/SQL recall comparison. Neither route established complete dispatch behavior; no consumer session ran in this fixed-check phase.
- **B1:** five deliberately selected historical relationship questions were investigated with preserved records and analyst-designed SQL. Two supporting cases are included here: in cattrs, native retrieval selected four required stored navigation relationships but emitted none; focused analyst-written SQL delivered all four. The original broad SQL also lost two of those four at its byte cap. In HTTPX, native call refinement recovered the one required relationship, as did scoped analyst-written SQL. These case-specific counts are not pooled. Emitted output is not necessarily model delivery, and addressability measures neither an unfamiliar agent's formulation effort nor avoided source reads. Source remains necessary for behavior and completeness.

## Reproduction

The standard-library [renderer](../scripts/render_evidence.py) divides aggregate sums by session counts and rounds half up to whole tokens. It regenerates [total input](figures/total-input.svg), [uncached input](figures/uncached-input.svg) and [retrieval delivery](figures/retrieval-delivery.svg), and checks every number the README states. Run with `--check` to compare bytes. The nominal interval and the ledger are retained analysis results, not recalculated from aggregates. These files reproduce displayed calculations and figures, not the underlying experiments or independent grading. No raw sessions, study source, patch, identity, host or private path is included. Private primary records remain outside the public distribution.
