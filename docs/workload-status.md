# Workload status

The synthetic greeting workflow was executed through the real graph and reached
READY_FOR_DEPLOYMENT. Its labeled simulated human decisions, initial tooling
failure, human recovery, actual test outputs and actual wheel build are recorded
in `examples/minimal/execution.json`. No product approval is inferred from this run.

The requested URL-shortener requirement is staged in
`examples/url-shortener/requirement.txt` and submitted to the configured local
model as run `url-shortener-local`. Inspect the live checkpoint with:

```powershell
python -m ssdlc inspect url-shortener-local
```

Observed outcome: SAFE_STOP after two unsuccessful provider attempts on the local
qwen3:1.7b model with a 180-second request timeout. No requirement artifact was
accepted, and no product code was generated. The smaller native API/schema smoke
test passed in approximately five seconds. This establishes integration, not
sufficient model performance for the full product workload.

The run remains resumable after addressing model resources/timeouts and explicitly
renewing its budget. A human retry decision file must identify an actor, action
`retry` and rationale. Increasing only `LLM_TIMEOUT` preserves provider identity;
switching model or token budgets requires a new run.

This product must receive actual requirement clarification and approval before
architecture, then actual architecture/technology approval before coding. The
platform does not manually implement or silently approve the product.

Brownfield analytics and ambiguous expiration follow-up requirements are staged
alongside it. Their real product demonstrations depend on an approved, implemented
URL-shortener baseline. Brownfield and ambiguity platform mechanics are exercised
with deterministic fixtures in the test suite; this is not a claim that the three
URL-shortener product scenarios have already completed.
