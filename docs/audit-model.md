# Audit and observability

Audit events include event ID, workflow ID, timestamp, actor type and identity,
action, stage, artifact references, before/after version, rationale, related review,
ADR and approval references, and correlation ID. Material transitions emit events;
provider failures preserve a sanitized error rather than hidden retries.

SQLite `events` is append-only through the application API. Each row hashes the
previous workflow hash plus exact serialized payload. `ssdlc audit RUN` verifies
the chain. This detects accidental changes, not a privileged attacker rewriting
the entire database. Production requires signed append-only external storage.

Artifact content and dependency digests cannot change within a version. Validity
and approval metadata may change under application policy. LangGraph checkpoints
retain authoritative structured state; artifact/audit tables make review and export
convenient. Operation cache rows record validated provider results by role/context.

`ssdlc metrics RUN` exposes JSON counters: runs/success/failure, agent failures,
retries, rollbacks, replans, safe stops, review cycles and findings by severity,
test/build pass/fail counts. It also reports stage and agent durations, human wait
and end-to-end elapsed seconds. Test counters count **commands**, not test cases.
Coverage percentage is not inferred. Paused runs report elapsed time so far.

`ssdlc export RUN --output file.json` includes the complete state, pending gates,
events, chain verification and metrics. Exports can contain proprietary requirements
or source: review them before publishing. The bundled demonstration is synthetic.
