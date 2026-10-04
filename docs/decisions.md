# Decisions and tradeoffs

| Area | Decision and reason | Limit or alternative |
|---|---|---|
| Orchestration | Keep LangGraph for nonlinear routing, parallel branch barriers, loops and durable interrupts. | A linear prompt chain cannot represent recovery well; a custom scheduler duplicates framework work. |
| Governance | Explicit deterministic transitions and three normal human gates. | No LLM supervisor choosing policy; exceptional pauses remain for ambiguity, risk and exhausted budgets. |
| Providers | Primary deterministic engineering workers generate the real URL-shortener demo; DeepSeek is optional behind the same protocol. | Templates support bounded scenarios, not arbitrary requirements; no hidden model call or synthetic fallback. |
| Planning | Merge plan and per-slice implementation design in one typed response. | Reduces calls and repeated context; large plans still need bounded responses and coverage checks. |
| Review | Independent architecture review; one shared code/test quality review after join. | Model review can miss defects, so actual tool evidence remains mandatory. |
| Documents | Release Readiness owns engineering documentation and evidence report. | No additional documentation agent or duplicated report lifecycle. |
| Persistence | Filesystem artifact bodies plus SQLite state/indexes/audit/checkpoints. | Local single-writer prototype; not distributed storage or externally authenticated approvals. |
| Execution | Fixed actual Python commands; known deterministic demos enable local execution, generic/live runs require an explicit flag. | Path/environment guards are not process isolation. No production sandbox, deployment or multi-language guarantee. |
| Retry | Two response attempts, two review cycles, three failure replans by default. | Human renewal is explicit; no automatic unlimited loops. |

The refactor keeps requirements provenance, exact approval versions, artifact invalidation, audit history, existing metrics, real execution and brownfield source evidence. It removes extra orchestration and configuration layers rather than introducing a generic agent platform. Historical [ADR-001](adr/001-governed-langgraph.md) and [ADR-002](adr/002-local-evidence-and-execution.md) record the retained foundational decisions.

Remaining prototype limits: approvals identify a local actor without IAM; audit integrity is a local hash chain, not external immutable storage; no coverage percentage, production security assessment or model-quality benchmark is inferred from deterministic results. The offline URL-shortener has its own actual tool evidence. Live workloads still require separate human decisions and generated-source/tool evidence.

[Pending work and enhancements](enhancements.md) prioritizes closing evidence gaps and improving the current CLI before extending the platform.
