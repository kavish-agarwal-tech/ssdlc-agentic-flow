# Testing and workload evidence

## Platform verification

After [installation](../README.md#1-install), run:

```powershell
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format --check src tests
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m build --wheel --no-isolation
```

CI installs the pinned tools and runs these checks with Python 3.11 on Ubuntu. Tests use deterministic workers, fixtures and stubbed provider HTTP responses. They never require DeepSeek or a real key. Local PowerShell uses the explicit virtual-environment interpreter; on Linux/macOS substitute `.venv/bin/python`.

Coverage includes real LangGraph interrupts/resume, parallel branch synchronization and test independence, exact human approval versions, source snapshots, bounded retries, safe stops, targeted replanning, artifact invalidation, actual lint/pytest/build, audit integrity and approved folder/ZIP exports. The legacy greeting fixture remains for focused platform regressions; it is no longer the assignment workload.

## Three required offline scenarios

Use a fresh home when repeating:

```powershell
.venv\Scripts\python -m ssdlc --home .ssdlc/evaluation demo greenfield --scripted
.venv\Scripts\python -m ssdlc --home .ssdlc/evaluation demo ambiguous --scripted
.venv\Scripts\python -m ssdlc --home .ssdlc/evaluation demo brownfield --scripted
```

`--scripted` uses explicit synthetic fixture decisions, never real product authorization. Omit it to exercise human prompts. All three use the same graph, actual generated files and fixed tools. No API key, `.env`, model installation or external LLM call occurs. Brownfield reads the approved greenfield application's source and adds daily analytics; it is not a second hard-coded workflow.

| Scenario | Expected evidence |
|---|---|
| Greenfield | Zero clarification questions; six FRs, four NFRs, eleven ACs; real URL-shortener HTTP source/tests; passing tools/build; explicit three-gate approval history. |
| Ambiguous | Four product questions; answers create requirement v2; separate approval; selected expiry behavior tested with an injected clock and prior permanent-link database. |
| Brownfield | Snapshot of generated application; parsed source impact; bounded source patch; additive daily table migration; preserved total counts; UTC daily/restart tests. |

The integration suite runs these commands with an external-model request guard and DeepSeek environment settings, proving that the CLI default remains mock. It inspects real output, audit validity, acceptance criteria, approvals, changed source, wheels and ZIPs. Another test injects a wrong redirect status, runs real failing pytest, verifies implementation routing/invalidation, and confirms the corrected code reuses independent tests.

## How the generated application is tested

The independent Test Design worker consumes approved requirements/design only. It uses a separate bounded test template and never reads generated implementation. Tests start an ephemeral loopback HTTP server and use temporary SQLite files; no redirect target is fetched. They verify creation, exact redirects/cache headers, unknown codes, invalid URL/JSON/media/fields, duplicate targets, zero/two click counts, sanitized store failures, health and restart durability. Extension tests exercise prior database schemas and injected UTC clocks.

| Stage | Actual command | Evidence |
|---|---|---|
| Lint | `python -m ruff check --isolated .` | Exit status and captured output. |
| Static | `python -m compileall -q .` | Compilation result, not a type-checking claim. |
| Tests | `python -m pytest -q --junitxml=.results.xml` | Exit status and JUnit node IDs matched to approved acceptance mappings. |
| Build | `python -m build --wheel --no-isolation` | Actual wheel output before final release approval. |

Tools run in the assembled candidate using the CLI interpreter. They install no dependencies and strip application credentials from child environments. The known demo enables execution; generic/live runs require `--allow-local-execution`. Candidate fingerprints and all mapped executed tests must pass before final approval. Packaging checks approval, audit and evidence integrity again.

Each tool invocation uses a unique `runs/<run>/tool-tmp/<id>/` directory for temporary files. Pytest receives an explicit `--basetemp` beneath it, avoiding shared Windows `pytest-of-unknown` permissions. Temporary directories stay outside the candidate and are not exported in the application package. Safe stops show failed tool commands/output; deterministic progress is labeled as an agent rather than an LLM call.

On Windows, successful generated wheel builds publish byte-identical wheel files with the output folder's inherited permissions. This avoids owner-only backend temporary-file ACLs preventing the normal operator from packaging an agent-built wheel. The regression test verifies unchanged bytes and restored inheritance; publication errors mark the build failed rather than approving an unreadable output.

The application is a local prototype with synchronous SQLite counting. Health is liveness, not readiness. HTTPServer, local actor identities and filesystem guards do not establish production hosting, authentication or process isolation. Metrics count tool events; JUnit reports individual tests. No coverage percentage or model-quality score is claimed.

## Recorded evidence

On October 4, 2026, local verification passed **108 platform tests**, Ruff lint/format checks and a platform wheel build. A separately installed platform wheel completed the actual greenfield workflow and folder/ZIP packaging using its bundled templates. The three recorded scenarios passed **10, 11 and 11 generated application tests**, respectively, plus compilation, lint and wheel build. These are measured results from the default deterministic path.

The Windows temp-directory recovery follow-up passed **111 platform tests** and the wheel build. The user's `demo-greenfield` run retried validation with workspace-owned temporary directories, passed its ten application tests and build, and reached the separate final human release gate. Its earlier failed attempts remain in audit history; no final approval was supplied by the recovery.

After the user approved the release, wheel access was repaired by restoring its existing folder permissions without changing its SHA-256 hash, and the delivery folder/ZIP was successfully exported. The permanent wheel-publication follow-up passed **112 platform tests**, lint/format checks and the platform build. Normal operator read access was verified for the delivery README, wheel and ZIP.

The [offline execution summary](../examples/url-shortener/offline-execution.json) records dated scenario results, actual tool output, approvals, artifact references, JUnit counts and audit integrity. These are deterministic template results with synthetic approvals, not live-LLM evidence. Rerun validation after future changes.

Historical [greeting execution](../examples/minimal/execution.json) and [live analysis attempts](../examples/url-shortener/refactor-analysis.json) retain earlier provenance. The [permanent-link DeepSeek snapshot](../examples/url-shortener/permanent-v1-analysis.json) is an unapproved historical analysis with eleven questions. The local run was later rejected/aborted. A subsequent clarification-check run reached unapproved requirement review with zero questions; neither analysis proves a completed live URL-shortener release. The large 28-criterion input is retained as advanced evidence and is not the default submission.

Inspect current state with the original home:

```powershell
.venv\Scripts\python -m ssdlc --home .ssdlc/evaluation inspect demo-greenfield
.venv\Scripts\python -m ssdlc --home .ssdlc/evaluation metrics demo-greenfield
```
