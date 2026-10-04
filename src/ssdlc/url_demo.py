"""Bounded deterministic engineering workers for the assignment URL shortener.

Templates are explicit fixture output, not LLM reasoning. All scenarios use the
normal graph and actual validation tools. Test templates are independent of source.
"""

import ast
import json
from importlib.resources import files

from ssdlc.models import ARCHITECTURE_SECTIONS, DESIGN_SECTIONS

GREENFIELD_INPUT = "DETERMINISTIC URL SHORTENER: permanent anonymous links, synchronous click counts, SQLite, no deletion or deduplication. Local assignment demo."
AMBIGUOUS_INPUT = "Add expiration support."
BROWNFIELD_INPUT = "Add daily click analytics."

FUNCTIONAL = {
    "FR1": "POST /links creates a new code and /r/{code} path for each HTTP/HTTPS target (201).",
    "FR2": "GET /r/{code} redirects with 302, exact Location and no-store; unknown codes return 404.",
    "FR3": "Persist mappings and counts in SQLite across restarts; never reuse a generated code.",
    "FR4": "Synchronously and transactionally increment click count per successful redirect.",
    "FR5": "GET /links/{code}/analytics returns code/clicks (200) or unknown code (404).",
    "FR6": "GET /health returns 200/status ok independent of storage availability.",
}
NONFUNCTIONAL = {
    "NFR1": "Validate JSON fields/body<=8192 bytes and HTTP/HTTPS URLs<=2048 characters; reject credentials/control characters.",
    "NFR2": "Use parameterized SQL, sanitized errors and no private request logs; store failures return 503.",
    "NFR3": "Local Python HTTPServer, one process, SQLite, no external service or model needed.",
    "NFR4": "Deliver source, independent pytest tests, README, build metadata and wheel.",
}
CRITERIA = [
    ("FR1", "Valid creation returns 201 with code and short path", "test_create"),
    ("FR2", "302 preserves target and sets no-store", "test_redirect_and_count"),
    ("FR2", "Unknown and malformed codes return 404", "test_unknown"),
    ("FR3", "Mappings/counts survive restart; codes are not reused", "test_restart"),
    ("FR4", "Two successful redirects produce count two", "test_redirect_and_count"),
    ("FR5", "Analytics returns code/count or 404", "test_redirect_and_count"),
    ("FR6", "Health remains healthy without store availability", "test_health"),
    ("NFR1", "Invalid URLs/JSON/fields/media are rejected without creation", "test_invalid_body"),
    ("NFR2", "Database errors produce sanitized 503", "test_store_failure"),
    ("FR1", "Duplicate targets get distinct codes", "test_duplicates"),
    ("NFR4", "README and build metadata define the executable package", "test_delivery_files"),
]
EXPIRATION_QUESTIONS = [
    ("optional", "Is expiration optional or mandatory?", ["Optional", "Mandatory"]),
    ("ttl", "What default TTL applies to new links?", ["No default", "3600 seconds"]),
    ("expired", "Which response should an expired link return?", ["410", "404"]),
    ("retention", "Should expired mappings/counts be retained?", ["Retain", "Delete on access"]),
]
API_CONTRACT = {
    "url_shortener.py": """class Store:
    def __init__(self, path, clock=...): ...
    def create(self, url, ttl=None): ...
    def resolve(self, code): ...
    def analytics(self, code): ...
    def close(self): ...

def create_server(database="links.sqlite", host="127.0.0.1", port=8000): ...
def main(): ...
"""
}


def supported(text):
    value = text.lower().strip()
    return value.startswith("deterministic url shortener") or value in {
        AMBIGUOUS_INPUT.lower(),
        BROWNFIELD_INPUT.lower(),
    }


def mode(text):
    value = text.lower().strip()
    if value == AMBIGUOUS_INPUT.lower():
        return "expiration"
    if value == BROWNFIELD_INPUT.lower():
        return "daily"
    return "greenfield"


def expiration_policy(requirement):
    if mode(requirement["original_text"]) != "expiration":
        return None
    decisions = requirement["decisions"]
    for key, _, options in EXPIRATION_QUESTIONS:
        if decisions.get(key) not in options:
            raise ValueError(
                f"Choose a supported deterministic product policy for {key}: {options}"
            )
    return {
        "mandatory": decisions["optional"] == "Mandatory",
        "default_ttl": None if decisions["ttl"] == "No default" else 3600,
        "expired_status": int(decisions["expired"]),
        "delete_on_access": decisions["retention"] == "Delete on access",
    }


def requirement_analysis(context):
    text, answers = context["original_text"], context.get("answers", {})
    scenario = mode(text)
    functional = dict(FUNCTIONAL)
    criteria = [(f"AC{i}", ref, description) for i, (ref, description, _) in enumerate(CRITERIA, 1)]
    questions = []
    if scenario == "expiration":
        for key, unclear, options in EXPIRATION_QUESTIONS:
            if answers.get(key) not in options:
                questions.append(
                    dict(
                        id=key,
                        classification="BLOCKING_AMBIGUITY",
                        uncertainty_type="PRODUCT_AMBIGUITY",
                        unclear=unclear,
                        why_it_matters="Changes observable link lifetime or retention.",
                        options=options,
                        recommendation=options[0],
                        reasoning="Bounded assignment policies; select explicitly.",
                        human_confirmation_required=True,
                    )
                )
        functional["FR7"] = (
            "Add expiry using the explicit clarification answers; existing links stay permanent. "
            + json.dumps(answers, sort_keys=True)
        )
        criteria.append(
            (
                "AC12",
                "FR7",
                "New links follow chosen TTL, expired response and retention; no expired redirect is counted; prior links stay permanent.",
            )
        )
    elif scenario == "daily":
        functional["FR7"] = (
            "Add UTC daily click counts to existing analytics; preserve redirects, total counts and existing database records."
        )
        criteria.append(
            (
                "AC12",
                "FR7",
                "Clicks on two UTC dates have distinct daily counts; totals survive restart and existing schema migrates without loss.",
            )
        )
    return dict(
        original_text=text,
        normalized_requirement="MOCK / DETERMINISTIC MODE: local URL-shortener " + scenario,
        functional_requirements=functional,
        non_functional_requirements=NONFUNCTIONAL,
        invariants=[
            "Three explicit normal human gates; no automatic product approval.",
            "No target fetching; generated codes never reused.",
            "Only the selected bounded fixture scope is implemented.",
        ],
        assumptions=[
            "ARCHITECTURE_DECISION: Python standard-library HTTPServer, SQLite, lowercase hexadecimal sequence codes.",
            "NON_BLOCKING_ASSUMPTION: local anonymous prototype; no authentication, deletion, alias, rate limit or distributed service in the baseline.",
            "MOCK / DETERMINISTIC MODE: templates support this documented demo, not arbitrary specifications.",
        ],
        open_questions=questions,
        acceptance_criteria=[dict(id=i, requirement_ref=r, description=d) for i, r, d in criteria],
        human_input=answers,
        decisions=answers,
    )


def _template(name):
    return files("ssdlc").joinpath("templates", name).read_text(encoding="utf-8")


def _alternative(description, downside):
    return dict(
        description=description,
        advantages=["Works offline"],
        disadvantages=[downside],
        complexity="Low",
        operational_impact="Local single process",
        security_impact="Bind to loopback; no public production claims",
        reliability_impact="Durable local transactions",
        scalability_impact="Prototype only",
        cost_implication="No external service cost",
    )


def architecture(requirement):
    sections = {
        key: "Local single-process HTTPServer -> Store -> SQLite. Explicit request validation; parameterized transactions; no target fetching, credentials or private request logs. Store/create_server are the shared API seams; tests exercise actual HTTP and database restart. No cloud deployment; final approval records readiness only."
        for key in ARCHITECTURE_SECTIONS
    }
    sections["scope"] = requirement["normalized_requirement"]
    return dict(
        sections=sections,
        requirement_mapping={
            key: "url_shortener.Store / create_server, independent HTTP and persistence tests"
            for key in requirement["functional_requirements"]
            | requirement["non_functional_requirements"]
        },
        technology_stack={
            "language": "Python",
            "framework": "standard-library HTTPServer",
            "persistence": "SQLite",
            "test": "pytest",
            "build": "setuptools",
        },
        adrs=[
            dict(
                adr_id="ADR-001",
                decision="Standard-library HTTP and SQLite in one serving process",
                context="Reproducible small offline assignment; no service provisioning or framework dependency",
                alternatives=[
                    _alternative("HTTPServer and SQLite", "Not a production HTTP server"),
                    _alternative(
                        "Flask and SQLite", "Additional dependency unnecessary for this scope"
                    ),
                ],
                recommendation="HTTPServer and SQLite",
                tradeoffs=[
                    "Simple setup and real durability; limited concurrency and HTTP capabilities"
                ],
                rationale="Fits the supported offline demo and fixed Python toolchain",
                requirement_refs=list(requirement["functional_requirements"]),
                affected_artifacts=["plan", "code", "tests"],
            )
        ],
    )


def plan(requirement):
    return dict(
        slices=[
            dict(
                id="url-shortener",
                title="URL-shortener vertical slice",
                depends_on=[],
                requirement_refs=list(
                    requirement["functional_requirements"]
                    | requirement["non_functional_requirements"]
                ),
                acceptance_criteria=[
                    criterion["id"] for criterion in requirement["acceptance_criteria"]
                ],
                design={
                    key: "url_shortener.py: Store(path, clock=time.time), create(url, ttl=None)->hex code, resolve(code)->(status,target), analytics(code)->dict or None, close(); create_server(database='links.sqlite',host='127.0.0.1',port=8000)->HTTPServer. POST /links, GET /r/{code}, GET /links/{code}/analytics, GET /health. Parameterized SQL and synchronous count transaction; SQLite.Error -> sanitized 503. Independent tests use local ephemeral HTTP port, temp database and injected clock. Selected extension changes only declared expiry or daily behavior; README and setuptools metadata included."
                    for key in DESIGN_SECTIONS
                },
                api_contract=API_CONTRACT,
                risks=["Local prototype, no production server/abuse controls"],
            )
        ],
        rationale="One coherent bounded slice; independent templates share an explicit public contract",
    )


def production_bundle(requirement, context):
    scenario = mode(requirement["original_text"])
    policy = expiration_policy(requirement)
    source = (
        _template("url_shortener.py.txt")
        .replace("__DAILY_ANALYTICS__", repr(scenario == "daily"))
        .replace("__EXPIRATION_POLICY__", repr(policy))
    )
    if scenario == "daily":
        # A bounded patch of inspected source, not replacement by an unrelated fixture.
        existing = context.get("implementation", {}).get("url_shortener.py")
        if existing is None or "DAILY_ANALYTICS = False" not in existing:
            raise ValueError(
                "Daily demo needs the prior deterministic URL-shortener application with daily analytics disabled"
            )
        source = existing.replace("DAILY_ANALYTICS = False", "DAILY_ANALYTICS = True", 1)
    return dict(
        files={
            "url_shortener.py": source,
            "pyproject.toml": '[build-system]\nrequires = ["setuptools>=77"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "demo-url-shortener"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n\n[project.scripts]\nurl-shortener = "url_shortener:main"\n\n[tool.setuptools]\npy-modules = ["url_shortener"]\n\n[tool.pytest.ini_options]\npythonpath = ["."]\njunit_family = "legacy"\n',
            "README.md": '# Generated URL-shortener demo\n\nMOCK / DETERMINISTIC MODE: bounded template output, validated with real tools.\n\nRun `python -m url_shortener --database links.sqlite --port 8000` from this directory, or install the wheel and run `url-shortener`. Python standard library only; pytest is needed for tests.\n\nPOST /links with application/json and {"url":"https://example.org"} returns code/short_url. GET /r/{code} redirects; GET /links/{code}/analytics reads counts; GET /health checks liveness. URLs are not fetched.\n\nRun `python -m pytest -q` and `python -m build --wheel --no-isolation` with the development tools installed.\n\nSingle loopback serving process, durable SQLite, synchronous click count. Baseline: permanent anonymous links, no deletion, deduplication, auth or rate limiting. HTTPServer is for a local prototype, not public production hosting.\n\nSelected extension: '
            + scenario
            + ". Expiration policy: "
            + json.dumps(policy)
            + ". Daily analytics, when selected, adds a UTC day/count map; historical clicks before the migration remain only in the total. For expiration, POST may include ttl_seconds, positive integer seconds up to one year; prior links stay permanent. Back up the database before upgrades. Rollback restores code and matching database backup.\n",
        },
        change_summary="Deterministic URL-shortener " + scenario + " source and packaging",
    )


DAILY_TEST = """
def test_daily(tmp_path):
    import sqlite3

    database = str(tmp_path / "old.sqlite")
    old = sqlite3.connect(database)
    old.execute("CREATE TABLE links (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0)")
    old.execute("INSERT INTO links(url, clicks) VALUES ('https://example.org', 3)")
    old.commit()
    old.close()
    clock = [1704067200]
    store = Store(database, clock=lambda: clock[0])
    assert store.analytics("1")["clicks"] == 3
    assert store.resolve("1")[0] == 302
    clock[0] += 86400
    assert store.resolve("1")[0] == 302
    assert store.analytics("1") == {"code": "1", "clicks": 5, "daily": {"2024-01-01": 1, "2024-01-02": 1}}
    store.close()
    reopened = Store(database)
    assert reopened.analytics("1")["daily"] == {"2024-01-01": 1, "2024-01-02": 1}
    reopened.close()
"""
EXPIRATION_TEST = """
def test_expiration(tmp_path):
    import sqlite3

    database = str(tmp_path / "expiry.sqlite")
    old = sqlite3.connect(database)
    old.execute("CREATE TABLE links (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0)")
    old.execute("INSERT INTO links(url) VALUES ('https://example.org/old')")
    old.commit()
    old.close()
    clock = [1000]
    store = Store(database, clock=lambda: clock[0])
    code = store.create("https://example.org/new", ttl=10)
    assert store.resolve(code)[0] == 302
    clock[0] += 10
    assert store.resolve(code)[0] == POLICY["expired_status"]
    if POLICY["delete_on_access"]:
        assert store.analytics(code) is None
    else:
        assert store.analytics(code)["clicks"] == 1
    assert store.resolve("1") == (302, "https://example.org/old")
    if POLICY["mandatory"] and POLICY["default_ttl"] is None:
        with pytest.raises(ValueError):
            store.create("https://example.org/missing")
    else:
        default = store.create("https://example.org/default")
        clock[0] += 4000
        assert store.resolve(default)[0] == (302 if POLICY["default_ttl"] is None else POLICY["expired_status"])
    with pytest.raises(ValueError):
        store.create("https://example.org/invalid", ttl=-1)
    store.close()
    reopened = Store(database, clock=lambda: clock[0])
    assert reopened.resolve("1")[0] == 302
    assert reopened.resolve(code)[0] == (404 if POLICY["delete_on_access"] else POLICY["expired_status"])
    reopened.close()
"""


def test_bundle(requirement):
    scenario = mode(requirement["original_text"])
    extension = (
        DAILY_TEST if scenario == "daily" else EXPIRATION_TEST if scenario == "expiration" else ""
    )
    source = (
        _template("test_url_shortener.py.txt")
        .replace("__FEATURE_TESTS__", extension)
        .replace("__EXPIRATION_POLICY__", repr(expiration_policy(requirement)))
    )
    trace = {
        f"AC{i}": ["tests/test_url_shortener.py::" + test]
        for i, (_, _, test) in enumerate(CRITERIA, 1)
    }
    trace["AC8"] += ["tests/test_url_shortener.py::test_invalid_url"]
    trace["AC7"] += ["tests/test_url_shortener.py::test_store_failure"]
    if extension:
        trace["AC12"] = ["tests/test_url_shortener.py::test_" + scenario]
    return dict(
        files={"tests/test_url_shortener.py": source},
        change_summary="Independent deterministic HTTP/persistence acceptance tests",
        criterion_tests=trace,
    )


def review(role, context):
    artifact = context["artifact"]["content"]
    problems = []
    if role == "architecture_reviewer":
        if ARCHITECTURE_SECTIONS - artifact["sections"].keys():
            problems.append("Required architecture sections missing")
    else:
        code, tests = artifact["code"], artifact["tests"]
        required = {"url_shortener.py", "pyproject.toml", "README.md"}
        if required - code["files"].keys():
            problems.append("Required source/build/document files missing")
        if "tests/test_url_shortener.py" not in tests["files"]:
            problems.append("Expected independent acceptance tests missing")
        if code.get("deviations") or tests.get("deviations"):
            problems.append("Unresolved design deviations")
        if set(tests["criterion_tests"]) != set(context["slice"]["acceptance_criteria"]):
            problems.append("Acceptance coverage incomplete")
        if any(name.startswith("tests/") or name.endswith(".env") for name in code["files"]):
            problems.append("Forbidden production file ownership")
    findings = [
        dict(
            id=f"DEMO-{i}",
            category="deterministic-review",
            severity="HIGH",
            description=problem,
            rationale="Explicit fixture contract violation",
            affected_component="candidate",
            suggested_resolution="Restore the declared fixture contract",
        )
        for i, problem in enumerate(problems, 1)
    ]
    return dict(complete=not problems, findings=findings)


def failure_analysis(context):
    latest = {value["tool"]: value for value in context["tool_results"].values()}
    results = [value for value in latest.values() if value.get("exit_status") != 0]
    output = json.dumps(results).lower()
    if any(
        fragment in output
        for fragment in (
            "no module named",
            "filenotfounderror",
            "command timed out",
            "permissionerror",
            "access is denied",
        )
    ):
        category = "ENVIRONMENT_OR_TOOLING"
    elif "importerror" in output:
        category = "DESIGN_DEFECT"
    elif (
        "assertionerror" in output
        or "failed" in output
        or any(result.get("tool") == "lint" for result in results)
    ):
        category = "IMPLEMENTATION_DEFECT"
    else:
        category = "ENVIRONMENT_OR_TOOLING"
    failed = results[0] if results else {}
    lines = failed.get("output_summary", "").splitlines()
    detail = next(
        (
            line.strip()
            for line in lines
            if any(
                term in line.lower()
                for term in (
                    "permissionerror",
                    "no module named",
                    "importerror",
                    "assertionerror",
                    "command timed out",
                )
            )
        ),
        next((line.strip() for line in lines if line.strip()), "No failed output available"),
    )
    return dict(
        category=category,
        evidence=["Failed saved tool results: " + json.dumps(results)],
        reasoning=f"{category}: {failed.get('tool', 'tool')} exited {failed.get('exit_status', 'unknown')}: {detail[:350]}. Correct the reported cause before retrying.",
    )


def impact(context):
    repository = context["repository"]
    if "url_shortener.py" not in repository:
        raise ValueError("Brownfield demo requires the generated URL-shortener source directory")
    tree = ast.parse(repository["url_shortener.py"])
    names = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
    if (
        not {"Store", "create_server"} <= names
        or "daily_clicks" not in repository["url_shortener.py"]
    ):
        raise ValueError("Source is outside the bounded deterministic brownfield template contract")
    return dict(
        affected_modules=[
            name
            for name in ("url_shortener.py", "tests/test_url_shortener.py", "README.md")
            if name in repository
        ],
        services=["Local HTTPServer"],
        apis=["GET /links/{code}/analytics adds daily UTC counts"],
        data_flows=[
            "Successful redirect -> SQLite total + UTC daily count transaction -> analytics read"
        ],
        persistence_impact="Create daily_clicks table if missing; preserve links and historical total counts.",
        test_impact="Keep existing HTTP/restart regression tests and add UTC-date aggregation/migration test.",
        configuration_impact="Enable daily analytics; retain database/port invocation.",
        backward_compatibility="Existing routes and total clicks remain unchanged; pre-upgrade clicks have no daily attribution.",
        migration_requirements="Additive CREATE TABLE IF NOT EXISTS on opening the prior database; back up before upgrade.",
        regression_risk="Losing old counts or double-counting in daily update; tested with prior schema and restart.",
    )


def generate(role, context):
    if role == "requirement":
        return requirement_analysis(context)
    if role.endswith("reviewer"):
        return review(role, context)
    if role == "failure_analysis":
        return failure_analysis(context)
    if role == "brownfield_analysis":
        return impact(context)
    requirement = context["requirement"]["content"]
    if role == "architecture":
        if mode(requirement["original_text"]) == "expiration":
            expiration_policy(requirement)
        return architecture(requirement)
    if role == "planning_design":
        return plan(requirement)
    if role == "coding":
        return production_bundle(requirement, context)
    if role == "test_design":
        return test_bundle(requirement)
    if role == "release_readiness":
        return dict(
            sections={
                "engineering_summary": requirement["normalized_requirement"],
                "setup": "Install wheel or run python -m url_shortener from application directory. No service credentials.",
                "api": "POST /links; GET /r/{code}; GET /links/{code}/analytics; GET /health.",
                "configuration": "--database links.sqlite --port 8000; bind loopback; selected fixture policy is declared in source.",
                "architecture": "Single-process standard-library HTTPServer and SQLite Store; synchronous transactions.",
                "adrs": "ADR-001 chooses existing standard-library tools over additional framework dependencies.",
                "tests": "Independent actual HTTP tests, SQLite restart and selected extension migration tests; consult saved JUnit/tool results, not model assertions.",
                "operations": "Start locally, check /health, back up SQLite before upgrade; health is liveness only.",
                "known_risks": "No auth, abuse controls, DNS validation or production HTTP server; local prototype only.",
                "release_notes": "Deterministic URL-shortener scenario: "
                + mode(requirement["original_text"]),
                "rollback": "Restore prior approved code and matching database backup; no automated rollback/deployment.",
                "limitations": "Bounded template workers, not LLM generation or arbitrary-repository modification; no production scalability claim.",
                "tradeoffs": "Offline reproducibility and small surface over general generation; old clicks cannot be assigned historical daily buckets.",
                "deployment": "Final explicit human approval records READY_FOR_DEPLOYMENT; does not deploy.",
                "packaging": "Actual wheel build follows this report; final evidence gate and human approval precede readable folder/ZIP export.",
            }
        )
    raise ValueError(f"Unsupported URL demo role: {role}")
