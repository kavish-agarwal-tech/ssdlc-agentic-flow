# Orchestration

```mermaid
flowchart TD
  R[Requirement analysis] --> H1[Human clarification and approval]
  H1 --> A[Architecture author]
  A --> AR[Independent architecture review: max 2 cycles]
  AR -->|revision within budget| A
  AR --> H2[Human architecture and ADR approval]
  H2 --> B[Brownfield impact when applicable]
  B --> P[Combined planning and design]
  P --> C[Coding]
  P --> T[Independent test design]
  C --> J[Join]
  T --> J
  J --> Q[Shared Quality Review]
  Q -->|bounded revision| C
  Q -->|bounded revision| T
  Q --> V[Real lint, static checks, pytest]
  V -->|failure| F[Classify and invalidate affected artifacts]
  F -->|implementation or test| J2[Regenerate affected branch; reuse valid sibling]
  J2 --> J
  F -->|design| P
  F -->|architecture| A
  F -->|requirement| R
  V -->|pass| S[Slice acceptance]
  S -->|next slice| C
  S -->|next slice| T
  S -->|all accepted| RR[Release Readiness and documentation]
  RR --> Build[Real package build]
  Build --> Gate[Deterministic release gate]
  Gate --> H3[Final human approval]
  H3 --> Ready[READY_FOR_DEPLOYMENT]
```

Every policy failure can route to a persistent safe stop. Missing product decisions and unapproved scope changes pause rather than invent decisions. Architecture has two autonomous author/reviewer cycles; shared quality review is likewise bounded. BLOCKER findings prevent progress. HIGH findings require resolution or explicit human risk acceptance. Findings retain exact IDs across versions; omission is not resolution. Resolution needs a changed artifact, author response, actual change and reviewer verification.

There is no normal plan-approval gate, separate design call, per-branch reviewer graph, or standalone documentation call. Default failure-analysis replans are bounded at three. IMPLEMENTATION_DEFECT and TEST_DEFECT invalidate their corresponding branch and dependent review/tool evidence. DESIGN_DEFECT returns to combined planning/design. ARCHITECTURE_DEFECT and REQUIREMENT_DEFECT invalidate approvals downstream and re-enter the corresponding human governance. ENVIRONMENT_OR_TOOLING stops for configuration correction. Reviewer diagnosis does not itself count as a passing tool result.

Test generation receives authoritative requirement, architecture/ADRs and slice design. It does not receive generated implementation files or code-author output. Test files are owned by the test branch; production files by the coding branch. Both must finish before quality review and validation. Targeted tool-failure recovery preserves a valid reviewed sibling, then reviews the new pair again.

Brownfield starts with a bounded snapshot of the supplied source. Impact analysis references actual files and feeds the combined plan. The workflow writes into its run workspace and leaves the supplied repository unchanged. Rollback restores an approved historical pointer, retains audit history and invalidates descendants. Human retry, revise, risk disposition and abort are explicit checkpointed actions.
