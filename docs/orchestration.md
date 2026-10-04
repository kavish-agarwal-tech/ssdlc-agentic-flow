# Orchestration and recovery

The parent graph persists JSON state under a stable `thread_id`. Major human gates
call `interrupt` with the exact artifact and full review context. The local service
validates a decision before passing `Command(resume=...)`. Clarifying requirements
returns to analysis; the revised version requires a separate approval.

Architecture author/reviewer use a conditional edge loop. Coding and test design
run in parallel, each through a bounded author/reviewer LangGraph subgraph. The
parent joins both branches before tool execution. Review subgraphs return only
changed map entries to prevent concurrent scalar writes. Successful unaffected
branches can be reused after targeted remediation.

Failure classification proposes one of six categories. Deterministic routing maps:

| Category | Route | Invalidated root |
|---|---|---|
| IMPLEMENTATION_DEFECT | code/test fork, reusing valid tests | current code |
| TEST_DEFECT | code/test fork, reusing valid code | current tests |
| LLD_DEFECT | LLD | current LLD |
| ARCHITECTURE_DEFECT | architecture review/approval flow | architecture |
| REQUIREMENT_DEFECT | requirements and human approval | requirement |
| ENVIRONMENT_OR_TOOLING | human safe stop | no invented code change |

All transitive descendants of a changed root become INVALIDATED (plans and
architecture use REVALIDATE). Both statuses prohibit use. Superseded versions
remain historical. Unrelated branches keep their exact versions. No blanket reset
is used for artifact invalidation, although human-authorized budget renewal resets
the bounded counters for the recovery episode.

Safe-stop retains the reason, evidence and unresolved findings, and presents retry,
risk acceptance, rollback or abort options. Rollback targets an earlier approved
requirement/architecture whose dependencies are still current. It restores artifact
authority, invalidates descendants, and re-enters architecture governance. It never
deletes audit history or reverts a deployed database.

Persistent checkpoints survive a normal CLI exit or process restart at an interrupt.
Local leases prevent concurrent writes. After an abrupt crash, inspect the process
and database before manually clearing the corresponding `leases` record; automatic
lease stealing is deliberately absent. Audit and checkpoint commits are not atomic
together. Cache keys bind provider results to full role context to reduce replay.
