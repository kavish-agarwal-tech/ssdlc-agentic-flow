# Decisions and tradeoffs

| Area | Decision and reason | Limit or alternative |
|---|---|---|
| Orchestration | Keep LangGraph for nonlinear routing, parallel branch barriers, loops and durable interrupts. | A linear prompt chain cannot represent recovery well; a custom scheduler duplicates framework work. |
| Governance | Explicit deterministic transitions and three normal human gates. | No LLM supervisor choosing policy; exceptional pauses remain for ambiguity, risk and exhausted budgets. |
| Providers | One real DeepSeek adapter and one labeled mock fixture behind a small protocol. | No local model setup, silent synthetic fallback, arbitrary factory loader or untested provider chain. |
| Planning | Merge plan and per-slice implementation design in one typed response. | Reduces calls and repeated context; large plans still need bounded responses and coverage checks. |
| Review | Independent architecture review; one shared code/test quality review after join. | Model review can miss defects, so actual tool evidence remains mandatory. |
| Documents | Release Readiness owns engineering documentation and evidence report. | No additional documentation agent or duplicated report lifecycle. |
| Persistence | Filesystem artifact bodies plus SQLite state/indexes/audit/checkpoints. | Local single-writer prototype; not distributed storage or externally authenticated approvals. |
| Execution | Fixed actual Python commands on an opt-in trusted host. | Path/environment guards are not process isolation. No production sandbox, deployment or multi-language guarantee. |
| Retry | Two response attempts, two review cycles, three failure replans by default. | Human renewal is explicit; no automatic unlimited loops. |

The refactor keeps requirements provenance, exact approval versions, artifact invalidation, audit history, existing metrics, real execution and brownfield source evidence. It removes extra orchestration and configuration layers rather than introducing a generic agent platform. Historical [ADR-001](adr/001-governed-langgraph.md) and [ADR-002](adr/002-local-evidence-and-execution.md) record the retained foundational decisions.

Remaining prototype limits: approvals identify a local actor without IAM; audit integrity is a local hash chain, not external immutable storage; no coverage percentage, production security assessment, model-quality benchmark or URL-shortener delivery is inferred from the mock greeting. A successful live workload requires real human decisions and its own generated-source/tool evidence.

[Pending work and enhancements](enhancements.md) prioritizes closing evidence gaps and improving the current CLI before extending the platform.
