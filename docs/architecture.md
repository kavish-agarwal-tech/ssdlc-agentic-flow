# Architecture

The implementation collects explicit human decisions, generates typed engineering proposals and enforces progress using saved state and actual evidence. LangGraph orchestrates these responsibilities; application code owns policy.

```mermaid
flowchart LR
  Operator["Operator"] --> CLI["CLI<br/>start / resume / inspect"]
  CLI --> Runtime["Runtime<br/>run identity and local lease"]
  Runtime --> Graph["LangGraph<br/>routing, parallel join, interrupts"]
  Graph --> Nodes["Nodes and policy<br/>typed proposals, approvals, evidence gates"]
  Nodes --> Provider["Provider protocol"]
  Provider --> Mock["PRIMARY: deterministic workers<br/>URL-shortener templates"]
  Provider --> DeepSeek["OPTIONAL: DeepSeek<br/>real-LLM extension"]
  Nodes --> Executor["Local executor<br/>Ruff, compile, pytest, wheel"]
  Nodes --> Repository["Artifact repository"]
  Repository --> Files["Filesystem<br/>versions, documents, source, candidates"]
  Repository --> Audit["audit.sqlite<br/>indexes, audit, cache pointers, leases"]
  Graph --> Checkpoint["checkpoints.sqlite<br/>durable workflow state"]
```

## Component ownership

| Component | Main source files under `src/ssdlc/` | Responsibility |
|---|---|---|
| CLI | `cli.py`, `config.py` | Load local configuration, show progress/gates, collect decisions and expose inspection/export. |
| Runtime | `runtime.py` | Bind run/provider identity, open stores, snapshot brownfield input, start/resume workflows and report metrics. |
| Graph | `graph.py`, `state.py` | Explicit conditional routes, parallel branch map merges and the join barrier. |
| Engineering and policy | `nodes.py`, `engine.py`, `agents.py`, `models.py`, `policy.py` | Typed role contracts, semantic validation, bounded calls/reviews, exact approvals, invalidation and release gates. |
| Providers | `providers.py`, `mock.py`, `url_demo.py`, `templates/` | Primary deterministic URL-shortener workers and independent source/test templates; optional DeepSeek JSON-mode HTTP calls. No synthetic fallback. |
| Persistence | `persistence.py` | Immutable content files, Markdown/source companions, mutable metadata and a local audit hash chain. |
| Tools | `tools.py` | Confined candidate materialization and actual fixed Python commands with captured evidence. |
| Delivery packaging | `packaging.py`, `Runtime.package` | Export an approved release as a readable folder/ZIP, with named documents, source/tests, wheel, artifact references and evidence. No model calls or workflow changes. |

## Engineering artifacts

Requirements preserve original input and actual human answers as system-owned provenance. Architecture includes requirement mappings, alternatives and ADRs. An independent architecture reviewer assesses it before joint human approval of architecture/ADRs.

One Plan response contains ordered vertical slices with requirement references, acceptance IDs, risks and implementation design. Code and independent tests consume the same approved baseline and slice design concurrently. The test designer does not receive generated implementation files or code-author output. Shared Quality Review assesses the joined pair. Release Readiness combines engineering documentation, operations, limitations and measured evidence.

Each slice also contains a shared Python API contract as declaration stubs. Planning validates it before either generator runs; generated public signatures, data fields and direct test imports are checked before shared review. Persistent contract mismatches return to planning under the existing replan budget. Runtime behavior remains subject to independent tests, review and actual execution.

Pydantic validates shape. Stage validators enforce exact references, coverage, meaningful required sections, dependency order, paths, file ownership and criterion-to-test mappings. Responses enter the cache only after validation; cached responses are checked again. Strict schemas can still reject a model response after bounded repair attempts, so model availability does not guarantee success.

Default agents are deterministic specialized workers, not LLM simulations. They produce structured requirement, architecture/design, review, code, test, impact and readiness artifacts for bounded assignment scenarios. `PRODUCT_AMBIGUITY` may block requirements; `ARCHITECTURE_DECISION` and `NON_BLOCKING_ASSUMPTION` belong in normal artifact review. Greenfield has six functional requirements, four nonfunctional requirements, eleven criteria and zero clarification questions. Expiration asks four product questions. Brownfield parses the supplied module and patches daily analytics while preserving its source and database records.

## Generated application

```mermaid
flowchart LR
  Client["Local HTTP client"] --> Server["HTTPServer / create_server"]
  Server -->|create / redirect / analytics| Store["Store: validate and transact"]
  Store --> SQLite["links.sqlite<br/>mappings + synchronous counts"]
  Server -->|GET /health| Health["Liveness: 200 / status ok"]
  Store -->|database failure| Error["Sanitized 503"]
```

The application's SQLite database is separate from the platform's checkpoint/audit databases. The server binds loopback and never fetches a target. SQLite transactions commit creation and successful redirect counts; generated tests reopen the same file to verify durability. The daily extension adds a table and enables transactional UTC buckets; the expiration scenario stores chosen TTLs separately so prior mappings stay permanent.

## Filesystem and database boundary

Canonical artifact content, dependencies and digests live in versioned JSON. Artifacts with `sections` also have Markdown companions; code/test bundles have raw-file companions. Requirements and plans remain JSON. Candidates assemble the brownfield snapshot and valid slice changes, including tests, JUnit reports and wheels.

`audit.sqlite` holds artifact indexes/mutable metadata, provider-cache file pointers, audit records and local leases. `checkpoints.sqlite` holds LangGraph state, which can include serialized artifact data. Artifact storage is filesystem-backed with database-managed state; this does not mean artifact data never appears in SQLite.

New versions retain old content and invalidate dependent evidence or mark it for revalidation. Targeted tool-failure recovery can reuse a valid reviewed sibling; the changed pair is reviewed again. Audit hashes support local integrity checks, not externally guaranteed tamper resistance. The stores support the local single-writer prototype.

## Evidence and release boundary

The executor uses the CLI's Python interpreter. Its child environment strips ordinary application credentials, disables pytest plugin autoload and disallows package-index access through pip. It records command, status, duration, output summary, artifact references and candidate fingerprint. These guards do not create an OS sandbox or prevent all network access; generated code/build hooks run on the host.

Release requires the approved current baseline, complete reviews without prohibited findings, accepted slices with passing actual tests, a successful actual build and a matching candidate. Earlier slice tests must pass in the final cumulative candidate too. Final approval rechecks the candidate and records readiness. No server-start or deployment tool is exposed.

See [orchestration](orchestration.md) for the lifecycle and recovery, and [enhancements](enhancements.md) for remaining work.
