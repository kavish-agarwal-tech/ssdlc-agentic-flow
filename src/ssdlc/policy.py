"""Deterministic gates: model opinions never become objective evidence."""

from dataclasses import dataclass

from ssdlc.models import Requirement
from ssdlc.state import Workflow, active_artifact


@dataclass(frozen=True)
class Policy:
    max_review_cycles: int = 2
    max_replans: int = 3
    max_provider_attempts: int = 2
    command_timeout: int = 60

    def __post_init__(self):
        if (
            min(
                self.max_review_cycles,
                self.max_replans,
                self.max_provider_attempts,
                self.command_timeout,
            )
            < 1
        ):
            raise ValueError("Budgets must be positive")


def approved(state: Workflow, key: str) -> dict:
    artifact = active_artifact(state, key)
    ref = state["active"][key]
    if artifact["approval_status"] != "APPROVED" or not any(
        a["artifact_ref"] == ref and a["decision"] == "approve"
        for a in state.get("approvals", {}).values()
    ):
        raise ValueError(f"Human approval required for {ref}")
    if key == "requirement":
        req = Requirement.model_validate(artifact["content"])
        unresolved = [
            q.id
            for q in req.open_questions
            if (q.human_confirmation_required or q.classification == "BLOCKING_AMBIGUITY")
            and not req.decisions.get(q.id, "").strip()
        ]
        if unresolved:
            raise ValueError(f"Unresolved human decisions: {unresolved}")
    return artifact


def prohibited_findings(state: Workflow, artifact_id: str | None = None) -> list[dict]:
    return [
        f
        for f in state.get("findings", {}).values()
        if (artifact_id is None or f["artifact_id"] == artifact_id)
        and f["severity"] in {"BLOCKER", "HIGH"}
        and f["status"] not in {"RESOLVED", "ACCEPTED_RISK"}
    ]


def reviewed(state: Workflow, key: str):
    active_artifact(state, key)
    review_key = key
    if key.startswith(("code:", "tests:")):
        review_key = "quality:" + key.split(":", 1)[1]
        quality = active_artifact(state, review_key)
        if state["active"][key] not in quality["dependencies"]:
            raise ValueError(f"Quality review does not cover {key}")
    review = state.get("reviews", {}).get(state["active"][review_key])
    if not review or not review["complete"] or prohibited_findings(state, review_key):
        raise ValueError(f"Review incomplete or prohibited findings for {key}")


def baseline(state: Workflow):
    approved(state, "requirement")
    approved(state, "architecture")
    architecture = active_artifact(state, "architecture")
    for adr in architecture["content"]["adrs"]:
        approved(state, adr["adr_id"])


def release_gate(state: Workflow):
    baseline(state)
    if prohibited_findings(state):
        raise ValueError("Unresolved prohibited findings")
    plan = active_artifact(state, "plan")["content"]
    if set(state["completed_slices"]) != {s["id"] for s in plan["slices"]}:
        raise ValueError("Not all slices accepted")
    for item in plan["slices"]:
        sid = item["id"]
        for kind in ("code", "tests"):
            reviewed(state, f"{kind}:{sid}")
        evidence = active_artifact(state, f"validation:{sid}")
        active_artifact(state, f"acceptance:{sid}")
        for result in evidence["content"]["results"]:
            if result["exit_status"] != 0:
                raise ValueError("Failed deterministic validation")
    # The final cumulative candidate must have executed all earlier acceptance
    # tests too, even if a later slice replaced a test file.
    final_acceptance = active_artifact(state, f"acceptance:{plan['slices'][-1]['id']}")
    final_passed = set(final_acceptance["content"]["passed_tests"])
    for item in plan["slices"]:
        tests = active_artifact(state, f"tests:{item['id']}")["content"]
        claimed = {test for values in tests["criterion_tests"].values() for test in values}
        if not claimed.issubset(final_passed):
            raise ValueError("Final candidate did not pass every slice's acceptance tests")
    active_artifact(state, "release_report")
    build = active_artifact(state, "build")["content"]
    if build["exit_status"] != 0:
        raise ValueError("Build failed")
