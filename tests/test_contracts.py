import pytest

from ssdlc.contracts import (
    ContractError,
    validate_contract,
    validate_implementation,
    validate_test_imports,
)

CONTRACT = {
    "service/api.py": (
        "class Config:\n"
        "    def __init__(self, *, base_url: str): ...\n"
        "class StoreUnavailable(Exception): ...\n"
        "def create(url: str, /, *, config: Config, resolver, store) -> dict: ...\n"
    )
}


def test_shared_contract_detects_constructor_and_injection_drift():
    validate_contract(CONTRACT)
    implementation = CONTRACT["service/api.py"].replace("...", "pass")
    validate_implementation(CONTRACT, {"service/api.py": implementation})
    for before, after in [("base_url", "base"), (", resolver", ""), ("url: str, /", "url: str")]:
        with pytest.raises(ContractError, match="signature mismatch"):
            validate_implementation(
                CONTRACT, {"service/api.py": implementation.replace(before, after)}
            )


def test_contract_checks_dataclass_response_fields():
    contract = {"response.py": "class Response:\n    status_code: int\n    body: dict\n"}
    with pytest.raises(ContractError, match="fields missing"):
        validate_implementation(
            contract, {"response.py": "class Response:\n    status: int\n    body: dict\n"}
        )


@pytest.mark.parametrize(
    "contract",
    [
        {},
        {"../api.py": "def f(): ..."},
        {"api.py": "def f(): return 1"},
        {"api.py": "class Config: ..."},
    ],
)
def test_incomplete_or_executable_contract_rejected(contract):
    with pytest.raises(ContractError):
        validate_contract(contract)


def test_test_imports_use_declared_api_without_loading_production():
    validate_test_imports(
        CONTRACT, {"tests/test_api.py": "from service.api import Config, create\nimport pytest\n"}
    )
    for source in ["from service.api import GuessedConfig", "from service.guessed import create"]:
        with pytest.raises(ContractError, match="outside shared API"):
            validate_test_imports(CONTRACT, {"tests/test_api.py": source})
