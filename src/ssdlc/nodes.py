"""Lifecycle nodes; routing and budgets are deterministic application policy."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from langgraph.types import interrupt

from ssdlc.engine import Engine
from ssdlc.models import (
    ARCHITECTURE_SECTIONS,
    DESIGN_SECTIONS,
    Approval,
    HumanDecision,
    Requirement,
    now,
)
from ssdlc.persistence import digest, invalidate
from ssdlc.policy import approved, baseline, prohibited_findings, release_gate, reviewed
from ssdlc.state import active_artifact
from ssdlc.tools import codebase_snapshot, safe_path, tree_digest


def junit_test_id(test_case, root: Path) -> str:
    file_name = test_case.get("file", "").replace("\\", "/")
    if file_name:
        candidate = Path(file_name)
        if candidate.is_absolute():
            try:
                file_name = candidate.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                file_name = candidate.as_posix()
    else:
        module_parts = test_case.get("classname", "").split(".")
        for length in range(len(module_parts), 0, -1):
            candidate = root.joinpath(*module_parts[:length]).with_suffix(".py")
            if candidate.is_file():
                file_name = candidate.relative_to(root).as_posix()
                break
        if not file_name:
            file_name = "/".join(module_parts) + ".py"
    return f"{file_name}::{test_case.get('name', '')}"


class Nodes(Engine):
    def requirement(self, state):
        context = {
            "original_text": state["original_text"],
            "answers": state.get("answers", {}),
            "feedback": state.get("feedback", {}),
        }
        if "requirement" in state["active"]:
            context["previous_version"] = state["artifacts"][state["active"]["requirement"]]
        result = self.call(state, "requirement", context)
        result.original_text = state["original_text"]
        result.human_input = state.get("answers", {})
        result.decisions = state.get("answers", {})
        ids = [c.id for c in result.acceptance_criteria]
        question_ids = [q.id for q in result.open_questions]
        if len(ids) != len(set(ids)) or len(question_ids) != len(set(question_ids)):
            raise ValueError("Duplicate criterion or question IDs")
        for criterion in result.acceptance_criteria:
            if (
                criterion.requirement_ref
                not in result.functional_requirements | result.non_functional_requirements
            ):
                raise ValueError("Acceptance criterion has no requirement")
        if context.get("previous_version"):
            result.changes_from_previous_version = [
                "Reanalyzed with human input or failure evidence"
            ]
            result.reason_for_change = "Human clarification / governed re-planning"
        update = self.artifact(
            state, "requirement", "requirement", result.model_dump(mode="json"), []
        )
        pending = [
            q
            for q in result.open_questions
            if (q.human_confirmation_required or q.classification == "BLOCKING_AMBIGUITY")
            and not result.decisions.get(q.id)
        ]
        self.event(
            state,
            "human_question_raised" if pending else "requirement_ready_for_approval",
            "requirement",
            json.dumps([q.model_dump() for q in pending]),
            [update["active"]["requirement"]],
        )
        return {**update, "workflow_status": "WAITING_FOR_HUMAN", "route": "requirement_approval"}

    def requirement_approval(self, state):
        artifact = active_artifact(state, "requirement")
        decision = HumanDecision.model_validate(
            interrupt(
                {
                    "gate": "requirement",
                    "artifact_ref": state["active"]["requirement"],
                    "artifact": artifact,
                    "actions": ["clarify", "approve", "reject"],
                }
            )
        )
        if decision.action in {"clarify", "revise"}:
            self.event(
                state,
                "human_response_received",
                "requirement",
                decision.rationale,
                [state["active"]["requirement"]],
                actor_type="human",
                actor_id=decision.actor,
            )
            return {
                "answers": {**state.get("answers", {}), **decision.answers},
                "feedback": decision.model_dump(),
                "route": "requirement",
                "workflow_status": "RUNNING",
            }
        if decision.action != "approve":
            return self.rejection(state, decision, "requirement")
        req = Requirement.model_validate(artifact["content"])
        pending = [
            q.id
            for q in req.open_questions
            if (q.human_confirmation_required or q.classification == "BLOCKING_AMBIGUITY")
            and not req.decisions.get(q.id, "").strip()
        ]
        if pending:
            raise ValueError(f"Unresolved human decisions: {pending}")
        return {
            **self.approve(state, decision, ["requirement"]),
            "route": "architecture",
            "workflow_status": "RUNNING",
        }

    def approve(self, state, decision, keys):
        changes, approvals = {}, {}
        if decision.artifact_ref != state["active"][keys[0]]:
            raise ValueError("Approval targets a stale or different artifact")
        for key in keys:
            value = active_artifact(state, key).copy()
            record = Approval(
                artifact_ref=state["active"][key],
                actor=decision.actor,
                decision="approve",
                rationale=decision.rationale,
            )
            value.update(
                approval_status="APPROVED",
                approver=decision.actor,
                approval_timestamp=record.timestamp,
            )
            changes[record.artifact_ref] = value
            approvals[record.id] = record.model_dump()
            self.event(
                state,
                "human_approval",
                key,
                decision.rationale,
                [record.artifact_ref],
                actor_type="human",
                actor_id=decision.actor,
                related_approval_ids=[record.id],
            )
        self.persist_changes(state, changes)
        return {"artifacts": changes, "approvals": approvals}

    def rejection(self, state, decision, key):
        self.event(
            state,
            "human_rejection",
            key,
            decision.rationale,
            [state["active"][key]],
            actor_type="human",
            actor_id=decision.actor,
        )
        artifact = active_artifact(state, key).copy()
        artifact["approval_status"] = "REJECTED"
        self.persist_changes(state, {state["active"][key]: artifact})
        return {
            "artifacts": {state["active"][key]: artifact},
            "route": "safe_stop",
            "safe_stop_reason": f"Human rejected {key}: {decision.rationale}",
            "recovery_node": {"release": "release_readiness", "plan": "planning"}.get(key, key),
            "workflow_status": "SAFE_STOP",
        }

    def architecture(self, state):
        requirement = approved(state, "requirement")
        counter = "architecture_review"
        count = state["counters"].get(counter, 0)
        if count >= self.policy.max_review_cycles:
            raise ValueError("Architecture review cycle budget exhausted")
        context = {
            "requirement": requirement,
            "previous_findings": [
                f for f in state["findings"].values() if f["artifact_id"] == "architecture"
            ],
            "feedback": state.get("feedback", {}),
        }
        if "architecture" in state["active"]:
            context["previous_version"] = state["artifacts"][state["active"]["architecture"]]
        requirements = (
            requirement["content"]["functional_requirements"]
            | requirement["content"]["non_functional_requirements"]
        )
        required_ids = set(requirements)

        def validate_architecture(result):
            missing_sections = ARCHITECTURE_SECTIONS - result.sections.keys()
            empty_sections = [key for key, value in result.sections.items() if not value.strip()]
            if missing_sections or empty_sections:
                raise ValueError(
                    "Architecture package is incomplete. "
                    f"Missing sections: {sorted(missing_sections)}. "
                    f"Empty sections: {sorted(empty_sections)}. "
                    "Include every required section with meaningful text; explain non-applicability where appropriate."
                )
            missing_ids = required_ids - result.requirement_mapping.keys()
            unexpected_ids = result.requirement_mapping.keys() - required_ids
            if missing_ids or unexpected_ids:
                raise ValueError(
                    "Correct requirement_mapping. Its keys must be exactly the approved functional "
                    "and non-functional requirement IDs, not acceptance-criterion IDs. "
                    f"Missing IDs: {sorted(missing_ids)}. Unexpected IDs: {sorted(unexpected_ids)}. "
                    "Return a complete architecture package with a meaningful mapping for every ID."
                )
            if any(not value.strip() for value in result.requirement_mapping.values()):
                raise ValueError("Every requirement_mapping value must contain meaningful text")
            if len({a.adr_id for a in result.adrs}) != len(result.adrs):
                raise ValueError("Duplicate ADR IDs")
            if any(not adr.adr_id.startswith("ADR-") for adr in result.adrs):
                raise ValueError("ADR identifiers must begin ADR-")

        result = self.call(state, "architecture", context, validator=validate_architecture)
        update = self.artifact(
            state,
            "architecture",
            "architecture",
            result.model_dump(mode="json"),
            [state["active"]["requirement"]],
        )
        working = self.apply(state, update)
        for adr in result.adrs:
            working = self.apply(
                working,
                self.artifact(
                    working,
                    adr.adr_id,
                    "adr",
                    adr.model_dump(mode="json"),
                    [working["active"]["architecture"]],
                ),
            )
        return {
            "artifacts": {
                k: v for k, v in working["artifacts"].items() if state["artifacts"].get(k) != v
            },
            "active": working["active"],
            "counters": {counter: count + 1},
            "route": "architecture_review",
        }

    def architecture_review(self, state):
        update = self.review(state, "architecture", "architecture_reviewer")
        working = self.apply(state, update)
        complete = working["reviews"][state["active"]["architecture"]]["complete"]
        if complete and not prohibited_findings(working, "architecture"):
            return {
                **update,
                "route": "architecture_approval",
                "workflow_status": "WAITING_FOR_HUMAN",
            }
        if state["counters"]["architecture_review"] >= self.policy.max_review_cycles:
            return {
                **update,
                "route": "safe_stop",
                "workflow_status": "SAFE_STOP",
                "safe_stop_reason": "Architecture review cycle budget exhausted",
                "recovery_node": "architecture",
            }
        return {**update, "route": "architecture"}

    def architecture_approval(self, state):
        approved(state, "requirement")
        reviewed(state, "architecture")
        keys = ["architecture"] + [
            a["adr_id"] for a in active_artifact(state, "architecture")["content"]["adrs"]
        ]
        decision = HumanDecision.model_validate(
            interrupt(
                {
                    "gate": "architecture",
                    "artifact_ref": state["active"]["architecture"],
                    "architecture": active_artifact(state, "architecture"),
                    "adrs": [active_artifact(state, k) for k in keys[1:]],
                    "findings": list(state["findings"].values()),
                    "actions": ["approve", "reject", "revise"],
                }
            )
        )
        if decision.action == "revise":
            return {
                "route": "architecture",
                "feedback": decision.model_dump(),
                "counters": {"architecture_review": 0},
            }
        if decision.action != "approve":
            return self.rejection(state, decision, "architecture")
        return {
            **self.approve(state, decision, keys),
            "route": "brownfield" if state["scenario_type"] == "brownfield" else "planning",
            "workflow_status": "RUNNING",
        }

    def brownfield(self, state):
        baseline(state)
        snapshot = codebase_snapshot(Path(state["workspace"]) / "source")
        if not snapshot:
            raise ValueError("Brownfield requires source files in the run's source directory")
        update = self.artifact(state, "snapshot", "snapshot", {"files": snapshot}, [])
        working = self.apply(state, update)
        context = self.context(state)
        context["repository"] = snapshot
        impact = self.call(state, "brownfield_analysis", context)
        result = self.artifact(
            working,
            "impact",
            "impact",
            impact.model_dump(mode="json"),
            [
                working["active"]["snapshot"],
                state["active"]["requirement"],
                state["active"]["architecture"],
            ],
        )
        return {
            "artifacts": {**update["artifacts"], **result["artifacts"]},
            "active": {**update["active"], **result["active"]},
            "route": "planning",
        }

    def planning(self, state):
        context = self.context(state)
        context["feedback"] = state.get("feedback", {})
        if state["scenario_type"] == "brownfield":
            context["impact"] = active_artifact(state, "impact")
        result = self.call(state, "planning", context)
        req = context["requirement"]["content"]
        requirements = set(req["functional_requirements"]) | set(req["non_functional_requirements"])
        criteria = {criterion["id"] for criterion in req["acceptance_criteria"]}

        def invalid_references(plan):
            errors = []
            for item in plan.slices:
                invalid_requirements = set(item.requirement_refs) - requirements
                invalid_criteria = set(item.acceptance_criteria) - criteria
                if invalid_requirements or invalid_criteria:
                    errors.append(
                        f"{item.id}: invalid requirement_refs={sorted(invalid_requirements)}, "
                        f"invalid acceptance_criteria={sorted(invalid_criteria)}"
                    )
            return errors

        def missing_controls(plan):
            errors = []
            for item in plan.slices:
                missing_reviews = {"code", "tests"} - set(item.required_reviews)
                missing_validation = {"lint", "static", "test", "build"} - set(
                    item.deterministic_validation
                )
                if missing_reviews or missing_validation:
                    errors.append(
                        f"{item.id}: missing required_reviews={sorted(missing_reviews)}, "
                        f"missing deterministic_validation={sorted(missing_validation)}"
                    )
            return errors

        feedback = []
        if result.proposed_scope_changes:
            feedback.append(
                "Correct proposed_scope_changes: include only actual scope additions or removals. "
                "Do not include status statements such as 'No scope changes proposed'; return an "
                f"empty list when preserving approved scope. Current entries: {result.proposed_scope_changes}"
            )
        reference_errors = invalid_references(result)
        if reference_errors:
            feedback.append(
                "Correct slice references. requirement_refs must be exact approved functional or "
                "non-functional requirement IDs only; acceptance_criteria must be exact approved "
                f"AC IDs only. Requirement IDs: {sorted(requirements)}. AC IDs: {sorted(criteria)}. "
                f"Invalid references: {reference_errors}"
            )
        control_errors = missing_controls(result)
        if control_errors:
            feedback.append(
                "Correct required policy markers for every slice. required_reviews must include "
                "the exact labels ['code', 'tests']; deterministic_validation must include the "
                "exact labels ['build', 'lint', 'static', 'test']. Descriptive review names and "
                f"commands do not replace these labels. Missing markers: {control_errors}"
            )
        if feedback:
            context["validation_feedback"] = " ".join(feedback)
            result = self.call(state, "planning", context)
        if result.proposed_scope_changes:
            return {
                "route": "safe_stop",
                "workflow_status": "SAFE_STOP",
                "safe_stop_reason": "Planning proposed a scope change: "
                + "; ".join(result.proposed_scope_changes),
                "recovery_node": "planning",
                "feedback": result.model_dump(),
            }
        reference_errors = invalid_references(result)
        if reference_errors:
            raise ValueError("Plan uses unapproved identifiers: " + "; ".join(reference_errors))
        control_errors = missing_controls(result)
        if control_errors:
            raise ValueError(
                "Plan omits required review/validation markers: " + "; ".join(control_errors)
            )
        covered, seen = set(), set()
        for item in result.slices:
            if item.id in seen or set(item.depends_on) - seen:
                raise ValueError("Plan must be a topologically ordered DAG with unique slice IDs")
            safe_path(Path(state["workspace"]), item.id)
            if set(item.acceptance_criteria) - criteria or set(item.requirement_refs) - (
                req["functional_requirements"].keys() | req["non_functional_requirements"].keys()
            ):
                raise ValueError("Plan introduced unapproved scope")
            if not {"code", "tests"}.issubset(item.required_reviews) or not {
                "lint",
                "static",
                "test",
                "build",
            }.issubset(item.deterministic_validation):
                raise ValueError("Plan omits required review/validation")
            covered.update(item.acceptance_criteria)
            seen.add(item.id)
        if criteria - covered:
            raise ValueError("Plan omits acceptance criteria")
        deps = [state["active"]["requirement"], state["active"]["architecture"]] + [
            state["active"][a["adr_id"]] for a in context["architecture"]["content"]["adrs"]
        ]
        if "impact" in context:
            deps.append(state["active"]["impact"])
        return {
            **self.artifact(state, "plan", "plan", result.model_dump(mode="json"), deps),
            "current_slice": result.slices[0].id,
            "completed_slices": [],
            "route": "plan_approval",
            "workflow_status": "WAITING_FOR_HUMAN",
        }

    def plan_approval(self, state):
        approved(state, "requirement")
        reviewed(state, "architecture")
        artifact = active_artifact(state, "plan")
        decision = HumanDecision.model_validate(
            interrupt(
                {
                    "gate": "plan",
                    "artifact_ref": state["active"]["plan"],
                    "plan": artifact,
                    "actions": ["approve", "revise", "reject"],
                }
            )
        )
        if decision.action == "revise":
            self.event(
                state,
                "human_response_received",
                "plan",
                decision.rationale,
                [state["active"]["plan"]],
                actor_type="human",
                actor_id=decision.actor,
            )
            return {
                "feedback": decision.model_dump(),
                "route": "planning",
                "workflow_status": "RUNNING",
            }
        if decision.action != "approve":
            return self.rejection(state, decision, "plan")
        return {
            **self.approve(state, decision, ["plan"]),
            "route": "lld",
            "workflow_status": "RUNNING",
        }

    def lld(self, state):
        approved(state, "plan")
        context = self.context(state)
        item = context["slice"]
        deps = [state["active"]["plan"]]
        for dependency in item["depends_on"]:
            if dependency not in state["completed_slices"]:
                raise ValueError("Slice dependency has not passed acceptance")
            deps.append(state["active"][f"acceptance:{dependency}"])

        def validate_lld(result):
            problems = []
            if result.slice_id != item["id"]:
                problems.append(f"slice_id must be exactly {item['id']!r}.")
            for field, expected in (
                ("acceptance_criteria", item["acceptance_criteria"]),
                ("requirement_refs", item["requirement_refs"]),
                ("adr_refs", [adr["id"] for adr in context["adrs"]]),
            ):
                actual = getattr(result, field)
                if set(actual) != set(expected) or len(actual) != len(set(actual)):
                    problems.append(
                        f"{field} must contain exactly these IDs, once each: {sorted(expected)}. "
                        "Use IDs only; descriptions, extensions and deferral notes belong in sections."
                    )
            missing = DESIGN_SECTIONS - result.sections.keys()
            empty = [key for key, value in result.sections.items() if not value.strip()]
            if missing or empty:
                problems.append(
                    f"Missing sections: {sorted(missing)}. Empty sections: {sorted(empty)}. "
                    "Include every required section with meaningful text."
                )
            if problems:
                raise ValueError("LLD contract invalid. " + " ".join(problems))

        result = self.call(
            state,
            "lld",
            {**context, "feedback": state.get("feedback", {})},
            validator=validate_lld,
        )
        return {
            **self.artifact(
                state, f"lld:{item['id']}", "lld", result.model_dump(mode="json"), deps
            ),
            "route": "fork",
        }

    def branch_generate(self, state, kind):
        key = f"{kind}:{state['current_slice']}"
        # Targeted re-planning can reuse the unaffected, reviewed sibling.
        try:
            reviewed(state, key)
            return {"route": "done"}
        except ValueError:
            pass
        count = state["counters"].get(f"review:{key}", 0)
        if count >= self.policy.max_review_cycles:
            raise ValueError(f"{key} review cycle budget exhausted")
        context = self.context(state, design=True, include_code=kind == "code")
        context["previous_findings"] = [
            f for f in state["findings"].values() if f["artifact_id"] == key
        ]
        context["feedback"] = state.get("feedback", {})
        if key in state["active"]:
            context["previous_artifact"] = state["artifacts"][state["active"][key]]
        result = self.call(state, "coding" if kind == "code" else "test_design", context)
        if result.deviations:
            raise ValueError(
                "Implementation/design deviation requires upstream approval: "
                + "; ".join(result.deviations)
            )
        for name in result.files:
            safe_path(Path(state["workspace"]), name)
            is_test = (
                name.startswith("tests/")
                or Path(name).name.startswith("test_")
                or name.endswith("_test.go")
            )
            if kind == "tests" and not is_test:
                raise ValueError("Test design attempted to change a non-test file")
            if kind == "code" and is_test:
                raise ValueError("Coding agent attempted to author acceptance tests")
        if kind == "tests":
            criteria = context["slice"]["acceptance_criteria"]
            if set(criteria) != set(result.criterion_tests):
                raise ValueError("Test traceability is incomplete")
            for tests in result.criterion_tests.values():
                if not tests or any(t.split("::")[0] not in result.files for t in tests):
                    raise ValueError("Traceability references absent test files")
        deps = [state["active"][f"lld:{state['current_slice']}"]]
        if kind == "code":
            deps += [state["active"][f"code:{s}"] for s in state["completed_slices"]]
        update = self.artifact(state, key, kind, result.model_dump(mode="json"), deps)
        return {**update, "counters": {f"review:{key}": count + 1}, "route": "review"}

    def branch_review(self, state, kind):
        key = f"{kind}:{state['current_slice']}"
        update = self.review(state, key, "code_reviewer" if kind == "code" else "test_reviewer")
        working = self.apply(state, update)
        try:
            reviewed(working, key)
            return {**update, "route": "done"}
        except ValueError:
            if state["counters"][f"review:{key}"] >= self.policy.max_review_cycles:
                return {
                    **update,
                    "route": "done",
                    "branch_errors": {kind: f"{key} review budget exhausted"},
                }
            # Prevent reusing this version in branch_generate.
            return {**update, "route": "generate"}

    def synchronize(self, state):
        errors = [v for v in state.get("branch_errors", {}).values() if v]
        if errors:
            raise ValueError("; ".join(errors))
        baseline(state)
        for kind in ("code", "tests"):
            reviewed(state, f"{kind}:{state['current_slice']}")
        self.event(
            state,
            "branches_synchronized",
            "synchronize",
            "Both independently reviewed branches completed",
            [state["active"][f"{kind}:{state['current_slice']}"] for kind in ("code", "tests")],
        )
        return {"route": "validate"}

    def validate(self, state):
        files, refs = self.files(state)
        root = self.executor.materialize(files, digest(files)[:24])
        results = [self.executor.run(tool, root, refs) for tool in ("lint", "static", "test")]
        update = self.artifact(
            state,
            f"validation:{state['current_slice']}",
            "validation",
            {"results": [r.model_dump() for r in results], "candidate": str(root)},
            refs,
        )
        self.tool_events(state, results)
        return {
            **update,
            "tool_results": {r.id: r.model_dump() for r in results},
            "route": "acceptance"
            if all(r.exit_status == 0 for r in results)
            else "failure_analysis",
        }

    def tool_events(self, state, results):
        for result in results:
            self.event(
                state, "tool_executed", result.tool, result.model_dump_json(), result.artifact_refs
            )
            if result.tool in {"test", "build"}:
                self.event(
                    state,
                    f"{result.tool}_{'passed' if result.exit_status == 0 else 'failed'}",
                    result.tool,
                    result.id,
                    result.artifact_refs,
                )

    def acceptance(self, state):
        sid = state["current_slice"]
        self.synchronize(state)
        evidence = active_artifact(state, f"validation:{sid}")
        if any(r["exit_status"] != 0 for r in evidence["content"]["results"]):
            raise ValueError("Feature has failed deterministic validation")
        root = Path(evidence["content"]["candidate"])
        if tree_digest(root) != evidence["content"]["results"][0]["workspace_digest"]:
            raise ValueError("Candidate changed after validation")
        # Python profile verifies that claimed acceptance tests actually ran and passed.
        # Custom language profiles must supply the same JUnit evidence contract.
        report = ET.parse(root / ".results.xml")
        passed = {
            junit_test_id(case, root)
            for case in report.iter("testcase")
            if not any(child.tag in {"failure", "error", "skipped"} for child in case)
        }
        tests = active_artifact(state, f"tests:{sid}")["content"]
        claimed = {test for values in tests["criterion_tests"].values() for test in values}
        if not claimed or not claimed.issubset(passed):
            raise ValueError(
                f"Acceptance tests missing, skipped or failed: {sorted(claimed - passed)}"
            )
        update = self.artifact(
            state,
            f"acceptance:{sid}",
            "acceptance",
            {"criteria": tests["criterion_tests"], "passed_tests": sorted(passed)},
            [state["active"][f"validation:{sid}"]],
        )
        done = list(dict.fromkeys([*state["completed_slices"], sid]))
        remaining = [
            s for s in active_artifact(state, "plan")["content"]["slices"] if s["id"] not in done
        ]
        return {
            **update,
            "completed_slices": done,
            "current_slice": remaining[0]["id"] if remaining else sid,
            "route": "lld" if remaining else "documentation",
        }

    def failure_analysis(self, state):
        count = state["counters"].get("replans", 0)
        if count >= self.policy.max_replans:
            raise ValueError("Re-plan budget exhausted")
        result = self.call(
            state,
            "failure_analysis",
            {
                "tool_results": state["tool_results"],
                "active_artifacts": {k: state["artifacts"][v] for k, v in state["active"].items()},
                "attempt": count,
            },
        )
        routes = {
            "IMPLEMENTATION_DEFECT": (f"code:{state['current_slice']}", "fork"),
            "TEST_DEFECT": (f"tests:{state['current_slice']}", "fork"),
            "LLD_DEFECT": (f"lld:{state['current_slice']}", "lld"),
            "ARCHITECTURE_DEFECT": ("architecture", "architecture"),
            "REQUIREMENT_DEFECT": ("requirement", "requirement"),
        }
        self.event(state, "replan_triggered", "failure_analysis", result.model_dump_json())
        if result.category not in routes:
            return {
                "route": "safe_stop",
                "workflow_status": "SAFE_STOP",
                "safe_stop_reason": result.reasoning,
                "recovery_node": "validate",
                "counters": {"replans": count + 1},
                "feedback": result.model_dump(),
            }
        key, route = routes[result.category]
        ref = state["active"][key]
        changes = invalidate(state["artifacts"], {ref})
        changes[ref] = {**state["artifacts"][ref], "validity": "INVALIDATED"}
        self.persist_changes(state, changes)
        for changed in changes:
            self.event(
                state, "artifact_invalidated", "failure_analysis", result.category, [changed]
            )
        counters = {"replans": count + 1}
        for kind in ("code", "tests"):
            if state["active"].get(f"{kind}:{state['current_slice']}") in changes:
                counters[f"review:{kind}:{state['current_slice']}"] = 0
        if route in {"architecture", "requirement"}:
            counters["architecture_review"] = 0
        completed = [
            s
            for s in state["completed_slices"]
            if state["active"].get(f"acceptance:{s}") not in changes
        ]
        return {
            "artifacts": changes,
            "counters": counters,
            "route": route,
            "feedback": result.model_dump(),
            "completed_slices": completed,
            "branch_errors": {"code": "", "tests": ""},
        }

    def documentation(self, state):
        result = self.call(
            state,
            "documentation",
            {
                **self.context(state),
                "files": self.files(state)[0],
                "tool_results": state["tool_results"],
            },
        )
        required = {
            "setup",
            "api",
            "configuration",
            "architecture",
            "adrs",
            "tests",
            "operations",
            "release_notes",
            "rollback",
            "limitations",
            "tradeoffs",
        }
        if required - result.sections.keys():
            raise ValueError("Documentation incomplete")
        deps = [state["active"][f"acceptance:{s}"] for s in state["completed_slices"]]
        return {
            **self.artifact(state, "documentation", "documentation", result.model_dump(), deps),
            "route": "release_readiness",
        }

    def release_readiness(self, state):
        result = self.call(
            state,
            "release_readiness",
            {
                "documentation": active_artifact(state, "documentation"),
                "tool_results": state["tool_results"],
                "findings": state["findings"],
                "files": self.files(state)[0],
            },
        )
        if {"rollback", "deployment", "limitations", "packaging"} - result.sections.keys():
            raise ValueError("Release report lacks operational instructions")
        return {
            **self.artifact(
                state,
                "release_report",
                "release_report",
                result.model_dump(),
                [state["active"]["documentation"]],
            ),
            "route": "build",
        }

    def build(self, state):
        files, refs = self.files(state)
        root = self.executor.materialize(files, digest(files)[:24])
        result = self.executor.run("build", root, refs)
        self.tool_events(state, [result])
        update = self.artifact(state, "build", "build", result.model_dump(), refs)
        return {
            **update,
            "tool_results": {result.id: result.model_dump()},
            "route": "release_gate" if result.exit_status == 0 else "failure_analysis",
        }

    def release_gate(self, state):
        release_gate(state)
        files, refs = self.files(state)
        build = active_artifact(state, "build")["content"]
        if tree_digest(Path(build["cwd"])) != build["workspace_digest"] or set(
            build["artifact_refs"]
        ) != set(refs):
            raise ValueError("Build evidence is stale")
        deps = [state["active"][key] for key in ("build", "documentation", "release_report")]
        update = self.artifact(
            state,
            "release",
            "release",
            {
                "summary": "Deterministic gates passed; human sign-off pending",
                "candidate": build["cwd"],
                "file_digest": digest(files),
            },
            deps,
        )
        self.event(
            state, "release_gate_passed", "release_gate", "All deterministic gates passed", deps
        )
        return {**update, "route": "release_approval", "workflow_status": "WAITING_FOR_HUMAN"}

    def release_approval(self, state):
        release_gate(state)
        decision = HumanDecision.model_validate(
            interrupt(
                {
                    "gate": "release",
                    "artifact_ref": state["active"]["release"],
                    "release": active_artifact(state, "release"),
                    "report": active_artifact(state, "release_report"),
                    "findings": list(state["findings"].values()),
                    "build": active_artifact(state, "build"),
                    "actions": ["approve", "reject"],
                    "notice": "Approval marks readiness only. No deployment will occur.",
                }
            )
        )
        if decision.action != "approve":
            return self.rejection(state, decision, "release")
        build = active_artifact(state, "build")["content"]
        if tree_digest(Path(build["cwd"])) != build["workspace_digest"]:
            raise ValueError("Candidate changed while waiting for approval")
        update = self.approve(state, decision, ["release"])
        self.event(
            state,
            "workflow_success",
            "release",
            "READY_FOR_DEPLOYMENT",
            [state["active"]["release"]],
        )
        return {
            **update,
            "route": "end",
            "workflow_status": "READY_FOR_DEPLOYMENT",
            "updated_at": now(),
        }

    def safe_stop(self, state):
        self.event(state, "safe_stop", "safe_stop", state.get("safe_stop_reason", "Policy stop"))
        actions = ["retry", "rollback", "accept_risk", "abort"]
        planning_scope_stop = state.get("safe_stop_reason", "").startswith(
            "Planning proposed a scope change:"
        )
        branch_failure = any(state.get("branch_errors", {}).values())
        if state.get("recovery_node") == "planning" or planning_scope_stop or branch_failure:
            actions.insert(1, "revise")
        decision = HumanDecision.model_validate(
            interrupt(
                {
                    "gate": "safe_stop",
                    "reason": state.get("safe_stop_reason"),
                    "findings": list(state["findings"].values()),
                    "recovery_node": state.get("recovery_node"),
                    "actions": actions,
                    "options": "Inspect evidence, correct the provider/tool configuration, explicitly renew a bounded budget, or abort.",
                }
            )
        )
        self.event(
            state,
            "human_response_received",
            "safe_stop",
            decision.model_dump_json(),
            actor_type="human",
            actor_id=decision.actor,
        )
        if decision.action == "abort":
            self.event(state, "workflow_failure", "safe_stop", decision.rationale)
            return {"route": "end", "workflow_status": "ABORTED", "updated_at": now()}
        if decision.action == "rollback":
            return self.rollback(state, decision)
        findings = {}
        if decision.action == "accept_risk":
            for fid in decision.finding_ids:
                finding = state["findings"][fid]
                if finding["severity"] == "BLOCKER":
                    raise ValueError("BLOCKER risks cannot be accepted")
                findings[fid] = {
                    **finding,
                    "status": "ACCEPTED_RISK",
                    "resolution_reason": decision.rationale,
                    "updated_at": now(),
                }
                self.event(
                    state,
                    "risk_accepted",
                    "safe_stop",
                    decision.rationale,
                    actor_type="human",
                    actor_id=decision.actor,
                    related_review_ids=[fid],
                )
        route = state.get("recovery_node", "requirement")
        feedback = state.get("feedback", {})
        if decision.action == "retry" and route != "planning":
            plan_ref = state.get("active", {}).get("plan")
            plan = state.get("artifacts", {}).get(plan_ref, {}) if plan_ref else {}
            if plan.get("validity") == "VALID" and plan.get("approval_status") == "DRAFT":
                route = "plan_approval"
        if decision.action == "revise":
            if route != "planning" and planning_scope_stop:
                route = "planning"
            if route != "planning" and branch_failure:
                route = "fork"
            if route not in {"planning", "fork"}:
                raise ValueError("Revision feedback is not supported for this safe stop")
            feedback = decision.model_dump()
        if decision.action == "accept_risk" and route == "architecture":
            working = self.apply(state, {"findings": findings})
            reviewed(working, "architecture")
            route = "architecture_approval"
        if route in {"synchronize", "branch_generate", "branch_review"}:
            route = "fork"
        counters = {k: 0 for k in state["counters"]}
        self.event(
            state,
            "budget_renewed",
            "safe_stop",
            decision.rationale,
            actor_type="human",
            actor_id=decision.actor,
        )
        return {
            "findings": findings,
            "counters": counters,
            "branch_errors": {"code": "", "tests": ""},
            "workflow_status": "RUNNING",
            "safe_stop_reason": "",
            "feedback": feedback,
            "route": route,
        }

    def rollback(self, state, decision):
        target = state["artifacts"].get(decision.target_ref)
        if (
            not target
            or target["kind"] not in {"requirement", "architecture"}
            or target["approval_status"] != "APPROVED"
        ):
            raise ValueError("Rollback requires a previously approved requirement or architecture")
        for ref in target["dependencies"]:
            if (
                state["artifacts"][ref]["validity"] != "VALID"
                or state["active"].get(state["artifacts"][ref]["id"]) != ref
            ):
                raise ValueError("Rollback target has stale dependencies")
        current = state["active"][target["id"]]
        changes = invalidate(state["artifacts"], {current, decision.target_ref})
        changes[current] = {**state["artifacts"][current], "validity": "SUPERSEDED"}
        changes[decision.target_ref] = {**target, "validity": "VALID"}
        self.persist_changes(state, changes)
        self.event(
            state,
            "rollback",
            "safe_stop",
            decision.rationale,
            [current, decision.target_ref],
            actor_type="human",
            actor_id=decision.actor,
        )
        # Architecture rollback reauthors the ADR package and requests fresh approval.
        return {
            "artifacts": changes,
            "active": {target["id"]: decision.target_ref},
            "route": "architecture",
            "workflow_status": "RUNNING",
            "completed_slices": [],
            "counters": {k: 0 for k in state["counters"]},
            "answers": target["content"].get("decisions", state.get("answers", {})),
            "feedback": {"rollback": decision.target_ref},
        }
