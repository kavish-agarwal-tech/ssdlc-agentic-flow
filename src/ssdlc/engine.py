"""Application-owned state changes, provider boundary and artifact lineage."""

import json
import logging
import time

from langgraph.errors import GraphBubbleUp
from pydantic import ValidationError

from ssdlc.agents import CONTRACTS
from ssdlc.models import Artifact, AuditEvent, Finding, now
from ssdlc.persistence import Repository, digest, invalidate
from ssdlc.policy import Policy, approved, baseline
from ssdlc.providers import Provider, ProviderError
from ssdlc.state import Workflow, active_artifact
from ssdlc.tools import Executor, redact, reject_secrets


class Engine:
    def __init__(
        self, repository: Repository, provider: Provider, policy: Policy, executor: Executor
    ):
        self.repo, self.provider, self.policy, self.executor = (
            repository,
            provider,
            policy,
            executor,
        )

    def event(self, state, action, stage, rationale="", refs=None, **kwargs):
        identity = digest([state["workflow_run_id"], action, stage, rationale, refs, kwargs])
        event = AuditEvent(
            event_id=identity,
            workflow_id=state["workflow_run_id"],
            action=action,
            stage=stage,
            rationale=redact(rationale),
            artifact_refs=refs or [],
            correlation_id=state["workflow_run_id"],
            **kwargs,
        )
        self.repo.record(event)
        logging.getLogger("ssdlc.audit").info(event.model_dump_json())

    @staticmethod
    def validation_detail(exc):
        # ValidationError inherits ValueError; never stringify it with raw inputs.
        if isinstance(exc, ValidationError):
            return "ValidationError: " + json.dumps(
                [
                    {"field": list(e["loc"]), "error": e["type"]}
                    for e in exc.errors(include_input=False, include_context=False)
                ]
            )
        if isinstance(exc, (ProviderError, ValueError)):
            return type(exc).__name__ + ": " + redact(str(exc))
        return type(exc).__name__

    def call(self, state: Workflow, role: str, context: dict, validator=None):
        schema, instructions = CONTRACTS[role]
        reject_secrets(json.dumps(context))

        def validate(raw):
            reject_secrets(json.dumps(raw))
            result = schema.model_validate(raw)
            if role == "requirement":
                requirement_refs = set(result.functional_requirements) | set(
                    result.non_functional_requirements
                )
                if any(
                    criterion.requirement_ref not in requirement_refs
                    for criterion in result.acceptance_criteria
                ):
                    raise ValueError(
                        "Every acceptance criterion requirement_ref must match an exact functional or non-functional requirement ID."
                    )
            if validator is not None:
                validator(result)
            return result

        key = digest([self.provider.name, role, instructions, schema.model_json_schema(), context])
        cached = self.repo.cached(state["workflow_run_id"], key)
        initial_feedback = {}
        replace_cached = False
        if cached is not None:
            try:
                return validate(cached)
            except (ValidationError, ValueError) as exc:
                detail = self.validation_detail(exc)
                self.event(state, "cached_response_rejected", role, f"{key}; {detail}")
                initial_feedback = {
                    "validation_feedback": detail
                    + ". Return a corrected complete object matching the schema."
                }
                replace_cached = True
        start = time.monotonic()
        self.event(state, "agent_started", role, key, actor_type="agent", actor_id=role)
        provider = self.provider
        last_detail = ""
        feedback = initial_feedback
        for attempt in range(self.policy.max_provider_attempts):
            try:
                raw = provider.generate(role, instructions, {**context, **feedback}, schema)
                result = validate(raw)
                self.repo.cache(
                    state["workflow_run_id"],
                    key,
                    result.model_dump(mode="json"),
                    replace=replace_cached,
                )
                self.event(
                    state,
                    "agent_completed",
                    role,
                    json.dumps(
                        {
                            "operation": key,
                            "provider": provider.name,
                            "duration": time.monotonic() - start,
                        }
                    ),
                    actor_type="agent",
                    actor_id=role,
                )
                return result
            except GraphBubbleUp:
                raise
            except Exception as exc:
                # Validation exception strings include raw input; record only
                # field locations/error types, never a remote response body.
                detail = self.validation_detail(exc)
                last_detail = detail
                self.event(
                    state,
                    "agent_failure",
                    role,
                    f"{key}; provider={provider.name}; attempt={attempt + 1}; {detail}",
                )
                feedback = {
                    "validation_feedback": detail
                    + ". Return a corrected complete object matching the schema."
                }
                if attempt + 1 < self.policy.max_provider_attempts:
                    self.event(
                        state,
                        "retry_attempted",
                        role,
                        f"{key}; provider={provider.name}; attempt={attempt + 1}",
                    )
        raise ValueError(
            f"Provider failed for {role} after {self.policy.max_provider_attempts} attempts. Last error: {last_detail}. See audit, then retry or abort."
        )

    def artifact(
        self, state: Workflow, key: str, kind: str, content: dict, dependencies: list[str]
    ) -> dict:
        for ref in dependencies:
            if ref not in state["artifacts"] or state["artifacts"][ref]["validity"] != "VALID":
                raise ValueError(f"Broken dependency: {ref}")
        old_ref = state["active"].get(key)
        version = 1 + max(
            [a["version"] for a in state["artifacts"].values() if a["id"] == key] or [0]
        )
        artifact = Artifact(
            id=key,
            version=version,
            kind=kind,
            content=content,
            dependencies=dependencies,
            digest=digest({"content": content, "dependencies": dependencies}),
        )
        changes = {}
        if old_ref:
            changes.update(invalidate(state["artifacts"], {old_ref}))
            old = state["artifacts"][old_ref].copy()
            old["validity"] = "SUPERSEDED"
            changes[old_ref] = old
        changes[artifact.ref] = artifact.model_dump(mode="json")
        for ref, value in changes.items():
            self.repo.save_artifact(state["workflow_run_id"], Artifact.model_validate(value))
            if value["validity"] in {"REVALIDATE", "INVALIDATED"}:
                self.event(state, "artifact_invalidated", kind, "Upstream revision", [ref])
        self.event(
            state,
            f"{kind}_version_created",
            kind,
            "Versioned proposal/evidence",
            [artifact.ref],
            before_version=version - 1 or None,
            after_version=version,
        )
        return {"artifacts": changes, "active": {key: artifact.ref}}

    @staticmethod
    def apply(state: Workflow, update: dict) -> Workflow:
        result = dict(state)
        maps = {
            "artifacts",
            "active",
            "findings",
            "approvals",
            "tool_results",
            "reviews",
            "counters",
            "branch_errors",
        }
        for key, value in update.items():
            result[key] = {**result.get(key, {}), **value} if key in maps else value
        return result

    def persist_changes(self, state, changes):
        for value in changes.values():
            self.repo.save_artifact(state["workflow_run_id"], Artifact.model_validate(value))

    def context(self, state, design=False, include_code=False):
        baseline(state)
        result = {
            "requirement": approved(state, "requirement"),
            "architecture": approved(state, "architecture"),
            "adrs": [
                approved(state, a["adr_id"])
                for a in active_artifact(state, "architecture")["content"]["adrs"]
            ],
        }
        if (
            "plan" in state["active"]
            and state["artifacts"][state["active"]["plan"]]["validity"] == "VALID"
        ):
            result["plan"] = active_artifact(state, "plan")
        if (
            "impact" in state["active"]
            and state["artifacts"][state["active"]["impact"]]["validity"] == "VALID"
        ):
            result["impact"] = active_artifact(state, "impact")
        if state.get("current_slice") and "plan" in result:
            result["slice"] = next(
                s for s in result["plan"]["content"]["slices"] if s["id"] == state["current_slice"]
            )
        if design:
            result["design"] = result["slice"]["design"]
        if include_code:
            result["implementation"] = self.files(state)[0]
        return result

    def files(self, state):
        files, refs = {}, []
        if "snapshot" in state["active"]:
            snapshot = active_artifact(state, "snapshot")
            files.update(snapshot["content"]["files"])
            refs.append(state["active"]["snapshot"])
        # Plan order is topologically validated; later slices can intentionally
        # replace earlier file content. Same-slice code/test collisions are forbidden.
        for item in active_artifact(state, "plan")["content"]["slices"]:
            for kind in ("code", "tests"):
                key = f"{kind}:{item['id']}"
                if key in state["active"]:
                    artifact = state["artifacts"][state["active"][key]]
                    if artifact["validity"] == "VALID":
                        files.update(artifact["content"]["files"])
                        refs.append(state["active"][key])
        return files, refs

    def review(self, state, key, role):
        artifact = active_artifact(state, key)
        prior = [f for f in state["findings"].values() if f["artifact_id"] == key]
        context = {
            "artifact": artifact,
            "previous_findings": prior,
            "requirement": approved(state, "requirement"),
        }
        if role != "architecture_reviewer":
            context.update(self.context(state, design=True))
        result = self.call(state, role, context)
        findings = {}
        for proposal in result.findings:
            identifier = f"{key}/{proposal.id}"
            old = state["findings"].get(identifier)
            data = proposal.model_dump()
            data["id"] = identifier
            finding = Finding(**data, artifact_id=key, artifact_version=artifact["version"])
            if old:
                finding.created_at = old["created_at"]
                finding.before_version = old["artifact_version"]
            findings[identifier] = finding.model_dump(mode="json")
            self.event(
                state,
                "review_finding_created",
                role,
                proposal.description,
                [state["active"][key]],
                related_review_ids=[identifier],
            )
        for resolution in result.resolutions:
            identifier = resolution.finding_id
            if identifier not in state["findings"]:
                raise ValueError("Reviewer attempted to resolve unknown finding")
            old = state["findings"][identifier]
            if (
                old["artifact_id"] != key
                or artifact["version"] <= old["artifact_version"]
                or not all(
                    [
                        resolution.actual_change,
                        resolution.reviewer_verification,
                        resolution.author_response,
                    ]
                )
            ):
                raise ValueError(
                    "Finding resolution requires changed artifact and reviewer verification"
                )
            findings[identifier] = {
                **old,
                **resolution.model_dump(exclude={"finding_id"}),
                "status": "RESOLVED",
                "before_version": old["artifact_version"],
                "after_version": artifact["version"],
                "updated_at": now(),
            }
            self.event(
                state,
                "finding_resolved",
                role,
                resolution.resolution_reason,
                [state["active"][key]],
                related_review_ids=[identifier],
            )
        self.event(state, "review_completed", role, str(result.complete), [state["active"][key]])
        return {
            "findings": findings,
            "reviews": {state["active"][key]: result.model_dump(mode="json")},
        }

    def guarded(self, name, function):
        def node(state):
            start = time.monotonic()
            try:
                result = function(state)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                # Interrupts are control flow, not provider/policy failures.
                result = {
                    "route": "safe_stop",
                    "workflow_status": "SAFE_STOP",
                    "safe_stop_reason": f"{name}: {type(exc).__name__}: {redact(str(exc))}",
                    "recovery_node": name,
                }
                self.event(state, "policy_or_stage_failure", name, result["safe_stop_reason"])
            self.event(
                state,
                "stage_completed",
                name,
                json.dumps(
                    {
                        "duration": time.monotonic() - start,
                        "active": state.get("active", {}),
                        "counters": state.get("counters", {}),
                    }
                ),
            )
            return result

        return node
