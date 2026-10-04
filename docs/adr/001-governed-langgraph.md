# ADR-001: LangGraph with application-owned governance

Status: accepted for the platform implementation.

Context: non-linear engineering lifecycle with approvals, parallel work, review loops
and durable resume. Alternatives: linear prompt chains; custom scheduler; LangGraph.

Decision: use LangGraph for graph lifecycle and SQLite checkpoint integration.
Keep domain artifacts, approval rules, retry policy and deterministic evidence
outside framework abstractions. Avoid an LLM supervisor deciding transitions.

Consequences: standard graph primitives reduce custom infrastructure. Explicit JSON
contracts remain portable. Framework replay and parallel state merging require
integration tests; dependency versions are pinned/tested.
