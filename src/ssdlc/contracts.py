"""Check shared Python API declarations without importing generated code."""

import ast
from pathlib import PurePosixPath


class ContractError(ValueError):
    """A shared API is absent, incomplete, or inconsistent with a bundle."""


def declarations(source):
    tree = ast.parse(source)
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def signature(node):
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    required = len(positional) - len(args.defaults)
    return (
        isinstance(node, ast.AsyncFunctionDef),
        tuple(
            (arg.arg, i < len(args.posonlyargs), i < required) for i, arg in enumerate(positional)
        ),
        args.vararg.arg if args.vararg else None,
        tuple(
            (arg.arg, default is None) for arg, default in zip(args.kwonlyargs, args.kw_defaults)
        ),
        args.kwarg.arg if args.kwarg else None,
    )


def fields(node):
    return {
        item.target.id: item
        for item in node.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    }


def validate_contract(contract):
    if not contract:
        raise ContractError(
            "Plan needs api_contract: exact Python file paths and public declaration stubs, "
            "including constructors, injected collaborators, response types and store errors."
        )
    count = 0
    for path, source in contract.items():
        name = PurePosixPath(path)
        if name.is_absolute() or ".." in name.parts or "\\" in path or name.suffix != ".py":
            raise ContractError(f"Invalid API contract Python path: {path}")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ContractError(
                f"API contract syntax invalid in {path}, line {exc.lineno}"
            ) from None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = {ast.unparse(base) for base in node.bases}
                abstract_or_error = any(
                    base
                    in {
                        "Protocol",
                        "typing.Protocol",
                        "ABC",
                        "Exception",
                        "BaseException",
                        "Enum",
                        "IntEnum",
                        "StrEnum",
                        "enum.Enum",
                    }
                    or base.endswith("Error")
                    for base in bases
                )
                if (
                    not abstract_or_error
                    and not fields(node)
                    and not any(
                        isinstance(member, ast.FunctionDef) and member.name == "__init__"
                        for member in node.body
                    )
                ):
                    raise ContractError(
                        f"API contract {path}:{node.name} needs an explicit constructor "
                        "or declared data fields; do not leave construction unspecified"
                    )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                ):
                    if isinstance(body[0].value.value, str):
                        body = body[1:]
                if not body or any(
                    not (
                        isinstance(item, ast.Pass)
                        or isinstance(item, ast.Expr)
                        and isinstance(item.value, ast.Constant)
                        and item.value.value is Ellipsis
                    )
                    for item in body
                ):
                    raise ContractError(
                        f"API contract {path} must contain declarations, not function implementations"
                    )
        count += len(declarations(source))
    if not count:
        raise ContractError("API contract must declare a public function or class")


def validate_implementation(contract, files):
    """Reject API drift before review; declarations never execute."""
    validate_contract(contract)
    for path, source in contract.items():
        expected = declarations(source)
        if not expected:
            continue
        if path not in files:
            raise ContractError(f"Implementation is missing declared API file {path}")
        try:
            actual = declarations(files[path])
        except SyntaxError as exc:
            raise ContractError(
                f"Implementation syntax invalid in {path}, line {exc.lineno}"
            ) from None
        for name, declaration in expected.items():
            implementation = actual.get(name)
            if implementation is None or type(implementation) is not type(declaration):
                raise ContractError(f"Implementation must declare {path}:{name}")
            if isinstance(declaration, ast.ClassDef):
                expected_members = declarations(
                    ast.unparse(ast.Module(body=declaration.body, type_ignores=[]))
                )
                actual_members = declarations(
                    ast.unparse(ast.Module(body=implementation.body, type_ignores=[]))
                )
                for member, method in expected_members.items():
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        candidate = actual_members.get(member)
                        if (
                            candidate is None
                            or not isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef))
                            or signature(method) != signature(candidate)
                        ):
                            raise ContractError(f"API signature mismatch: {path}:{name}.{member}")
                if fields(declaration).keys() - fields(implementation).keys():
                    raise ContractError(f"API fields missing: {path}:{name}")
                for field, expected_field in fields(declaration).items():
                    if (expected_field.value is None) != (
                        fields(implementation)[field].value is None
                    ):
                        raise ContractError(f"API field default mismatch: {path}:{name}.{field}")
            elif signature(declaration) != signature(implementation):
                raise ContractError(f"API signature mismatch: {path}:{name}")


def validate_test_imports(contract, files):
    modules = {}
    for path, source in contract.items():
        parts = list(PurePosixPath(path).with_suffix("").parts)
        if parts[0] == "src":
            parts.pop(0)
        if parts[-1] == "__init__":
            parts.pop()
        symbols = set(declarations(source))
        for node in ast.parse(source).body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.add(node.target.id)
            elif isinstance(node, ast.Assign):
                symbols.update(target.id for target in node.targets if isinstance(target, ast.Name))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                symbols.update(
                    alias.asname or alias.name for alias in node.names if alias.name != "*"
                )
        modules[".".join(parts)] = symbols
    roots = {module.split(".")[0] for module in modules}
    for path, source in files.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ContractError(f"Test syntax invalid in {path}, line {exc.lineno}") from None
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and not node.level and node.module:
                module = node.module
                if module.split(".")[0] not in roots:
                    continue
                if module not in modules or any(
                    alias.name not in modules[module] for alias in node.names
                ):
                    raise ContractError(
                        f"Test import outside shared API contract: {path}: {module}"
                    )
