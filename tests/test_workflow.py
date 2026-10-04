import io
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from threading import Barrier

import pytest

from ssdlc.agents import CONTRACTS
from ssdlc.cli import (
    LLMProgressHandler,
    available_actions,
    display_gate,
    interactive_session,
    prompt_decision,
)
from ssdlc.mock import MINIMAL_REQUIREMENT, MockProvider
from ssdlc.nodes import junit_test_id
from ssdlc.persistence import digest
from ssdlc.policy import Policy
from ssdlc.runtime import Runtime


def decide(runtime, run, result, action="approve", **kwargs):
    gate = result["interrupts"][0]
    return runtime.resume(
        run,
        {
            "actor": "test-human",
            "action": action,
            "rationale": "Explicit test decision",
            "artifact_ref": gate.get("artifact_ref"),
            **kwargs,
        },
    )


def to_architecture(runtime, run="demo", scenario="greenfield", source=None):
    result = runtime.start(MINIMAL_REQUIREMENT, run, scenario, source)
    assert result["interrupts"][0]["gate"] == "requirement"
    result = decide(runtime, run, result, "clarify", answers={"blank": "Reject with ValueError"})
    assert result["state"]["active"]["requirement"] == "requirement@2"
    return decide(runtime, run, result)


def test_persistent_human_gate_and_invalid_approval(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = runtime.start(MINIMAL_REQUIREMENT, "demo")
        assert "architecture" not in result["state"]["active"]
        with pytest.raises(ValueError, match="Clarify"):
            decide(runtime, "demo", result)
    with Runtime(tmp_path) as runtime:
        result = runtime.inspect("demo")
        result = decide(
            runtime, "demo", result, "clarify", answers={"blank": "Reject with ValueError"}
        )
        result = decide(runtime, "demo", result)
        assert result["interrupts"][0]["gate"] == "architecture"
        assert "plan" not in result["state"]["active"]
        assert runtime.repo.verify_audit("demo")


def test_architecture_mapping_is_repaired_with_exact_requirement_ids(tmp_path):
    class IncorrectFirstArchitectureProvider(MockProvider):
        def __init__(self):
            self.architecture_contexts = []

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "architecture":
                self.architecture_contexts.append(context)
                if len(self.architecture_contexts) == 1:
                    result["requirement_mapping"] = {
                        "AC1": "Maps an acceptance criterion, not a requirement."
                    }
            return result

    provider = IncorrectFirstArchitectureProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = to_architecture(runtime, run="architecture-repair")

    assert result["interrupts"][0]["gate"] == "architecture"
    assert len(provider.architecture_contexts) == 2
    repair_feedback = provider.architecture_contexts[1]["validation_feedback"]
    assert "Missing IDs" in repair_feedback
    assert "Unexpected IDs: ['AC1']" in repair_feedback
    requirement = result["state"]["artifacts"][result["state"]["active"]["requirement"]]["content"]
    required_ids = set(requirement["functional_requirements"]) | set(
        requirement["non_functional_requirements"]
    )
    architecture = result["state"]["artifacts"][result["state"]["active"]["architecture"]][
        "content"
    ]
    assert set(architecture["requirement_mapping"]) == required_ids


@pytest.mark.parametrize("invalid_scope", [None, "   "])
def test_incomplete_architecture_is_repaired_before_caching(tmp_path, invalid_scope):
    class IncompleteFirstArchitectureProvider(MockProvider):
        def __init__(self):
            self.architecture_contexts = []

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "architecture":
                self.architecture_contexts.append(context)
                if len(self.architecture_contexts) == 1:
                    if invalid_scope is None:
                        result["sections"].pop("scope")
                    else:
                        result["sections"]["scope"] = invalid_scope
            return result

    provider = IncompleteFirstArchitectureProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = to_architecture(runtime, run="section-repair")
        assert result["interrupts"][0]["gate"] == "architecture"
        assert len(provider.architecture_contexts) == 2
        assert "scope" in provider.architecture_contexts[1]["validation_feedback"]
        schema, instructions = CONTRACTS["architecture"]
        key = digest(
            [
                provider.name,
                "architecture",
                instructions,
                schema.model_json_schema(),
                provider.architecture_contexts[0],
            ]
        )
        assert runtime.repo.cached("section-repair", key)["sections"]["scope"].strip()


@pytest.mark.parametrize("legacy_format", ["embedded", "file"])
def test_legacy_incomplete_architecture_cache_is_repaired(tmp_path, legacy_format):
    class RecordingProvider(MockProvider):
        def __init__(self):
            self.architecture_contexts = []

        def generate(self, role, instructions, context, schema):
            if role == "architecture":
                self.architecture_contexts.append(context)
            return super().generate(role, instructions, context, schema)

    provider = RecordingProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = to_architecture(runtime, run="legacy-architecture")
        schema, instructions = CONTRACTS["architecture"]
        key = digest(
            [
                provider.name,
                "architecture",
                instructions,
                schema.model_json_schema(),
                provider.architecture_contexts[0],
            ]
        )
        bad = runtime.repo.cached("legacy-architecture", key)
        bad["sections"].pop("scope")
        legacy_file = None
        payload = bad
        if legacy_format == "file":
            relative = Path("legacy-architecture", "provider-cache", f"{key}.json")
            legacy_file = runtime.repo.artifact_root / relative
            legacy_file.write_text(json.dumps(bad), encoding="utf-8")
            payload = {"cache_file": relative.as_posix(), "digest": digest(bad)}
        with runtime.repo.connection:
            runtime.repo.connection.execute(
                "UPDATE operations SET payload=? WHERE workflow=? AND key=?",
                (json.dumps(payload), "legacy-architecture", key),
            )
        state = dict(result["state"])
        # Reproduce the pre-architecture context of an old safe stop while
        # retaining the approved requirement and saved artifact history.
        state["active"] = {"requirement": state["active"]["requirement"]}
        _, nodes = runtime.graph("legacy-architecture")
        update = nodes.architecture(state)
        assert update["active"]["architecture"] == "architecture@2"
        assert len(provider.architecture_contexts) == 2
        assert (
            "Missing sections: ['scope']"
            in provider.architecture_contexts[1]["validation_feedback"]
        )
        assert runtime.repo.cached("legacy-architecture", key)["sections"]["scope"].strip()
        assert any(
            event["action"] == "cached_response_rejected"
            for event in runtime.repo.events("legacy-architecture")
        )
        if legacy_file is not None:
            assert json.loads(legacy_file.read_text(encoding="utf-8")) == bad


def test_incomplete_architecture_exhausts_budget_without_caching(tmp_path):
    class AlwaysIncompleteProvider(MockProvider):
        def __init__(self):
            self.architecture_calls = 0

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "architecture":
                self.architecture_calls += 1
                result["sections"].pop("scope")
            return result

    provider = AlwaysIncompleteProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = to_architecture(runtime, run="bounded-architecture")
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert "Missing sections: ['scope']" in result["interrupts"][0]["reason"]
        assert provider.architecture_calls == runtime.policy.max_provider_attempts
        assert "architecture" not in result["state"]["active"]
        completed = [
            event
            for event in runtime.repo.events("bounded-architecture")
            if event["action"] == "agent_completed" and event["stage"] == "architecture"
        ]
        assert not completed


def test_retry_legacy_safe_stop_reviews_existing_draft_plan(tmp_path, monkeypatch):
    with Runtime(tmp_path) as runtime:
        _, nodes = runtime.graph("legacy-plan-review")
        monkeypatch.setattr(
            "ssdlc.nodes.interrupt",
            lambda _: {
                "actor": "local-operator",
                "action": "retry",
                "rationale": "Review the legacy draft plan before continuing.",
            },
        )
        state = {
            "workflow_run_id": "legacy-plan-review",
            "safe_stop_reason": "Previous run stopped downstream of planning.",
            "recovery_node": "lld",
            "findings": {},
            "counters": {},
            "branch_errors": {},
            "active": {"plan": "plan@1"},
            "artifacts": {"plan@1": {"validity": "VALID", "approval_status": "DRAFT"}},
        }

        result = nodes.safe_stop(state)

    assert result["route"] == "planning_design"


def test_requirement_provenance_fields_are_system_owned(tmp_path):
    class MisreportingProvider(MockProvider):
        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "requirement":
                result["original_text"] = "model-rewritten requirement"
                result["human_input"] = {"invented": "model claim"}
                result["decisions"] = {"status": "No human decisions were recorded"}
            return result

    original_text = "A requirement with an unresolved question."
    with Runtime(tmp_path, provider=MisreportingProvider()) as runtime:
        result = runtime.start(original_text, "provenance")
        requirement = result["interrupts"][0]["artifact"]["content"]
        assert result["interrupts"][0]["gate"] == "requirement"
        assert requirement["original_text"] == original_text
        assert requirement["human_input"] == {}
        assert requirement["decisions"] == {}


def test_file_bundle_agent_prompts_require_all_contract_fields():
    for role in ("coding", "test_design"):
        instructions = CONTRACTS[role][1]
        for field in ("files", "change_summary", "criterion_tests", "deviations"):
            assert field in instructions
        assert "never omit" in instructions
    assert "never create or edit tests" in CONTRACTS["coding"][1]


def test_junit_test_id_uses_module_path_when_file_attribute_is_missing(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_greet.py").write_text("", encoding="utf-8")
    test_case = ET.Element(
        "testcase", {"classname": "tests.test_greet", "name": "test_greet_simple_name"}
    )

    assert junit_test_id(test_case, tmp_path) == "tests/test_greet.py::test_greet_simple_name"


def test_prompt_decision_collects_requirement_answers():
    gate = {
        "gate": "requirement",
        "artifact_ref": "requirement@1",
        "actions": ["clarify", "approve", "reject"],
        "artifact": {
            "content": {
                "open_questions": [
                    {
                        "id": "Q1",
                        "unclear": "What should blank names do?",
                        "options": ["Raise ValueError", "Return a greeting"],
                    },
                    {
                        "id": "Q2",
                        "unclear": "How should whitespace be trimmed?",
                        "options": ["Trim both ends", "Collapse internal spaces"],
                    },
                ]
            }
        },
    }
    answers = iter(["clarify", "", "Resolve blank names", "1", "Trim both ends"])

    decision = prompt_decision(gate, input_fn=lambda _: next(answers), output_fn=lambda _: None)

    assert decision == {
        "actor": "local-operator",
        "action": "clarify",
        "rationale": "Resolve blank names",
        "artifact_ref": "requirement@1",
        "answers": {"Q1": "Raise ValueError", "Q2": "Trim both ends"},
    }


def test_interactive_actions_hide_unavailable_safe_stop_choices():
    gate = {
        "gate": "safe_stop",
        "actions": ["retry", "rollback", "accept_risk", "abort"],
        "findings": [],
    }

    assert available_actions(gate) == ["retry", "abort"]


def test_interactive_actions_offer_revise_for_branch_failure():
    gate = {
        "gate": "safe_stop",
        "recovery_node": "synchronize",
        "actions": ["retry", "rollback", "accept_risk", "abort"],
        "findings": [],
    }

    assert "revise" in available_actions(gate, branch_errors={"code": "generation failed"})
    assert "accept_risk" not in available_actions(
        {**gate, "findings": [{"severity": "HIGH", "status": "OPEN"}]},
        branch_errors={"code": "generation failed"},
    )


def test_branch_failure_revise_routes_feedback_to_branch_generation(tmp_path, monkeypatch):
    with Runtime(tmp_path) as runtime:
        _, nodes = runtime.graph("branch-revise")
        captured = {}
        decision = {
            "actor": "local-operator",
            "action": "revise",
            "rationale": "Do not report work explicitly assigned to later slices as a deviation.",
        }

        def resume_interrupt(payload):
            captured.update(payload)
            return decision

        monkeypatch.setattr("ssdlc.nodes.interrupt", resume_interrupt)
        state = {
            "workflow_run_id": "branch-revise",
            "safe_stop_reason": "synchronize: coding branch failed",
            "recovery_node": "synchronize",
            "findings": {},
            "counters": {},
            "branch_errors": {"code": "coding branch failed", "tests": ""},
            "active": {},
            "artifacts": {},
        }

        result = nodes.safe_stop(state)

    assert "revise" in captured["actions"]
    assert result["route"] == "fork"
    assert result["feedback"]["rationale"] == decision["rationale"]


def test_planning_repairs_unapproved_reference_identifiers(tmp_path):
    class IncorrectReferencesProvider(MockProvider):
        def __init__(self):
            self.planning_contexts = []

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "planning_design":
                self.planning_contexts.append(context)
                if len(self.planning_contexts) == 1:
                    result["slices"][0]["requirement_refs"] = ["AC1", "architecture@1"]
                    result["slices"][0]["acceptance_criteria"] = [
                        "Calling greet('World') returns 'Hello, World!'"
                    ]
            return result

    provider = IncorrectReferencesProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = to_architecture(runtime, run="plan-reference-repair")
        result = decide(runtime, "plan-reference-repair", result)

    assert len(provider.planning_contexts) == 2
    assert "requirement_refs" in provider.planning_contexts[1]["validation_feedback"]
    plan = result["state"]["artifacts"][result["state"]["active"]["plan"]]["content"]
    requirement = result["state"]["artifacts"][result["state"]["active"]["requirement"]]["content"]
    requirement_ids = set(requirement["functional_requirements"]) | set(
        requirement["non_functional_requirements"]
    )
    acceptance_ids = {item["id"] for item in requirement["acceptance_criteria"]}
    assert set(plan["slices"][0]["requirement_refs"]) <= requirement_ids
    assert set(plan["slices"][0]["acceptance_criteria"]) <= acceptance_ids


def test_planning_safe_stop_allows_interactive_revise_feedback(tmp_path):
    class ScopeProposalProvider(MockProvider):
        def __init__(self):
            self.planning_contexts = []

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "planning_design":
                self.planning_contexts.append(context)
                if context.get("feedback", {}).get("action") != "revise":
                    result["proposed_scope_changes"] = ["Add an unapproved web API."]
            return result

    provider = ScopeProposalProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = to_architecture(runtime, run="planning-revise")
        result = decide(runtime, "planning-revise", result)
        assert result["interrupts"][0]["gate"] == "safe_stop"
        gate = result["interrupts"][0]
        assert "revise" in available_actions(gate)
        result = decide(
            runtime,
            "planning-revise",
            result,
            action="revise",
            rationale="Keep the plan within approved scope; do not add a web API.",
        )

    assert provider.planning_contexts[-1]["feedback"]["action"] == "revise"
    assert "web API" in provider.planning_contexts[-1]["feedback"]["rationale"]
    assert result["state"]["active"].get("plan") == "plan@1"
    assert result["interrupts"][0]["gate"] == "safe_stop"


@pytest.mark.parametrize("status", ["RESOLVED", "ACCEPTED_RISK"])
def test_safe_stop_hides_settled_findings_and_risk_acceptance(status):
    finding = {"id": "architecture/old", "severity": "LOW", "status": status}
    gate = {
        "gate": "safe_stop",
        "actions": ["retry", "accept_risk", "abort"],
        "findings": [finding],
        "recovery_node": "lld",
    }
    actions = available_actions(gate)
    assert actions == ["retry", "revise", "abort"]
    output = []
    display_gate(gate, actions=actions, output_fn=output.append)
    assert "architecture/old" not in "\n".join(output)
    assert gate["findings"] == [finding]


def test_llm_progress_handler_reports_wait_retry_and_completion():
    output = io.StringIO()
    handler = LLMProgressHandler(stream=output)
    try:
        events = [
            {"action": "agent_started", "stage": "planning", "rationale": "operation-1"},
            {"action": "retry_attempted", "stage": "planning", "rationale": "retry"},
            {
                "action": "agent_completed",
                "stage": "planning",
                "rationale": json.dumps({"operation": "operation-1"}),
            },
        ]
        for event in events:
            record = logging.LogRecord(
                "ssdlc.audit", logging.INFO, __file__, 1, json.dumps(event), (), None
            )
            handler.handle(record)
    finally:
        handler.close()

    assert "[wait] LLM: planning" in output.getvalue()
    assert "[retry] LLM response for planning" in output.getvalue()
    assert "[done] LLM response received for planning" in output.getvalue()


def test_interactive_actions_hide_approval_with_unanswered_question():
    gate = {
        "gate": "requirement",
        "actions": ["clarify", "approve", "reject"],
        "artifact": {
            "content": {
                "decisions": {},
                "open_questions": [
                    {
                        "id": "Q1",
                        "classification": "BLOCKING_AMBIGUITY",
                        "human_confirmation_required": True,
                    }
                ],
            }
        },
    }

    assert available_actions(gate) == ["clarify", "reject"]


def test_interactive_session_resumes_until_workflow_finishes():
    gate = {
        "gate": "architecture",
        "artifact_ref": "architecture@1",
        "actions": ["approve", "reject", "revise"],
        "architecture": {"sections": {"scope": "A small greeting library"}},
    }
    result = {
        "state": {
            "workflow_run_id": "interactive-test",
            "workflow_status": "WAITING_FOR_HUMAN",
            "artifacts": {},
        },
        "interrupts": [gate],
    }

    class RuntimeStub:
        def __init__(self):
            self.decision = None

        def resume(self, run, decision):
            self.decision = (run, decision)
            return {
                "state": {
                    "workflow_run_id": run,
                    "workflow_status": "READY_FOR_DEPLOYMENT",
                    "artifacts": {},
                },
                "interrupts": [],
            }

    runtime = RuntimeStub()
    answers = iter(["approve", "", "Architecture reviewed"])
    finished = interactive_session(
        runtime,
        result,
        input_fn=lambda _: next(answers),
        output_fn=lambda _: None,
    )

    assert runtime.decision == (
        "interactive-test",
        {
            "actor": "local-operator",
            "action": "approve",
            "rationale": "Architecture reviewed",
            "artifact_ref": "architecture@1",
        },
    )
    assert finished["state"]["workflow_status"] == "READY_FOR_DEPLOYMENT"


def test_interactive_session_redirects_early_approval_to_clarification():
    gate = {
        "gate": "requirement",
        "artifact_ref": "requirement@1",
        "actions": ["clarify", "approve", "reject"],
        "artifact": {
            "content": {
                "open_questions": [
                    {
                        "id": "Q1",
                        "unclear": "What should blank names do?",
                        "options": ["Raise ValueError", "Return a greeting"],
                    }
                ]
            }
        },
    }
    result = {
        "state": {
            "workflow_run_id": "retry-prompt-test",
            "workflow_status": "WAITING_FOR_HUMAN",
            "artifacts": {},
        },
        "interrupts": [gate],
    }

    class RuntimeStub:
        def __init__(self):
            self.decisions = []

        def resume(self, run, decision):
            self.decisions.append(decision)
            return {
                "state": {
                    "workflow_run_id": run,
                    "workflow_status": "WAITING_FOR_HUMAN",
                    "artifacts": {},
                },
                "interrupts": [],
            }

    runtime = RuntimeStub()
    messages = []
    answers = iter(
        [
            "approve",
            "clarify",
            "",
            "Review requirement",
            "1",
        ]
    )
    finished = interactive_session(
        runtime,
        result,
        input_fn=lambda _: next(answers),
        output_fn=messages.append,
    )

    assert [decision["action"] for decision in runtime.decisions] == ["clarify"]
    assert any("Choose one of: clarify, reject" in message for message in messages)
    assert finished["interrupts"] == []


def test_full_real_graph_and_real_tools(tmp_path):
    with Runtime(tmp_path, allow_execution=True) as runtime:
        result = to_architecture(runtime)
        result = decide(runtime, "demo", result)
        assert result["interrupts"][0]["gate"] == "release", result["interrupts"]
        result = decide(runtime, "demo", result)
        assert result["state"]["workflow_status"] == "READY_FOR_DEPLOYMENT"
        assert not result["interrupts"]
        state = result["state"]
        assert len(state["tool_results"]) == 4
        assert all(r["exit_status"] == 0 for r in state["tool_results"].values())
        assert (
            len(
                list(
                    Path(state["artifacts"][state["active"]["build"]]["content"]["cwd"]).glob(
                        "dist/*.whl"
                    )
                )
            )
            == 1
        )
        actions = [e["action"] for e in runtime.repo.events("demo")]
        assert "branches_synchronized" in actions
        assert actions.index("branches_synchronized") < actions.index("tool_executed")
        assert runtime.metrics("demo")["workflow_success_total"] == 1
        assert runtime.metrics("demo")["test_pass_count"] == 1


class BlockingReviewer(MockProvider):
    def generate(self, role, instructions, context, schema):
        if role == "architecture_reviewer":
            return {
                "complete": True,
                "findings": [
                    {
                        "id": "ownership",
                        "category": "correctness",
                        "severity": "BLOCKER",
                        "description": "Unresolved issue",
                        "rationale": "Test scenario",
                        "affected_component": "greeting",
                        "suggested_resolution": "Revise",
                    }
                ],
            }
        return super().generate(role, instructions, context, schema)


def test_bounded_review_and_blocker_safe_stop(tmp_path):
    with Runtime(tmp_path, provider=BlockingReviewer()) as runtime:
        result = to_architecture(runtime)
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert result["state"]["counters"]["architecture_review"] == 2
        assert result["state"]["findings"]["architecture/ownership"]["status"] == "OPEN"
        with pytest.raises(ValueError, match="non-BLOCKER"):
            decide(runtime, "demo", result, "accept_risk", finding_ids=["architecture/ownership"])
        result = decide(runtime, "demo", result, "abort")
        assert result["state"]["workflow_status"] == "ABORTED"


class BrokenImplementation(MockProvider):
    def generate(self, role, instructions, context, schema):
        result = super().generate(role, instructions, context, schema)
        if role == "coding":
            result["files"]["greeting.py"] = 'def greet(name):\n    return "wrong"\n'
        if role == "failure_analysis":
            result["category"] = "IMPLEMENTATION_DEFECT"
        return result


def test_failed_tests_retry_budget_and_unaffected_test_artifact(tmp_path):
    with Runtime(
        tmp_path,
        provider=BrokenImplementation(),
        policy=Policy(max_replans=1),
        allow_execution=True,
    ) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert "Re-plan budget exhausted" in result["interrupts"][0]["reason"]
        assert result["state"]["active"]["tests:greeting"] == "tests:greeting@1"
        assert result["state"]["active"]["code:greeting"] == "code:greeting@2"
        assert "release" not in result["state"]["active"]
        assert runtime.metrics("demo")["test_fail_count"] == 2


def test_execution_disabled_stops_before_tools(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert "Local execution disabled" in result["interrupts"][0]["reason"]
        assert not result["state"]["tool_results"]


class ConcurrentProvider(MockProvider):
    def __init__(self):
        self.barrier = Barrier(2, timeout=10)
        self.contexts = {}

    def generate(self, role, instructions, context, schema):
        if role in {"coding", "test_design"}:
            self.contexts[role] = context
            self.barrier.wait()
        return super().generate(role, instructions, context, schema)


def test_parallel_branches_share_baseline_without_code_leakage(tmp_path):
    provider = ConcurrentProvider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert "Local execution disabled" in result["interrupts"][0]["reason"]
        code, tests = provider.contexts["coding"], provider.contexts["test_design"]
        for key in ("requirement", "architecture", "adrs", "design", "slice"):
            assert code[key] == tests[key]
        assert "implementation" not in tests


def test_brownfield_impact_precedes_planning(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "greeting.py").write_text("# Existing repository\n", encoding="utf-8")
    with Runtime(tmp_path / "runs") as runtime:
        result = decide(
            runtime, "demo", to_architecture(runtime, scenario="brownfield", source=source)
        )
        state = result["state"]
        impact = state["artifacts"][state["active"]["impact"]]
        assert "greeting.py" in impact["content"]["affected_modules"]
        assert (
            state["active"]["impact"] in state["artifacts"][state["active"]["plan"]]["dependencies"]
        )
        assert (source / "greeting.py").read_text() == "# Existing repository\n"


def test_rollback_preserves_audit_and_invalidates_descendants(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = to_architecture(runtime)
        result = decide(runtime, "demo", result, "reject")
        before = runtime.repo.events("demo")
        result = decide(runtime, "demo", result, "rollback", target_ref="requirement@2")
        assert result["interrupts"][0]["gate"] == "architecture"
        assert result["state"]["active"]["architecture"] == "architecture@2"
        assert result["state"]["artifacts"]["architecture@1"]["validity"] == "SUPERSEDED"
        after = runtime.repo.events("demo")
        assert after[: len(before)] == before
        assert runtime.metrics("demo")["rollback_count"] == 1


def test_stale_approval_does_not_consume_interrupt(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = to_architecture(runtime)
        with pytest.raises(ValueError, match="exact current"):
            runtime.resume(
                "demo",
                {
                    "actor": "human",
                    "action": "approve",
                    "rationale": "test stale target",
                    "artifact_ref": "architecture@0",
                },
            )
        assert runtime.inspect("demo")["interrupts"][0] == result["interrupts"][0]


def test_release_rechecks_candidate_after_human_wait(tmp_path):
    with Runtime(tmp_path, allow_execution=True) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["interrupts"][0]["gate"] == "release"
        root = Path(result["interrupts"][0]["release"]["content"]["candidate"])
        (root / "greeting.py").write_text("# Changed after validation\n", encoding="utf-8")
        result = decide(runtime, "demo", result)
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert result["state"]["workflow_status"] != "READY_FOR_DEPLOYMENT"


def test_high_risk_requires_explicit_human_disposition(tmp_path):
    class HighReviewer(BlockingReviewer):
        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "architecture_reviewer":
                result["findings"][0]["severity"] = "HIGH"
            return result

    with Runtime(tmp_path, provider=HighReviewer()) as runtime:
        result = to_architecture(runtime)
        assert result["interrupts"][0]["gate"] == "safe_stop"
        result = decide(
            runtime, "demo", result, "accept_risk", finding_ids=["architecture/ownership"]
        )
        assert result["interrupts"][0]["gate"] == "architecture"
        assert result["state"]["findings"]["architecture/ownership"]["status"] == "ACCEPTED_RISK"
        assert "plan" not in result["state"]["active"]
        result = decide(runtime, "demo", result)
        assert result["interrupts"][0]["gate"] == "safe_stop"
        with pytest.raises(ValueError, match="unresolved non-BLOCKER"):
            decide(runtime, "demo", result, "accept_risk", finding_ids=["architecture/ownership"])
        assert runtime.inspect("demo")["interrupts"][0] == result["interrupts"][0]


@pytest.mark.parametrize("defect", ["sections", "blank", "references", "coverage"])
def test_combined_design_is_repaired_before_publication(tmp_path, defect):
    class Provider(MockProvider):
        def __init__(self):
            self.contexts = []

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "planning_design":
                self.contexts.append(context)
                if len(self.contexts) == 1:
                    item = result["slices"][0]
                    if defect == "sections":
                        item["design"].pop("interfaces")
                    elif defect == "blank":
                        item["design"]["contracts"] = " "
                    elif defect == "references":
                        item["requirement_refs"] = ["unapproved"]
                    else:
                        item["acceptance_criteria"] = ["AC1"]
            return result

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["state"]["active"]["plan"] == "plan@1"
        assert len(provider.contexts) == 2
        assert provider.contexts[1]["validation_feedback"]
        assert "lld:greeting" not in result["state"]["active"]


def test_shared_quality_review_is_bounded_and_runs_after_join(tmp_path):
    class Provider(MockProvider):
        def __init__(self):
            self.roles = []

        def generate(self, role, instructions, context, schema):
            self.roles.append(role)
            if role == "quality_reviewer":
                assert set(context["artifact"]["content"]) == {"code", "tests"}
                return {"complete": False, "findings": []}
            return super().generate(role, instructions, context, schema)

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert result["state"]["counters"]["quality_review:greeting"] == 2
        assert provider.roles.count("planning_design") == 1
        assert provider.roles.count("quality_reviewer") == 2
        assert "code_reviewer" not in provider.roles
        assert not result["state"]["tool_results"]


def test_shared_review_requires_verified_resolution_on_new_pair(tmp_path):
    class Provider(MockProvider):
        def __init__(self):
            self.reviews = 0

        def generate(self, role, instructions, context, schema):
            if role == "quality_reviewer":
                self.reviews += 1
                if self.reviews == 1:
                    return {
                        "complete": True,
                        "findings": [
                            {
                                "id": "contract",
                                "category": "correctness",
                                "severity": "HIGH",
                                "description": "Verify blank-name contract",
                                "rationale": "Review scenario",
                                "affected_component": "greeting",
                                "suggested_resolution": "Verify contract",
                            }
                        ],
                    }
                prior = context["previous_findings"][0]
                assert context["artifact"]["version"] > prior["artifact_version"]
                return {
                    "complete": True,
                    "findings": [],
                    "resolutions": [
                        {
                            "finding_id": prior["id"],
                            "author_response": "Confirmed contract",
                            "actual_change": "Regenerated code and tests against the contract",
                            "resolution_reason": "Review confirmed the behavior",
                            "reviewer_verification": "Checked blank validation and negative tests",
                        }
                    ],
                }
            return super().generate(role, instructions, context, schema)

    with Runtime(tmp_path, provider=Provider()) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        state = result["state"]
        assert "Local execution disabled" in result["interrupts"][0]["reason"]
        assert state["active"]["quality:greeting"] == "quality:greeting@2"
        assert state["findings"]["quality:greeting/contract"]["status"] == "RESOLVED"


def test_design_failure_routes_to_combined_plan_and_invalidates_children(tmp_path):
    class Provider(MockProvider):
        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "failure_analysis":
                result["category"] = "DESIGN_DEFECT"
            return result

    with Runtime(tmp_path, provider=Provider()) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        _, nodes = runtime.graph("demo")
        update = nodes.failure_analysis(result["state"])
        assert update["route"] == "planning_design"
        assert update["artifacts"]["plan@1"]["validity"] == "INVALIDATED"
        assert update["artifacts"]["code:greeting@1"]["validity"] != "VALID"
        assert update["artifacts"]["tests:greeting@1"]["validity"] != "VALID"
        assert "architecture@1" not in update["artifacts"]


@pytest.mark.parametrize(
    "defect",
    ["blank_author", "blank_verification", "unresolved", "unknown", "wrong_artifact", "both"],
)
def test_invalid_review_resolution_is_repaired_before_caching(tmp_path, defect):
    class Provider(MockProvider):
        def __init__(self):
            self.contexts = []

        def generate(self, role, instructions, context, schema):
            if role != "quality_reviewer":
                return super().generate(role, instructions, context, schema)
            self.contexts.append(context)
            finding = {
                "id": "quality:greeting/contract",
                "category": "correctness",
                "severity": "HIGH",
                "description": "Contract needs review",
                "rationale": "Regression",
                "affected_component": "greeting",
                "suggested_resolution": "Review contract",
            }
            if len(self.contexts) == 1:
                return {"complete": True, "findings": [finding]}
            resolution = {
                "finding_id": context["previous_findings"][0]["id"],
                "author_response": "Revised against contract",
                "actual_change": "Revised code/test pair",
                "reviewer_verification": "Checked revised validation and tests",
                "resolution_reason": "Verified fixed",
            }
            findings = []
            if len(self.contexts) == 2:
                if defect == "blank_author":
                    resolution["author_response"] = ""
                elif defect == "blank_verification":
                    resolution["reviewer_verification"] = "   "
                elif defect == "unresolved":
                    resolution["resolution_reason"] = "Not fully resolved: still broken"
                elif defect == "unknown":
                    resolution["finding_id"] = "unknown"
                elif defect == "wrong_artifact":
                    resolution["finding_id"] = "architecture/old"
                else:
                    findings = [finding]
            return {"complete": True, "findings": findings, "resolutions": [resolution]}

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert "Local execution disabled" in result["interrupts"][0]["reason"]
        assert len(provider.contexts) == 3
        assert "validation_feedback" in provider.contexts[2]
        assert set(result["state"]["findings"]) == {"quality:greeting/contract"}
        assert result["state"]["findings"]["quality:greeting/contract"]["status"] == "RESOLVED"
        schema, instructions = CONTRACTS["quality_reviewer"]
        key = digest(
            [
                provider.name,
                "quality_reviewer",
                instructions,
                schema.model_json_schema(),
                provider.contexts[1],
            ]
        )
        cached = runtime.repo.cached("demo", key)
        assert cached["resolutions"][0]["author_response"]
        assert cached["resolutions"][0]["resolution_reason"] == "Verified fixed"


def test_retry_quality_blockers_regenerates_branches_without_accepting_risk(tmp_path, monkeypatch):
    class Provider(MockProvider):
        def generate(self, role, instructions, context, schema):
            if role == "quality_reviewer":
                return {
                    "complete": True,
                    "findings": [
                        {
                            "id": "QF-07",
                            "category": "correctness",
                            "severity": "BLOCKER",
                            "description": "Test seam mismatch",
                            "rationale": "Regression",
                            "affected_component": "tests",
                            "suggested_resolution": "Fix seam",
                        }
                    ],
                }
            return super().generate(role, instructions, context, schema)

    with Runtime(tmp_path, provider=Provider()) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        state = result["state"]
        assert state["recovery_node"] == "quality_review"
        monkeypatch.setattr(
            "ssdlc.nodes.interrupt",
            lambda _: {
                "actor": "human",
                "action": "retry",
                "rationale": "Fix outstanding defects",
            },
        )
        _, nodes = runtime.graph("demo")
        update = nodes.safe_stop(state)
        assert update["route"] == "fork"
        assert update["counters"]["quality_review:greeting"] == 0
        assert not update["findings"]
        assert state["findings"]["quality:greeting/QF-07"]["status"] == "OPEN"
        for kind in ("code", "tests", "quality"):
            assert (
                update["artifacts"][state["active"][f"{kind}:greeting"]]["validity"]
                == "INVALIDATED"
            )


def test_review_preserves_existing_duplicated_finding_ids(tmp_path):
    class Provider(MockProvider):
        def generate(self, role, instructions, context, schema):
            if role == "quality_reviewer" and context["previous_findings"]:
                finding = context["previous_findings"][0]
                return {
                    "complete": True,
                    "findings": [
                        {
                            k: finding[k]
                            for k in (
                                "id",
                                "category",
                                "severity",
                                "description",
                                "rationale",
                                "affected_component",
                                "suggested_resolution",
                            )
                        }
                    ],
                }
            return super().generate(role, instructions, context, schema)

    with Runtime(tmp_path, provider=Provider()) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        state = result["state"]
        legacy_id = "quality:greeting/quality:greeting/QF-07"
        state["findings"][legacy_id] = {
            "id": legacy_id,
            "artifact_id": "quality:greeting",
            "artifact_version": 1,
            "category": "correctness",
            "severity": "HIGH",
            "status": "OPEN",
            "description": "Unfixed",
            "rationale": "Legacy",
            "affected_component": "tests",
            "suggested_resolution": "Fix",
            "created_at": "2026-10-04T15:55:08+00:00",
        }
        _, nodes = runtime.graph("demo")
        update = nodes.review(state, "quality:greeting", "quality_reviewer")
        assert set(update["findings"]) == {legacy_id}
        assert update["findings"][legacy_id]["status"] == "OPEN"


def test_invalid_cached_review_resolution_is_replaced_only_after_repair(tmp_path):
    class Provider(MockProvider):
        def __init__(self):
            self.contexts = []

        def generate(self, role, instructions, context, schema):
            if role == "quality_reviewer" and context["previous_findings"]:
                self.contexts.append(context)
                return {
                    "complete": True,
                    "findings": [],
                    "resolutions": [
                        {
                            "finding_id": context["previous_findings"][0]["id"],
                            "author_response": "Revised",
                            "actual_change": "Changed pair",
                            "reviewer_verification": "Confirmed fix",
                            "resolution_reason": "Verified fixed",
                        }
                    ],
                }
            return super().generate(role, instructions, context, schema)

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        state = decide(runtime, "demo", to_architecture(runtime))["state"]
        state["findings"]["quality:greeting/contract"] = {
            "id": "quality:greeting/contract",
            "artifact_id": "quality:greeting",
            "artifact_version": 1,
            "severity": "HIGH",
            "status": "OPEN",
        }
        _, nodes = runtime.graph("demo")
        old = state["artifacts"][state["active"]["quality:greeting"]]
        state = nodes.apply(
            state,
            nodes.artifact(
                state, "quality:greeting", "quality", old["content"], old["dependencies"]
            ),
        )
        nodes.review(state, "quality:greeting", "quality_reviewer")
        schema, instructions = CONTRACTS["quality_reviewer"]
        key = digest(
            [
                provider.name,
                "quality_reviewer",
                instructions,
                schema.model_json_schema(),
                provider.contexts[0],
            ]
        )
        bad = runtime.repo.cached("demo", key)
        bad["resolutions"][0]["author_response"] = ""
        runtime.repo.cache("demo", key, bad, replace=True)
        update = nodes.review(state, "quality:greeting", "quality_reviewer")
        assert update["findings"]["quality:greeting/contract"]["status"] == "RESOLVED"
        assert len(provider.contexts) == 2
        assert "empty fields" in provider.contexts[1]["validation_feedback"]
        assert runtime.repo.cached("demo", key)["resolutions"][0]["author_response"] == "Revised"
        assert any(e["action"] == "cached_response_rejected" for e in runtime.repo.events("demo"))


def test_retry_does_not_overwrite_artifact_published_before_failed_checkpoint(tmp_path):
    with Runtime(tmp_path) as runtime:
        state = decide(runtime, "demo", to_architecture(runtime))["state"]
        _, nodes = runtime.graph("demo")
        original = state["artifacts"][state["active"]["quality:greeting"]]
        # Publish a review candidate as a failed node did, without applying its update.
        orphan = nodes.artifact(
            state,
            "quality:greeting",
            "quality",
            {"attempt": "failed review"},
            original["dependencies"],
        )
        assert orphan["active"]["quality:greeting"] == "quality:greeting@2"
        # Resume from the old checkpoint with a changed pair.
        repaired = nodes.artifact(
            state,
            "quality:greeting",
            "quality",
            {"attempt": "new review"},
            original["dependencies"],
        )
        assert repaired["active"]["quality:greeting"] == "quality:greeting@3"
        assert runtime.repo.artifact("demo", "quality:greeting@2")["content"] == {
            "attempt": "failed review"
        }


@pytest.mark.parametrize("target", ["requirement", "planning_design"])
def test_branch_stop_can_revise_upstream_without_approving_it(tmp_path, target):
    class Provider(MockProvider):
        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "test_design" and not context.get("feedback", {}).get("revision_target"):
                result["deviations"] = ["The shared design is missing a required test seam"]
            return result

    with Runtime(tmp_path, provider=Provider()) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["state"]["recovery_node"] == "synchronize"
        assert "accept_risk" not in result["interrupts"][0]["actions"]
        with pytest.raises(ValueError, match="not permitted"):
            decide(runtime, "demo", result, "accept_risk", finding_ids=["old-finding"])
        assert "tests:greeting" not in result["state"]["active"]
        old_requirement = result["state"]["active"]["requirement"]
        old_plan = result["state"]["active"]["plan"]
        result = decide(
            runtime,
            "demo",
            result,
            "revise",
            revision_target=target,
            rationale="Clarify the requirement"
            if target == "requirement"
            else "Define exact seams",
        )
        state = result["state"]
        assert state["feedback"]["revision_target"] == target
        assert state["artifacts"][old_plan]["validity"] != "VALID"
        if target == "requirement":
            assert result["interrupts"][0]["gate"] == "requirement"
            assert state["active"]["requirement"] != old_requirement
            assert state["artifacts"][state["active"]["requirement"]]["approval_status"] == "DRAFT"
            assert state["artifacts"][state["active"]["architecture"]]["validity"] != "VALID"
        else:
            assert state["active"]["requirement"] == old_requirement
            assert state["active"]["plan"] == "plan@2"
            assert "Local execution disabled" in result["interrupts"][0]["reason"]
        assert runtime.repo.verify_audit("demo")


def test_cached_branch_deviation_is_rejected_and_repaired_before_publication(tmp_path):
    class Provider(MockProvider):
        def __init__(self):
            self.contexts = []

        def generate(self, role, instructions, context, schema):
            if role == "test_design":
                self.contexts.append(context)
            return super().generate(role, instructions, context, schema)

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        state = decide(runtime, "demo", to_architecture(runtime))["state"]
        schema, instructions = CONTRACTS["test_design"]
        key = digest(
            [
                provider.name,
                "test_design",
                instructions,
                schema.model_json_schema(),
                provider.contexts[0],
            ]
        )
        bad = runtime.repo.cached("demo", key)
        bad["deviations"] = ["Skip durability when the adapter is missing"]
        runtime.repo.cache("demo", key, bad, replace=True)
        # Replay from before branch generation, as an older checkpoint would.
        state = dict(state, reviews={}, active=dict(state["active"]))
        del state["active"]["tests:greeting"]
        _, nodes = runtime.graph("demo")
        update = nodes.branch_generate(state, "tests")
        assert len(provider.contexts) == 2
        assert "Skip durability" in provider.contexts[-1]["validation_feedback"]
        assert "do not hide" in provider.contexts[-1]["validation_feedback"]
        assert (
            update["artifacts"][update["active"]["tests:greeting"]]["content"]["deviations"] == []
        )
        assert runtime.repo.cached("demo", key)["deviations"] == []
        assert any(e["action"] == "cached_response_rejected" for e in runtime.repo.events("demo"))


def test_interactive_safe_stop_revision_selects_upstream_target():
    gate = {"gate": "safe_stop", "actions": ["revise"]}
    replies = iter(
        ["revise", "human", "DNS failures return 503 with nothing persisted", "requirement"]
    )
    decision = prompt_decision(gate, input_fn=lambda _: next(replies), output_fn=lambda _: None)
    assert decision["revision_target"] == "requirement"
    assert decision["rationale"] == "DNS failures return 503 with nothing persisted"


def test_revision_target_cannot_bypass_a_normal_approval_gate(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = to_architecture(runtime)
        with pytest.raises(ValueError, match="supported safe-stop revision"):
            decide(runtime, "demo", result, "revise", revision_target="requirement")
        assert runtime.inspect("demo")["interrupts"] == result["interrupts"]


def test_missing_api_contract_repaired_during_planning_before_generation(tmp_path):
    class Provider(MockProvider):
        def __init__(self):
            self.plans = []

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "planning_design":
                self.plans.append(context)
                if len(self.plans) == 1:
                    result["slices"][0].pop("api_contract")
            if role in {"coding", "test_design"}:
                assert len(self.plans) == 2
                assert context["slice"]["api_contract"]["greeting.py"]
            return result

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert "api_contract" in provider.plans[-1]["validation_feedback"]
        assert "Local execution disabled" in result["interrupts"][0]["reason"]


def test_legacy_missing_contract_returns_to_planning_with_bounded_recovery(tmp_path):
    with Runtime(tmp_path) as runtime:
        state = decide(runtime, "demo", to_architecture(runtime))["state"]
        _, nodes = runtime.graph("demo")
        state["artifacts"][state["active"]["plan"]]["content"]["slices"][0].pop("api_contract")
        # An older saved plan is rejected before either independent generation call.
        branch = nodes.guarded("branch_generate", lambda s: nodes.branch_generate(s, "tests"))(
            state
        )
        assert "ContractError:" in branch["safe_stop_reason"]
        state["branch_errors"] = {"code": "", "tests": branch["safe_stop_reason"]}
        update = nodes.synchronize(state)
        assert update["route"] == "planning_design"
        assert update["counters"]["replans"] == 1
        assert update["feedback"]["contract_errors"]
        state["counters"]["replans"] = runtime.policy.max_replans
        with pytest.raises(ValueError, match="repair budget exhausted"):
            nodes.synchronize(state)


def test_signature_conflict_replans_automatically_before_quality_review(tmp_path):
    class Provider(MockProvider):
        def __init__(self):
            self.coding_calls = 0
            self.quality_calls = 0

        def generate(self, role, instructions, context, schema):
            result = super().generate(role, instructions, context, schema)
            if role == "coding":
                self.coding_calls += 1
                if not context.get("feedback", {}).get("contract_errors"):
                    result["files"]["greeting.py"] = result["files"]["greeting.py"].replace(
                        "def greet(name: str)", "def greet(person: str)"
                    )
            elif role == "quality_reviewer":
                self.quality_calls += 1
                assert self.coding_calls == 3
            elif role == "test_design":
                assert "implementation" not in context
            return result

    provider = Provider()
    with Runtime(tmp_path, provider=provider) as runtime:
        result = decide(runtime, "demo", to_architecture(runtime))
        assert result["state"]["active"]["plan"] == "plan@2"
        assert result["state"]["counters"]["replans"] == 1
        assert "Local execution disabled" in result["interrupts"][0]["reason"]
        assert provider.quality_calls == 1
        assert runtime.repo.verify_audit("demo")
