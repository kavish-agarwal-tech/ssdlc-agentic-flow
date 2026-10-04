# Governed agentic SSDLC

An in-place implementation of the assignment and the updated [SupplementaryPrompt.txt](SupplementaryPrompt.txt). DeepSeek reasons about engineering artifacts; LangGraph runs explicit transitions; real Python tools supply objective evidence. The offline mock is a greeting fixture, not a URL-shortener generator.

## Setup and run

Use Python 3.11 or later and the project virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.lock
.venv\Scripts\python -m pip install -e . --no-build-isolation --no-deps
```

Put `DEEPSEEK_API_KEY` in the ignored `.env`. Supported configuration: `LLM_PROVIDER=deepseek`, `LLM_MODEL=deepseek-flash`, `LLM_BASE_URL=https://api.deepseek.com`, `LLM_TIMEOUT=180`. `.env.example` documents these settings. Existing nonempty environment variables take precedence. No local model installation is needed. Do not put credentials in requirements, generated artifacts, or commits.

Start the real URL-shortener workflow:

```powershell
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution start --requirement examples/url-shortener/requirement.txt --run url-shortener --interactive
```

Answer blocking product questions, approve the resulting requirement, review and approve architecture/ADRs, then review the final release. Local execution is opt-in and runs generated code on this host; it is not a security sandbox. Deployment is outside this application's tool surface.

Resume or inspect a saved run:

```powershell
.venv\Scripts\python -m ssdlc --provider deepseek --allow-local-execution resume url-shortener --interactive
.venv\Scripts\python -m ssdlc inspect url-shortener
.venv\Scripts\python -m ssdlc audit url-shortener
.venv\Scripts\python -m ssdlc metrics url-shortener
.venv\Scripts\python -m ssdlc export url-shortener --output .ssdlc/url-shortener-export.json
```

Use `--home` before the command to isolate runs. Interactive EOF leaves a durable pause. Approval requires an actor, rationale, and the exact artifact version. Retry at a safe stop explicitly renews a bounded budget; repeated retry without correcting the cause is unlikely to help. Legacy safe stops whose recovery stage was separate design/planning now return to combined planning/design. Direct checkpoints inside removed nodes require starting a fresh run; history is retained.

Run the labeled offline fixture with real tools:

```powershell
.venv\Scripts\python -m ssdlc --allow-local-execution demo --scripted --run greeting-demo
```

`--scripted` uses synthetic human decisions only for this fixture. Live DeepSeek runs never automatically approve product decisions. Three normal gates remain: requirement, architecture/ADRs, final release. Plan/design, quality review, and slice acceptance are autonomous within the approved baseline and bounded budgets.

## Artifacts and state

Human-readable versioned artifact JSON, provider response cache, source snapshots, and generated candidate files live under `.ssdlc/runs/<run>/`. SQLite holds indexes, audit records, and LangGraph checkpoints. Artifact bodies belong on the filesystem; database state makes resume and lineage reliable. Published artifact versions are immutable; upstream changes supersede versions and invalidate dependent evidence. Candidate directories include source, tests, and successful wheel output under `dist/`.

See [architecture](docs/architecture.md), [orchestration](docs/orchestration.md), [decisions and tradeoffs](docs/decisions.md), and [testing and workload evidence](docs/testing.md). Original assignment inputs remain as provenance; operational documentation follows the supplementary refactor.
