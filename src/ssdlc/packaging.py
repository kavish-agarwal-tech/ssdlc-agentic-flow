"""Readable delivery bundles derived from approved artifacts, without model calls."""

import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

from ssdlc.persistence import digest
from ssdlc.policy import approved, release_gate
from ssdlc.state import active_artifact
from ssdlc.tools import reject_secrets, safe_path, tree_digest


def readable_artifact(artifact):
    lines = [
        f"# {artifact['id']} — version {artifact['version']}",
        "",
        f"Artifact reference: `{artifact['id']}@{artifact['version']}`",
        "",
    ]
    content = artifact["content"]
    if isinstance(content.get("sections"), dict):
        content = {**content["sections"], **{k: v for k, v in content.items() if k != "sections"}}
    for key, value in content.items():
        lines.extend([f"## {key.replace('_', ' ').title()}", ""])
        if isinstance(value, str):
            lines.append(value)
        elif key == "acceptance_criteria":
            lines.extend(
                f"- **{item['id']}** ({item['requirement_ref']}): {item['description']}"
                for item in value
            )
        elif key == "open_questions":
            for question in value:
                lines.extend(
                    [
                        f"### {question['id']}: {question['unclear']}",
                        "",
                        f"Classification: {question['classification']}",
                        question["why_it_matters"],
                        "",
                    ]
                )
                lines.extend(f"- {option}" for option in question["options"])
        elif isinstance(value, dict) and all(isinstance(v, str) for v in value.values()):
            lines.extend(f"- **{name}:** {text}" for name, text in value.items())
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            lines.extend(f"- {text}" for text in value)
        else:
            lines.extend(["```json", json.dumps(value, indent=2, ensure_ascii=False), "```"])
        lines.append("")
    return "\n".join(lines)


def create_bundle(state, nodes, evidence, destination: Path):
    if state["workflow_status"] != "READY_FOR_DEPLOYMENT":
        raise ValueError("Package requires READY_FOR_DEPLOYMENT after final human approval")
    release_gate(state)
    release = approved(state, "release")
    build = active_artifact(state, "build")["content"]
    candidate = Path(build["cwd"]).resolve()
    if not candidate.is_relative_to(Path(state["workspace"]).resolve()):
        raise ValueError("Release candidate is outside the run workspace")
    files, refs = nodes.files(state)
    if (
        tree_digest(candidate) != build["workspace_digest"]
        or set(refs) != set(build["artifact_refs"])
        or digest(files) != release["content"]["file_digest"]
    ):
        raise ValueError("Release evidence is stale; package refused")
    if not evidence["audit_chain_valid"]:
        raise ValueError("Audit integrity check failed; package refused")
    reject_secrets(json.dumps(evidence, ensure_ascii=False))
    destination = destination.resolve()
    archive = destination.with_name(state["workflow_run_id"] + "-" + destination.name + ".zip")
    if destination.exists() or archive.exists():
        raise ValueError("Package destination already exists; choose another --output directory")
    if destination.is_relative_to(candidate):
        raise ValueError("Package destination must be outside the validated candidate")
    destination.mkdir(parents=True)
    manifest_artifacts = []
    document_links = []

    def write(name, content):
        reject_secrets(content)
        target = safe_path(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def write_json(name, content):
        write(name, json.dumps(content, indent=2, ensure_ascii=False) + "\n")

    try:
        # Copy only the authoritative assembled file set, not caches or older candidates.
        for name in files:
            source = safe_path(candidate, name)
            if source.read_text(encoding="utf-8") != files[name]:
                raise ValueError(f"Candidate does not match approved source: {name}")
            target = safe_path(destination, "application/" + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        wheels = sorted((candidate / "dist").glob("*.whl"))
        if not wheels:
            raise ValueError("Successful build has no wheel file; package refused")
        for wheel in wheels:
            source = safe_path(candidate, "dist/" + wheel.name)
            target = safe_path(destination, "distribution/" + wheel.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        documents = {
            "requirement": "01-requirements.md",
            "architecture": "02-architecture.md",
            "plan": "04-plan-and-design.md",
            "release_report": "05-release-readiness.md",
            "impact": "06-brownfield-impact.md",
        }
        titles = {
            "requirement": "Requirements",
            "architecture": "Architecture",
            "plan": "Implementation plan and designs",
            "release_report": "Release readiness and application setup",
            "impact": "Brownfield impact",
        }
        filenames = set()
        for key, ref in sorted(state["active"].items()):
            artifact = active_artifact(state, key)
            slug = re.sub(r"[^A-Za-z0-9_-]+", "-", key).strip("-")[:100] or "artifact"
            name = f"{slug}-v{artifact['version']:04d}.json"
            if name in filenames:
                name = f"{slug}-{hashlib.sha256(key.encode()).hexdigest()[:12]}-v{artifact['version']:04d}.json"
            filenames.add(name)
            path = "artifacts/" + name
            write_json(path, artifact)
            manifest_artifacts.append(
                {"reference": ref, "file": path, "digest": artifact["digest"]}
            )
            document = documents.get(key)
            if artifact["kind"] == "adr":
                document = f"03-decisions/{slug}.md"
            if document:
                write("documents/" + document, readable_artifact(artifact))
                document_links.append((document, titles.get(key, f"Architecture decision: {key}")))

        plan = active_artifact(state, "plan")["content"]
        slices = ["# Implementation plan and slice designs", "", plan["rationale"], ""]
        for index, item in enumerate(plan["slices"], 1):
            slices.extend(
                [
                    f"## {index}. {item['title']} (`{item['id']}`)",
                    "",
                    f"Requirements: {', '.join(item['requirement_refs'])}",
                    f"Acceptance criteria: {', '.join(item['acceptance_criteria'])}",
                    f"Depends on: {', '.join(item['depends_on']) or 'none'}",
                    "",
                ]
            )
            for section, text in item["design"].items():
                slices.extend([f"### {section.replace('_', ' ').title()}", "", text, ""])
            for path, declarations in item.get("api_contract", {}).items():
                slices.extend(
                    [f"### Shared API: `{path}`", "", "```python", declarations.rstrip(), "```", ""]
                )
            slices.extend(["### Risks", "", *[f"- {risk}" for risk in item["risks"]], ""])
        write("documents/04-plan-and-design.md", "\n".join(slices))
        write_json("evidence/workflow-history.json", evidence)
        for name, value in {
            "tool-results": state["tool_results"],
            "reviews": state["reviews"],
            "findings": state["findings"],
            "human-approvals": state["approvals"],
            "audit": evidence["audit"],
            "metrics": evidence["metrics"],
        }.items():
            write_json(f"evidence/{name}.json", value)
        validation = [
            "# Validation and review evidence",
            "",
            "## Actual tool executions",
            "",
            "| Tool | Exit status | Duration (seconds) |",
            "|---|---|---|",
        ]
        validation.extend(
            f"| {result['tool']} | {result['exit_status']} | {result['duration']:.3f} |"
            for result in state["tool_results"].values()
        )
        validation.extend(["", "## Review findings and dispositions", ""])
        validation.extend(
            f"- **{finding['severity']} / {finding['status']}** — `{finding['id']}`: {finding['description']}"
            for finding in state["findings"].values()
        )
        if not state["findings"]:
            validation.append("No recorded review findings.")
        validation.extend(
            [
                "",
                "See `evidence/` for full tool output, reviewer responses, approval records and the final JUnit report.",
                "",
            ]
        )
        write("documents/07-validation-and-review.md", "\n".join(validation))
        document_links.append(("07-validation-and-review.md", "Validation and review evidence"))
        report = safe_path(candidate, ".results.xml")
        if not report.exists():
            raise ValueError("Final JUnit report is missing; package refused")
        target = safe_path(destination, "evidence/acceptance-tests.xml")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, target)
        write(
            "README.md",
            "\n".join(
                [
                    f"# Delivery package: {state['project_id']}",
                    "",
                    f"Run: `{state['workflow_run_id']}`",
                    f"Release: `{state['active']['release']}`",
                    f"Provider: `{state['provider_id']}`",
                    "Status: **READY_FOR_DEPLOYMENT** — final approval recorded; no deployment performed.",
                    "",
                    "## Start here",
                    "",
                    *[f"- [{title}](documents/{name})" for name, title in sorted(document_links)],
                    "",
                    "## Contents",
                    "",
                    "- `application/`: final assembled source and tests, preserving their project layout.",
                    "- `distribution/`: built wheel files.",
                    "- `documents/`: readable approved requirements, architecture, decisions, plan/design and release report.",
                    "- `artifacts/`: final active artifact JSON with readable names and versions.",
                    "- `evidence/`: tests, tool results, reviews, approvals, audit, metrics and full saved workflow history.",
                    "- `manifest.json`: artifact references and SHA-256 checksums for package files.",
                    "",
                    "Follow the release-readiness document for application setup, configuration and API usage. The package does not install dependencies or start the application.",
                    "If the provider is `mock-fixture-v1`, this is a greeting fixture with synthetic approvals, not a live-model URL-shortener release.",
                    "",
                ]
            ),
        )
        if tree_digest(candidate) != build["workspace_digest"]:
            raise ValueError("Candidate changed during packaging; package refused")
        checksums = {
            path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        }
        write_json(
            "manifest.json",
            {
                "run": state["workflow_run_id"],
                "release": state["active"]["release"],
                "provider": state["provider_id"],
                "status": state["workflow_status"],
                "artifacts": manifest_artifacts,
                "files_sha256": checksums,
            },
        )
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(destination.rglob("*")):
                if path.is_file():
                    zipped.write(
                        path, archive.stem + "/" + path.relative_to(destination).as_posix()
                    )
    except Exception:
        # Remove only the new package paths created by this invocation.
        if destination.resolve() == destination and not destination.is_symlink():
            shutil.rmtree(destination)
        archive.unlink(missing_ok=True)
        raise
    return {
        "directory": str(destination),
        "archive": str(archive),
        "release": state["active"]["release"],
    }
