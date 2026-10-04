# Verification record

Local environment: Windows 11 Home, Python 3.14.6, LangGraph 1.2.11,
Ollama 0.35.1. Local model: qwen3:1.7b, model ID 8f68893c685c, approximately 1.4 GB.

* Full automated suite: **32 passed**, entirely mock-driven/offline with real local
  lint, static compilation, pytest and wheel-build subprocesses in workflow tests.
* Ruff lint and formatting checks: passed.
* Platform wheel: built successfully with `python -m build --wheel --no-isolation`.
* Initial synthetic workflow: READY_FOR_DEPLOYMENT. Actual fixture tests and wheel
  passed, with explicitly labeled simulated human decisions. A natural inherited
  Ruff-config failure and its recovery remain in the exported audit.
* Native local Ollama smoke: validated the `local-model-ready` structured response
  through `OllamaProvider` in approximately five seconds.
* Full URL-shortener local-model analysis: SAFE_STOP after bounded provider failures.
  No product implementation, product approval or production deployment claimed.

The workflow tests also cover persisted resume, code/test concurrency with identical
design inputs, independent test context, review limits, HIGH risk approval, BLOCKER
rejection, retry exhaustion, targeted invalidation, brownfield impact, rollback,
stale human decisions and candidate tampering before release approval.

GitHub Actions configuration is included but has not been run remotely. Hosted
providers and non-Python tool adapters have not been integration-tested.
