"""Optional live smoke test. No generated code is executed and no approvals made."""

import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ssdlc.config import load_env_file, provider_from_environment


class SmokeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["local-model-ready"]


load_env_file(Path(".env"))
provider = provider_from_environment()
started = time.monotonic()
result = provider.generate(
    "documentation",
    "Return a JSON object with status equal to local-model-ready.",
    {"task": "Connectivity and JSON-schema smoke test"},
    SmokeResponse,
)
validated = SmokeResponse.model_validate(result)
print(
    json.dumps(
        {
            "provider": provider.name,
            "status": "local-model-ready",
            "seconds": round(time.monotonic() - started, 2),
        }
    )
)
