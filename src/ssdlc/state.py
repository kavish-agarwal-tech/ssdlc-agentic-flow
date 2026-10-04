"""Only disjoint branch keys may be merged; node outputs are checkpointed JSON."""

from typing import Annotated, Any, TypedDict


def merge(left: dict, right: dict) -> dict:
    return {**left, **right}


class Workflow(TypedDict, total=False):
    workflow_run_id: str
    project_id: str
    scenario_type: str
    workflow_status: str
    original_text: str
    workspace: str
    provider_id: str
    artifacts: Annotated[dict[str, dict], merge]
    active: Annotated[dict[str, str], merge]
    findings: Annotated[dict[str, dict], merge]
    approvals: Annotated[dict[str, dict], merge]
    tool_results: Annotated[dict[str, dict], merge]
    reviews: Annotated[dict[str, dict], merge]
    counters: Annotated[dict[str, int], merge]
    branch_errors: Annotated[dict[str, str], merge]
    current_slice: str
    completed_slices: list[str]
    answers: dict[str, str]
    feedback: dict[str, Any]
    route: str
    safe_stop_reason: str
    recovery_node: str
    created_at: str
    updated_at: str


def active_artifact(state: Workflow, key: str) -> dict:
    ref = state.get("active", {}).get(key)
    if not ref or ref not in state.get("artifacts", {}):
        raise ValueError(f"Missing authoritative artifact: {key}")
    value = state["artifacts"][ref]
    if value["validity"] != "VALID":
        raise ValueError(f"Stale authoritative artifact: {ref}")
    return value
