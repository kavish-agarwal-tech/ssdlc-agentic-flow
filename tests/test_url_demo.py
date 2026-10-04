import pytest

from ssdlc.cli import main
from ssdlc.config import provider_from_environment
from ssdlc.mock import MockProvider
from ssdlc.models import Requirement
from ssdlc.runtime import Runtime
from ssdlc.url_demo import AMBIGUOUS_INPUT, GREENFIELD_INPUT, generate


def approve(runtime, run, result, action="approve", answers=None):
    gate = result["interrupts"][0]
    return runtime.resume(
        run,
        {
            "actor": "synthetic-test-reviewer",
            "action": action,
            "rationale": "SYNTHETIC TEST ONLY: explicit test fixture decision",
            "artifact_ref": gate.get("artifact_ref"),
            "answers": answers or {},
        },
    )


def finish(runtime, run, result):
    assert result["interrupts"][0]["gate"] == "requirement"
    result = approve(runtime, run, result)
    assert result["interrupts"][0]["gate"] == "architecture"
    result = approve(runtime, run, result)
    assert result["interrupts"][0]["gate"] == "release", result["state"]["safe_stop_reason"]
    result = approve(runtime, run, result)
    assert result["state"]["workflow_status"] == "READY_FOR_DEPLOYMENT"
    assert runtime.repo.verify_audit(run)
    assert {tool["tool"] for tool in result["state"]["tool_results"].values()} == {
        "lint",
        "static",
        "test",
        "build",
    }
    assert all(tool["exit_status"] == 0 for tool in result["state"]["tool_results"].values())
    return result


def test_three_offline_cli_scenarios_generate_validate_build_and_package(
    tmp_path, monkeypatch, capsys
):
    def reject_network(*args, **kwargs):
        raise AssertionError("Offline demo attempted an external LLM request")

    monkeypatch.setattr("urllib.request.urlopen", reject_network)
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-test-key")
    home = tmp_path / "offline"
    for scenario in ("greenfield", "ambiguous", "brownfield"):
        main(["--home", str(home), "demo", scenario, "--scripted"])
        output = capsys.readouterr().out
        assert "MOCK / DETERMINISTIC MODE" in output
        assert '"status": "READY_FOR_DEPLOYMENT"' in output, output
        run = "demo-" + scenario
        with Runtime(home) as runtime:
            state = runtime.inspect(run)["state"]
            assert runtime.repo.verify_audit(run)
            content = state["artifacts"][state["active"]["requirement"]]["content"]
            if scenario == "greenfield":
                assert content["open_questions"] == []
                assert len(content["functional_requirements"]) == 6
                assert len(content["non_functional_requirements"]) == 4
                assert len(content["acceptance_criteria"]) == 11
            if scenario == "ambiguous":
                assert state["active"]["requirement"] == "requirement@2"
                assert len(state["artifacts"]["requirement@1"]["content"]["open_questions"]) == 4
            if scenario == "brownfield":
                impact = state["artifacts"][state["active"]["impact"]]["content"]
                assert "url_shortener.py" in impact["affected_modules"]
                assert "daily_clicks" in impact["persistence_impact"]
                original = state["artifacts"][state["active"]["snapshot"]]["content"]["files"][
                    "url_shortener.py"
                ]
                final = state["artifacts"][state["active"]["code:url-shortener"]]["content"][
                    "files"
                ]["url_shortener.py"]
                assert final == original.replace(
                    "DAILY_ANALYTICS = False", "DAILY_ANALYTICS = True", 1
                )
            assert all(tool["exit_status"] == 0 for tool in state["tool_results"].values())
            assert len(state["approvals"]) == 4  # requirement, architecture, ADR, release
        delivery = home / "deliverables" / run / "release-v1"
        assert (delivery / "application" / "url_shortener.py").exists()
        assert not (delivery / "application" / "greeting.py").exists()
        delivery_readme = (delivery / "README.md").read_text(encoding="utf-8")
        assert "application/README.md" in delivery_readme
        assert "MOCK / DETERMINISTIC MODE" in delivery_readme
        assert "this is a greeting fixture" not in delivery_readme
        assert list((delivery / "distribution").glob("*.whl"))
        assert delivery.with_name(run + "-release-v1.zip").exists()


def test_ambiguous_pause_requires_product_answers_and_separate_approval(tmp_path):
    with Runtime(tmp_path) as runtime:
        result = runtime.start(AMBIGUOUS_INPUT, "ambiguous", "ambiguous")
        questions = result["interrupts"][0]["artifact"]["content"]["open_questions"]
        assert {q["id"] for q in questions} == {"optional", "ttl", "expired", "retention"}
        assert all(q["uncertainty_type"] == "PRODUCT_AMBIGUITY" for q in questions)
        with pytest.raises(ValueError, match="Clarify"):
            approve(runtime, "ambiguous", result)
        result = approve(runtime, "ambiguous", result, "clarify", {"optional": "Optional"})
        assert result["state"]["active"]["requirement"] == "requirement@2"
        assert len(result["interrupts"][0]["artifact"]["content"]["open_questions"]) == 3
        assert not result["state"]["approvals"]


def test_application_failure_triggers_targeted_real_replanning(tmp_path):
    class OnceBrokenProvider(MockProvider):
        def __init__(self):
            self.calls = 0
            self.contexts = {}

        def generate(self, role, instructions, context, schema):
            self.contexts.setdefault(role, []).append(context)
            result = super().generate(role, instructions, context, schema)
            if role == "coding":
                self.calls += 1
                if self.calls == 1:
                    result["files"]["url_shortener.py"] = result["files"][
                        "url_shortener.py"
                    ].replace("return 302, row[0]", "return 301, row[0]")
            return result

    provider = OnceBrokenProvider()
    with Runtime(tmp_path, provider=provider, allow_execution=True) as runtime:
        result = runtime.start(GREENFIELD_INPUT, "replan")
        result = approve(runtime, "replan", result)
        result = approve(runtime, "replan", result)
        assert result["interrupts"][0]["gate"] == "release", result["state"]["safe_stop_reason"]
        state = result["state"]
        assert state["counters"]["replans"] == 1
        assert state["active"]["code:url-shortener"] == "code:url-shortener@2"
        assert state["active"]["tests:url-shortener"] == "tests:url-shortener@1"
        assert state["artifacts"]["code:url-shortener@1"]["validity"] == "SUPERSEDED"
        assert any(
            event["action"] == "artifact_invalidated"
            and "code:url-shortener@1" in event["artifact_refs"]
            for event in runtime.repo.events("replan")
        )
        assert "implementation" not in provider.contexts["test_design"][0]
        assert "implementation" in provider.contexts["coding"][0]
        assert runtime.metrics("replan")["test_fail_count"] == 1
        assert runtime.repo.verify_audit("replan")


def test_mock_is_default_and_unknown_spec_does_not_become_demo():
    assert isinstance(provider_from_environment({}), MockProvider)
    context = {
        "original_text": "Build an enterprise URL shortener with mandatory accounts and asynchronous analytics",
        "answers": {},
    }
    result = MockProvider().generate("requirement", "", context, Requirement)
    assert result["open_questions"][0]["id"] == "scope"
    assert result["original_text"] == context["original_text"]


def test_daily_review_rejects_missing_evidence_and_source_contract():
    requirement = generate("requirement", {"original_text": GREENFIELD_INPUT, "answers": {}})
    result = generate(
        "quality_reviewer",
        {
            "requirement": {"content": requirement},
            "artifact": {
                "content": {
                    "code": {"files": {".env": "forbidden"}},
                    "tests": {"files": {}, "criterion_tests": {}},
                }
            },
            "slice": {"acceptance_criteria": ["AC1"]},
        },
    )
    assert not result["complete"]
    assert len(result["findings"]) >= 3
    with pytest.raises(ValueError, match="requires"):
        generate("brownfield_analysis", {"repository": {"greeting.py": "def greet(): pass"}})


def test_demo_expiration_policy_variants(tmp_path):
    import importlib.util
    from itertools import product

    for index, (mandatory, default, status, retention) in enumerate(
        product(
            ["Optional", "Mandatory"],
            ["No default", "3600 seconds"],
            ["410", "404"],
            ["Retain", "Delete on access"],
        )
    ):
        requirement = generate(
            "requirement",
            {
                "original_text": AMBIGUOUS_INPUT,
                "answers": {
                    "optional": mandatory,
                    "ttl": default,
                    "expired": status,
                    "retention": retention,
                },
            },
        )
        source = generate("coding", {"requirement": {"content": requirement}})["files"][
            "url_shortener.py"
        ]
        path = tmp_path / f"app_{index}.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"expiry_{index}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        clock = [1000]
        store = module.Store(str(tmp_path / f"db_{index}.sqlite"), clock=lambda: clock[0])
        try:
            code = store.create("https://example.org", ttl=10)
            assert store.resolve(code)[0] == 302
            clock[0] = 1010
            assert store.resolve(code)[0] == int(status)
            assert store.analytics(code) == (
                None if retention == "Delete on access" else {"code": code, "clicks": 1}
            )
            if mandatory == "Mandatory" and default == "No default":
                with pytest.raises(ValueError, match="required"):
                    store.create("https://example.org")
        finally:
            store.close()
