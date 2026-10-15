# Optional SCIP interoperability

Supply `--scip index.json` for UTF-8 JSON with `documents` and optional `metadata`. Documents have `relative_path`, optional `position_encoding`, `occurrences` and `symbols`. Occurrences use `symbol`, `symbol_roles`, and either a legacy `range` array of three or four coordinates, snake-case `single_line_range`/`multi_line_range`, or Go `TypedRange` oneof wrappers. Enclosing ranges follow the corresponding enclosing field names. Conflicting encodings and unsupported camel-case shapes reject. See the [synthetic JSON](../tests/fixtures/mini/scip.json).

Ranges are half open. Three coordinates mean line/start/end on one line; four mean start-line/start-column/end-line/end-column. Position units are preserved, not converted between UTF-8, UTF-16 and UTF-32. Missing encoding remains unknown.

For binary input, install a compatible external SCIP CLI separately. The adapter probes typed ranges and position_encoding before decoding; compatibility was checked in development with v0.9.0. An absent or incapable decoder yields an actionable error. JSON needs no decoder. See [SCIP](https://github.com/scip-code/scip) and its [license](https://github.com/scip-code/scip/blob/main/LICENSE).

Identity links require exact path, declaration line and name, or a file/module identity. Ambiguity stays unlinked. Symbols and references do not establish call semantics or source correctness.
