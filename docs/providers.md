# Provider integration

Native Ollama and environment selection are implemented. See
[provider architecture](llm-provider-architecture.md) and [configuration](configuration.md).
The central Engine owns bounded retry, schema repair and explicit audited fallback.
Agents never access provider-specific clients directly.

Implement the protocol in `ssdlc.providers.Provider`, or inject a model into
`StructuredChatProvider(model, name, reviewers={...})`. Each call receives a
role-specific instruction, bounded explicit context and Pydantic output schema.
Providers must be thread-safe because code and test design run concurrently.
Configure finite network timeouts at the client. The orchestrator bounds attempts,
but cannot interrupt a provider that blocks indefinitely inside arbitrary Python.

A trusted factory module can return an adapter. The CLI loads it with
`--provider package.module:create`. Use the same stable provider name when resuming
a run. The provider name should include the model/configuration version. Reviewers
may use different models via the `reviewers` map. Separate roles do not guarantee
independent reasoning if they share a model; critical review remains human-owned.

The offline mock returns fixture proposals only. It intentionally refuses arbitrary
product architecture/implementation. Its URL and expiration analysis are explicitly
fixture questions, not evidence of an LLM independently discovering ambiguities.

Output schemas are in `models.py`; role instructions are in `agents.py`. Do not
return approval status, tool claims, command strings or routing directives. Unknown
Pydantic fields are rejected. Model failures get bounded retries and then safe stop.

The default trusted tool profile is Python. Alternate operator-owned profiles must
provide `lint`, `static`, `test`, `build` argument arrays. Commands run without a shell
inside a candidate directory. The test command must generate `.results.xml` JUnit
with testcase `file` and `name` attributes. The test agent maps criteria to
`relative/file::name`; every mapped test must execute and pass. A Go/Java adapter
must normalize its reports to this contract. Commands and report adapters are
trusted code and must never be accepted directly from an LLM response.
