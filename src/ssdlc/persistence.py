"""Append-only audit and immutable artifact content, with mutable active pointers."""

import hashlib
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ssdlc.models import Artifact, AuditEvent, Validity
from ssdlc.tools import safe_path


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Repository:
    """SQLite stores state and indexes; immutable artifact bytes live in files."""

    def __init__(self, path: Path, artifact_root: Path | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root = (artifact_root or path.parent / "artifacts").resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.RLock()
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS artifacts (
                workflow TEXT, ref TEXT, payload TEXT, PRIMARY KEY(workflow, ref));
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE,
                workflow TEXT, payload TEXT, previous_hash TEXT, hash TEXT);
            CREATE TABLE IF NOT EXISTS operations (
                workflow TEXT, key TEXT, payload TEXT, PRIMARY KEY(workflow, key));
            CREATE TABLE IF NOT EXISTS leases (
                workflow TEXT PRIMARY KEY, owner TEXT);
        """)
        self.connection.commit()
        self._migrate_embedded_artifacts()

    def _artifact_relative_path(self, workflow: str, artifact: Artifact) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", workflow):
            raise ValueError("Invalid workflow ID for artifact storage")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", artifact.kind):
            raise ValueError("Invalid artifact kind for file storage")
        identifier = hashlib.sha256(artifact.id.encode()).hexdigest()[:16]
        return Path(
            workflow, "artifacts", artifact.kind, identifier, f"v{artifact.version:04d}.json"
        )

    def _write_artifact_file(self, workflow: str, artifact: Artifact) -> str:
        relative = self._artifact_relative_path(workflow, artifact)
        path = safe_path(self.artifact_root, relative.as_posix())
        data = (
            canonical(
                {
                    "id": artifact.id,
                    "version": artifact.version,
                    "kind": artifact.kind,
                    "content": artifact.content,
                    "dependencies": artifact.dependencies,
                    "digest": artifact.digest,
                }
            )
            + "\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_text(encoding="utf-8") != data:
                raise ValueError(f"Artifact file is immutable and differs from {artifact.ref}")
        else:
            temporary = path.with_name(path.name + f".{threading.get_ident()}.tmp")
            temporary.write_text(data, encoding="utf-8")
            try:
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

        # Raw source and test files stay reviewable beside their versioned JSON.
        if artifact.kind in {"code", "tests"}:
            files = artifact.content.get("files", {})
            for name, content in files.items():
                target = safe_path(path.with_suffix("") / "files", name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_text(encoding="utf-8") != content:
                    raise ValueError(f"Artifact source file is immutable: {name}")
                if not target.exists():
                    target.write_text(content, encoding="utf-8")
        elif isinstance(artifact.content.get("sections"), dict):
            lines = [
                f"# {artifact.kind.replace('_', ' ').title()} — {artifact.id} v{artifact.version}\n"
            ]
            lines.append(f"\nArtifact: `{artifact.ref}`  \nDigest: `{artifact.digest}`\n")
            for key, value in artifact.content["sections"].items():
                lines.extend([f"\n## {key.replace('_', ' ').title()}\n", str(value).rstrip(), "\n"])
            markdown = path.with_suffix(".md")
            rendered = "\n".join(lines)
            if markdown.exists() and markdown.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Artifact document is immutable: {artifact.ref}")
            if not markdown.exists():
                markdown.write_text(rendered, encoding="utf-8")
        return relative.as_posix()

    def _metadata_payload(self, artifact: Artifact, content_file: str) -> str:
        data = artifact.model_dump(mode="json", exclude={"content"})
        data["content_file"] = content_file
        return canonical(data)

    def _migrate_embedded_artifacts(self):
        """Move legacy SQLite artifact bodies to immutable workspace files once."""
        rows = self.connection.execute("SELECT workflow,ref,payload FROM artifacts").fetchall()
        for workflow, ref, payload in rows:
            value = json.loads(payload)
            if "content_file" in value:
                continue
            artifact = Artifact.model_validate(value)
            relative = self._write_artifact_file(workflow, artifact)
            with self.connection:
                self.connection.execute(
                    "UPDATE artifacts SET payload=? WHERE workflow=? AND ref=?",
                    (self._metadata_payload(artifact, relative), workflow, ref),
                )

    def close(self):
        self.connection.close()

    def acquire(self, workflow: str, owner: str):
        with self.lock, self.connection:
            try:
                self.connection.execute("INSERT INTO leases VALUES (?,?)", (workflow, owner))
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(
                    "Workflow is in use; recover a stale lease only after confirming its process stopped"
                ) from exc

    def release(self, workflow: str, owner: str):
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM leases WHERE workflow=? AND owner=?", (workflow, owner)
            )

    def record(self, event: AuditEvent):
        payload = event.model_dump_json()
        with self.lock, self.connection:
            if self.connection.execute(
                "SELECT 1 FROM events WHERE event_id=?", (event.event_id,)
            ).fetchone():
                return
            row = self.connection.execute(
                "SELECT hash FROM events WHERE workflow=? ORDER BY seq DESC LIMIT 1",
                (event.workflow_id,),
            ).fetchone()
            previous = row[0] if row else ""
            chain = hashlib.sha256((previous + payload).encode()).hexdigest()
            self.connection.execute(
                "INSERT INTO events(event_id,workflow,payload,previous_hash,hash) VALUES (?,?,?,?,?)",
                (event.event_id, event.workflow_id, payload, previous, chain),
            )

    def events(self, workflow: str) -> list[dict]:
        with self.lock:
            return [
                json.loads(row[0])
                for row in self.connection.execute(
                    "SELECT payload FROM events WHERE workflow=? ORDER BY seq", (workflow,)
                )
            ]

    def verify_audit(self, workflow: str) -> bool:
        previous = ""
        with self.lock:
            for payload, prev, chain in self.connection.execute(
                "SELECT payload,previous_hash,hash FROM events WHERE workflow=? ORDER BY seq",
                (workflow,),
            ):
                if (
                    prev != previous
                    or hashlib.sha256((prev + payload).encode()).hexdigest() != chain
                ):
                    return False
                previous = chain
        return True

    def save_artifact(self, workflow: str, artifact: Artifact):
        expected_digest = digest(
            {"content": artifact.content, "dependencies": artifact.dependencies}
        )
        if artifact.digest != expected_digest:
            raise ValueError("Artifact content/dependency digest does not match")
        with self.lock:
            old = self.connection.execute(
                "SELECT payload FROM artifacts WHERE workflow=? AND ref=?", (workflow, artifact.ref)
            ).fetchone()
        if old and json.loads(old[0])["digest"] != artifact.digest:
            raise ValueError("Cannot mutate content of a persisted artifact version")
        relative = self._write_artifact_file(workflow, artifact)
        with self.lock, self.connection:
            old = self.connection.execute(
                "SELECT payload FROM artifacts WHERE workflow=? AND ref=?", (workflow, artifact.ref)
            ).fetchone()
            if old and json.loads(old[0])["digest"] != artifact.digest:
                raise ValueError("Cannot mutate content of a persisted artifact version")
            if old:
                old_meta = json.loads(old[0])
                if old_meta.get("content_file") != relative:
                    raise ValueError("Artifact version cannot change its content file")
            self.connection.execute(
                "INSERT INTO artifacts VALUES (?,?,?) ON CONFLICT(workflow,ref) DO UPDATE SET payload=excluded.payload",
                (workflow, artifact.ref, self._metadata_payload(artifact, relative)),
            )

    def artifact(self, workflow: str, ref: str) -> dict:
        with self.lock:
            row = self.connection.execute(
                "SELECT payload FROM artifacts WHERE workflow=? AND ref=?", (workflow, ref)
            ).fetchone()
        if not row:
            raise KeyError(f"Unknown artifact: {ref}")
        metadata = json.loads(row[0])
        artifact_metadata = {key: value for key, value in metadata.items() if key != "content_file"}
        relative = self._artifact_relative_path(
            workflow, Artifact.model_validate({**artifact_metadata, "content": {}})
        )
        path = safe_path(self.artifact_root, relative.as_posix())
        file_value = json.loads(path.read_text(encoding="utf-8"))
        if (
            file_value.get("id") != metadata["id"]
            or file_value.get("version") != metadata["version"]
        ):
            raise ValueError(f"Artifact file identity does not match {ref}")
        if metadata.get("content_file") != relative.as_posix():
            raise ValueError(f"Artifact index path does not match {ref}")
        result = {key: value for key, value in metadata.items() if key != "content_file"}
        result["content"] = file_value["content"]
        artifact = Artifact.model_validate(result)
        if artifact.digest != file_value.get("digest") or artifact.digest != digest(
            {"content": artifact.content, "dependencies": artifact.dependencies}
        ):
            raise ValueError(f"Artifact content integrity check failed: {ref}")
        return artifact.model_dump(mode="json")

    def cache(self, workflow: str, key: str, payload: dict, *, replace=False):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", workflow) or not re.fullmatch(
            r"[0-9a-f]{64}", key
        ):
            raise ValueError("Invalid provider cache reference")
        content_digest = digest(payload)
        # A repaired response gets its own immutable file; the old bytes remain
        # available as evidence while the operation's index points to the repair.
        relative = Path(workflow, "provider-cache", key, f"{content_digest}.json")
        path = safe_path(self.artifact_root, relative.as_posix())
        serialized = canonical(payload) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") != serialized:
            raise ValueError("Cached provider output is immutable")
        if not path.exists():
            path.write_text(serialized, encoding="utf-8")
        with self.lock, self.connection:
            existing = self.connection.execute(
                "SELECT payload FROM operations WHERE workflow=? AND key=?", (workflow, key)
            ).fetchone()
            if existing and not replace:
                old = json.loads(existing[0])
                old_digest = old.get("digest") if "cache_file" in old else digest(old)
                if old_digest != content_digest:
                    raise ValueError("Cached provider output is immutable")
            self.connection.execute(
                "INSERT INTO operations VALUES (?,?,?) ON CONFLICT(workflow,key) DO UPDATE SET payload=excluded.payload",
                (
                    workflow,
                    key,
                    canonical({"cache_file": relative.as_posix(), "digest": content_digest}),
                ),
            )

    def cached(self, workflow: str, key: str) -> dict | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT payload FROM operations WHERE workflow=? AND key=?", (workflow, key)
            ).fetchone()
        if not row:
            return None
        index = json.loads(row[0])
        if "cache_file" not in index:
            # Migrate embedded legacy outputs without discarding their content.
            self.cache(workflow, key, index)
            return index
        relative = Path(workflow, "provider-cache", key, f"{index.get('digest')}.json")
        legacy_relative = Path(workflow, "provider-cache", f"{key}.json")
        if index["cache_file"] == legacy_relative.as_posix():
            relative = legacy_relative
        elif index["cache_file"] != relative.as_posix():
            raise ValueError("Provider-cache index path mismatch")
        path = safe_path(self.artifact_root, relative.as_posix())
        payload = json.loads(path.read_text(encoding="utf-8"))
        if digest(payload) != index.get("digest"):
            raise ValueError(f"Provider cache integrity check failed for {key}")
        return payload


def descendants(artifacts: dict[str, dict], roots: set[str]) -> set[str]:
    affected = set(roots)
    while True:
        more = {
            ref for ref, value in artifacts.items() if affected.intersection(value["dependencies"])
        }
        if more.issubset(affected):
            return affected - roots
        affected |= more


def invalidate(artifacts: dict[str, dict], roots: set[str]) -> dict[str, dict]:
    updates = {}
    for ref in descendants(artifacts, roots):
        value = artifacts[ref].copy()
        if value["validity"] == Validity.SUPERSEDED:
            continue
        value["validity"] = (
            Validity.REVALIDATE
            if value["kind"] in {"plan", "architecture"}
            else Validity.INVALIDATED
        )
        updates[ref] = value
    return updates
