# Deferred work and limitations

The submission priority is the three reproducible offline scenarios defined by [SupplementaryPrompt.txt](../SupplementaryPrompt.txt). Deterministic workers are the primary path; DeepSeek is an optional extension. Broader provider repair and production-like URL requirements are deferred.

## Current limits

| Area | Limit |
|---|---|
| Agent behavior | Bounded templates implement the documented URL-shortener scenarios, not arbitrary specifications or repositories. |
| Generated app | Local HTTPServer, one serving process, synchronous SQLite counts; no baseline TTL, auth, deletion, alias, rate limit, DNS policy or distributed worker. |
| Expiration | Four bounded choices; retain or delete on access. No scheduler, reactivation or production retention framework. |
| Brownfield | Inspects the previous deterministic app and enables daily counts; does not infer historical daily buckets or general code migrations. |
| Execution | Runs trusted demo source/build hooks on the host; path/environment guards are not process isolation. |
| Governance | Local actor names, local audit hash chain, no authenticated multi-user approvals. |
| Optional LLM | Kept behind Provider; successful deterministic runs do not prove live-model reliability. |

## Possible enhancements after submission

| Priority | Enhancement | Small next step |
|---|---|---|
| P2 | Friendlier artifact review | Summarize changes and assumptions at gates while preserving complete documents and exact version references. |
| P2 | Interrupted-process recovery | Add explicit stale-lease recovery after checking that the owning process stopped. |
| P2 | Execution isolation | Add a tested isolation boundary only if untrusted generated code must be run. |
| P2 | Wider installed-wheel scenario coverage | Greenfield has been checked from the installed platform wheel; extend that check to the other CLI paths without new services or model calls. |
| P3 | Additional bounded scenario | Add one requested product change with independent tests; avoid generic repository automation. |
| P3 | Production URL-shortener controls | Define a separate requirement for authentication, abuse protection, production HTTP hosting and capacity before implementing them. |

No cloud deployment, UI, policy DSL, distributed locking, generalized provider fallback, multi-language runtime or enterprise audit is planned for the current assignment. Live DeepSeek completion and the historical large requirement remain optional future exercises, not unfinished core submission requirements.
