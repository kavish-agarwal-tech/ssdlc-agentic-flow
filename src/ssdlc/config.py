"""Environment-driven provider selection; credentials never enter workflow state."""

import os
from pathlib import Path

from ssdlc.mock import MockProvider
from ssdlc.providers import DeepSeekProvider


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
    name = values.get("LLM_PROVIDER", "deepseek")
    if name == "mock":
        return MockProvider()
    if name != "deepseek":
        raise ValueError("Supported providers: deepseek, mock")
    return DeepSeekProvider(
        values.get("LLM_MODEL", values.get("DEEPSEEK_MODEL", "deepseek-flash")),
        values.get("LLM_API_KEY") or values.get("DEEPSEEK_API_KEY", ""),
        values.get("LLM_BASE_URL", "https://api.deepseek.com"),
        timeout=float(values.get("LLM_TIMEOUT", "180")),
    )
