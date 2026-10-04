"""LangGraph owns execution, fan-out/barriers, looping and interrupt checkpoints."""

from langgraph.graph import END, START, StateGraph

from ssdlc.nodes import Nodes
from ssdlc.state import Workflow


def branch(nodes: Nodes, kind: str):
    graph = StateGraph(Workflow)
    graph.add_node(
        "generate", nodes.guarded("branch_generate", lambda s: nodes.branch_generate(s, kind))
    )
    graph.add_node("review", nodes.guarded("branch_review", lambda s: nodes.branch_review(s, kind)))
    graph.add_edge(START, "generate")
    graph.add_conditional_edges(
        "generate", lambda s: s["route"], {"review": "review", "done": END, "safe_stop": END}
    )
    graph.add_conditional_edges(
        "review", lambda s: s["route"], {"generate": "generate", "done": END, "safe_stop": END}
    )
    compiled = graph.compile()

    def execute(state):
        result = compiled.invoke(state, {"recursion_limit": 30})
        keys = {"artifacts", "active", "findings", "reviews", "counters", "branch_errors"}
        update = {
            key: {k: v for k, v in result.get(key, {}).items() if state.get(key, {}).get(k) != v}
            for key in keys
        }
        if result.get("route") == "safe_stop":
            update["branch_errors"][kind] = result["safe_stop_reason"]
        return update

    return execute


def build_graph(nodes: Nodes, checkpointer):
    graph = StateGraph(Workflow)
    names = [
        "requirement",
        "requirement_approval",
        "architecture",
        "architecture_review",
        "architecture_approval",
        "brownfield",
        "planning",
        "plan_approval",
        "lld",
        "synchronize",
        "validate",
        "acceptance",
        "failure_analysis",
        "documentation",
        "release_readiness",
        "build",
        "release_gate",
        "release_approval",
        "safe_stop",
    ]
    routes = {name: name for name in names} | {"fork": "fork", "end": END}
    for name in names:
        graph.add_node(name, nodes.guarded(name, getattr(nodes, name)))
        graph.add_conditional_edges(name, lambda s: s["route"], routes)
    graph.add_node("fork", lambda s: {"branch_errors": {"code": "", "tests": ""}})
    graph.add_node("coding_branch", branch(nodes, "code"))
    graph.add_node("test_design_branch", branch(nodes, "tests"))
    graph.add_edge("fork", "coding_branch")
    graph.add_edge("fork", "test_design_branch")
    graph.add_edge(["coding_branch", "test_design_branch"], "synchronize")
    graph.add_edge(START, "requirement")
    return graph.compile(checkpointer=checkpointer)
