"""Thread-safe, role-configurable mock response/error sequences for tests."""

from copy import deepcopy
from threading import Lock

from ssdlc.mock import MockProvider


class ScriptedMockProvider(MockProvider):
    name = "scripted-mock-v1"

    def __init__(self, responses: dict[str, list]):
        self.responses = responses
        if any(not sequence for sequence in responses.values()):
            raise ValueError("Mock sequences cannot be empty")
        self.calls = {}
        self.lock = Lock()

    def generate(self, role, instructions, context, schema):
        with self.lock:
            index = self.calls.get(role, 0)
            self.calls[role] = index + 1
            sequence = self.responses.get(role)
            response = sequence[min(index, len(sequence) - 1)] if sequence else None
        if isinstance(response, Exception):
            raise response
        if response is not None:
            return deepcopy(response)
        return super().generate(role, instructions, context, schema)
