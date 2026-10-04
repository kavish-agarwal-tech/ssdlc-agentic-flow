# Verification and interview demo

```powershell
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m build --wheel --no-isolation
python -m ssdlc --allow-local-execution demo --scripted --run interview
python -m ssdlc audit interview
python -m ssdlc metrics interview
```

Use the project's virtual-environment interpreter. The real-tool workflow test
requires the dev dependencies, including setuptools and build, installed locally.
It does not download packages while validating a candidate.

Tests cover ambiguity blocking, exact version approval, persistence across Runtime
instances, architecture/plan gates, bounded blocker review, real branch join, actual
failed test routing and retry exhaustion, unaffected test reuse, artifact invalidation,
audit integrity, path confinement, release evidence and metrics.

Additional tests verify real parallel branch entry with a threading barrier,
absence of code in test-design context, brownfield impact before planning, rollback
history preservation, stale approval rejection, and candidate tampering while the
human gate is waiting. Provider tests use fake HTTP transports and configurable
mock sequences for request schemas, model routing, timeout/failure budgets,
schema repair, explicit fallback and secret omission.

Architecture regression tests cover missing and whitespace-only sections,
semantic repair before caching, rejection of incomplete legacy caches in both
SQLite and file formats, preservation of rejected response files, and exhaustion
of the bounded provider budget with actionable missing-section details.

Local Ollama setup was separately verified with a live schema-constrained smoke
response from qwen3:1.7b through the native adapter. Run
`python scripts/check_ollama.py` to repeat it. Automated tests remain offline.

The fixture creates a greeting function plus independently specified tests, runs
real tools and builds a wheel. Scripted human decisions are labeled simulation.
For the interview, start without `--scripted`, inspect the gate payload, submit
clarification, approve the new requirement version and inspect architecture before
approval. Show artifact versions, audit lineage and the generated wheel. End with
the readiness gate and explain that no production deployment occurs.

Negative test fixtures deliberately introduce failures **only in the test suite**
to verify controls. Real generated product code is never sabotaged to manufacture
a recovery story. No coverage percentage or real-model quality benchmark is claimed.
