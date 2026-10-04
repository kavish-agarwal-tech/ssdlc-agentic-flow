# Orchestration

The diagram groups related nodes to show the normal lifecycle. Blue marks human gates, green marks engineering proposals and yellow marks tool execution/evidence gates. Recovery is listed separately to keep the main flow readable.

```mermaid
flowchart TD
  R["Requirement analysis"] --> H1["Human: review requirement<br/>clarify only product blockers"]
  H1 --> A["Architecture author + independent review"]
  A --> H2["Human: approve architecture and ADRs"]
  H2 --> B["Brownfield impact<br/>brownfield runs only"]
  B --> P["Planning, slice design<br/>shared API contract checked"]
  P --> Fork["Current slice: parallel generation"]
  Fork --> C["Coding"]
  Fork --> T["Independent test design"]
  C --> Q["Join, then shared Quality Review"]
  T --> Q
  Q --> V["Actual lint, compilation and pytest"]
  V --> S["Deterministic slice acceptance"]
  S -->|next slice| Fork
  S -->|all slices accepted| Report["Release Readiness and documentation"]
  Report --> Build["Actual wheel build"]
  Build --> Gate["Deterministic release gate"]
  Gate --> H3["Human: final release approval"]
  H3 --> Ready["READY_FOR_DEPLOYMENT"]
  classDef human fill:#dbeafe,stroke:#2563eb,color:#111827
  classDef proposal fill:#dcfce7,stroke:#16a34a,color:#111827
  classDef evidence fill:#fef3c7,stroke:#d97706,color:#111827
  class H1,H2,H3 human
  class R,A,B,P,C,T,Q,Report proposal
  class V,S,Build,Gate,Ready evidence
```

Greenfield and ambiguous runs skip brownfield impact. Architecture revisions occur inside the grouped author/reviewer step. A rejected shared review sends both branches back for bounded revision. Tools run only after both branches finish and shared review passes. There is no separate design call, plan-approval gate, per-branch reviewer graph or documentation agent.

## Decisions and findings

Blocking questions must be clarified; clarification creates a new requirement version requiring separate approval. Architecture approval covers its ADRs. Approvals record actor, rationale and exact current reference; stale references are rejected. Final approval records readiness only.

Explicit input settles product intent without another confirmation questionnaire. Design choices and consistent defaults are recorded as assumptions for the normal requirement review or deferred to architecture. Non-blocking questions do not require individual answers. Genuine unresolved product decisions or contradictions still block approval; the agent must not strengthen guarantees or change scope to manufacture a blocker.

At a requirement gate, choose `revise` to request a better draft in the rationale without answering the old questions. This also works for previously saved requirement interrupts. The agent reanalyzes the same input and preserves prior explicit answers, then stops for review of the new unapproved version. Choose `clarify` when supplying answers to genuine blockers; `approve` remains a separate decision.

BLOCKER and HIGH findings prevent normal progress. A human can explicitly accept eligible unresolved non-BLOCKER findings; BLOCKER risk cannot be accepted. Omission of an earlier finding does not resolve it. Resolution needs the same finding ID, a newer artifact, actual change, author response and reviewer verification. Interactive views hide settled findings from risk-acceptance choices while preserving history.

## Default bounds

| Limit | Default | Configuration |
|---|---|---|
| Schema/semantic response attempts | 2 per call | `Policy.max_provider_attempts` |
| Architecture review cycles | 2 | `Policy.max_review_cycles` |
| Shared quality review cycles | 2 per slice | `Policy.max_review_cycles` |
| Failure-analysis replans | 3 per run before explicit renewal | `Policy.max_replans` |
| Local command timeout | 60 seconds per command | `Policy.command_timeout` |
| DeepSeek HTTP timeout | 180 seconds per request | `LLM_TIMEOUT` |
| DeepSeek response output cap | 32768 tokens | `LLM_MAX_OUTPUT_TOKENS` |

Policy limits are constructor settings in the Python API; the CLI does not expose all of them. Human retry explicitly renews counters at a safe stop; it does not fix an underlying provider, artifact or environment problem.

## Failure and recovery

Actual validation/build failure triggers model-assisted classification. The orchestrator chooses a route and invalidates affected artifacts and descendants. Model diagnosis never counts as a passing tool result.

| Classification / event | Recovery |
|---|---|
| `IMPLEMENTATION_DEFECT` | Regenerate current code; reuse a valid reviewed test sibling, then review the changed pair. |
| `TEST_DEFECT` | Regenerate current tests; reuse valid reviewed code, then review the changed pair. |
| `DESIGN_DEFECT` | Invalidate Plan and descendants; return to combined planning/design. |
| `ARCHITECTURE_DEFECT` | Invalidate architecture and descendants; repeat author/review and human architecture/ADR approval. |
| `REQUIREMENT_DEFECT` | Invalidate requirement and descendants; reanalyze and obtain new approval. |
| `ENVIRONMENT_OR_TOOLING` | Safe stop; correct configuration/dependencies before retrying validation. |
| Schema/policy failure or exhausted budget | Persistent safe stop with reason and recovery stage. |
| Unapproved scope proposal or branch deviation | Stop rather than implement it; revise supported feedback or return to governance. |
| Candidate changed during final human review | Safe stop; stale evidence cannot authorize readiness. |

Safe-stop choices depend on evidence: retry, supported revision, rollback, eligible risk acceptance or abort. Rollback restores an approved historical pointer, retains audit history and invalidates descendants. It does not change the supplied brownfield source. Legacy safe stops naming former planning/design stages return to combined planning/design; checkpoints directly inside removed graph nodes require a new run.

At a quality-review safe stop with open HIGH/BLOCKER findings, `retry` renews the budget and invalidates the current code/test pair so the branches revise it before review. No finding ID is needed for retry. Review resolutions are validated before caching, including on replay: missing verification, unchanged versions, unknown targets and assessments beginning with “not resolved” must be corrected within the response-attempt budget. New finding IDs are qualified once; exact historical IDs remain usable.

At a supported generation/planning stop, `revise` accepts an optional `revision_target`: `requirement` returns to requirement analysis and separate approval; `planning_design` returns to the common per-slice contract; omitting it corrects generation (or the current planning proposal). Interactive mode asks for the target after the rationale. Old saved interrupts also support these targets when branch errors identify a generation failure. Replacing an upstream artifact invalidates its descendants and preserves history. Product decisions supplied in the rationale are input to analysis, not approval of the resulting document.

Code/test deviations are validated before cache publication and on cache replay. The provider gets bounded corrective feedback for implementation shortcuts while genuine upstream conflicts remain a safe stop. The shared design specifies exact public interfaces and injection seams for both independent branches; tests must not guess APIs, use unintended live DNS, or skip required persistence evidence.

Generation failures do not offer `accept_risk`: accepting earlier review findings cannot clear a failed bundle. Runtime also rejects that action for older saved generation interrupts. Required evidence and BLOCKER findings still need actual fixes and verification.

Planning now includes `api_contract` for each slice: exact Python source paths and public declaration stubs, including constructor/method signatures, injected collaborators, data fields and error types. Missing contracts, unspecified concrete constructors and function implementations in stubs are rejected with bounded planning feedback before generation. Both branches receive the same stubs; these are design declarations, not generated production code shared with the test author.

Before quality review, static AST checks compare production names, callable parameter shapes and declared data fields against these stubs, and check direct test imports from the declared application modules. They do not execute generated code or prove runtime behavior, typing, inherited APIs or error semantics. Required acceptance tests still provide that evidence. A persistent `ContractError` returns to combined planning automatically within `Policy.max_replans`; an older plan without stubs follows the same recovery when resumed. Budget exhaustion still pauses for human review. No additional graph node or human gate is introduced.

## Brownfield scope

The source snapshot allows at most 100 selected files and 150,000 bytes. It includes `.py`, `.go`, `.java`, `.md`, `.toml`, `.json` and `.yaml`, excluding hidden directories and common build/dependency outputs. These extensions do not imply non-Python execution support. Over-budget snapshots are rejected, not silently truncated; provide a focused workspace.

Impact analysis runs after architecture approval and feeds combined planning/design. Candidates include the snapshot plus generated changes; the original source remains unchanged. A real analytics extension needs real previously generated URL-shortener source, not the mock greeting.
