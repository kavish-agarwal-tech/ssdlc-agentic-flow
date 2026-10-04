"""Explicit deterministic assignment workers and legacy greeting test fixture."""

from ssdlc.models import ARCHITECTURE_SECTIONS, DESIGN_SECTIONS

MINIMAL_REQUIREMENT = "Create a Python greeting library: greet(name) returns Hello, <trimmed name>! Reject non-string inputs and clarify blank-name behavior."


def question(identifier, unclear, why, options, recommendation):
    return dict(
        id=identifier,
        classification="BLOCKING_AMBIGUITY",
        unclear=unclear,
        why_it_matters=why,
        options=options,
        recommendation=recommendation,
        reasoning="Conservative starting point; confirm the actual product constraints.",
        recommendation_is_binding=False,
        human_confirmation_required=True,
    )


class MockProvider:
    name = "mock-fixture-v1"

    def generate(self, role, instructions, context, schema):
        from ssdlc import url_demo

        text = context.get(
            "original_text",
            context.get("requirement", {}).get("content", {}).get("original_text", ""),
        )
        if role == "failure_analysis":
            text = (
                context.get("active_artifacts", {})
                .get("requirement", {})
                .get("content", {})
                .get("original_text", "")
            )
        if url_demo.supported(text):
            return url_demo.generate(role, context)
        if role == "requirement":
            text = context["original_text"]
            if "greeting" in text.lower():
                questions = [
                    question(
                        "blank",
                        "How should blank names behave?",
                        "Defines the public validation contract.",
                        ["Reject with ValueError", "Use World"],
                        "Reject with ValueError",
                    )
                ]
                criteria = [
                    ("AC1", "FR1", "Greeting trims a non-empty string and returns Hello, <name>!"),
                    ("AC2", "FR2", "Blank names raise ValueError; non-strings raise TypeError."),
                ]
                functional = {"FR1": "Return a greeting", "FR2": "Validate input"}
            elif "expir" in text.lower() and "shortener" not in text.lower():
                questions = [
                    question(k, u, "Changes lifecycle and persisted data semantics.", opts, opts[0])
                    for k, u, opts in [
                        ("ttl", "What default TTL applies?", ["No default", "30 days"]),
                        ("optional", "Is expiration optional?", ["Optional", "Mandatory"]),
                        ("expired", "Which HTTP response follows expiration?", ["410", "404"]),
                        (
                            "retention",
                            "Retain expired-link analytics?",
                            ["30 days", "Indefinitely"],
                        ),
                        ("reactivation", "Can expired links reactivate?", ["No", "Owner action"]),
                        (
                            "cleanup",
                            "How should expired mappings be cleaned?",
                            ["Scheduled cleanup", "Retain tombstones"],
                        ),
                    ]
                ]
                criteria = [("AC1", "FR1", "Expiration semantics follow explicit human decisions")]
                functional = {"FR1": text}
            else:
                questions = [
                    question(
                        "scope",
                        "What are the observable acceptance criteria and invariants?",
                        "The fixture provider cannot infer arbitrary product behavior.",
                        ["Provide explicit criteria", "Use a configured model provider"],
                        "Provide explicit criteria",
                    )
                ]
                criteria = [("AC1", "FR1", "Human must define measurable expected behavior")]
                functional = {"FR1": text}
            answers = context.get("answers", {})
            return dict(
                original_text=text,
                normalized_requirement=text.strip(),
                functional_requirements=functional,
                non_functional_requirements={
                    "NFR1": "Local deterministic validation, no secrets in logs"
                },
                invariants=["Only approved requirements drive implementation"],
                assumptions=["Offline fixture analysis; human validation required"],
                open_questions=questions,
                acceptance_criteria=[
                    dict(id=i, requirement_ref=r, description=d) for i, r, d in criteria
                ],
                human_input=answers,
                decisions=answers,
            )
        if role.endswith("reviewer"):
            return dict(complete=True, findings=[])
        if role == "failure_analysis":
            return dict(
                category="ENVIRONMENT_OR_TOOLING",
                evidence=["See persisted tool results"],
                reasoning="Fixture provider cannot diagnose arbitrary failures; escalate to the operator.",
            )
        if role == "brownfield_analysis":
            return dict(
                affected_modules=list(context.get("repository", {})),
                services=[],
                apis=["greet(name)"],
                data_flows=["caller -> greeting library"],
                persistence_impact="None for synthetic library",
                test_impact="Run existing tests and add regression assertions",
                configuration_impact="Preserve package metadata",
                backward_compatibility="Keep public greet contract",
                migration_requirements="None",
                regression_risk="Existing greeting behavior must remain unchanged",
            )
        if role == "release_readiness":
            return dict(
                sections={
                    "engineering_summary": "Approved synthetic greeting library with executed validation.",
                    "known_risks": "See recorded findings and explicit risk acceptance.",
                    "setup": "Install the generated wheel in a virtual environment.",
                    "api": "greet(name: str) -> str; blank raises ValueError, non-string raises TypeError.",
                    "configuration": "No environment variables required.",
                    "architecture": "Single pure Python module; no persistence.",
                    "adrs": "Python standard library chosen for the approved synthetic fixture.",
                    "tests": "Consult deterministic validation artifacts; coverage percentage is not measured.",
                    "operations": "Library has no service health endpoint or migrations.",
                    "release_notes": "Initial greeting library.",
                    "rollback": "Restore the previous approved package/artifact pointer; no database migration.",
                    "limitations": "Offline fixture; not a generated production application.",
                    "tradeoffs": "Small package with synchronous pure function.",
                    "deployment": "Human deployment authorization required; this system never deploys.",
                    "packaging": "Wheel built using the fixed local Python tools.",
                }
            )
        requirement = context["requirement"]["content"]
        if "greeting" not in requirement["original_text"].lower():
            raise ValueError(
                "Mock provider implements only the synthetic greeting fixture; configure a real provider for product implementation"
            )
        if requirement["decisions"].get("blank") != "Reject with ValueError":
            raise ValueError(
                "Mock fixture supports only the explicitly chosen Reject with ValueError contract"
            )
        if role == "architecture":

            def alternative(description, complexity):
                return dict(
                    description=description,
                    advantages=["Portable"],
                    disadvantages=["Requires runtime"],
                    complexity=complexity,
                    operational_impact="Local library",
                    security_impact="No network or storage",
                    reliability_impact="Deterministic pure function",
                    scalability_impact="Caller-managed",
                    cost_implication="No service cost",
                )

            return dict(
                sections={
                    k: "Pure greeting function; validation at public boundary; no shared state, storage or network. Scope: approved synthetic greeting fixture."
                    for k in ARCHITECTURE_SECTIONS
                },
                requirement_mapping={
                    k: "greeting.greet"
                    for k in requirement["functional_requirements"]
                    | requirement["non_functional_requirements"]
                },
                technology_stack={
                    "language": "Python",
                    "framework": "standard library",
                    "test": "pytest",
                    "build": "setuptools",
                    "persistence": "none",
                },
                adrs=[
                    dict(
                        adr_id="ADR-001",
                        decision="Python library",
                        context="Small deterministic local greeting API",
                        alternatives=[
                            alternative("Python library", "Low"),
                            alternative("Java library", "Higher build setup"),
                        ],
                        recommendation="Python library",
                        tradeoffs=["Runtime dependency; smallest implementation for fixture"],
                        rationale="Fits approved synthetic scope",
                        requirement_refs=list(requirement["functional_requirements"]),
                        affected_artifacts=["plan", "code", "tests"],
                    )
                ],
            )
        if role == "planning_design":
            return dict(
                slices=[
                    dict(
                        id="greeting",
                        title="Validated greeting end to end",
                        depends_on=[],
                        requirement_refs=list(requirement["functional_requirements"]),
                        acceptance_criteria=[a["id"] for a in requirement["acceptance_criteria"]],
                        design={
                            key: "greeting.py exports greet(name): validate str, trim, reject blank, and format Hello, <name>!. Pure function; standard library only. Independent tests exercise normal, blank, and non-string inputs."
                            for key in DESIGN_SECTIONS
                        },
                        api_contract={"greeting.py": "def greet(name: str) -> str: ...\n"},
                        risks=["Input boundary ambiguity"],
                    )
                ],
                rationale="One coherent vertical slice with implementation-level design",
            )
        if role == "coding":
            return dict(
                files={
                    "greeting.py": 'def greet(name: str) -> str:\n    if not isinstance(name, str):\n        raise TypeError("name must be a string")\n    name = name.strip()\n    if not name:\n        raise ValueError("name cannot be blank")\n    return f"Hello, {name}!"\n',
                    "pyproject.toml": '[build-system]\nrequires = ["setuptools>=77"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "synthetic-greeting"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n\n[tool.setuptools]\npy-modules = ["greeting"]\n\n[tool.pytest.ini_options]\npythonpath = ["."]\njunit_family = "legacy"\n',
                },
                change_summary="Implement approved greeting fixture",
            )
        if role == "test_design":
            return dict(
                files={
                    "tests/test_greeting.py": 'import pytest\n\nfrom greeting import greet\n\n\ndef test_greeting():\n    assert greet("  Ada  ") == "Hello, Ada!"\n    assert greet("世界") == "Hello, 世界!"\n\n\ndef test_blank():\n    with pytest.raises(ValueError):\n        greet("   ")\n    with pytest.raises(ValueError):\n        greet("")\n\n\ndef test_type():\n    with pytest.raises(TypeError):\n        greet(None)\n'
                },
                change_summary="Independent acceptance tests",
                criterion_tests={
                    "AC1": ["tests/test_greeting.py::test_greeting"],
                    "AC2": [
                        "tests/test_greeting.py::test_blank",
                        "tests/test_greeting.py::test_type",
                    ],
                },
            )
        raise ValueError(f"Unsupported fixture role: {role}")
