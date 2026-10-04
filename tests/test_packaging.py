import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from ssdlc.mock import MINIMAL_REQUIREMENT
from ssdlc.runtime import Runtime


@pytest.fixture
def completed_run(tmp_path):
    with Runtime(tmp_path / "runs", allow_execution=True) as runtime:
        result = runtime.start(MINIMAL_REQUIREMENT, "delivery-test")
        while result["interrupts"]:
            gate = result["interrupts"][0]
            assert gate["gate"] != "safe_stop", gate
            decision = {
                "actor": "synthetic-test-human",
                "action": "approve",
                "rationale": "Synthetic fixture approval only",
                "artifact_ref": gate["artifact_ref"],
            }
            if gate["gate"] == "requirement" and not gate["artifact"]["content"]["decisions"]:
                decision.update(action="clarify", answers={"blank": "Reject with ValueError"})
            result = runtime.resume("delivery-test", decision)
        assert result["state"]["workflow_status"] == "READY_FOR_DEPLOYMENT"
        yield runtime


def test_delivery_contains_readable_final_artifacts_source_and_evidence(completed_run):
    runtime = completed_run
    before = runtime.inspect("delivery-test")
    bundle = runtime.package("delivery-test")
    root = Path(bundle["directory"])
    assert root == runtime.home / "deliverables" / "delivery-test" / "release-v1"
    assert (root / "application/greeting.py").exists()
    assert (root / "application/tests/test_greeting.py").exists()
    assert list((root / "distribution").glob("*.whl"))
    assert "AC1" in (root / "documents/01-requirements.md").read_text(encoding="utf-8")
    assert (root / "documents/02-architecture.md").exists()
    assert (root / "documents/03-decisions/ADR-001.md").exists()
    assert "Implementation" in (root / "documents/04-plan-and-design.md").read_text(
        encoding="utf-8"
    )
    assert (root / "documents/05-release-readiness.md").exists()
    assert (root / "documents/07-validation-and-review.md").exists()
    assert (root / "evidence/acceptance-tests.xml").exists()
    assert (root / "evidence/human-approvals.json").exists()
    history = json.loads((root / "evidence/workflow-history.json").read_text(encoding="utf-8"))
    assert history["audit_chain_valid"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["release"] == "release@1"
    assert len(manifest["artifacts"]) == len(before["state"]["active"])
    for name, expected in manifest["files_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(bundle["archive"]) as zipped:
        for path in root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                assert (
                    zipped.read(Path(bundle["archive"]).stem + "/" + relative) == path.read_bytes()
                )
        assert not any(
            "__pycache__" in name or ".pytest_cache" in name for name in zipped.namelist()
        )
    assert runtime.inspect("delivery-test") == before
    with pytest.raises(ValueError, match="already exists"):
        runtime.package("delivery-test")
    assert (root / "manifest.json").exists()


def test_package_rejects_pending_approval(tmp_path):
    with Runtime(tmp_path / "runs") as runtime:
        runtime.start(MINIMAL_REQUIREMENT, "pending")
        with pytest.raises(ValueError, match="final human approval"):
            runtime.package("pending")
        assert not (runtime.home / "deliverables").exists()


def test_package_rejects_modified_candidate_and_missing_wheel(completed_run, tmp_path):
    runtime = completed_run
    state = runtime.inspect("delivery-test")["state"]
    candidate = Path(state["artifacts"][state["active"]["build"]]["content"]["cwd"])
    source = candidate / "greeting.py"
    original = source.read_bytes()
    source.write_text("# Modified after approval\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        runtime.package("delivery-test", tmp_path / "stale")
    source.write_bytes(original)
    wheel = next((candidate / "dist").glob("*.whl"))
    wheel.unlink()
    with pytest.raises(ValueError, match="no wheel"):
        runtime.package("delivery-test", tmp_path / "missing-wheel")
    assert not (tmp_path / "missing-wheel").exists()
