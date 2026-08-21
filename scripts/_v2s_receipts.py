#!/usr/bin/env python3
"""Bounded LibTV download receipts and candidate-source validation."""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from _v2s_common import (
    Video2SpriteError,
    atomic_write_json,
    fingerprint,
    sha256_file,
    utc_now,
)


LIBTV_RECEIPT_SCHEMA_VERSION = 1
LIBTV_RECEIPT_TYPE = "libtv_watermark_free_download"
LIBTV_RECEIPT_ISSUER = "sloth-codex-video2sprite-skill"
LIBTV_RECEIPT_FILENAME = "source.receipt.json"
MAX_LIBTV_RECEIPT_BYTES = 64 * 1024
MAX_LIBTV_VERSION_CHARS = 96
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUIRED_LIBTV_FLAGS = {
    "without_ai_watermark": True,
    "vip": True,
}
LIBTV_REFERENCE_AUDIT_MODES = {
    "no-libtv-ancestors",
    "verified-libtv-ancestors",
}
MAX_LIBTV_REFERENCE_ANCESTORS = 16
LIBTV_PROOF_SCOPE = {
    "download_flags_and_artifact_identity": True,
    "visual_watermark_absence": False,
}


def libtv_receipt_sidecar_path(artifact_path: Path) -> Path:
    """Return the deterministic receipt path beside a wrapper download."""
    return artifact_path.with_name(f"{artifact_path.name}.libtv-receipt.json")


def _bounded_version(raw: str) -> str:
    text = " ".join(str(raw).split())[:MAX_LIBTV_VERSION_CHARS]
    if not text:
        raise Video2SpriteError("LibTV version output is empty")
    return text


def _reference_hash(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return fingerprint({"opaque_reference": str(value)})


def write_libtv_receipt(
    artifact_path: Path,
    receipt_path: Path,
    *,
    libtv_version: str,
    node: str,
    project: Optional[str] = None,
    group: Optional[str] = None,
    reference_audit: str,
    reference_ancestors: Optional[Sequence[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Write a credential-free receipt bound to one downloaded artifact hash."""
    source = artifact_path.expanduser().resolve()
    if not source.is_file():
        raise Video2SpriteError("Cannot receipt a missing LibTV artifact")
    refs = {"node_sha256": _reference_hash(node)}
    if project is not None:
        refs["project_sha256"] = _reference_hash(project)
    if group is not None:
        refs["group_sha256"] = _reference_hash(group)
    ancestors = list(reference_ancestors or [])
    _validate_reference_audit(reference_audit, ancestors)
    receipt = {
        "schema_version": LIBTV_RECEIPT_SCHEMA_VERSION,
        "receipt_type": LIBTV_RECEIPT_TYPE,
        "issuer": LIBTV_RECEIPT_ISSUER,
        "created_at": utc_now(),
        "libtv_version": _bounded_version(libtv_version),
        "required_flags": dict(REQUIRED_LIBTV_FLAGS),
        "proof_scope": dict(LIBTV_PROOF_SCOPE),
        "artifact": {
            "filename": source.name[:255],
            "sha256": sha256_file(source),
            "bytes": source.stat().st_size,
        },
        "request_refs": refs,
        "reference_audit": {
            "status": reference_audit,
            "ancestors": ancestors,
        },
    }
    atomic_write_json(receipt_path, receipt)
    return validate_libtv_receipt(receipt_path, source)


def validate_libtv_reference_ancestors(
    source_paths: Sequence[Path],
    receipt_paths: Sequence[Path],
) -> List[Dict[str, str]]:
    """Validate and reduce LibTV-origin input lineage to bounded hashes."""
    if len(source_paths) != len(receipt_paths):
        raise Video2SpriteError(
            "Each LibTV reference ancestor source requires one matching receipt"
        )
    if len(source_paths) > MAX_LIBTV_REFERENCE_ANCESTORS:
        raise Video2SpriteError(
            f"At most {MAX_LIBTV_REFERENCE_ANCESTORS} LibTV reference ancestors are allowed"
        )
    ancestors: List[Dict[str, str]] = []
    for source, receipt in zip(source_paths, receipt_paths):
        validated = validate_libtv_receipt(receipt, source)
        ancestors.append(
            {
                "artifact_sha256": validated["artifact_sha256"],
                "receipt_sha256": validated["receipt_sha256"],
            }
        )
    return ancestors


def _validate_reference_audit(
    status: Any,
    ancestors: Any,
) -> None:
    if status not in LIBTV_REFERENCE_AUDIT_MODES:
        raise Video2SpriteError("LibTV receipt reference audit status is invalid")
    if not isinstance(ancestors, list):
        raise Video2SpriteError("LibTV receipt reference ancestors must be a list")
    if len(ancestors) > MAX_LIBTV_REFERENCE_ANCESTORS:
        raise Video2SpriteError("LibTV receipt has too many reference ancestors")
    if status == "no-libtv-ancestors" and ancestors:
        raise Video2SpriteError(
            "No LibTV reference ancestors may be recorded for no-libtv-ancestors"
        )
    if status == "verified-libtv-ancestors" and not ancestors:
        raise Video2SpriteError(
            "Verified LibTV reference lineage requires at least one ancestor receipt"
        )
    for ancestor in ancestors:
        if not isinstance(ancestor, dict) or set(ancestor) != {
            "artifact_sha256",
            "receipt_sha256",
        }:
            raise Video2SpriteError("LibTV receipt reference ancestor is invalid")
        for value in ancestor.values():
            if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
                raise Video2SpriteError("LibTV receipt reference ancestor hash is invalid")


def _load_bounded_receipt(path: Path) -> Dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise Video2SpriteError("LibTV receipt is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise Video2SpriteError("LibTV receipt must be a regular file, not a link")
    if metadata.st_size < 2 or metadata.st_size > MAX_LIBTV_RECEIPT_BYTES:
        raise Video2SpriteError(
            f"LibTV receipt must be between 2 and {MAX_LIBTV_RECEIPT_BYTES} bytes"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Video2SpriteError("LibTV receipt is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise Video2SpriteError("LibTV receipt must be a JSON object")
    return payload


def validate_libtv_receipt(
    receipt_path: Path,
    source_path: Path,
) -> Dict[str, Any]:
    """Validate both mandatory flags and the exact local source hash/size."""
    receipt = receipt_path.expanduser().resolve()
    source = source_path.expanduser().resolve()
    if not source.is_file():
        raise Video2SpriteError("LibTV receipt source artifact is missing")
    payload = _load_bounded_receipt(receipt)
    if payload.get("schema_version") != LIBTV_RECEIPT_SCHEMA_VERSION:
        raise Video2SpriteError("Unsupported LibTV receipt schema version")
    if payload.get("receipt_type") != LIBTV_RECEIPT_TYPE:
        raise Video2SpriteError("LibTV receipt type is invalid")
    if payload.get("issuer") != LIBTV_RECEIPT_ISSUER:
        raise Video2SpriteError("LibTV receipt issuer is invalid")
    if payload.get("required_flags") != REQUIRED_LIBTV_FLAGS:
        raise Video2SpriteError(
            "LibTV receipt must prove both --without-ai-watermark and --vip"
        )
    if payload.get("proof_scope") != LIBTV_PROOF_SCOPE:
        raise Video2SpriteError("LibTV receipt proof scope is invalid")
    version = payload.get("libtv_version")
    if not isinstance(version, str) or not version or len(version) > MAX_LIBTV_VERSION_CHARS:
        raise Video2SpriteError("LibTV receipt version is invalid")
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise Video2SpriteError("LibTV receipt artifact binding is missing")
    expected_hash = artifact.get("sha256")
    expected_bytes = artifact.get("bytes")
    filename = artifact.get("filename")
    if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
        raise Video2SpriteError("LibTV receipt artifact hash is invalid")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes < 1
    ):
        raise Video2SpriteError("LibTV receipt artifact size is invalid")
    if (
        not isinstance(filename, str)
        or not filename
        or len(filename) > 255
        or Path(filename).name != filename
    ):
        raise Video2SpriteError("LibTV receipt artifact filename is invalid")
    actual_hash = sha256_file(source)
    actual_bytes = source.stat().st_size
    if actual_hash != expected_hash or actual_bytes != expected_bytes:
        raise Video2SpriteError("LibTV receipt does not match the source artifact hash and size")
    refs = payload.get("request_refs")
    if not isinstance(refs, dict) or not isinstance(refs.get("node_sha256"), str):
        raise Video2SpriteError("LibTV receipt node reference binding is missing")
    for label, value in refs.items():
        if label not in {"node_sha256", "project_sha256", "group_sha256"}:
            raise Video2SpriteError("LibTV receipt contains an unsupported reference field")
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            raise Video2SpriteError("LibTV receipt reference hash is invalid")
    reference_audit = payload.get("reference_audit")
    if not isinstance(reference_audit, dict) or set(reference_audit) != {
        "status",
        "ancestors",
    }:
        raise Video2SpriteError("LibTV receipt reference audit is missing")
    _validate_reference_audit(
        reference_audit.get("status"),
        reference_audit.get("ancestors"),
    )
    return {
        "receipt_type": LIBTV_RECEIPT_TYPE,
        "receipt_sha256": sha256_file(receipt),
        "libtv_version": version,
        "required_flags": dict(REQUIRED_LIBTV_FLAGS),
        "proof_scope": dict(LIBTV_PROOF_SCOPE),
        "reference_audit": {
            "status": reference_audit["status"],
            "ancestor_count": len(reference_audit["ancestors"]),
        },
        "artifact_sha256": actual_hash,
        "artifact_bytes": actual_bytes,
    }


def validate_candidate_source(
    candidate_path: Path,
    candidate: Dict[str, Any],
    *,
    allow_legacy: bool = False,
) -> Dict[str, Any]:
    """Validate source provenance before processing, approval, or packaging."""
    source_metadata = candidate.get("source")
    if not isinstance(source_metadata, dict):
        raise Video2SpriteError("Candidate source metadata is missing")
    source = candidate_path / "source.mp4"
    if not source.is_file():
        raise Video2SpriteError("Candidate source video is missing")
    recorded_hash = source_metadata.get("sha256")
    actual_hash = sha256_file(source)
    if not isinstance(recorded_hash, str) or recorded_hash != actual_hash:
        raise Video2SpriteError("Candidate source video hash does not match candidate.json")
    recorded_bytes = source_metadata.get("bytes")
    if recorded_bytes is not None and recorded_bytes != source.stat().st_size:
        raise Video2SpriteError("Candidate source video size does not match candidate.json")
    origin = source_metadata.get("origin")
    receipt_metadata = source_metadata.get("receipt")
    receipt_path = candidate_path / LIBTV_RECEIPT_FILENAME
    if origin is None:
        if receipt_metadata is not None or receipt_path.exists():
            raise Video2SpriteError(
                "Candidate source origin is missing while LibTV receipt evidence exists"
            )
        if not allow_legacy:
            raise Video2SpriteError(
                "Candidate source origin is missing; reattach with --source-origin"
            )
        return {
            "origin": "legacy",
            "source_sha256": actual_hash,
            "source_bytes": source.stat().st_size,
            "receipt": None,
        }
    if origin not in {"local", "provider", "libtv"}:
        raise Video2SpriteError("Candidate source origin is invalid")
    if origin != "libtv":
        if receipt_metadata is not None or receipt_path.exists():
            raise Video2SpriteError("Only a LibTV source may carry a LibTV receipt")
        return {
            "origin": origin,
            "source_sha256": actual_hash,
            "source_bytes": source.stat().st_size,
            "receipt": None,
        }
    if not isinstance(receipt_metadata, dict):
        raise Video2SpriteError("LibTV candidate source receipt metadata is missing")
    if receipt_metadata.get("path") != LIBTV_RECEIPT_FILENAME:
        raise Video2SpriteError("LibTV candidate receipt path is invalid")
    validated = validate_libtv_receipt(receipt_path, source)
    if receipt_metadata.get("sha256") != validated["receipt_sha256"]:
        raise Video2SpriteError("LibTV candidate receipt hash does not match candidate.json")
    for label in (
        "receipt_type",
        "required_flags",
        "proof_scope",
        "reference_audit",
    ):
        if receipt_metadata.get(label) != validated[label]:
            raise Video2SpriteError("LibTV candidate receipt summary does not match the receipt")
    return {
        "origin": origin,
        "source_sha256": actual_hash,
        "source_bytes": source.stat().st_size,
        "receipt": validated,
    }
