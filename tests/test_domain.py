import pytest

from ssdlc.models import Artifact, AuditEvent
from ssdlc.persistence import Repository, digest, invalidate
from ssdlc.policy import approved
from ssdlc.tools import ToolError, safe_path


def test_targeted_transitive_invalidation():
    artifacts = {
        "req@1": {"dependencies": [], "kind": "requirement", "validity": "VALID"},
        "arch@1": {"dependencies": ["req@1"], "kind": "architecture", "validity": "VALID"},
        "code@1": {"dependencies": ["arch@1"], "kind": "code", "validity": "VALID"},
        "other@1": {"dependencies": [], "kind": "code", "validity": "VALID"},
    }
    changed = invalidate(artifacts, {"req@1"})
    assert set(changed) == {"arch@1", "code@1"}
    assert changed["arch@1"]["validity"] == "REVALIDATE"
    assert changed["code@1"]["validity"] == "INVALIDATED"
    assert artifacts["code@1"]["validity"] == "VALID"


def test_approval_cannot_be_claimed_by_artifact():
    state = {
        "active": {"architecture": "arch@1"},
        "artifacts": {"arch@1": {"approval_status": "APPROVED", "validity": "VALID"}},
    }
    with pytest.raises(ValueError, match="Human approval"):
        approved(state, "architecture")


def test_audit_chain_and_immutable_content(tmp_path):
    repo = Repository(tmp_path / "audit.sqlite", artifact_root=tmp_path / "workspace")
    event = AuditEvent(workflow_id="w", action="created", stage="start")
    repo.record(event)
    repo.record(event)
    assert len(repo.events("w")) == 1
    assert repo.verify_audit("w")
    artifact = Artifact(
        id="r",
        version=1,
        kind="requirement",
        content={"a": 1},
        digest=digest({"content": {"a": 1}, "dependencies": []}),
    )
    repo.save_artifact("w", artifact)
    assert repo.artifact("w", artifact.ref)["content"] == {"a": 1}
    artifact_row = repo.connection.execute(
        "SELECT payload FROM artifacts WHERE workflow='w' AND ref=?", (artifact.ref,)
    ).fetchone()[0]
    assert '"content"' not in artifact_row
    artifact_file = (
        tmp_path
        / "workspace"
        / "w"
        / "artifacts"
        / "requirement"
        / "454349e422f05297"
        / "v0001.json"
    )
    assert artifact_file.exists()
    with pytest.raises(ValueError, match="Cannot mutate"):
        changed = artifact.model_copy(
            update={
                "content": {"a": 2},
                "digest": digest({"content": {"a": 2}, "dependencies": []}),
            }
        )
        repo.save_artifact("w", changed)
    repo.connection.execute("UPDATE events SET payload='{}'")
    assert not repo.verify_audit("w")
    repo.close()


@pytest.mark.parametrize(
    "name", ["../escape.py", "C:/escape.py", "/etc/x", "a\\b", ".git/config", ".env", ".aws/key"]
)
def test_workspace_path_guard(tmp_path, name):
    with pytest.raises(ToolError):
        safe_path(tmp_path, name)
