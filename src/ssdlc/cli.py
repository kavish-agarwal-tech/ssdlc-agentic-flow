"""Local operator CLI. Approval identity is asserted by the trusted local user."""

import argparse
import importlib
import json
import logging
import sys
from contextlib import contextmanager
from itertools import cycle
from pathlib import Path
from threading import Event, Lock, Thread

from ssdlc.config import load_env_file, provider_from_environment
from ssdlc.mock import MINIMAL_REQUIREMENT, MockProvider
from ssdlc.runtime import Runtime


class LLMProgressHandler(logging.Handler):
    def __init__(self, stream=None):
        super().__init__(logging.INFO)
        self.stream = stream or sys.stderr
        self.animated = getattr(self.stream, "isatty", lambda: False)()
        self.active = {}
        self._state_lock = Lock()
        self.closing = Event()
        self.frames = cycle("|/-\\")
        self.thread = None
        if self.animated:
            self.thread = Thread(target=self._animate, daemon=True)
            self.thread.start()

    def emit(self, record):
        try:
            event = json.loads(record.getMessage())
            action = event.get("action")
            role = event.get("stage", "agent")
            if action == "agent_started":
                self._start(event.get("rationale", ""), role)
            elif action == "agent_completed":
                details = json.loads(event.get("rationale", "{}"))
                self._complete(details.get("operation", ""), role)
            elif action == "retry_attempted":
                self._status(f"[retry] LLM response for {role} needs correction; retrying")
            elif action == "provider_fallback":
                self._status(f"[fallback] Switching provider for {role}")
            elif action == "agent_failure":
                self._status(f"[working] LLM attempt for {role} failed validation")
            elif action == "safe_stop":
                self._finish_all("LLM activity stopped")
        except (TypeError, ValueError, KeyError):
            self.handleError(record)

    def _start(self, operation, role):
        with self._state_lock:
            self.active[operation] = role
            if not self.animated:
                self.stream.write(f"[wait] LLM: {role} is working...\n")
                self.stream.flush()

    def _complete(self, operation, role):
        with self._state_lock:
            completed_role = self.active.pop(operation, role)
            if self.active:
                return
            if self.animated:
                self.stream.write("\r" + " " * 100 + "\r")
            self.stream.write(f"[done] LLM response received for {completed_role}\n")
            self.stream.flush()

    def _status(self, message):
        with self._state_lock:
            if not self.animated:
                self.stream.write(message + "\n")
                self.stream.flush()

    def _finish_all(self, message):
        with self._state_lock:
            if not self.active:
                return
            self.active.clear()
            if self.animated:
                self.stream.write("\r" + " " * 100 + "\r")
            self.stream.write(f"[stopped] {message}\n")
            self.stream.flush()

    def _animate(self):
        while not self.closing.wait(0.12):
            with self._state_lock:
                if self.active:
                    roles = ", ".join(dict.fromkeys(self.active.values()))
                    self.stream.write(f"\r[{next(self.frames)}] Waiting for LLM: {roles}...")
                    self.stream.flush()

    def close(self):
        self.closing.set()
        if self.thread:
            self.thread.join(timeout=1)
        super().close()


@contextmanager
def interactive_progress(enabled):
    if not enabled:
        yield
        return
    logger = logging.getLogger("ssdlc.audit")
    previous_level = logger.level
    handler = LLMProgressHandler()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)


def emit(result):
    print(json.dumps(result, indent=2, ensure_ascii=False))


def summary(result):
    return {
        "run": result["state"]["workflow_run_id"],
        "status": result["state"]["workflow_status"],
        "active_artifacts": result["state"]["active"],
        "interrupts": result["interrupts"],
    }


def unanswered_questions(gate):
    content = gate.get("artifact", {}).get("content", {})
    decisions = content.get("decisions", {})
    return [
        question
        for question in content.get("open_questions", [])
        if not decisions.get(question["id"], "").strip()
    ]


def available_actions(gate, artifact_refs=(), branch_errors=None):
    actions = list(gate["actions"])
    planning_scope_stop = gate.get("reason", "").startswith("Planning proposed a scope change:")
    if (
        gate.get("gate") == "safe_stop"
        and (
            gate.get("recovery_node") == "planning"
            or planning_scope_stop
            or any((branch_errors or {}).values())
        )
        and "revise" not in actions
    ):
        actions.insert(1, "revise")
    if gate["gate"] == "requirement" and "approve" in actions:
        pending = [
            question
            for question in unanswered_questions(gate)
            if question.get("human_confirmation_required", True)
            or question.get("classification") == "BLOCKING_AMBIGUITY"
        ]
        if pending:
            actions.remove("approve")
    if "accept_risk" in actions and not any(
        finding.get("severity") != "BLOCKER" for finding in gate.get("findings", [])
    ):
        actions.remove("accept_risk")
    if "rollback" in actions and not artifact_refs:
        actions.remove("rollback")
    return actions


def display_gate(gate, actions=None, output_fn=print):
    output_fn(f"\nHuman review required: {gate['gate']}")
    if gate.get("artifact_ref"):
        output_fn(f"Artifact: {gate['artifact_ref']}")
    if gate.get("reason"):
        output_fn(f"Reason: {gate['reason']}")
    if gate.get("notice"):
        output_fn(gate["notice"])
    details = {key: value for key, value in gate.items() if key not in {"actions", "gate"}}
    output_fn(json.dumps(details, indent=2, ensure_ascii=False))
    output_fn("Available actions: " + ", ".join(actions or gate["actions"]))


def prompt_decision(gate, artifact_refs=(), actions=None, input_fn=None, output_fn=print):
    input_fn = input if input_fn is None else input_fn
    actions = actions or available_actions(gate, artifact_refs)
    while True:
        action = input_fn("Action: ").strip().lower()
        if action in actions:
            break
        output_fn("Choose one of: " + ", ".join(actions))

    actor = input_fn("Your name [local-operator]: ").strip() or "local-operator"
    while True:
        rationale = input_fn("Rationale (required): ").strip()
        if rationale:
            break
        output_fn("Please provide a rationale.")

    decision = {
        "actor": actor,
        "action": action,
        "rationale": rationale,
        "artifact_ref": gate.get("artifact_ref"),
    }
    if action in {"clarify", "revise"}:
        questions = unanswered_questions(gate)
        answers = {}
        for question in questions:
            output_fn(f"\n{question['id']}: {question['unclear']}")
            options = question.get("options", [])
            for index, option in enumerate(options, 1):
                output_fn(f"  {index}. {option}")
            required = (
                question.get("human_confirmation_required", True)
                or question.get("classification") == "BLOCKING_AMBIGUITY"
            )
            prompt = "Answer (option number or text): " if required else "Answer (Enter to skip): "
            answer = input_fn(prompt).strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                answer = options[int(answer) - 1]
            while required and not answer:
                output_fn("An answer is required for this question.")
                answer = input_fn(prompt).strip()
                if answer.isdigit() and 1 <= int(answer) <= len(options):
                    answer = options[int(answer) - 1]
            if answer:
                answers[question["id"]] = answer
        if answers:
            decision["answers"] = answers
    if action == "rollback":
        choices = sorted(artifact_refs)
        if choices:
            output_fn("Rollback targets: " + ", ".join(choices))
        decision["target_ref"] = input_fn("Target artifact reference: ").strip()
    if action == "accept_risk":
        decision["finding_ids"] = [
            value.strip()
            for value in input_fn("Finding IDs to accept (comma-separated): ").split(",")
            if value.strip()
        ]
    return decision


def interactive_session(runtime, result, input_fn=None, output_fn=print):
    run = result["state"]["workflow_run_id"]
    try:
        while result["interrupts"]:
            gate = result["interrupts"][0]
            artifacts = result["state"].get("artifacts", {})
            rollback_refs = [
                ref
                for ref, artifact in artifacts.items()
                if artifact.get("kind") in {"requirement", "architecture"}
                and artifact.get("approval_status") == "APPROVED"
            ]
            actions = available_actions(
                gate, rollback_refs, result["state"].get("branch_errors", {})
            )
            display_gate(gate, actions=actions, output_fn=output_fn)
            decision = prompt_decision(
                gate,
                rollback_refs,
                actions=actions,
                input_fn=input_fn,
                output_fn=output_fn,
            )
            try:
                result = runtime.resume(run, decision)
            except ValueError as exc:
                output_fn(f"Decision not accepted: {exc}")
    except (EOFError, KeyboardInterrupt):
        output_fn("\nInput ended. The workflow remains paused and can be resumed later.")
    return result


def report_interactive_result(result):
    state = result["state"]
    print(f"\nRun {state['workflow_run_id']}: {state['workflow_status']}")
    if result["interrupts"]:
        gate = result["interrupts"][0]
        reference = gate.get("artifact_ref", "no artifact reference")
        print(f"Paused at {gate['gate']} gate ({reference}).")
    if state.get("safe_stop_reason"):
        print("Safe stop: " + state["safe_stop_reason"])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Governed agentic SSDLC; no autonomous production deployment"
    )
    parser.add_argument("--home", type=Path, default=Path(".ssdlc"))
    parser.add_argument(
        "--provider",
        help="ollama, deepseek, mock, or trusted module:factory; otherwise use environment configuration",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--verbose", action="store_true", help="Emit structured audit logs to stderr"
    )
    parser.add_argument(
        "--allow-local-execution",
        action="store_true",
        help="Execute generated code on this host; use a disposable environment for untrusted models",
    )
    parser.add_argument(
        "--tool-profile",
        type=Path,
        help="Operator-owned JSON commands: lint/static/test/build; never model-authored",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--requirement", required=True, type=Path)
    start.add_argument("--run")
    start.add_argument(
        "--interactive", action="store_true", help="Prompt for human decisions at workflow gates"
    )
    start.add_argument(
        "--scenario", choices=["greenfield", "brownfield", "ambiguous"], default="greenfield"
    )
    start.add_argument("--source", type=Path)
    resume = commands.add_parser("resume")
    resume.add_argument("run")
    resume_mode = resume.add_mutually_exclusive_group(required=True)
    resume_mode.add_argument("--decision", type=Path)
    resume_mode.add_argument(
        "--interactive", action="store_true", help="Prompt for human decisions and continue"
    )
    for name in ("inspect", "audit", "metrics"):
        command = commands.add_parser(name)
        command.add_argument("run")
    export = commands.add_parser("export")
    export.add_argument("run")
    export.add_argument("--output", required=True, type=Path)
    demo = commands.add_parser("demo")
    demo.add_argument("--run", default="minimal-demo")
    demo.add_argument(
        "--scripted",
        action="store_true",
        help="Use explicitly labeled synthetic human decisions for the fixture only",
    )
    args = parser.parse_args(argv)
    profile = (
        json.loads(args.tool_profile.read_text(encoding="utf-8")) if args.tool_profile else None
    )
    try:
        load_env_file(args.env_file)
        if args.verbose:
            logging.basicConfig(level=logging.INFO, format="%(message)s")
        if args.command == "demo":
            if args.provider and args.provider != "mock":
                raise ValueError("Fixture demo requires the mock provider")
            provider = MockProvider()
        elif args.provider == "mock" or args.command in {"inspect", "audit", "metrics", "export"}:
            provider = MockProvider()
        elif args.provider and ":" in args.provider:
            module, factory = args.provider.split(":", 1)
            provider = getattr(importlib.import_module(module), factory)()
        else:
            import os

            configuration = dict(os.environ)
            if args.provider:
                configuration["LLM_PROVIDER"] = args.provider
            provider = provider_from_environment(configuration)
        with Runtime(
            args.home,
            provider=provider,
            allow_execution=args.allow_local_execution,
            profile=profile,
        ) as runtime:
            if args.command == "start":
                with interactive_progress(args.interactive):
                    result = runtime.start(
                        args.requirement.read_text(encoding="utf-8"),
                        args.run,
                        args.scenario,
                        args.source,
                    )
                    if args.interactive:
                        report_interactive_result(interactive_session(runtime, result))
                    else:
                        emit(summary(result))
            elif args.command == "resume":
                if args.interactive:
                    with interactive_progress(True):
                        result = runtime.inspect(args.run)
                        result = interactive_session(runtime, result)
                        report_interactive_result(result)
                else:
                    emit(
                        summary(
                            runtime.resume(
                                args.run, json.loads(args.decision.read_text(encoding="utf-8"))
                            )
                        )
                    )
            elif args.command == "inspect":
                emit(runtime.inspect(args.run))
            elif args.command == "audit":
                emit(
                    {
                        "chain_valid": runtime.repo.verify_audit(args.run),
                        "events": runtime.repo.events(args.run),
                    }
                )
            elif args.command == "metrics":
                emit(runtime.metrics(args.run))
            elif args.command == "export":
                print(runtime.export(args.run, args.output))
            elif args.command == "demo":
                result = runtime.start(MINIMAL_REQUIREMENT, args.run)
                if args.scripted:
                    for _ in range(5):
                        if not result["interrupts"]:
                            break
                        gate = result["interrupts"][0]
                        if gate["gate"] == "safe_stop":
                            break
                        decision = {
                            "actor": "synthetic-demo-human",
                            "action": "approve",
                            "rationale": "SCRIPTED FIXTURE ONLY: synthetic human approval; not authorization for any real product",
                            "artifact_ref": gate["artifact_ref"],
                        }
                        if (
                            gate["gate"] == "requirement"
                            and not gate["artifact"]["content"]["decisions"]
                        ):
                            decision.update(
                                action="clarify", answers={"blank": "Reject with ValueError"}
                            )
                        result = runtime.resume(args.run, decision)
                emit(summary(result))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f"ssdlc: {exc}\n")


if __name__ == "__main__":
    main()
