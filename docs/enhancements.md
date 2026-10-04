# Pending work and possible enhancements

This is a planning backlog, not an implementation claim or a commitment to build a larger platform. Priorities favor making the current Python CLI easier to use and proving it on a real workload.

## Pending validation

| Priority | Work | Current evidence and completion condition |
|---|---|---|
| P1 | Complete the real DeepSeek greenfield URL shortener | Analysis reached a genuine clarification gate. Completion needs confirmed requirements, architecture/ADR approval, workflow-generated code/tests, real passing tools/build and final approval. |
| P1 | Complete expiration behavior validation | Confirmed policy is saved in requirement v2; approval and implementation are pending. Verify permanent-by-default links, HTTP 410, retention, final expiration and scheduled cleanup against generated tests. |
| P1 | Run a real analytics brownfield extension | Mock/source-snapshot integration tests exist. A live run needs generated URL-shortener source, impact/compatibility evidence and final approval. |

The [live evidence summary](../examples/url-shortener/refactor-analysis.json) is a dated record, not live state. Use `inspect` with the correct local `--home` for present status.

## Proposed improvements

| Priority | Enhancement | Current limitation | Small next step |
|---|---|---|---|
| P1 | Clearer artifact review | Large JSON payloads are cumbersome; requirements/plans lack Markdown companions. | Add readable summaries with exact IDs/version links, retaining authoritative JSON and explicit decisions. |
| P1 | Stronger alignment with human intent | Schemas cannot establish that every proposed requirement or performance target was requested. | Highlight new assumptions, acceptance criteria and changed decisions before approval. |
| P1 | Early stack/dependency feasibility checks | Architecture can propose packages/languages the fixed executor cannot run; candidate tools install nothing. | Check approved stack/packages against the CLI environment before generation and stop with actionable feedback. |
| P2 | Better failure/retry guidance | Model diagnosis can be wrong; renewing a budget may repeat failures. | Summarize failed commands and affected versions; add regression examples for misclassification. |
| P2 | More quality evidence | Static checks are Ruff/compilation; coverage, type checking and dependency-security scans are not implemented. | Add one explicitly configured check at a time and report measured results. |
| P2 | Realistic multi-slice validation | The real-tool fixture is a small greeting; controls do not prove broad model effectiveness. | Exercise cumulative files/tests, migrations and recovery with a compact workload; record live-model evidence separately. |
| P2 | Checkpoint/interruption recovery | Removed-node checkpoints need a fresh run; a killed process may leave a lease. | Add compatibility checks and an explicit stale-lease recovery path after confirming the owning process stopped. |
| P2 | Usage/cost visibility | Metrics report counts/durations, not token usage or spend. | Record provider-reported usage; distinguish measured usage from cost estimates. |
| P2 | Isolated generated-code execution | Code/build hooks run on the host; guards are not process isolation. | If needed beyond a trusted demo, add one tested isolation boundary with time/resource/network controls. |
| P3 | Authenticated approvals/external audit | Actor names are local assertions; audit storage is local. | Add identity and external audit retention when multi-user or production governance is required. |

## Outside the current scope

A UI, distributed workers, multi-provider routing, automatic deployment and more language toolchains are possible future directions. Each needs a concrete requirement and independent validation. Restoring generic factories or orchestration layers would work against the current simplification.
