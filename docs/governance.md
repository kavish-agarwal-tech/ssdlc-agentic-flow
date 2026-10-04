# Governance

Autonomous: structured analysis, proposals, independent critique, planning,
implementation and test proposals, bounded remediation and documentation.

Human-controlled: requirement approval, scope revisions, architecture and technology
baseline, HIGH risk acceptance, budget renewal, artifact rollback and final readiness.
No deploy operation exists. Passing readiness is not authorization for deployment.

Never delegated to models: test/build outcomes, approval state, execution commands,
gate pass/fail, retry counts, artifact validity and state transitions.

Architecture requires an approved requirement with every required decision answered.
Planning requires approved architecture and ADRs. Code/test generation requires a
structurally accepted LLD with matching criteria and ADR references. Both branches
must finish independent review before deterministic validation. Every claimed
acceptance test must appear in the JUnit report and pass; skips do not count.
Build and release gates also require current, unmodified evidence.

Review budgets are three cycles per artifact remediation episode. Failure re-plans
have a separate global budget of three. Provider schema/network failures get two
attempts, then safe-stop rather than an invented fallback answer. Tool/environment
failures are escalated. Human retry explicitly renews bounded budgets and is audited.
BLOCKER cannot be risk-accepted. HIGH can be accepted at safe-stop with named human
identity, finding IDs and rationale. A later reviewer may reopen a finding.

The CLI trusts the local operator; it does not authenticate their asserted name.
Provider plug-ins and tool profiles are trusted application configuration. Generated
file paths reject traversal, protected directories, symlinks and Windows junctions.
Commands use argument arrays, no shell interpolation, a configured working directory,
timeouts and a minimal child environment. Secret screening/redaction is best effort,
not a comprehensive DLP system. Do not submit secrets.

Host execution remains opt-in because generated Python, build backends and tests
can execute arbitrary code regardless of command allowlisting. Use a disposable OS
sandbox/container/VM without sensitive mounts or egress for untrusted providers.
The prototype does not claim to confine arbitrary generated process behavior.
