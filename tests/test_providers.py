import json

import pytest

from ssdlc.config import load_env_file, provider_from_environment
from ssdlc.models import Document
from ssdlc.providers import DeepSeekProvider, OllamaProvider, ProviderChain, ProviderError
from ssdlc.runtime import Runtime
from ssdlc.scripted_mock import ScriptedMockProvider


def test_local_default_requires_explicit_model():
    with pytest.raises(ValueError, match="LLM_MODEL"):
        provider_from_environment({})
    provider = provider_from_environment({"LLM_MODEL": "local-model:small"})
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://localhost:11434"


def test_deepseek_configuration_and_request(monkeypatch):
    calls = []

    def open_request(request, timeout):
        calls.append((request, timeout))
        return Response(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"sections":{"result":"ok"}}'},
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    provider = provider_from_environment(
        {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key"}
    )
    assert isinstance(provider, DeepSeekProvider)
    assert provider.model == "deepseek-flash"
    assert provider.base_url == "https://api.deepseek.com"
    assert (
        provider.generate("coding", "instructions", {"test": 1}, Document)["sections"]["result"]
        == "ok"
    )
    request, timeout = calls[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    payload = json.loads(request.data)
    assert payload["model"] == "deepseek-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert timeout == 180


def test_deepseek_requires_api_key():
    with pytest.raises(ValueError, match="API key"):
        provider_from_environment({"LLM_PROVIDER": "deepseek"})


def test_configuration_switch_and_no_synthetic_fallback():
    assert provider_from_environment({"LLM_PROVIDER": "mock"}).name == "mock-fixture-v1"
    with pytest.raises(ValueError, match="synthetic"):
        provider_from_environment({"LLM_MODEL": "local", "LLM_FALLBACK_PROVIDER": "mock"})
    provider = provider_from_environment(
        {"LLM_MODEL": "a", "LLM_FALLBACK_PROVIDER": "ollama", "LLM_FALLBACK_MODEL": "b"}
    )
    assert isinstance(provider, ProviderChain)
    assert [p.model for p in provider.providers] == ["a", "b"]


def test_env_loader_does_not_evaluate_or_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "already-set")
    path = tmp_path / "config.env"
    path.write_text('LLM_MODEL="ignored"\nTEST_LITERAL="$(not-executed)"\n', encoding="utf-8")
    load_env_file(path)
    import os

    assert os.environ["LLM_MODEL"] == "already-set"
    assert os.environ["TEST_LITERAL"] == "$(not-executed)"
    monkeypatch.delenv("TEST_LITERAL")


def test_env_loader_fills_empty_inherited_values(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    path = tmp_path / "config.env"
    path.write_text("DEEPSEEK_API_KEY=local-test-key\n", encoding="utf-8")
    load_env_file(path)
    import os

    assert os.environ["DEEPSEEK_API_KEY"] == "local-test-key"


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, _):
        return json.dumps(self.value).encode()


def test_ollama_native_request_and_schema(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return Response({"done": True, "message": {"content": '{"sections":{"result":"ok"}}'}})

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    provider = OllamaProvider("small", role_models={"coding": "coder"}, timeout=7)
    assert (
        provider.generate("coding", "instructions", {"test": 1}, Document)["sections"]["result"]
        == "ok"
    )
    request, timeout = calls[0]
    payload = json.loads(request.data)
    assert request.full_url == "http://localhost:11434/api/chat"
    assert payload["model"] == "coder"
    assert payload["format"] == Document.model_json_schema()
    assert payload["stream"] is False and timeout == 7


@pytest.mark.parametrize(
    "response",
    [
        {"done": False},
        {"done": True, "done_reason": "length"},
        {"done": True, "message": {"content": "not-json"}},
        {"done": True, "message": {"content": "[]"}},
    ],
)
def test_malformed_ollama_output_fails(monkeypatch, response):
    class Opener:
        def open(self, *args, **kwargs):
            return Response(response)

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ProviderError):
        OllamaProvider("small").generate("requirement", "instruction", {}, Document)


def test_bounded_provider_failure_and_audited_fallback(tmp_path):
    primary = ScriptedMockProvider({"requirement": [TimeoutError("not logged")]})
    fallback = ScriptedMockProvider({})
    fallback.name = "fallback-mock"
    with Runtime(tmp_path, provider=ProviderChain(primary, fallback)) as runtime:
        result = runtime.start("Create a greeting library", "fallback")
        assert result["interrupts"][0]["gate"] == "requirement"
        assert primary.calls["requirement"] == 2
        events = runtime.repo.events("fallback")
        assert sum(e["action"] == "provider_fallback" for e in events) == 1
        assert runtime.metrics("fallback")["agent_failure_count"] == 2


def test_invalid_schema_exhausts_budget_without_raw_secrets(tmp_path, monkeypatch):
    secret = "arbitrary-private-provider-credential"
    monkeypatch.setenv("TEST_API_KEY", secret)
    provider = ScriptedMockProvider({"requirement": [{"unexpected": secret}]})
    with Runtime(tmp_path, provider=provider) as runtime:
        result = runtime.start("A greeting library", "invalid")
        assert result["interrupts"][0]["gate"] == "safe_stop"
        assert provider.calls["requirement"] == 2
        assert secret not in json.dumps(runtime.repo.events("invalid"))
        assert not result["state"]["artifacts"]


def test_schema_repair_then_success(tmp_path):
    from ssdlc.mock import MockProvider
    from ssdlc.models import Requirement

    good = MockProvider().generate(
        "requirement", "", {"original_text": "greeting", "answers": {}}, Requirement
    )
    provider = ScriptedMockProvider({"requirement": [{"bad": True}, good]})
    with Runtime(tmp_path, provider=provider) as runtime:
        result = runtime.start("greeting", "repair")
        assert result["interrupts"][0]["gate"] == "requirement"
        assert runtime.metrics("repair")["retry_count"] == 1


def test_semantic_requirement_failure_is_retried_before_caching(tmp_path):
    from ssdlc.mock import MockProvider
    from ssdlc.models import Requirement

    provider = MockProvider()
    good = provider.generate(
        "requirement", "", {"original_text": "greeting", "answers": {}, "feedback": {}}, Requirement
    )
    bad = good.copy()
    bad["acceptance_criteria"] = [dict(good["acceptance_criteria"][0], requirement_ref="missing")]
    scripted = ScriptedMockProvider({"requirement": [bad, good]})
    with Runtime(tmp_path, provider=scripted) as runtime:
        result = runtime.start("greeting", "semantic-repair")
        assert result["interrupts"][0]["gate"] == "requirement"
        assert scripted.calls["requirement"] == 2
        assert runtime.metrics("semantic-repair")["retry_count"] == 1
        assert result["state"]["active"]["requirement"] == "requirement@1"
