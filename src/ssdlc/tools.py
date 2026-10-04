"""Fixed Python tools and confined materialization. Not an OS sandbox."""

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

from ssdlc.models import ToolResult, uid


class ToolError(ValueError):
    pass


def safe_path(root: Path, name: str) -> Path:
    posix = PurePosixPath(name)
    if "\\" in name or ":" in name or posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise ToolError(f"Unsafe relative path: {name}")
    if any(
        p.lower() in {".git", ".env", ".aws", ".ssh", ".ssdlc", ".venv"} or p.startswith(".env.")
        for p in posix.parts
    ):
        raise ToolError("Protected path")
    target = root.joinpath(*posix.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ToolError("Path escapes workspace")
    for parent in [target, *target.parents]:
        if parent == root.parent:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ToolError("Symlinks and junctions are not permitted")
    if target.name.lower() in {"con", "nul", "aux", "prn"}:
        raise ToolError("Reserved filename")
    return target


def reject_secrets(text: str):
    patterns = [
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b",
    ]
    if any(re.search(pattern, text) for pattern in patterns):
        raise ToolError("Possible secret in content; remove it before submission")
    for key, value in os.environ.items():
        if (
            any(word in key.upper() for word in ("SECRET", "TOKEN", "API_KEY", "PASSWORD"))
            and len(value) >= 8
            and value in text
        ):
            raise ToolError("Environment credential detected in content")


def redact(text: str) -> str:
    for key, value in os.environ.items():
        if (
            any(word in key.upper() for word in ("SECRET", "TOKEN", "API_KEY", "PASSWORD"))
            and len(value) >= 8
        ):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{20,}\b", "[REDACTED]", text)
    return text[-16000:]


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            any(
                p in {"__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}
                or p.endswith(".egg-info")
                for p in relative.parts
            )
            or path.name == ".results.xml"
        ):
            continue
        if path.is_file():
            safe_path(root, relative.as_posix())
            h.update(relative.as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def publish_wheels(root: Path):
    """Keep wheel bytes, replacing build temp-file ACLs with folder inheritance.

    On Windows, a backend's secure temporary wheel can retain owner-only access
    when moved into dist. A normal new file inherits the workspace directory's
    permissions, including the operator who owns it. Do not copy file metadata.
    """
    for wheel in sorted((root / "dist").glob("*.whl")):
        source = safe_path(root, "dist/" + wheel.name)
        published = safe_path(root, f"dist/.wheel-{uid()}.tmp")
        try:
            with published.open("xb") as target:
                target.write(source.read_bytes())
            published.replace(source)
        finally:
            published.unlink(missing_ok=True)


class Executor:
    def __init__(
        self,
        workspace: Path,
        timeout: int = 60,
        enabled: bool = False,
    ):
        self.workspace = workspace.resolve()
        self.timeout = timeout
        self.enabled = enabled
        self.commands = {
            "lint": [sys.executable, "-m", "ruff", "check", "--isolated", "."],
            "static": [sys.executable, "-m", "compileall", "-q", "."],
            "test": [sys.executable, "-m", "pytest", "-q", "--junitxml=.results.xml"],
            "build": [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
        }

    def materialize(self, files: dict[str, str], key: str) -> Path:
        root = safe_path(self.workspace, f"candidates/{key}")
        root.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            reject_secrets(content)
            path = safe_path(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def run(self, tool: str, cwd: Path, refs: list[str]) -> ToolResult:
        if not self.enabled:
            raise ToolError(
                "Local execution disabled. Inspect generated artifacts and enable execution in a disposable environment."
            )
        if not cwd.resolve().is_relative_to(self.workspace) or cwd.is_symlink():
            raise ToolError("Execution directory outside configured workspace")
        command = list(self.commands[tool])
        # Keep each invocation away from shared Windows pytest/temp directories.
        # Outside the candidate: temporary output must not change its fingerprint.
        scratch = safe_path(self.workspace, f"tool-tmp/{uid()}")
        scratch.mkdir(parents=True, exist_ok=False)
        if tool == "test":
            command.extend(["--basetemp", str(scratch / "pytest")])
        reject_secrets(" ".join(command))
        allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT"}
        env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        env.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONNOUSERSITE": "1",
                "PIP_NO_INDEX": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "TEMP": str(scratch),
                "TMP": str(scratch),
                "TMPDIR": str(scratch),
            }
        )
        before = tree_digest(cwd)
        if tool == "test":
            report = safe_path(cwd, ".results.xml")
            report.unlink(missing_ok=True)
        start = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
            status, output = result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            status, output = 124, "Command timed out; no pass evidence produced"
        except OSError as exc:
            status, output = 127, type(exc).__name__
        if tool == "build" and status == 0 and sys.platform == "win32":
            try:
                publish_wheels(cwd)
            except OSError as exc:
                status = 1
                output += f"\nCannot publish readable build outputs: {type(exc).__name__}: {exc}"
        if tree_digest(cwd) != before:
            status, output = 125, output + "\nValidation modified tracked inputs; evidence rejected"
        return ToolResult(
            tool=tool,
            command=command,
            cwd=str(cwd),
            exit_status=status,
            duration=time.monotonic() - start,
            output_summary=redact(output),
            artifact_refs=refs,
            environment={"python": sys.version.split()[0], "platform": sys.platform},
            workspace_digest=before,
        )


def codebase_snapshot(root: Path, max_files: int = 100, max_bytes: int = 150000) -> dict[str, str]:
    files = {}
    size = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(
            p.startswith(".") or p in {"node_modules", "__pycache__", "dist", "build"}
            for p in rel.parts
        ):
            continue
        if path.is_file() and path.suffix in {
            ".py",
            ".go",
            ".java",
            ".md",
            ".toml",
            ".json",
            ".yaml",
        }:
            safe_path(root, rel.as_posix())
            if (
                path.stat().st_size > max_bytes
                or size + path.stat().st_size > max_bytes
                or len(files) >= max_files
            ):
                raise ToolError(
                    "Codebase exceeds prototype snapshot budget; provide a focused workspace"
                )
            content = path.read_text(encoding="utf-8")
            reject_secrets(content)
            files[rel.as_posix()] = content
            size += len(content.encode())
    return files
