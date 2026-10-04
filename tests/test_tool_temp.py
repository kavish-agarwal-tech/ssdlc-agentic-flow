import io
import json
import logging
from pathlib import Path

from ssdlc.cli import LLMProgressHandler
from ssdlc.tools import Executor, tree_digest
from ssdlc.url_demo import failure_analysis


def test_pytest_uses_unique_workspace_temp_and_preserves_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmp_path / "unavailable-temp"))
    monkeypatch.setenv("TMP", str(tmp_path / "unavailable-temp"))
    executor = Executor(tmp_path / "run", enabled=True)
    candidate = executor.materialize(
        {
            "test_temp.py": "def test_temp(tmp_path):\n    import tempfile\n    from pathlib import Path\n    assert tmp_path.is_relative_to(Path(tempfile.gettempdir()))\n    (tmp_path / 'created.txt').write_text('fixture data')\n",
        },
        "candidate",
    )
    before = tree_digest(candidate)
    first = executor.run("test", candidate, [])
    second = executor.run("test", candidate, [])
    assert first.exit_status == second.exit_status == 0, first.output_summary
    paths = [
        Path(result.command[result.command.index("--basetemp") + 1]) for result in (first, second)
    ]
    assert paths[0] != paths[1]
    assert all(path.is_relative_to(executor.workspace / "tool-tmp") for path in paths)
    assert not paths[0].is_relative_to(candidate)
    assert tree_digest(candidate) == before
    assert "--basetemp" not in executor.commands["test"]


def test_permission_failure_is_actionable_and_old_failures_are_excluded():
    result = failure_analysis(
        {
            "tool_results": {
                "old-lint": {"tool": "lint", "exit_status": 1, "output_summary": "syntax error"},
                "new-lint": {"tool": "lint", "exit_status": 0, "output_summary": "passed"},
                "test": {
                    "tool": "test",
                    "exit_status": 1,
                    "output_summary": "E PermissionError: Access is denied: pytest-of-unknown",
                },
            }
        }
    )
    assert result["category"] == "ENVIRONMENT_OR_TOOLING"
    assert "test exited 1" in result["reasoning"]
    assert "PermissionError" in result["reasoning"]
    assert "syntax error" not in result["evidence"][0]


def test_deterministic_progress_does_not_claim_llm_execution():
    output = io.StringIO()
    handler = LLMProgressHandler(stream=output, real_llm=False)
    try:
        for event in [
            {"action": "agent_started", "stage": "failure_analysis", "rationale": "one"},
            {
                "action": "agent_completed",
                "stage": "failure_analysis",
                "rationale": json.dumps({"operation": "one"}),
            },
        ]:
            handler.handle(
                logging.LogRecord(
                    "ssdlc.audit", logging.INFO, __file__, 1, json.dumps(event), (), None
                )
            )
    finally:
        handler.close()
    assert "Deterministic agent" in output.getvalue()
    assert "LLM" not in output.getvalue()
