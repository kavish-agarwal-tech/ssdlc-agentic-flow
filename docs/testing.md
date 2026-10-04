# Testing and workload evidence

## Test the SSDLC platform

Run from the repository root after following [installation](../README.md#1-install). These checks use the local virtual environment; the automated suite does not call DeepSeek.

```powershell
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format --check src tests
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m build --wheel --no-isolation
.venv\Scripts\python -m ssdlc --allow-local-execution demo --scripted --run interview
```

Install the locked dev dependencies before running tools; candidate validation does not install packages. Automated tests are offline. They use mocked HTTP for DeepSeek request/JSON/error behavior and deterministic providers for governance. Integration tests run the actual LangGraph workflow and actual Ruff, compilation, pytest/JUnit and wheel build against generated greeting files. A threading barrier proves parallel generation and common baseline without implementation exposure to test generation.

The CI workflow performs locked installation, lint, formatting, pytest and wheel build on Ubuntu with Python 3.11. Local PowerShell commands use the interpreter explicitly; on Linux/macOS replace `.venv\Scripts\python` with `.venv/bin/python`.

Regression coverage includes persistent clarification/approval, exact version checks, semantic architecture repair before caching, rejection of invalid legacy cache formats, combined plan/design completeness and reference repair, independent test ownership, bounded architecture and shared quality review, failed-tool routing, unaffected sibling reuse, source snapshots, dependency invalidation, rollback history, audit integrity, path guards, release evidence and candidate tampering during human review. Obsolete separate design and plan-gate tests were replaced with combined-workflow checks.

Quality-recovery regressions cover validation of resolutions before caching and on cache replay, blank verification/author fields, unresolved assessments incorrectly placed in resolutions, unknown/cross-artifact targets, conflicting finding/resolution IDs, legacy duplicated namespaces, and retry routing to actual branch revision while preserving open blockers.

Shared-interface regressions verify planning repair before generation, declaration-only Python contracts, constructor/injection signatures, response fields, direct application imports, legacy-plan recovery and bounded automatic replanning before quality review. Local verification on October 4, 2026 passed all 91 tests, Ruff lint/format checks and the platform wheel build. This is platform/fixture evidence; the live URL-shortener still needs its own passing tools and final approval.

Delivery-package tests run a complete fixture through actual tests/build and final synthetic approval. They verify readable document names, source/test layout, wheel/JUnit evidence, all active artifact references, exported-file checksums and ZIP contents. They also check that packaging does not change saved workflow state, refuses pending approval or changed source, cleans up an incomplete export and does not overwrite an existing package.

The mock greeting reaches READY_FOR_DEPLOYMENT with labeled synthetic approvals and real passing tools. This verifies the system plumbing; it is not real DeepSeek product evidence.

## How the generated solution is tested

The test agent derives acceptance tests from the approved baseline and slice design independently of generated implementation. Shared review follows the code/test join. With `--allow-local-execution`, the executor runs these fixed commands in the assembled candidate directory using the CLI's Python interpreter:

| Stage | Actual command | Evidence |
|---|---|---|
| Lint | `python -m ruff check --isolated .` | Exit status and output; isolated Ruff settings. |
| Static check | `python -m compileall -q .` | Python compilation result; not a type checker. |
| Tests | `python -m pytest -q --junitxml=.results.xml` | Exit status and JUnit results matched to claimed acceptance-test IDs. |
| Packaging | `python -m build --wheel --no-isolation` | Build result and candidate output under `dist/`. |

The shared review and actual tests must pass before slice acceptance. The final candidate must also pass earlier slices' mapped tests. Tool output and candidate fingerprints are saved; changing source during validation or final approval invalidates readiness. Failed validation/build triggers diagnosis and bounded targeted recovery. The build runs after Release Readiness, before the final gate.

Packages must already be available in the CLI environment: generated dependency installation is not a workflow step. Runtime child processes disable pytest plugin autoload, so a solution requiring external plugins is outside the default tested toolchain. `READY_FOR_DEPLOYMENT` means the implemented gates passed and a human signed off; it does not prove exhaustive coverage, security or a running deployed service.

`metrics` reports workflow/tool event counts and timing. In particular, `test_pass_count` counts successful test-command events, not individual pytest cases; use `.results.xml` for case-level results. Coverage percentages, token usage and cost are not currently reported.

## Run the live workload scenarios

The [complete first-release input](../examples/url-shortener/requirement-complete.txt) is a new permanent-link baseline selected by the user. Its local checks confirm 15 unique FR/NFR definitions, 28 unique acceptance criteria and complete reference coverage. These structural checks do not establish semantic approval or a working service. Real requirement analysis, human requirement/architecture approval, generated code/tests, tool/build evidence and final sign-off remain necessary. Preserve the old TTL run as historical evidence rather than changing its approved artifacts in place.

On October 4, 2026, after explicit authorization to send this specification to DeepSeek, run `url-permanent-v1` produced `requirement@1` and reached `WAITING_FOR_HUMAN`. It retained 28 acceptance criteria, raised 11 questions (one classified blocking), and passed audit-chain verification. The [real analysis snapshot](../examples/url-shortener/permanent-v1-analysis.json) is explicitly unapproved. The model's proposed durable analytics capture exceeds the best-effort input and needs review; no architecture, code, tests/build or release approval was performed.

For this baseline, the [time-bucketed analytics enhancement](../examples/url-shortener/brownfield-time-buckets.txt) supplies a meaningful brownfield change; basic per-code counts already belong to the first release. The expiration input remains a separate ambiguous enhancement of generated permanent-link source.

These commands require your DeepSeek key and real human decisions. Use fresh run IDs or resume the existing runs. Global flags come before the subcommand.

```powershell
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution start --requirement examples/url-shortener/requirement.txt --run url-greenfield-1 --interactive
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution start --requirement examples/url-shortener/expiration.txt --scenario ambiguous --run url-expiration-1 --interactive
```

The standalone expiration example exercises ambiguity analysis; it does not supply an existing application. Human confirmation must resolve TTL, HTTP behavior, retention and cleanup choices. To implement a change against an existing solution, use a brownfield run with its source.

After a greenfield run has produced a validated candidate, set `$source` to its actual `release.content.candidate` path from `inspect`, then run the analytics extension:

```powershell
$source = "C:\path\to\the\generated\candidate"
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution start --requirement examples/url-shortener/brownfield-analytics.txt --scenario brownfield --source $source --run url-analytics-1 --interactive
```

Replace the illustrative path before execution. Inspect source impact and compatibility before approving the change. Do not substitute a hand-coded application or the greeting fixture for workflow-generated URL-shortener source.

## Recorded evidence

Live runs stop at genuine clarification and approval gates. Historical `examples/url-shortener/analysis-attempt.json` records a previous attempt; it does not prove a released URL shortener. On October 4, 2026, `url-shortener-schema-fix` (greenfield) reached WAITING_FOR_HUMAN at requirement@1 using the configured DeepSeek model. `expiration-refactor` (ambiguous) reached the same clarification gate, then produced requirement@2 after the user confirmed optional expiration, permanent-by-default links, HTTP 410 for expired links, 30-day analytics retention, no reactivation, daily cleanup after 30 days, permanent existing links and authoritative database records. Requirement@2 is awaiting its separate human approval; model-proposed nonfunctional constraints still require review. The first greenfield attempt safely stopped after two invalid responses; making allowed output keys and correction behavior explicit fixed the subsequent analysis. [Measured live summaries](../examples/url-shortener/refactor-analysis.json) retain the actual questions, confirmed decisions and status. No full live URL-shortener completion or subsequent brownfield completion is claimed until saved tools and final human approval support it.

The updated [mock execution summary](../examples/minimal/execution.json) records the READY_FOR_DEPLOYMENT outcome, actual tool output, agent calls and audit integrity. The October 4, 2026 refactor verification recorded 63 passing automated tests, passing Ruff lint/format checks and a successful package wheel build. This dated evidence does not replace rerunning validation after future code changes.

Resume live clarification with:

```powershell
.venv\Scripts\python -m ssdlc --home .ssdlc/refactor-live --provider deepseek --allow-local-execution resume url-shortener-schema-fix --interactive
```
