# Testing and workload evidence

```powershell
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format --check src tests
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m build --wheel --no-isolation
.venv\Scripts\python -m ssdlc --allow-local-execution demo --scripted --run interview
```

Install the locked dev dependencies before running tools; candidate validation does not install packages. Automated tests are offline. They use mocked HTTP for DeepSeek request/JSON/error behavior and deterministic providers for governance. Integration tests run the actual LangGraph workflow and actual Ruff, compilation, pytest/JUnit and wheel build against generated greeting files. A threading barrier proves parallel generation and common baseline without implementation exposure to test generation.

Regression coverage includes persistent clarification/approval, exact version checks, semantic architecture repair before caching, rejection of invalid legacy cache formats, combined plan/design completeness and reference repair, independent test ownership, bounded architecture and shared quality review, failed-tool routing, unaffected sibling reuse, source snapshots, dependency invalidation, rollback history, audit integrity, path guards, release evidence and candidate tampering during human review. Obsolete separate design and plan-gate tests were replaced with combined-workflow checks.

The mock greeting reaches READY_FOR_DEPLOYMENT with labeled synthetic approvals and real passing tools. This verifies the system plumbing; it is not real DeepSeek product evidence.

For real DeepSeek, run `examples/url-shortener/requirement.txt` using the README command. For ambiguity analysis, start `examples/url-shortener/expiration.txt` with `--scenario ambiguous` and a new run ID. Human confirmation must resolve TTL, HTTP behavior, retention and cleanup choices. After a greenfield run has generated a source candidate, start `examples/url-shortener/brownfield-analytics.txt` with `--scenario brownfield --source <candidate-directory>`. Inspect actual source impact before approving the change. Do not substitute a hand-coded application for workflow output.

Live runs stop at genuine clarification and approval gates. Historical `examples/url-shortener/analysis-attempt.json` records a previous attempt; it does not prove a released URL shortener. On October 4, 2026, `url-shortener-schema-fix` (greenfield) reached WAITING_FOR_HUMAN at requirement@1 using the configured DeepSeek model. `expiration-refactor` (ambiguous) reached the same clarification gate, then produced requirement@2 after the user confirmed optional expiration, permanent-by-default links, HTTP 410 for expired links, 30-day analytics retention, no reactivation, daily cleanup after 30 days, permanent existing links and authoritative database records. Requirement@2 is awaiting its separate human approval; model-proposed nonfunctional constraints still require review. The first greenfield attempt safely stopped after two invalid responses; making allowed output keys and correction behavior explicit fixed the subsequent analysis. [Measured live summaries](../examples/url-shortener/refactor-analysis.json) retain the actual questions, confirmed decisions and status. No full live URL-shortener completion or subsequent brownfield completion is claimed until saved tools and final human approval support it.

The updated [mock execution summary](../examples/minimal/execution.json) records the READY_FOR_DEPLOYMENT outcome, actual tool output, agent calls and audit integrity. After refactoring, 63 automated tests pass, Ruff lint/format checks pass and the package wheel builds.

Resume live clarification with:

```powershell
.venv\\Scripts\\python -m ssdlc --home .ssdlc/refactor-live --provider deepseek --allow-local-execution resume url-shortener-schema-fix --interactive
```
