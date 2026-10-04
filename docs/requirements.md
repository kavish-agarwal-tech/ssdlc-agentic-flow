# Requirements and delivery scope

Source: `Agentic_SSDLC_Coding_Agent_Prompt.txt`. The platform is implemented before
the URL-shortener workload. The assignment PDF is retained as supplied; the text
prompt is the implementation specification.

| Capability | Implementation / evidence |
|---|---|
| Typed requirements, ambiguities, approval/version history | Pydantic models; requirement analysis and two-step clarification/approval |
| Architecture, technology alternatives and ADRs | Architecture contract; independent bounded review; joint human approval |
| Vertical slices, LLD, dependency graph | Topological plan validation, acceptance and ADR mappings |
| Parallel independent code and test design | LangGraph fan-out and two reviewer subgraphs; join barrier |
| Deterministic tooling | Actual lint, compile, pytest/JUnit and wheel commands |
| Traceability and feature acceptance | Criterion-to-executed-test matching; no skipped/missing tests |
| Failure classification and targeted re-plan | Six classifications, exact root invalidation, bounded retries |
| Human recovery, rollback, risk policy | Persistent safe-stop interrupt; historical pointer restoration |
| Brownfield impact | Bounded source snapshot and structured impact before planning |
| Documentation and release | Structured documentation/report, package build and human readiness approval |
| Audit, metrics, checkpoint resume | SQLite, hash chain, JSON export and metrics |
| Mock and pluggable providers | Explicit fixture and structured chat adapter; no live API required |

Intentional prototype limits: no cloud deployment, IAM, UI, production sandbox,
general RAG/vector infrastructure, multi-service framework or custom scheduler.
The bundled Python profile is the only fully exercised language profile. Static
validation currently runs Ruff and Python bytecode compilation; no dependency
vulnerability scanner or type checker is silently claimed.

Acceptance of the platform is based on its automated tests and synthetic graph
execution. Acceptance of a URL-shortener product is a separate governed workload
and requires real decisions and a configured generative provider.
