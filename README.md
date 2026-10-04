# Governed agentic SSDLC

A CLI that turns requirements into reviewed engineering artifacts, generated code, independent tests and a release candidate. DeepSeek proposes engineering decisions; LangGraph runs the workflow; deterministic policy and actual tools decide whether it can proceed. Final approval marks `READY_FOR_DEPLOYMENT`; it does not deploy or start a service.

The implementation follows the original assignment and [SupplementaryPrompt.txt](SupplementaryPrompt.txt). The supported execution toolchain is **Python**. The offline mock generates a greeting fixture; real workloads use DeepSeek.

## Key features

| Feature | What the solution does |
|---|---|
| **Human control at three gates** | Requires explicit approval of requirements, architecture/ADRs and the final release. Blocking ambiguity must be clarified before approval. |
| **Stateful LangGraph workflow** | Handles conditional routing, parallel generation, synchronization, bounded revisions and durable pause/resume. |
| **Independent code and test generation** | Runs both branches concurrently from the same approved design. The test agent does not receive generated implementation; shared quality review follows their join. |
| **Actual testing and packaging** | Executes Ruff, Python compilation, pytest and wheel building. Checks that mapped acceptance tests ran and passed, including earlier slices in the final candidate. |
| **Targeted failure recovery** | Classifies failures and returns to code, tests, design, architecture or requirements. Invalidates affected evidence, reuses a valid sibling where possible and stops when budgets are exhausted. |
| **Versioned, reviewable artifacts** | Stores immutable JSON versions, Markdown for section-based documents and raw code/test files. SQLite manages indexes, audit and checkpoint state. |
| **Brownfield change support** | Snapshots existing source, analyzes impact and assembles a changed candidate without modifying the supplied source directory. |
| **Traceability and inspection** | Connects requirement IDs, acceptance criteria, artifacts, reviews and executed tests. CLI commands expose saved state, audit integrity, timing/count metrics and exports. |
| **Real and offline model modes** | Uses DeepSeek for live reasoning and a labeled deterministic greeting fixture for repeatable tests without an API key. |
| **Documented release and delivery package** | Produces an engineering/operations report before approval. After approval, `package` exports a readable folder and ZIP with application, documents, wheel and evidence. |

The design keeps probabilistic model proposals separate from deterministic approvals, routing and tool evidence. There is one combined planning/design response, one shared quality review and one release-documentation stage, keeping the workflow compact.

**Validation status:** the mock E2E completes with real tools; live DeepSeek requirement analysis has reached genuine human gates. A completed live URL-shortener release and its analytics extension remain pending. See [measured evidence](docs/testing.md#recorded-evidence) and the [enhancement backlog](docs/enhancements.md).

Start with [installation](#1-install), then [the offline demo](#2-verify-locally-without-an-api-key) or [a real workload](#4-run-a-real-workload). For the design, see the [component diagram](docs/architecture.md) and [workflow diagram](docs/orchestration.md).

## 1. Install

Prerequisites: Python 3.11 or later, a checkout of this repository, and internet access for initial dependency installation. Use PowerShell from the repository root. Calling the virtual-environment interpreter directly avoids activation and execution-policy problems.

```powershell
cd C:\Users\16122\learn\schwab-assignment
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.lock
.venv\Scripts\python -m pip install -e . --no-build-isolation --no-deps
.venv\Scripts\python -m ssdlc --help
```

On Linux/macOS, use your checkout directory and replace `.venv\Scripts\python` with `.venv/bin/python`; create the environment with `python3 -m venv .venv` if needed. The `ssdlc` console entry point is also installed; examples use `python -m ssdlc` to keep the interpreter explicit.

## 2. Verify locally without an API key

```powershell
.venv\Scripts\python -m ssdlc --allow-local-execution demo --scripted --run greeting-demo-1
```

Expected outcome: `READY_FOR_DEPLOYMENT`, with code, independent tests, a shared review, passing lint/compilation/pytest and a wheel. `--scripted` supplies labeled synthetic human decisions **only for the mock fixture**. It does not establish real-model quality or approve a real product. Use a new run ID when repeating.

To practice interactive prompts with the same fixture:

```powershell
.venv\Scripts\python -m ssdlc --provider mock --allow-local-execution start --requirement examples/minimal/requirement.txt --run greeting-interactive-1 --interactive
```

For the fixture's blank-name question, select `Reject with ValueError`. Then review and approve the revised requirement, architecture/ADRs and final release.

## 3. Configure DeepSeek

Create `.env` only if it does not already exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env` locally and set `DEEPSEEK_API_KEY` to your real key. Keep it out of requirements, source files and commits. `.env` and `.ssdlc/` are ignored by Git. Live runs need endpoint access; no local model installation is needed.

| Setting | Default / behavior |
|---|---|
| `LLM_PROVIDER` | `deepseek`; `mock` selects the fixture. `--provider` overrides selection. |
| `LLM_MODEL` | If unset, use `DEEPSEEK_MODEL`; if neither is set, use `deepseek-flash`. |
| `DEEPSEEK_API_KEY` | Required for live runs; nonempty `LLM_API_KEY` takes precedence. |
| `LLM_BASE_URL` | `https://api.deepseek.com`; the adapter appends `/chat/completions`. |
| `LLM_TIMEOUT` | `180` seconds per HTTP request. |
| `LLM_MAX_OUTPUT_TOKENS` | `32768` tokens per response; sent as `max_tokens`. Increase within your model's limit if code generation is truncated, or reduce the slice. |

The CLI loads `.env` by default; `--env-file <path>` selects another file. Nonempty process environment values override file values; empty entries can be filled from the file. This is a simple `KEY=value` loader, without shell evaluation or variable expansion.

## 4. Run a real workload

```powershell
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution start --requirement examples/url-shortener/requirement.txt --run url-shortener-1 --interactive
```

For the simpler first release, use the [complete permanent-link specification](examples/url-shortener/requirement-complete.txt). It defines exact HTTP behavior, failure handling and 28 mapped acceptance criteria, while leaving framework/datastore choices to architecture approval. It is a new draft baseline; keep earlier runs intact.

```powershell
$env:LLM_MAX_OUTPUT_TOKENS = "65536"
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution start --requirement examples/url-shortener/requirement-complete.txt --run url-permanent-v1 --interactive
```

Review and approve the analyzed requirement, then architecture/ADRs, then final release. No TTL, expiry response or mapping-age purge belongs in this first release. Use the existing expiration example afterward for the ambiguous enhancement. For brownfield analytics, use [time-bucketed reporting](examples/url-shortener/brownfield-time-buckets.txt), since basic counts already exist in this baseline. Final wheel build/sign-off are platform gates, not application tests that depend on future approval.

The input is initial intent. Answer blocking questions before approving the resulting version. Review any proposed stack or performance target. The fixed toolchain currently supports Python; third-party packages required by generated code must already be installed in the CLI environment. Candidate checks do not install dependencies.

| Human gate | Your decision | What follows |
|---|---|---|
| Requirement | Clarify ambiguity, then separately approve the new version. | Architecture authoring and independent review. |
| Architecture and ADRs | Review alternatives, mappings and risks; approve or request revision. | Combined planning/design, parallel coding and independent tests, shared review, actual checks and slice acceptance. |
| Final release | Review the report, risks and measured build/test evidence. | Readiness is recorded; no deployment occurs. |

`--allow-local-execution` runs generated code and build hooks on this host; path/environment guards are not process isolation. Without it, artifact generation/review can proceed but the workflow stops before running tools. Use an appropriate disposable environment for untrusted generated code.

Global options go **before** `start`, `resume` or other commands. Run IDs contain letters, digits, underscores or hyphens, up to 100 characters. Existing runs are resumed, not overwritten.

## 5. Resume, inspect and recover

```powershell
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution resume url-shortener-1 --interactive
.venv\Scripts\python -m ssdlc inspect url-shortener-1
.venv\Scripts\python -m ssdlc audit url-shortener-1
.venv\Scripts\python -m ssdlc metrics url-shortener-1
.venv\Scripts\python -m ssdlc export url-shortener-1 --output .ssdlc/url-shortener-1-export.json
```

Inspection, audit, metrics, export and packaging do not call DeepSeek. Resume requires the original provider identity, including model and base URL. If you start with `--home <directory>`, supply the same home for every subsequent command. For example, resume the previously created local expiration run with:

```powershell
.venv\Scripts\python -m ssdlc --home .ssdlc/refactor-live --provider deepseek --allow-local-execution resume expiration-refactor --interactive
```

That run's recorded requirement v2 contains the confirmed expiration policy and awaits separate approval. It exists only in the workspace where it was created; runtime state is not checked into Git.

Interactive EOF or Ctrl+C leaves the run resumable. Approvals require actor, rationale and exact current artifact reference; interactive mode supplies the reference. At a safe stop, inspect the reason/evidence before choosing an available action. Retry renews a bounded budget; supported revision supplies feedback; rollback preserves history and invalidates descendants; abort ends the run. BLOCKER risks cannot be accepted. See [recovery rules](docs/orchestration.md).

For a generation stop caused by an incomplete design or an undecided requirement, choose `revise`. After your name and rationale, select the revision target: `generation` to correct a bundle, `planning_design` to specify the shared interfaces, or `requirement` to clarify product behavior. Requirement revision creates a new draft and returns to human requirement approval; architecture/ADRs must then be reviewed and approved again. It does not accept findings or waive tests. No finding ID is needed.

For the URL-shortener DNS ambiguity, use `requirement` with the rationale: “DNS failure or resolution returning no addresses must return structured 503 and persist nothing. Preserve all other approved requirements.” Review the resulting requirement before approving it. The subsequent shared design must name the exact injected resolver, configuration interface, store error type, and durable store constructor/reopen lifecycle. Required restart tests must execute rather than skip a missing adapter.

Shared interface conflicts are now checked earlier: every slice needs a Python `api_contract` containing exact file paths and public declaration stubs. Planning validates it, then code signatures/data fields and direct test imports are checked before quality review. Persistent contract mismatches automatically return to planning within the replan budget. For an existing run with an older plan, restart the CLI and choose `retry` at its generation stop to run this recovery. This preserves approvals and does not waive tests; genuine product ambiguity still requires requirement revision.

Restart a running CLI after source or environment changes. Interactive sessions detect changed Python source before submitting the next decision and exit without consuming the saved gate. They cannot reload code already running. Changing the output-token budget preserves provider identity for resume; truncated responses are never accepted as artifacts.

For file-based decisions, start without `--interactive`, inspect the gate, then use `resume <run> --decision <file.json>`. A decision has `actor`, `action`, `rationale`, and the gate's `artifact_ref` when present; clarification adds `answers` keyed by question IDs. Clarification and approval are separate submissions.

| Symptom | Next step |
|---|---|
| Missing key, HTTP error or timeout | Check local environment, endpoint/model access and connectivity; inspect the safe-stop reason. |
| `Local execution disabled` | Resume with the same home/provider and `--allow-local-execution`, then explicitly retry. |
| Missing dependency/build tool | Install it in the CLI environment; retry after correcting the environment. |
| `Run already exists` / `Unknown run` | Resume the existing ID or use a new ID; verify `--home`. |
| Provider identity mismatch | Restore the original model/base URL/provider. |
| Schema/review/replan budget exhausted | Review feedback and correct the cause; retry alone can repeat the failure. |
| Legacy checkpoint in a removed node | Start a new run and retain history. Legacy safe stops naming planning/design recover through combined planning/design. |

## 6. Package the approved generated solution

Once the run reaches `READY_FOR_DEPLOYMENT`, create its delivery folder and ZIP:

```powershell
.venv\Scripts\python -m ssdlc package url-shortener-1
```

The default folder is `.ssdlc/deliverables/url-shortener-1/release-v1/`, with a sibling `url-shortener-1-release-v1.zip`. Use the same `--home` as the original run. Start with the package's `README.md`; it links to the numbered documents and explains the contents.

```text
release-v1/
  README.md
  application/                   # final source and tests, original project layout
  distribution/                  # built wheel files
  documents/
    01-requirements.md
    02-architecture.md
    03-decisions/ADR-001.md
    04-plan-and-design.md
    05-release-readiness.md
    06-brownfield-impact.md       # brownfield releases only
    07-validation-and-review.md
  artifacts/                     # final JSON, e.g. requirement-v0002.json
  evidence/                      # JUnit, tool results, reviews, approvals, audit, metrics
  manifest.json                  # artifact references and exported-file SHA-256 hashes
```

All active artifacts are exported with readable names and versions. Full saved history, including earlier artifact versions, is retained in `evidence/workflow-history.json`. Only the final assembled application is copied; intermediate candidates and caches are excluded. Tests remain inside the application's original layout so their imports continue to work.

Choose another **new** output directory if needed:

```powershell
.venv\Scripts\python -m ssdlc package url-shortener-1 --output .ssdlc/deliverables/url-shortener-handoff
```

Existing packages are not overwritten. Packaging checks final approval, release evidence, candidate integrity and audit integrity. It does not run models, change workflow state, install dependencies or deploy the application. A pending or failed run cannot be labeled as a final delivery package. File checksums describe exported bytes; they are not a digital signature.

## Internal artifacts and generated solution

Default storage:

```text
.ssdlc/
  audit.sqlite                 # indexes, metadata, cache pointers, audit, leases
  checkpoints.sqlite           # LangGraph resume state
  runs/<run>/
    artifacts/<kind>/<id-hash>/v0001.json
    artifacts/<kind>/<id-hash>/v0001.md          # section-based documents
    artifacts/<kind>/<id-hash>/v0001/files/...   # code/test bundles
    provider-cache/...
    source/...                 # brownfield input snapshot
    candidates/<digest>/...    # source, tests, .results.xml and dist/*.whl
```

Artifact content is versioned on the filesystem. SQLite indexes it and holds audit/checkpoint state; checkpoints also serialize workflow data. Section-based artifacts, including architecture and release reports, have Markdown companions. Requirements and plans are JSON internally; the final delivery package renders both as readable Markdown.

Find the validated candidate through `inspect`: `state.artifacts[state.active.release].content.candidate` at the release gate, or the build artifact's `content.cwd`. Follow the generated release report's setup/API instructions to run the application manually. The SSDLC CLI validates and packages it; it does not host it.

Brownfield accepts `--scenario brownfield --source <existing-source-directory>`. It snapshots selected text files, performs impact analysis after architecture approval and validates a changed candidate in the run workspace. The original source directory remains unchanged. [Testing](docs/testing.md) provides workload commands and measured evidence.

## Documentation

| Document | Purpose |
|---|---|
| [Architecture](docs/architecture.md) | Component diagram, ownership and persistence boundaries. |
| [Orchestration](docs/orchestration.md) | Lifecycle, human gates, budgets and recovery. |
| [Decisions](docs/decisions.md) | Design choices and tradeoffs. |
| [Testing](docs/testing.md) | Platform tests, generated-solution checks and live evidence. |
| [Pending work and enhancements](docs/enhancements.md) | Unfinished validation and proposed improvements. |

Original assignment inputs remain provenance; operational instructions follow the supplementary refactor.
