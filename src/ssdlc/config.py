"""Environment-driven provider selection; credentials never enter workflow state."""

import importlib
import json
import os
from pathlib import Path

from ssdlc.agents import CONTRACTS
from ssdlc.mock import MockProvider
from ssdlc.providers import DeepSeekProvider, OllamaProvider, ProviderChain


def load_env_file(path: Path):
    """Load simple KEY=value files without shell evaluation or variable expansion.

    Existing process environment wins. Quoted complete values are supported.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key.replace("_", "").isalnum():
            raise ValueError("Invalid environment-file entry")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        # Empty entries commonly come from dotenv placeholders or inherited
        # IDE processes. They must not shadow a populated local .env credential.
        if not os.environ.get(key):
            os.environ[key] = value


def provider_from_environment(env=None):
    values = os.environ if env is None else env

    def create(prefix):
        name = values.get(prefix + "PROVIDER", "ollama")
        if name == "mock":
            return MockProvider()
        if name == "plugin":
            factory = values.get(prefix + "FACTORY", "")
            if ":" not in factory:
                raise ValueError(prefix + "FACTORY must be a trusted module:function")
            module, function = factory.split(":", 1)
            return getattr(importlib.import_module(module), function)()
        if name == "deepseek":
            api_key = values.get(prefix + "API_KEY", "")
            if not api_key and prefix == "LLM_":
                api_key = values.get("DEEPSEEK_API_KEY", "")
            return DeepSeekProvider(
                values.get(prefix + "MODEL", "deepseek-flash"),
                api_key,
                values.get(prefix + "BASE_URL", "https://api.deepseek.com"),
                timeout=float(values.get(prefix + "TIMEOUT", "180")),
            )
        if name != "ollama":
            raise ValueError("Supported providers: ollama, deepseek, mock, plugin")
        model = values.get(prefix + "MODEL", "")
        if not model:
            raise ValueError(prefix + "MODEL is required; install a local model and set its tag")
        roles = json.loads(values.get(prefix + "ROLE_MODELS", "{}"))
        if (
            not isinstance(roles, dict)
            or set(roles) - CONTRACTS.keys()
            or any(not isinstance(v, str) or not v.strip() for v in roles.values())
        ):
            raise ValueError("ROLE_MODELS must map known agent roles to model tags")
        return OllamaProvider(
            model,
            values.get(prefix + "BASE_URL", "http://localhost:11434"),
            timeout=float(values.get(prefix + "TIMEOUT", "180")),
            context_tokens=int(values.get(prefix + "CONTEXT_TOKENS", "8192")),
            max_output_tokens=int(values.get(prefix + "MAX_OUTPUT_TOKENS", "4096")),
            role_models=roles,
            think=values.get(prefix + "THINK", "false").lower() == "true",
            concurrency=int(values.get(prefix + "CONCURRENCY", "1")),
        )

    primary = create("LLM_")
    if values.get("LLM_FALLBACK_PROVIDER"):
        fallback = create("LLM_FALLBACK_")
        if isinstance(fallback, MockProvider) and not isinstance(primary, MockProvider):
            raise ValueError("A real workflow cannot fall back to synthetic mock output")
        return ProviderChain(primary, fallback)
    return primary
