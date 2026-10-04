# Configuration

`start` and `resume` read `.env` by default; override with `--env-file`. Process
environment values take precedence. The loader accepts simple or quoted KEY=value
entries without variable expansion or shell evaluation. `.env` is Git-ignored.

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:1.7b
LLM_BASE_URL=http://localhost:11434
LLM_TIMEOUT=180
LLM_CONTEXT_TOKENS=8192
LLM_MAX_OUTPUT_TOKENS=4096
LLM_THINK=false
LLM_CONCURRENCY=1
```

For hosted DeepSeek inference, configure its chat-completions API and supply the
key locally in `.env` (do not paste it into chat or commit the file):

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
DEEPSEEK_API_KEY=replace-with-your-key
LLM_BASE_URL=https://api.deepseek.com
LLM_TIMEOUT=180
```

`LLM_API_KEY` can be used instead of `DEEPSEEK_API_KEY`. The model name is
configurable through `LLM_MODEL`; `deepseek-flash` is the requested default.

The model tag is an example, not an architectural dependency. This machine's 16 GB
RAM, integrated Intel graphics and roughly 2 GB initially free favored a small
initial model. Larger models need more memory and may run slowly without a GPU.

After installing [Ollama for Windows](https://ollama.com/download/windows):

```powershell
ollama pull qwen3:1.7b
ollama list
.\.venv\Scripts\python scripts/check_ollama.py
.\.venv\Scripts\python -m ssdlc start --run local-run --requirement examples/minimal/requirement.txt
```

If an old terminal cannot find Ollama, open a new terminal or use
`& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list`. The Windows application
starts the local server. Run `ollama serve` only if it is not already running.

| Setting | Meaning |
|---|---|
| LLM_PROVIDER | `ollama` (default), `deepseek`, `mock`, or `plugin` |
| LLM_MODEL | Ollama model tag or DeepSeek model name |
| LLM_BASE_URL | Ollama local server or DeepSeek API base URL |
| LLM_TIMEOUT | HTTP/queue timeout in seconds; defaults to 180 |
| DEEPSEEK_API_KEY / LLM_API_KEY | DeepSeek API credential; primary provider only |
| LLM_CONTEXT_TOKENS | Model context allocation |
| LLM_MAX_OUTPUT_TOKENS | Output cap; truncated responses fail |
| LLM_THINK | Request model thinking |
| LLM_CONCURRENCY | Concurrent local calls; default 1 |
| LLM_ROLE_MODELS | JSON map of role names to model tags |
| LLM_FACTORY | Trusted module:function for plugin providers |
| LLM_FALLBACK_PROVIDER | Optional explicit fallback provider |
| LLM_FALLBACK_MODEL | Optional fallback Ollama model tag |

Fallback DeepSeek credentials use `LLM_FALLBACK_API_KEY`. Provider settings also
accept the `LLM_FALLBACK_` prefix. There is no implicit cloud fallback. Real-model
runs cannot fall back to mocks.

`--provider mock` selects the offline fixture. `demo` always uses that fixture.
Read-only inspect/audit/metrics/export do not require a model. The Python Runtime
defaults to mocks for tests; inject `provider_from_environment()` for model use.
`--verbose` emits structured audit logs to stderr.

For optional hosted inference, set `LLM_PROVIDER=plugin` and
`LLM_FACTORY=my_provider:create`. Configure credentials only in the client
environment. Vendor SDKs are optional; no cloud account is needed for local use.
