# External projects and provenance

Graphify is an independent external graph producer: [official project](https://github.com/Graphify-Labs/graphify), [upstream license](https://github.com/Graphify-Labs/graphify/blob/HEAD/LICENSE). sql_orient imports JSON exports; it does not bundle Graphify or require it at runtime. No affiliation or endorsement is implied. Consult upstream for the license applicable to your version and use.

SCIP is an external interchange format: [specification](https://github.com/scip-code/scip/blob/main/scip.proto), [upstream license](https://github.com/scip-code/scip/blob/main/LICENSE). The input adapter and synthetic wire probe implement interoperability; no decoder or generated protobuf implementation is included.

The small Python fixture, its graph and SCIP facts are synthetic project test material. The SCIP documentation string contains only a declaration from that fixture. No Dulwich, structlog or other studied project source, patch or research capture is distributed.

Product runtime dependencies are Python's standard library (including SQLite). Build and test tools are installed separately. The project's Apache-2.0 license and its `NOTICE` copyright line cover sql_orient material only; they do not grant or claim rights in external projects. No upstream NOTICE is represented as a project notice requirement.
