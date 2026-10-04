"""Durable single-writer workflow service used by CLI and tests."""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from ssdlc.graph import build_graph
from ssdlc.mock import MockProvider
from ssdlc.models import HumanDecision, now, uid
from ssdlc.nodes import Nodes
from ssdlc.persistence import Repository
from ssdlc.policy import Policy
from ssdlc.tools import Executor, codebase_snapshot, reject_secrets


class Runtime:
    def __init__(self, home: Path, provider=None, policy=None, allow_execution=False):
        self.home = home.resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.repo = Repository(self.home / "audit.sqlite", artifact_root=self.home / "runs")
        self.checkpoint_connection = sqlite3.connect(
            self.home / "checkpoints.sqlite", check_same_thread=False
        )
        self.checkpointer = SqliteSaver(self.checkpoint_connection)
        self.provider = provider or MockProvider()
        reject_secrets(self.provider.name)
        self.policy = policy or Policy()
        self.allow_execution = allow_execution

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.repo.close()
        self.checkpoint_connection.close()

    def config(self, run):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run):
            raise ValueError("Run ID must contain only letters, digits, hyphens and underscores")
        return {"configurable": {"thread_id": run}, "recursion_limit": 300}

    def graph(self, run):
        self.config(run)
        executor = Executor(
            self.home / "runs" / run,
            self.policy.command_timeout,
            self.allow_execution,
        )
        nodes = Nodes(self.repo, self.provider, self.policy, executor)
        return build_graph(nodes, self.checkpointer), nodes

    def start(
        self, text: str, run: str | None = None, scenario="greenfield", source: Path | None = None
    ):
        reject_secrets(text)
        if not text.strip():
            raise ValueError("Requirement cannot be empty")
        if scenario not in {"greenfield", "brownfield", "ambiguous"}:
            raise ValueError("Unknown scenario")
        run = run or uid()
        graph, nodes = self.graph(run)
        owner = uid()
        self.repo.acquire(run, owner)
        try:
            if graph.get_state(self.config(run)).values:
                raise ValueError("Run already exists; resume it or choose a new ID")
            workspace = self.home / "runs" / run
            workspace.mkdir(parents=True, exist_ok=True)
            if scenario == "brownfield":
                if source is None:
                    raise ValueError("Brownfield requires a source directory")
                from ssdlc.tools import safe_path

                for name, content in codebase_snapshot(source.resolve()).items():
                    path = safe_path(workspace / "source", name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
            state = dict(
                workflow_run_id=run,
                project_id=run,
                scenario_type=scenario,
                workflow_status="RUNNING",
                original_text=text,
                workspace=str(workspace),
                provider_id=self.provider.name,
                artifacts={},
                active={},
                findings={},
                approvals={},
                tool_results={},
                reviews={},
                counters={},
                branch_errors={},
                current_slice="",
                completed_slices=[],
                answers={},
                feedback={},
                route="requirement",
                safe_stop_reason="",
                recovery_node="requirement",
                created_at=now(),
                updated_at=now(),
            )
            nodes.event(state, "workflow_created", "start", scenario)
            graph.invoke(state, self.config(run))
            return self.inspect(run)
        finally:
            self.repo.release(run, owner)

    def resume(self, run, decision: dict):
        parsed = HumanDecision.model_validate(decision)
        reject_secrets(parsed.model_dump_json())
        graph, nodes = self.graph(run)
        owner = uid()
        self.repo.acquire(run, owner)
        try:
            snapshot = graph.get_state(self.config(run))
            if not snapshot.values:
                raise ValueError("Unknown run")
            pending = [i for task in snapshot.tasks for i in task.interrupts]
            if len(pending) != 1:
                raise ValueError("Expected one pending human gate")
            gate = pending[0].value
            allowed_actions = list(gate["actions"])
            planning_scope_stop = gate.get("reason", "").startswith(
                "Planning proposed a scope change:"
            )
            branch_failure = any(snapshot.values.get("branch_errors", {}).values())
            if gate.get("gate") == "safe_stop" and (
                gate.get("recovery_node") in {"planning_design", "planning", "lld"}
                or planning_scope_stop
                or branch_failure
            ):
                allowed_actions.append("revise")
            if parsed.action not in allowed_actions:
                raise ValueError("Decision is not permitted at this gate")
            if gate.get("artifact_ref") and parsed.artifact_ref != gate["artifact_ref"]:
                raise ValueError("Decision requires exact current artifact_ref")
            if gate["gate"] == "requirement":
                req = gate["artifact"]["content"]
                question_ids = {q["id"] for q in req["open_questions"]}
                if set(parsed.answers) - question_ids or any(
                    not answer.strip() for answer in parsed.answers.values()
                ):
                    raise ValueError("Answers must target known questions and be non-empty")
                if parsed.action == "approve" and (
                    parsed.answers
                    or any(
                        (
                            q["human_confirmation_required"]
                            or q["classification"] == "BLOCKING_AMBIGUITY"
                        )
                        and not req["decisions"].get(q["id"])
                        for q in req["open_questions"]
                    )
                ):
                    raise ValueError(
                        "Clarify open questions, then approve the resulting version separately"
                    )
            if parsed.action == "accept_risk":
                if not parsed.finding_ids or any(
                    fid not in snapshot.values["findings"]
                    or snapshot.values["findings"][fid]["severity"] == "BLOCKER"
                    or snapshot.values["findings"][fid]["status"] in {"RESOLVED", "ACCEPTED_RISK"}
                    for fid in parsed.finding_ids
                ):
                    raise ValueError("Select existing unresolved non-BLOCKER findings")
            if (
                parsed.action == "rollback"
                and parsed.target_ref not in snapshot.values["artifacts"]
            ):
                raise ValueError("Unknown rollback target")
            if snapshot.values["provider_id"] != self.provider.name:
                raise ValueError("Resume requires the original provider identity")
            nodes.event(
                snapshot.values,
                "human_gate_resumed",
                gate["gate"],
                parsed.model_dump_json(),
                actor_type="human",
                actor_id=parsed.actor,
            )
            graph.invoke(Command(resume=parsed.model_dump()), self.config(run))
            return self.inspect(run)
        finally:
            self.repo.release(run, owner)

    def inspect(self, run):
        graph, _ = self.graph(run)
        snapshot = graph.get_state(self.config(run))
        if not snapshot.values:
            raise ValueError("Unknown run")
        for ref, indexed in snapshot.values.get("artifacts", {}).items():
            persisted = self.repo.artifact(run, ref)
            if persisted["digest"] != indexed["digest"]:
                raise ValueError(f"Artifact index and workspace disagree: {ref}")
        return {
            "state": snapshot.values,
            "interrupts": [i.value for task in snapshot.tasks for i in task.interrupts],
            "next": list(snapshot.next),
        }

    def export(self, run, destination: Path):
        data = self.inspect(run)
        data["audit"] = self.repo.events(run)
        data["audit_chain_valid"] = self.repo.verify_audit(run)
        data["metrics"] = self.metrics(run)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return destination

    def package(self, run, destination: Path | None = None):
        from ssdlc.packaging import create_bundle

        _, nodes = self.graph(run)
        owner = uid()
        self.repo.acquire(run, owner)
        try:
            evidence = self.inspect(run)
            state = evidence["state"]
            evidence["audit"] = self.repo.events(run)
            evidence["audit_chain_valid"] = self.repo.verify_audit(run)
            evidence["metrics"] = self.metrics(run)
            version = state["artifacts"].get(state["active"].get("release"), {}).get("version", 1)
            destination = destination or self.home / "deliverables" / run / f"release-v{version}"
            return create_bundle(state, nodes, evidence, destination)
        finally:
            self.repo.release(run, owner)

    def metrics(self, run):
        events = self.repo.events(run)
        counts = {
            name: 0
            for name in (
                "workflow_runs_total",
                "workflow_success_total",
                "workflow_failure_total",
                "agent_failure_count",
                "retry_count",
                "rollback_count",
                "replan_count",
                "safe_stop_count",
                "review_cycle_count",
                "test_pass_count",
                "test_fail_count",
                "build_pass_count",
                "build_fail_count",
            )
        }
        mapping = {
            "workflow_created": "workflow_runs_total",
            "workflow_success": "workflow_success_total",
            "workflow_failure": "workflow_failure_total",
            "agent_failure": "agent_failure_count",
            "retry_attempted": "retry_count",
            "rollback": "rollback_count",
            "replan_triggered": "replan_count",
            "safe_stop": "safe_stop_count",
            "review_completed": "review_cycle_count",
            "test_passed": "test_pass_count",
            "test_failed": "test_fail_count",
            "build_passed": "build_pass_count",
            "build_failed": "build_fail_count",
        }
        durations, agent_durations = {}, {}
        wait = 0.0
        last = None
        for event in events:
            if event["action"] in mapping:
                counts[mapping[event["action"]]] += 1
            if event["action"] in {"stage_completed", "agent_completed"}:
                target = durations if event["action"] == "stage_completed" else agent_durations
                target.setdefault(event["stage"], []).append(
                    json.loads(event["rationale"])["duration"]
                )
            if event["action"] in {
                "human_question_raised",
                "requirement_ready_for_approval",
                "safe_stop",
                "release_gate_passed",
            } or (event["action"] == "stage_completed" and event["stage"] == "architecture_review"):
                last = datetime.fromisoformat(event["timestamp"])
            if event["action"] == "human_gate_resumed" and last:
                wait += (datetime.fromisoformat(event["timestamp"]) - last).total_seconds()
                last = None
        findings = self.inspect(run)["state"]["findings"]
        severities = {
            level: sum(f["severity"] == level for f in findings.values())
            for level in ("BLOCKER", "HIGH", "MEDIUM", "LOW")
        }
        terminal = next(
            (
                e
                for e in reversed(events)
                if e["action"] in {"workflow_success", "workflow_failure"}
            ),
            None,
        )
        elapsed = (
            (
                datetime.fromisoformat(terminal["timestamp"] if terminal else now())
                - datetime.fromisoformat(events[0]["timestamp"])
            ).total_seconds()
            if events
            else 0
        )
        return {
            **counts,
            "workflow_end_to_end_latency": elapsed,
            "stage_latency": durations,
            "agent_task_duration": agent_durations,
            "human_approval_wait_time": wait,
            "review_findings_by_severity": severities,
        }
