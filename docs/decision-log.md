# Implementation decisions

1. Use the repository root as the package root: no existing code needed migration.
2. Keep domain/agent roles explicit, but consolidate small modules to avoid empty
   per-role scaffolding. All agent contracts remain separately named and testable.
3. Build the synthetic platform demonstration before submitting product workloads.
4. Use exact artifact references in human decisions; clarification never doubles
   as approval of a newly generated version.
5. Use separate reviewer contexts and preserve unresolved findings across revisions.
6. Keep feature sequencing topological and sequential in the first prototype;
   parallelize implementation/test design where their independence is meaningful.
7. Require actual JUnit evidence for mapped criteria, not merely a successful command.
8. Prefer safe-stop over unsupported mock generation or invented approvals.
9. Normalize JUnit file paths across Windows and POSIX, discovered in real execution.
10. Explicitly rethrow LangGraph control-flow exceptions before ordinary error handling.
11. Supplementary prompt: integrate native Ollama without changing graph semantics.
    Keep optional hosted clients behind a trusted factory and record fallback switches.
12. Require an explicitly configured model tag; the architecture hard-codes no model.
    Choose qwen3:1.7b only in this machine's ignored development configuration.
13. Prevent real-model fallback to synthetic fixtures. A successful mock response is
    not a substitute for an unavailable real-model engineering proposal.
14. Isolate Ruff from parent-directory configuration after a natural local demo
    failure. Preserve the failure/recovery events in the exported initial run.
