# Why LangGraph

The lifecycle requires a graph: conditional routes, backward failure routes,
review loops, parallel branches, synchronization, durable state, human interrupts
and safe resume. LangGraph supplies these orchestration primitives. A bespoke
workflow scheduler would add implementation and explanation cost without improving
the SSDLC domain model.

LangGraph owns graph execution, state propagation, conditional edges, checkpoint
integration, interrupts, resume and graph lifecycle. Our application owns requirements,
artifact versions, exact approval binding, reviewer findings, severity/risk policy,
retry budgets, invalidation, audit semantics, metrics, deterministic tool policy,
release gates, rollback and safe stop. Bounded loops are expressed with conditional
edges, while their budgets are application policy.

We considered a linear chain (cannot model the required non-linear stateful lifecycle)
and a custom engine (unnecessary scheduler and persistence maintenance). LangGraph
adds framework/version coupling and replay semantics that need testing, particularly
side effects before interrupts and exception handling. The domain/provider/tool
contracts remain framework-independent.

References checked during implementation:

* [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
* [Interrupts and node replay](https://docs.langchain.com/oss/python/langgraph/interrupts)
* [Persistence and threads](https://docs.langchain.com/oss/python/langgraph/persistence)

Tested framework version: 1.2.11. The wrapper explicitly rethrows `GraphBubbleUp`;
interrupts must never be converted into stage failures.
