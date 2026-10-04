# ADR-002: Local evidence and opt-in execution

Status: accepted for the prototype.

Context: a public interview repository needs reproducible execution without paid
model credentials, cloud infrastructure or implied production safety guarantees.

Decision: make labeled deterministic URL-shortener workers the primary offline path, with a DeepSeek adapter behind a provider
interface, filesystem artifact bodies, SQLite state/audit and real local tools.
Keep immutable content versions with separate validity and active pointers.
Known deterministic demo commands enable their real local tools; generic/live runs require opt-in host execution. Keep
deployment outside the tool surface.

Alternatives: cloud execution service (operational overhead), fully mocked validation
(does not prove deterministic outcomes), home-grown sandbox (unsafe overclaim).

Tradeoffs: SQLite suits local single-writer use. Host execution is useful for the
known synthetic fixture but cannot contain malicious generated code. Production
needs isolated workers, authenticated approvals and stronger audit storage.
