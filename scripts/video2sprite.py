#!/usr/bin/env python3
"""Bounded-output CLI for image-to-video-to-sprite production."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from _v2s_common import (
    Video2SpriteError,
    action_processing_fingerprint,
    action_dir,
    atomic_write_bytes,
    atomic_write_json,
    candidate_processing_fingerprint,
    candidate_dir,
    copy_file_atomic,
    credential_source,
    credential_value,
    emit,
    ensure_runtime_outside_skill,
    fingerprint,
    load_json,
    load_presets,
    parse_hex_color,
    parse_size,
    require_executable,
    resolve_image_settings,
    resolve_video_settings,
    run_command,
    safe_identifier,
    sanitize,
    sha256_file,
    store_private_credential,
    strip_url_query,
    utc_now,
)
from _v2s_media import probe_media, process_candidate_media
from _v2s_receipts import (
    LIBTV_RECEIPT_FILENAME,
    LIBTV_REFERENCE_AUDIT_MODES,
    libtv_receipt_sidecar_path,
    validate_candidate_source,
    validate_libtv_receipt,
    validate_libtv_reference_ancestors,
    write_libtv_receipt,
)
from _v2s_providers import (
    download_provider_video,
    generate_openai_master,
    poll_ark_video,
    submit_ark_video,
)


SCHEMA_VERSION = 1
MAX_PROMPT_CHARS = 30_000
SUPPORTED_ENGINES = ("generic", "godot")
PROCESS_PROFILES = ("production", "draft")
DEFAULT_CANDIDATE_BUDGET = 2
DEFAULT_NETWORK_WORKERS = 4
DEFAULT_LOCAL_WORKERS = 2
MAX_ADVANCE_WAIT_SECONDS = 55.0
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
ARK_REFERENCE_ROLES = ("first_frame", "reference_image")
ARK_RESOLUTIONS = ("480p", "720p", "1080p", "4k")
ARK_RATIOS = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
KEY_MODES = ("border", "global")
PLACEMENT_MODES = ("fixed", "fit-union")
RESAMPLING_MODES = ("nearest", "lanczos")
LIBTV_MEDIA_SUFFIXES = frozenset(
    {".mp4", ".mov", ".m4v", ".webm", ".png", ".jpg", ".jpeg", ".webp"}
)


def _runtime_dir(raw: str) -> Path:
    return ensure_runtime_outside_skill(Path(raw))


def _load_run(run_dir: Path) -> Dict[str, Any]:
    spec = load_json(run_dir / "run.json")
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise Video2SpriteError(
            f"Unsupported run schema version: {spec.get('schema_version')}"
        )
    return spec


def _load_action(run_dir: Path, action_id: str) -> Dict[str, Any]:
    return load_json(action_dir(run_dir, action_id) / "action.json")


def _read_prompt(args: argparse.Namespace) -> str:
    if getattr(args, "prompt", None):
        prompt = str(args.prompt)
    elif getattr(args, "prompt_file", None):
        prompt_path = Path(args.prompt_file).expanduser().resolve()
        try:
            prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise Video2SpriteError(f"Prompt file does not exist: {prompt_path}") from exc
    else:
        raise Video2SpriteError("Provide --prompt or --prompt-file")
    prompt = prompt.strip()
    if not prompt:
        raise Video2SpriteError("Prompt must not be empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise Video2SpriteError(f"Prompt exceeds {MAX_PROMPT_CHARS} characters")
    return prompt


def _add_prompt_group(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt")
    group.add_argument("--prompt-file")


def _archive_approval(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    stamp = utc_now().replace(":", "-")
    archived = path.with_name(f"approval.stale.{stamp}.json")
    path.replace(archived)
    return archived.name


def _candidate_id_from_model(model_alias: str) -> str:
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}", model_alias):
        return model_alias
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", model_alias).strip("-._")[:64]
    slug = slug or "model"
    suffix = hashlib.sha256(model_alias.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{suffix}"


def _validate_chroma(
    key: str, threshold: float, softness: float, mode: str = "border"
) -> None:
    parse_hex_color(key)
    if mode not in KEY_MODES:
        raise Video2SpriteError(
            f"Matte key mode must be one of: {', '.join(KEY_MODES)}"
        )
    if threshold < 0.0 or threshold > 442.0:
        raise Video2SpriteError("Chroma threshold must be between 0 and 442")
    if softness <= 0.0 or softness > 442.0:
        raise Video2SpriteError(
            "Chroma softness must be greater than 0 and no more than 442"
        )


def _parse_pivot(raw: str, width: int, height: int) -> Dict[str, Any]:
    text = raw.strip().lower()
    if text == "bottom-center":
        x, y = width / 2.0, float(height)
    else:
        match = re.fullmatch(
            r"\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*",
            raw,
        )
        if not match:
            raise Video2SpriteError(
                "Pivot must be bottom-center or an X,Y coordinate such as 144,144"
            )
        x, y = float(match.group(1)), float(match.group(2))
    if x < 0.0 or x > width or y < 0.0 or y > height:
        raise Video2SpriteError(
            f"Pivot {x:g},{y:g} must fit inside the {width}x{height} frame"
        )
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "normalized": [round(x / width, 8), round(y / height, 8)],
    }


def _save_action(run_dir: Path, action: Dict[str, Any]) -> None:
    atomic_write_json(action_dir(run_dir, str(action["action_id"])) / "action.json", action)


def _register_candidate(
    run_dir: Path, action: Dict[str, Any], candidate_id: str
) -> None:
    candidates = [str(item) for item in action.get("candidates") or []]
    if candidate_id not in candidates:
        candidates.append(candidate_id)
        action["candidates"] = candidates
        action["updated_at"] = utc_now()
        _save_action(run_dir, action)


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise Video2SpriteError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise Video2SpriteError(f"{name} must be between {minimum} and {maximum}")
    return value


def _candidate_budget() -> int:
    return _bounded_env_int(
        "VIDEO2SPRITE_MAX_CANDIDATES_PER_ACTION",
        DEFAULT_CANDIDATE_BUDGET,
        minimum=1,
        maximum=20,
    )


def _processing_profile(raw: Optional[str]) -> str:
    profile = raw or os.getenv("VIDEO2SPRITE_PROCESS_PROFILE", "production")
    if profile not in PROCESS_PROFILES:
        raise Video2SpriteError(
            "VIDEO2SPRITE_PROCESS_PROFILE must be production or draft"
        )
    return profile


def _remote_candidate_count(run_dir: Path, action: Dict[str, Any]) -> int:
    count = 0
    action_id = str(action["action_id"])
    for candidate_id in action.get("candidates") or []:
        path = candidate_dir(run_dir, action_id, str(candidate_id)) / "candidate.json"
        if not path.is_file():
            continue
        candidate = load_json(path)
        if candidate.get("provider") != "local":
            count += 1
    return count


def _remote_pilot_gate(
    run_dir: Path,
    run: Dict[str, Any],
    *,
    requested_action_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Require one approved remote pilot before expanding to other actions."""
    remote_action_ids = set()
    approved_action_ids = set()
    remote_candidate_count = 0
    for record in _candidate_records(run_dir, run):
        candidate = record.get("candidate")
        if not candidate or candidate.get("provider") == "local":
            continue
        remote_candidate_count += 1
        action_id = str(record["action_id"])
        remote_action_ids.add(action_id)
        path = candidate_dir(run_dir, action_id, str(record["candidate_id"]))
        approval = _approval_state(path)
        if approval == {"decision": "approved", "valid": True}:
            approved_action_ids.add(action_id)
    same_pilot_action = (
        bool(requested_action_id) and requested_action_id in remote_action_ids
    )
    unlocked = (
        remote_candidate_count == 0
        or same_pilot_action
        or bool(approved_action_ids)
    )
    return {
        "unlocked": unlocked,
        "remote_candidate_count": remote_candidate_count,
        "pilot_action_ids": sorted(remote_action_ids),
        "approved_pilot_action_ids": sorted(approved_action_ids),
        "requested_action_is_existing_pilot": same_pilot_action,
    }


def _candidate_with_input_fingerprint(
    run_dir: Path, action: Dict[str, Any], input_fingerprint: str
) -> Optional[str]:
    action_id = str(action["action_id"])
    for candidate_id in action.get("candidates") or []:
        path = candidate_dir(run_dir, action_id, str(candidate_id)) / "candidate.json"
        if path.is_file() and load_json(path).get("input_fingerprint") == input_fingerprint:
            return str(candidate_id)
    return None


def _master_prompt(user_prompt: str, chroma_key: str) -> str:
    return (
        f"{user_prompt}\n\n"
        "Production constraints: create one canonical full-body 2D game character, "
        "one fixed view, fully visible with comfortable margins, stable proportions and "
        f"a flat unlit solid {chroma_key} extraction matte. No green screen unless that exact "
        "color was explicitly requested. Every required held prop must be physically connected "
        "to the correct hand or joined hands, with its handle visibly seated in the grip; no "
        "gap, floating weapon, detached grip, or ambiguous hand-to-handle relationship. Include "
        "only equipment explicitly required by the brief: no unrelated gun, holster, scabbard, "
        "sheath, pouch, backpack, or secondary prop. No scenery, floor, cast shadow, text, UI, "
        "border, motion sequence, sprite grid, or duplicate character."
    )


def _video_prompt(
    action: Dict[str, Any], *, reference_role: str = "first_frame"
) -> str:
    chroma = action.get("chroma") or {}
    key = chroma.get("key") or "#3f0050"
    sound = (
        "Generate synchronized dry action sound effects only: no music, voice, ambience, or reverb."
        if action.get("audio_required")
        else "Do not add music, voice, ambience, or camera sounds."
    )
    loop_text = (
        "The pose, foot-root, and velocity must return cleanly to the exact opening state for a seamless loop."
        if action.get("loop")
        else (
            "Begin with a very short readable hold, perform exactly one action, recover to the "
            "same foot-root and matching ready pose, then remain still. Do not repeat the action."
        )
    )
    reference_text = (
        "Use input image 1 as the exact opening frame and preserve it as the character identity anchor."
        if reference_role == "first_frame"
        else "Use input image 1 only as the sole character identity and visual-style reference."
    )
    return (
        f"{action['prompt']}\n\n"
        f"{reference_text} "
        "This is source footage for one 2D game-sprite action, not a cinematic shot. "
        "Sprite-source constraints: exactly one full-body character; preserve identity, outfit, "
        "palette, proportions, view, handedness, and props from the reference. Lock the camera "
        "and framing as an orthographic side-view stage. Keep the foot-root at one fixed image "
        "coordinate; body anticipation may compress and a strike may lunge, but the character "
        "must recover to the original root. No zoom, pan, shake, perspective shift, cuts, "
        "scenery, floor, cast shadow, text, subtitles, logo, watermark, UI, or extra characters. "
        f"Keep a perfectly flat, unlit, textureless solid {key} extraction matte for every frame; "
        "do not add a green screen, gradient, horizon, vignette, or colored rim light. "
        f"{loop_text} {sound}"
    )


def _effective_video_settings(
    run: Dict[str, Any],
    action: Dict[str, Any],
    *,
    provider: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> Dict[str, Any]:
    action_override = action.get("video") or {}
    run_default = (run.get("defaults") or {}).get("video") or {}
    return resolve_video_settings(
        provider=provider or action_override.get("provider") or run_default.get("provider"),
        model=model or action_override.get("model_alias") or run_default.get("model_alias"),
        base_url=base_url or action_override.get("base_url") or run_default.get("base_url"),
    )


def _validate_known_video_request(
    settings: Dict[str, Any],
    action: Dict[str, Any],
    args: argparse.Namespace,
) -> None:
    capabilities = settings.get("capabilities") or {}
    duration = float(action["duration_seconds"])
    duration_spec = capabilities.get("duration_seconds")
    if isinstance(duration_spec, dict):
        minimum = duration_spec.get("minimum")
        maximum = duration_spec.get("maximum")
        if isinstance(minimum, (int, float)) and duration < float(minimum):
            raise Video2SpriteError(
                f"Model {settings['model_alias']} requires duration >= {minimum} seconds"
            )
        if isinstance(maximum, (int, float)) and duration > float(maximum):
            raise Video2SpriteError(
                f"Model {settings['model_alias']} requires duration <= {maximum} seconds"
            )
        if duration_spec.get("integer_only") and not duration.is_integer():
            raise Video2SpriteError(
                f"Model {settings['model_alias']} requires an integer duration"
            )
    supported_resolutions = capabilities.get("resolutions")
    if (
        isinstance(supported_resolutions, list)
        and args.resolution not in supported_resolutions
    ):
        raise Video2SpriteError(
            f"Model {settings['model_alias']} does not support resolution {args.resolution}"
        )
    supported_ratios = capabilities.get("ratios")
    if isinstance(supported_ratios, list) and args.ratio not in supported_ratios:
        raise Video2SpriteError(
            f"Model {settings['model_alias']} does not support ratio {args.ratio}"
        )
    supported_roles = capabilities.get("reference_roles")
    if isinstance(supported_roles, list) and args.reference_role not in supported_roles:
        raise Video2SpriteError(
            f"Model {settings['model_alias']} does not support reference role {args.reference_role}"
        )
    if args.seed is not None and capabilities.get("supports_seed") is False:
        raise Video2SpriteError(
            f"Model {settings['model_alias']} does not support the seed parameter"
        )


def _resolve_submit_reference(
    run_dir: Path,
    run: Dict[str, Any],
    args: argparse.Namespace,
) -> tuple[Optional[str], Optional[Path], str]:
    reference_path: Optional[Path] = None
    reference_url = args.reference_url
    if args.reference_file:
        reference_path = Path(args.reference_file).expanduser().resolve()
        if not reference_path.is_file():
            raise Video2SpriteError(f"Reference image does not exist: {reference_path}")
        expected_hash = str((run.get("master") or {}).get("sha256") or "")
        actual_hash = sha256_file(reference_path)
        if not expected_hash or actual_hash != expected_hash:
            raise Video2SpriteError(
                "Local reference image must exactly match the canonical run master hash"
            )
        return None, reference_path, str(reference_path)
    if args.reference_url_env:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.reference_url_env):
            raise Video2SpriteError("Reference environment variable name is invalid")
        reference_url = os.getenv(args.reference_url_env)
        if not reference_url:
            raise Video2SpriteError(
                f"Reference environment variable is empty or missing: {args.reference_url_env}"
            )
    if not reference_url:
        reference_url = os.getenv("VIDEO2SPRITE_REFERENCE_URL")
    if not reference_url:
        canonical = (run_dir / str(run["master"]["path"])).resolve()
        raise Video2SpriteError(
            "Provide --reference-file "
            f"{canonical}, --reference-url, --reference-url-env, or VIDEO2SPRITE_REFERENCE_URL"
        )
    if reference_url.lstrip().lower().startswith("data:"):
        raise Video2SpriteError(
            "Use --reference-file for local media; inline data URLs are forbidden"
        )
    return reference_url, None, strip_url_query(reference_url)


def command_doctor(_args: argparse.Namespace) -> Dict[str, Any]:
    dependencies = {
        "pillow": importlib.util.find_spec("PIL") is not None,
        "numpy": importlib.util.find_spec("numpy") is not None,
        "ffmpeg": shutil.which(os.getenv("VIDEO2SPRITE_FFMPEG", "ffmpeg")) is not None,
        "ffprobe": shutil.which(os.getenv("VIDEO2SPRITE_FFPROBE", "ffprobe")) is not None,
    }
    image = resolve_image_settings()
    video = resolve_video_settings()
    openai_source = credential_source("OPENAI_API_KEY")
    ark_source = credential_source("ARK_API_KEY")
    return {
        "status": "ready" if all(dependencies.values()) else "missing_dependencies",
        "python": {
            "version": ".".join(str(item) for item in sys.version_info[:3]),
            "executable": sys.executable,
        },
        "dependencies": dependencies,
        "credentials": {
            "openai_configured": bool(credential_value("OPENAI_API_KEY")),
            "openai_source": openai_source,
            "ark_configured": bool(credential_value("ARK_API_KEY")),
            "ark_source": ark_source,
        },
        "defaults": {
            "image": {
                "provider": image["provider"],
                "model_alias": image["model_alias"],
                "model_id": image["model_id"],
            },
            "video": {
                "provider": video["provider"],
                "model_alias": video["model_alias"],
                "model_id": video["model_id"],
                "capabilities": video["capabilities"],
            },
        },
        "efficiency": {
            "process_profile": _processing_profile(None),
            "network_workers": _bounded_env_int(
                "VIDEO2SPRITE_NETWORK_WORKERS",
                DEFAULT_NETWORK_WORKERS,
                minimum=1,
                maximum=16,
            ),
            "local_workers": _bounded_env_int(
                "VIDEO2SPRITE_LOCAL_WORKERS",
                DEFAULT_LOCAL_WORKERS,
                minimum=1,
                maximum=8,
            ),
            "max_candidates_per_action": _candidate_budget(),
        },
    }


def command_models(_args: argparse.Namespace) -> Dict[str, Any]:
    presets = load_presets()
    image_models: List[Dict[str, Any]] = []
    for provider, spec in presets["image"]["providers"].items():
        for alias, model in spec.get("models", {}).items():
            image_models.append(
                {
                    "provider": provider,
                    "alias": alias,
                    "model_id": model["model_id"],
                    "capabilities": {
                        key: value for key, value in model.items() if key != "model_id"
                    },
                }
            )
    video_models: List[Dict[str, Any]] = []
    for provider, spec in presets["video"]["providers"].items():
        for alias, model in spec.get("models", {}).items():
            video_models.append(
                {
                    "provider": provider,
                    "alias": alias,
                    "model_id": model["model_id"],
                    "capabilities": {
                        key: value for key, value in model.items() if key != "model_id"
                    },
                }
            )
    return {
        "image_default": resolve_image_settings(),
        "video_default": resolve_video_settings(),
        "image_models": image_models,
        "video_models": video_models,
        "note": "Presets do not guarantee account entitlement; full model IDs are accepted.",
    }


def command_configure_key(args: argparse.Namespace) -> Dict[str, Any]:
    credential_name = {
        "ark": "ARK_API_KEY",
        "openai": "OPENAI_API_KEY",
    }[args.name]
    if args.from_env:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.from_env):
            raise Video2SpriteError("Credential environment variable name is invalid")
        value = os.getenv(args.from_env)
        if not value:
            raise Video2SpriteError(
                f"Credential environment variable is empty or missing: {args.from_env}"
            )
        source = "environment"
    else:
        if not sys.stdin.isatty():
            raise Video2SpriteError(
                "Interactive key entry requires a terminal; use --from-env VARIABLE"
            )
        value = getpass.getpass(f"Enter {credential_name} (input hidden): ")
        source = "interactive"
    try:
        path = store_private_credential(credential_name, value)
    finally:
        value = ""
    return {
        "credential_name": credential_name,
        "credential_source": source,
        "path": str(path),
        "directory_permissions": "0700",
        "file_permissions": "0600",
    }


def command_generate_master(args: argparse.Namespace) -> Dict[str, Any]:
    output = ensure_runtime_outside_skill(Path(args.output)).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise Video2SpriteError("Master output must use a .png filename")
    parse_hex_color(args.chroma_key)
    settings = resolve_image_settings(args.provider, args.model, args.base_url)
    if settings["provider"] != "openai":
        raise Video2SpriteError(
            f"Image provider adapter is not implemented: {settings['provider']}"
        )
    prompt = _master_prompt(_read_prompt(args), args.chroma_key)
    generation_fingerprint = fingerprint(
        {
            "schema_version": 1,
            "provider": settings["provider"],
            "model_id": settings["model_id"],
            "base_url": strip_url_query(settings["base_url"]),
            "prompt_sha256": fingerprint(prompt),
            "size": args.size,
            "quality": args.quality,
            "chroma_key": args.chroma_key.lower(),
        }
    )
    provenance_path = output.with_name(f"{output.name}.provenance.json")
    if output.exists() and not args.overwrite:
        if provenance_path.is_file():
            provenance = load_json(provenance_path)
            recorded_output = provenance.get("output") or {}
            if (
                provenance.get("generation_fingerprint") == generation_fingerprint
                and recorded_output.get("sha256") == sha256_file(output)
            ):
                return {
                    "output": str(output),
                    "sha256": recorded_output["sha256"],
                    "bytes": output.stat().st_size,
                    "provider": provenance.get("provider"),
                    "model_id": provenance.get("model_id"),
                    "request_id": provenance.get("request_id"),
                    "cached": True,
                }
        raise Video2SpriteError(
            f"Output already exists with different or unverifiable inputs: {output}; "
            "reuse the existing approved master or pass --overwrite for an intentional new billed image"
        )
    metadata = generate_openai_master(
        prompt=prompt,
        output_path=output,
        model_id=settings["model_id"],
        base_url=settings["base_url"],
        size=args.size,
        quality=args.quality,
    )
    provenance = {
        "schema_version": 1,
        "provider": metadata["provider"],
        "model_id": metadata["model_id"],
        "request_id": metadata.get("request_id"),
        "created": metadata.get("created"),
        "usage": metadata.get("usage") or {},
        "prompt_sha256": fingerprint(prompt),
        "generation_fingerprint": generation_fingerprint,
        "request": {
            "size": args.size,
            "quality": args.quality,
        },
        "chroma_key": args.chroma_key.lower(),
        "output": {
            "path": output.name,
            "sha256": metadata["sha256"],
            "bytes": metadata["bytes"],
        },
        "completed_at": metadata["completed_at"],
    }
    atomic_write_json(provenance_path, provenance)
    return {
        "output": str(output),
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "provider": metadata["provider"],
        "model_id": metadata["model_id"],
        "request_id": metadata.get("request_id"),
        "cached": False,
    }


def _normalize_master_to_png(source: Path, destination: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise Video2SpriteError(
            "Pillow is required to normalize the character master to PNG"
        ) from exc
    try:
        with Image.open(source) as image:
            normalized = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            buffer = io.BytesIO()
            normalized.save(buffer, format="PNG", optimize=True)
    except OSError as exc:
        raise Video2SpriteError(f"Cannot decode master image: {source}") from exc
    atomic_write_bytes(destination, buffer.getvalue())


def command_init(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    safe_identifier(args.character_id, "character ID")
    master_source = Path(args.master).expanduser().resolve()
    if not master_source.is_file():
        raise Video2SpriteError(f"Master image does not exist: {master_source}")
    if (run_dir / "run.json").exists():
        raise Video2SpriteError(f"Run is already initialized: {run_dir}")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise Video2SpriteError(f"Run directory is not empty: {run_dir}")
    width, height = parse_size(args.frame_size)
    _validate_chroma(
        args.chroma_key,
        args.chroma_threshold,
        args.chroma_softness,
        args.chroma_mode,
    )
    if args.placement not in PLACEMENT_MODES:
        raise Video2SpriteError(
            f"Placement must be one of: {', '.join(PLACEMENT_MODES)}"
        )
    if args.resampling not in RESAMPLING_MODES:
        raise Video2SpriteError(
            f"Resampling must be one of: {', '.join(RESAMPLING_MODES)}"
        )
    pivot = _parse_pivot(args.pivot, width, height)
    run_dir.mkdir(parents=True, exist_ok=True)
    master_destination = run_dir / "master" / "source.png"
    master_destination.parent.mkdir(parents=True, exist_ok=True)
    source_sha256 = sha256_file(master_source)
    _normalize_master_to_png(master_source, master_destination)
    image_settings = resolve_image_settings(
        args.image_provider, args.image_model, args.image_base_url
    )
    video_settings = resolve_video_settings(
        args.video_provider, args.video_model, args.video_base_url
    )
    run = {
        "schema_version": SCHEMA_VERSION,
        "character_id": args.character_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "master": {
            "path": "master/source.png",
            "sha256": sha256_file(master_destination),
            "source_sha256": source_sha256,
        },
        "frame_size": {"width": width, "height": height},
        "pivot": pivot,
        "placement": args.placement,
        "resampling": args.resampling,
        "chroma": {
            "key": args.chroma_key.lower(),
            "threshold": args.chroma_threshold,
            "softness": args.chroma_softness,
            "mode": args.chroma_mode,
        },
        "defaults": {
            "image": image_settings,
            "video": video_settings,
        },
        "actions": [],
    }
    atomic_write_json(run_dir / "run.json", run)
    return {
        "run_dir": str(run_dir),
        "character_id": args.character_id,
        "master_sha256": run["master"]["sha256"],
        "frame_size": run["frame_size"],
        "pivot": run["pivot"],
        "placement": run["placement"],
        "resampling": run["resampling"],
        "video_default": {
            "provider": video_settings["provider"],
            "model_alias": video_settings["model_alias"],
            "model_id": video_settings["model_id"],
        },
    }


def command_add_action(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    action_id = safe_identifier(args.action_id, "action ID")
    destination = action_dir(run_dir, action_id) / "action.json"
    if destination.exists():
        raise Video2SpriteError(f"Action already exists: {action_id}")
    prompt = _read_prompt(args)
    if args.duration <= 0 or args.duration > 60:
        raise Video2SpriteError("Duration must be greater than 0 and no more than 60 seconds")
    window_duration = args.window_duration or args.duration
    if args.window_start < 0 or window_duration <= 0:
        raise Video2SpriteError("Action window must have a non-negative start and positive duration")
    if args.window_start + window_duration > args.duration + 1e-9:
        raise Video2SpriteError("Action window must fit inside the requested video duration")
    if args.frames is not None:
        frame_count = int(args.frames)
        if frame_count < 1 or frame_count > 512:
            raise Video2SpriteError("Frames must be between 1 and 512")
        sampling = {
            "mode": "count",
            "fps": round(frame_count / window_duration, 8),
        }
    else:
        requested_fps = float(args.fps)
        if requested_fps <= 0.0 or requested_fps > 120.0:
            raise Video2SpriteError("FPS must be greater than 0 and no more than 120")
        frame_count = max(1, int(round(window_duration * requested_fps)))
        if frame_count > 512:
            raise Video2SpriteError(
                "The action window and FPS produce more than 512 frames"
            )
        sampling = {
            "mode": "fps",
            "requested_fps": round(requested_fps, 8),
            "fps": round(frame_count / window_duration, 8),
        }
    run_chroma = run.get("chroma") or {}
    chroma_key = args.chroma_key or run_chroma.get("key") or "#00ff00"
    chroma_mode = args.chroma_mode or run_chroma.get("mode") or "global"
    resolved_threshold = (
        args.chroma_threshold
        if args.chroma_threshold is not None
        else float(run_chroma.get("threshold", 42.0))
    )
    resolved_softness = (
        args.chroma_softness
        if args.chroma_softness is not None
        else float(run_chroma.get("softness", 36.0))
    )
    _validate_chroma(
        chroma_key, resolved_threshold, resolved_softness, chroma_mode
    )
    video_override: Dict[str, Any] = {}
    if args.provider or args.model or args.base_url:
        video_override = resolve_video_settings(
            provider=args.provider or (run.get("defaults") or {}).get("video", {}).get("provider"),
            model=args.model or (run.get("defaults") or {}).get("video", {}).get("model_alias"),
            base_url=args.base_url or (run.get("defaults") or {}).get("video", {}).get("base_url"),
        )
    action = {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "prompt": prompt,
        "prompt_sha256": fingerprint(prompt),
        "frame_count": frame_count,
        "sampling": sampling,
        "columns": args.columns,
        "duration_seconds": round(args.duration, 6),
        "window": {
            "start_seconds": round(args.window_start, 6),
            "duration_seconds": round(window_duration, 6),
        },
        "loop": bool(args.loop),
        "audio_required": bool(args.audio_required),
        "events": args.event or [],
        "chroma": {
            "key": chroma_key.lower(),
            "threshold": resolved_threshold,
            "softness": resolved_softness,
            "mode": chroma_mode,
        },
        "video": video_override,
        "candidates": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(destination, action)
    actions = [str(item) for item in run.get("actions") or []]
    actions.append(action_id)
    run["actions"] = actions
    run["updated_at"] = utc_now()
    atomic_write_json(run_dir / "run.json", run)
    return {
        "run_dir": str(run_dir),
        "action_id": action_id,
        "frame_count": frame_count,
        "fps": sampling["fps"],
        "duration_seconds": args.duration,
        "audio_required": bool(args.audio_required),
    }


def command_attach_video(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    _load_run(run_dir)
    action = _load_action(run_dir, args.action_id)
    candidate_id = safe_identifier(args.candidate, "candidate ID")
    source = Path(args.video).expanduser().resolve()
    if not source.is_file():
        raise Video2SpriteError(f"Video does not exist: {source}")
    source_origin = str(args.source_origin)
    receipt_summary = None
    if source_origin == "libtv":
        if not args.source_receipt:
            raise Video2SpriteError(
                "A LibTV source requires --source-receipt from libtv-download"
            )
        receipt_summary = validate_libtv_receipt(
            Path(args.source_receipt).expanduser().resolve(),
            source,
        )
    elif args.source_receipt:
        raise Video2SpriteError("--source-receipt is valid only with --source-origin libtv")
    source_probe = probe_media(
        source, ffprobe=os.getenv("VIDEO2SPRITE_FFPROBE", "ffprobe")
    )
    if not source_probe["video"]["present"]:
        raise Video2SpriteError("Attached media has no video stream")
    destination_dir = candidate_dir(run_dir, args.action_id, candidate_id)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "source.mp4"
    destination_receipt = destination_dir / LIBTV_RECEIPT_FILENAME
    candidate_path = destination_dir / "candidate.json"
    existing = load_json(candidate_path) if candidate_path.is_file() else {}
    existing_source = existing.get("source") or {}
    previous_hash = sha256_file(destination) if destination.is_file() else None
    incoming_hash = sha256_file(source)
    incoming_receipt_hash = (
        receipt_summary["receipt_sha256"] if receipt_summary else None
    )
    receipt_reused = (
        destination_receipt.is_file()
        and receipt_summary is not None
        and sha256_file(destination_receipt) == incoming_receipt_hash
    ) if receipt_summary else not destination_receipt.exists()
    reused = (
        previous_hash == incoming_hash
        and existing_source.get("origin") == source_origin
        and (existing_source.get("receipt") or {}).get("sha256")
        == incoming_receipt_hash
        and receipt_reused
    )
    approval_archived = None
    if not reused:
        approval_archived = _archive_approval(destination_dir / "approval.json")
        copy_file_atomic(source, destination)
        if receipt_summary:
            copy_file_atomic(
                Path(args.source_receipt).expanduser().resolve(),
                destination_receipt,
            )
        elif destination_receipt.exists():
            destination_receipt.unlink()
    source_record: Dict[str, Any] = {
        "path": "source.mp4",
        "origin": source_origin,
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "duration_seconds": source_probe["duration_seconds"],
        "audio_present": source_probe["audio"]["present"],
    }
    if receipt_summary:
        copied_summary = validate_libtv_receipt(destination_receipt, destination)
        source_record["receipt"] = {
            "path": LIBTV_RECEIPT_FILENAME,
            "sha256": copied_summary["receipt_sha256"],
            "receipt_type": copied_summary["receipt_type"],
            "required_flags": copied_summary["required_flags"],
            "proof_scope": copied_summary["proof_scope"],
            "reference_audit": copied_summary["reference_audit"],
        }
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "provider": existing.get("provider") or "local",
        "model_alias": existing.get("model_alias") or "attached-video",
        "model_id": existing.get("model_id") or "attached-video",
        "base_url": existing.get("base_url"),
        "capabilities": existing.get("capabilities")
        or {"native_audio": source_probe["audio"]["present"], "image_to_video": None, "tier": "local"},
        "status": (existing.get("status") or "ready") if reused else "ready",
        "source": source_record,
        "task_id": existing.get("task_id"),
        "created_at": existing.get("created_at") or utc_now(),
        "updated_at": utc_now(),
    }
    if reused:
        for field in ("qc_status", "processed_at", "artifacts", "downloaded_at"):
            if field in existing:
                candidate[field] = existing[field]
    atomic_write_json(candidate_path, candidate)
    _register_candidate(run_dir, action, candidate_id)
    return {
        "run_dir": str(run_dir),
        "action_id": args.action_id,
        "candidate_id": candidate_id,
        "status": candidate["status"],
        "source_sha256": candidate["source"]["sha256"],
        "source_origin": source_origin,
        "source_receipt_sha256": incoming_receipt_hash,
        "duration_seconds": source_probe["duration_seconds"],
        "audio_present": source_probe["audio"]["present"],
        "reused": reused,
        "approval_archived": approval_archived,
    }


def command_libtv_download(args: argparse.Namespace) -> Dict[str, Any]:
    """Run the official CLI with both no-watermark VIP flags and receipt it."""
    if float(args.timeout) < 1.0 or float(args.timeout) > 3600.0:
        raise Video2SpriteError("LibTV download timeout must be between 1 and 3600 seconds")
    ancestor_sources = [Path(item).expanduser().resolve() for item in args.ancestor_source or []]
    ancestor_receipts = [Path(item).expanduser().resolve() for item in args.ancestor_receipt or []]
    ancestors = validate_libtv_reference_ancestors(
        ancestor_sources,
        ancestor_receipts,
    )
    if args.reference_audit == "no-libtv-ancestors" and ancestors:
        raise Video2SpriteError(
            "no-libtv-ancestors forbids ancestor source/receipt pairs"
        )
    if args.reference_audit == "verified-libtv-ancestors" and not ancestors:
        raise Video2SpriteError(
            "verified-libtv-ancestors requires at least one ancestor source/receipt pair"
        )
    output_dir = _runtime_dir(args.output_dir)
    if output_dir.exists():
        if not output_dir.is_dir():
            raise Video2SpriteError("LibTV output path must be a directory")
        if any(output_dir.iterdir()):
            raise Video2SpriteError(
                "LibTV output directory must be new or empty for one bounded artifact"
            )
    else:
        output_dir.mkdir(parents=True)
    executable = require_executable(args.libtv or os.getenv("LIBTV_BIN", "libtv"))
    version_result = run_command([executable, "--version"], timeout=30.0)
    command = [
        executable,
        "download",
        "-n",
        str(args.node),
        "-o",
        str(output_dir),
    ]
    if args.project:
        command.extend(["-p", str(args.project)])
    if args.group:
        command.extend(["-g", str(args.group)])
    command.extend(["--without-ai-watermark", "--vip"])
    run_command(command, timeout=float(args.timeout))
    artifacts = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in LIBTV_MEDIA_SUFFIXES
    )
    if len(artifacts) != 1:
        raise Video2SpriteError(
            "LibTV download must produce exactly one supported image or video artifact"
        )
    artifact = artifacts[0]
    receipt_path = libtv_receipt_sidecar_path(artifact)
    summary = write_libtv_receipt(
        artifact,
        receipt_path,
        libtv_version=str(version_result.stdout),
        node=str(args.node),
        project=str(args.project) if args.project else None,
        group=str(args.group) if args.group else None,
        reference_audit=str(args.reference_audit),
        reference_ancestors=ancestors,
    )
    return {
        "output_dir": str(output_dir),
        "artifact": str(artifact.resolve()),
        "receipt": str(receipt_path.resolve()),
        "artifact_sha256": summary["artifact_sha256"],
        "artifact_bytes": summary["artifact_bytes"],
        "artifact_kind": (
            "video" if artifact.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"} else "image"
        ),
        "libtv_version": summary["libtv_version"],
        "required_flags": summary["required_flags"],
        "proof_scope": summary["proof_scope"],
        "reference_audit": summary["reference_audit"],
    }


def command_submit(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    action = _load_action(run_dir, args.action_id)
    reference_url, reference_path, reference_summary = _resolve_submit_reference(
        run_dir,
        run,
        args,
    )
    settings = _effective_video_settings(
        run,
        action,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
    )
    if settings["provider"] != "volcengine-ark":
        raise Video2SpriteError(
            f"Video provider adapter is not implemented: {settings['provider']}"
        )
    _validate_known_video_request(settings, action, args)
    native_audio = settings["capabilities"].get("native_audio")
    generate_audio = bool(action.get("audio_required")) and not args.no_audio
    if action.get("audio_required") and args.no_audio and not args.allow_silent_model:
        raise Video2SpriteError(
            "This action requires audio; remove --no-audio or pass --allow-silent-model for a deliberate diagnostic"
        )
    if action.get("audio_required") and native_audio is False and not args.allow_silent_model:
        raise Video2SpriteError(
            f"Model {settings['model_alias']} does not support native audio; select another model"
        )
    candidate_id = safe_identifier(
        args.candidate or _candidate_id_from_model(settings["model_alias"]),
        "candidate ID",
    )
    destination_dir = candidate_dir(run_dir, args.action_id, candidate_id)
    candidate_path = destination_dir / "candidate.json"
    if candidate_path.is_file():
        raise Video2SpriteError(
            f"Candidate record already exists: {candidate_id}; inspect it first and use a new --candidate for an intentional new billed task"
        )
    request_prompt = _video_prompt(action, reference_role=args.reference_role)
    input_fingerprint = fingerprint(
        {
            "master_sha256": run["master"]["sha256"],
            "prompt_sha256": fingerprint(request_prompt),
            "provider": settings["provider"],
            "model_id": settings["model_id"],
            "duration": action["duration_seconds"],
            "resolution": args.resolution,
            "ratio": args.ratio,
            "seed": args.seed,
            "generate_audio": generate_audio,
            "reference_role": args.reference_role,
            "watermark": bool(args.watermark),
        }
    )
    duplicate = _candidate_with_input_fingerprint(run_dir, action, input_fingerprint)
    if duplicate and not args.allow_duplicate_input:
        raise Video2SpriteError(
            f"Candidate {duplicate} already has the same generation fingerprint. "
            "Reuse it, change an input, or pass --allow-duplicate-input for an intentional billed retry."
        )
    candidate_budget = _candidate_budget()
    candidate_count = _remote_candidate_count(run_dir, action)
    if candidate_count >= candidate_budget and not args.allow_over_budget:
        raise Video2SpriteError(
            f"Candidate budget reached for {args.action_id}: {candidate_count}/{candidate_budget}. "
            "Benchmark only representative actions, or pass --allow-over-budget for an intentional extra billed task."
        )
    pilot_gate = _remote_pilot_gate(
        run_dir,
        run,
        requested_action_id=args.action_id,
    )
    allow_unapproved_batch = bool(
        getattr(args, "allow_unapproved_batch", False)
    )
    if not pilot_gate["unlocked"] and not allow_unapproved_batch:
        pilot_actions = ", ".join(pilot_gate["pilot_action_ids"]) or "unknown"
        raise Video2SpriteError(
            "The paid pilot gate is locked. Review and approve a processed remote "
            f"candidate for pilot action {pilot_actions} before submitting another action, "
            "or pass --allow-unapproved-batch only for an explicitly authorized billed batch."
        )
    destination_dir.mkdir(parents=True, exist_ok=True)
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "provider": settings["provider"],
        "model_alias": settings["model_alias"],
        "model_id": settings["model_id"],
        "base_url": settings["base_url"],
        "capabilities": settings["capabilities"],
        "purpose": args.purpose,
        "reference": reference_summary,
        "request": {
            "reference_role": args.reference_role,
            "resolution": args.resolution,
            "ratio": args.ratio,
            "duration_seconds": action["duration_seconds"],
            "generate_audio": generate_audio,
            "watermark": bool(args.watermark),
        },
        "input_fingerprint": input_fingerprint,
        "pilot_gate_override": allow_unapproved_batch,
        "seed": args.seed,
        "status": "submitting",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    atomic_write_json(candidate_path, candidate)
    _register_candidate(run_dir, action, candidate_id)
    try:
        result = submit_ark_video(
            base_url=settings["base_url"],
            model_id=settings["model_id"],
            prompt=request_prompt,
            reference_url=reference_url,
            reference_path=reference_path,
            reference_role=args.reference_role,
            resolution=args.resolution,
            ratio=args.ratio,
            duration=float(action["duration_seconds"]),
            generate_audio=generate_audio,
            seed=args.seed,
            watermark=bool(args.watermark),
        )
    except Exception:
        candidate["status"] = "submission_failed"
        candidate["updated_at"] = utc_now()
        atomic_write_json(candidate_path, candidate)
        raise
    candidate.update(
        {
            "task_id": result["task_id"],
            "request_id": result.get("request_id"),
            "status": result["status"],
            "submitted_at": result["submitted_at"],
            "updated_at": utc_now(),
        }
    )
    atomic_write_json(candidate_path, candidate)
    return {
        "run_dir": str(run_dir),
        "action_id": args.action_id,
        "candidate_id": candidate_id,
        "provider": settings["provider"],
        "model_alias": settings["model_alias"],
        "model_id": settings["model_id"],
        "task_id": result["task_id"],
        "status": result["status"],
        "candidate_budget": candidate_budget,
        "candidate_budget_remaining": max(0, candidate_budget - candidate_count - 1),
        "pilot_gate": {
            **pilot_gate,
            "override_used": allow_unapproved_batch,
        },
    }


def command_poll(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    _load_run(run_dir)
    _load_action(run_dir, args.action_id)
    candidate_id = safe_identifier(args.candidate, "candidate ID")
    destination_dir = candidate_dir(run_dir, args.action_id, candidate_id)
    candidate_path = destination_dir / "candidate.json"
    candidate = load_json(candidate_path)
    source = destination_dir / "source.mp4"
    if source.is_file() and candidate.get("source", {}).get("sha256") == sha256_file(source):
        return {
            "run_dir": str(run_dir),
            "action_id": args.action_id,
            "candidate_id": candidate_id,
            "status": candidate.get("status") or "ready",
            "source_sha256": candidate["source"]["sha256"],
            "cached": True,
        }
    if candidate.get("provider") != "volcengine-ark":
        raise Video2SpriteError("Only Volcengine Ark remote candidates can be polled")
    task_id = candidate.get("task_id")
    if not task_id:
        raise Video2SpriteError(f"Candidate has no provider task ID: {candidate_id}")
    result = poll_ark_video(
        base_url=str(candidate["base_url"]),
        task_id=str(task_id),
    )
    candidate["status"] = result["status"]
    candidate["request_id"] = result.get("request_id") or candidate.get("request_id")
    candidate["last_polled_at"] = result["polled_at"]
    candidate["updated_at"] = utc_now()
    if result["status"] == "failed":
        candidate["error"] = sanitize(result.get("error"))
    if result.get("usage"):
        candidate["usage"] = result["usage"]
    downloaded: Optional[Dict[str, Any]] = None
    if result["status"] == "succeeded":
        video_url = result.get("video_url")
        if not video_url:
            candidate["status"] = "download_failed"
            atomic_write_json(candidate_path, candidate)
            raise Video2SpriteError("Provider task succeeded but returned no video URL")
        downloaded = download_provider_video(str(video_url), source)
        media_probe = probe_media(
            source,
            ffprobe=getattr(args, "ffprobe", None)
            or os.getenv("VIDEO2SPRITE_FFPROBE", "ffprobe"),
        )
        candidate["source"] = {
            "path": "source.mp4",
            "origin": "provider",
            "sha256": downloaded["sha256"],
            "bytes": downloaded["bytes"],
            "source_url": downloaded["source_url"],
            "duration_seconds": media_probe["duration_seconds"],
            "audio_present": media_probe["audio"]["present"],
        }
        candidate["status"] = "ready"
        candidate["downloaded_at"] = utc_now()
    atomic_write_json(candidate_path, candidate)
    response: Dict[str, Any] = {
        "run_dir": str(run_dir),
        "action_id": args.action_id,
        "candidate_id": candidate_id,
        "task_id": task_id,
        "status": candidate["status"],
    }
    if downloaded:
        response.update(
            {
                "source_sha256": downloaded["sha256"],
                "bytes": downloaded["bytes"],
            }
        )
    return response


def _processed_cache_result(
    *,
    run_dir: Path,
    action_id: str,
    candidate_id: str,
    run: Dict[str, Any],
    action: Dict[str, Any],
    candidate: Dict[str, Any],
    columns: Optional[int],
    profile: str,
) -> Optional[Dict[str, Any]]:
    path = candidate_dir(run_dir, action_id, candidate_id)
    source = path / "source.mp4"
    recorded_source_hash = (candidate.get("source") or {}).get("sha256")
    if not source.is_file() or not recorded_source_hash:
        return None
    source_hash = sha256_file(source)
    if source_hash != recorded_source_hash:
        return None
    required = (
        path / "atlas.png",
        path / "preview.mp4",
        path / "manifest.json",
        path / "qc.json",
        path / "review-data.json",
        path / "index.html",
    )
    if any(not item.is_file() or item.stat().st_size == 0 for item in required):
        return None
    try:
        manifest = load_json(path / "manifest.json")
        qc = load_json(path / "qc.json")
    except Video2SpriteError:
        return None
    expected = candidate_processing_fingerprint(
        run,
        action,
        candidate,
        columns=columns,
        profile=profile,
    )
    provenance = manifest.get("provenance") or {}
    if provenance.get("processing_fingerprint") != expected:
        return None
    if provenance.get("model_id") != candidate.get("model_id"):
        return None
    atlas_path = path / "atlas.png"
    atlas = manifest.get("atlas") or {}
    atlas_hash = sha256_file(atlas_path)
    if not atlas.get("sha256") or atlas_hash != atlas["sha256"]:
        return None
    artifacts = candidate.get("artifacts") or {}
    preview_hash = artifacts.get("preview_sha256")
    actual_preview_hash = sha256_file(path / "preview.mp4")
    if not preview_hash or actual_preview_hash != preview_hash:
        return None
    frames = manifest.get("frames") or []
    if len(frames) != int(action.get("frame_count") or 0):
        return None
    candidate_root = path.resolve()
    for frame in frames:
        relative = frame.get("file") if isinstance(frame, dict) else None
        frame_path = (path / str(relative)).resolve() if relative else None
        if (
            not frame_path
            or candidate_root not in frame_path.parents
            or not frame_path.is_file()
            or not frame.get("sha256")
            or sha256_file(frame_path) != frame["sha256"]
        ):
            return None
    audio_present = bool((manifest.get("audio") or {}).get("present"))
    if (audio_present or action.get("audio_required")) and not (path / "sfx.ogg").is_file():
        return None
    if audio_present:
        audio_hash = (manifest.get("audio") or {}).get("sha256")
        if not audio_hash or sha256_file(path / "sfx.ogg") != audio_hash:
            return None
    reviewed_hashes = {
        "source": source_hash,
        "atlas": atlas_hash,
        "manifest": sha256_file(path / "manifest.json"),
        "qc": sha256_file(path / "qc.json"),
        "preview": actual_preview_hash,
    }
    if (candidate.get("source") or {}).get("origin") == "libtv":
        receipt_path = path / LIBTV_RECEIPT_FILENAME
        if not receipt_path.is_file():
            return None
        reviewed_hashes["source_receipt"] = sha256_file(receipt_path)
    if audio_present:
        reviewed_hashes["audio"] = str((manifest.get("audio") or {})["sha256"])
    approval_state = {"decision": None, "valid": False}
    approval_path = path / "approval.json"
    if approval_path.is_file():
        approval = load_json(approval_path)
        approval_state = {
            "decision": approval.get("decision"),
            "valid": (
                approval.get("decision") in {"approved", "rejected"}
                and approval.get("action_id") == action_id
                and approval.get("candidate_id") == candidate_id
                and approval.get("reviewed_hashes") == reviewed_hashes
            ),
        }
    return {
        "status": qc.get("status") or candidate.get("qc_status") or "review",
        "candidate_dir": str(path),
        "frame_count": len(frames),
        "atlas_sha256": atlas.get("sha256") or artifacts.get("atlas_sha256"),
        "audio_present": audio_present,
        "preview_sha256": preview_hash,
        "qc_issue_codes": [
            issue.get("code")
            for issue in qc.get("issues") or []
            if isinstance(issue, dict) and issue.get("code")
        ],
        "processing_fingerprint": expected,
        "processing_profile": profile,
        "cached": True,
        "approval": approval_state,
        "review_required": not approval_state["valid"],
    }


def command_process(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    action = _load_action(run_dir, args.action_id)
    candidate_id = safe_identifier(args.candidate, "candidate ID")
    candidate_path = candidate_dir(run_dir, args.action_id, candidate_id) / "candidate.json"
    candidate = load_json(candidate_path)
    if candidate.get("status") not in {
        "ready",
        "processed",
        "processing_failed",
        "review",
        "approved",
        "rejected",
    }:
        raise Video2SpriteError(
            f"Candidate is not ready for local processing: {candidate.get('status')}"
        )
    profile = _processing_profile(args.profile)
    source_origin = (candidate.get("source") or {}).get("origin")
    if source_origin is not None:
        validate_candidate_source(candidate_path.parent, candidate)
    if not args.force:
        cached = _processed_cache_result(
            run_dir=run_dir,
            action_id=args.action_id,
            candidate_id=candidate_id,
            run=run,
            action=action,
            candidate=candidate,
            columns=args.columns,
            profile=profile,
        )
        if cached:
            cached.update(
                {
                    "run_dir": str(run_dir),
                    "action_id": args.action_id,
                    "candidate_id": candidate_id,
                    "approval_archived": None,
                }
            )
            return cached
    if source_origin is None:
        raise Video2SpriteError(
            "Legacy candidate has no source origin; its existing valid cache may be reused, but rebuilding requires reattaching with --source-origin"
        )
    stale_approval = _archive_approval(candidate_path.parent / "approval.json")
    candidate["status"] = "processing"
    candidate["updated_at"] = utc_now()
    atomic_write_json(candidate_path, candidate)
    try:
        result = process_candidate_media(
            run_dir=run_dir,
            action_id=args.action_id,
            candidate_id=candidate_id,
            run_spec=run,
            action=action,
            candidate=candidate,
            columns=args.columns,
            ffmpeg=args.ffmpeg or os.getenv("VIDEO2SPRITE_FFMPEG", "ffmpeg"),
            ffprobe=args.ffprobe or os.getenv("VIDEO2SPRITE_FFPROBE", "ffprobe"),
            profile=profile,
        )
    except Exception as exc:
        candidate["status"] = "processing_failed"
        candidate["processing_error"] = sanitize(str(exc))
        candidate["updated_at"] = utc_now()
        atomic_write_json(candidate_path, candidate)
        raise
    candidate["status"] = "processed"
    candidate["qc_status"] = result["status"]
    candidate["processed_at"] = utc_now()
    candidate["updated_at"] = utc_now()
    candidate["artifacts"] = {
        "atlas_sha256": result["atlas_sha256"],
        "preview_sha256": result["preview_sha256"],
        "audio_present": result["audio_present"],
        "processing_fingerprint": result["processing_fingerprint"],
        "processing_profile": result["processing_profile"],
    }
    candidate.pop("processing_error", None)
    atomic_write_json(candidate_path, candidate)
    result.update(
        {
            "run_dir": str(run_dir),
            "action_id": args.action_id,
            "candidate_id": candidate_id,
            "approval_archived": stale_approval,
            "review_required": True,
            "cached": False,
        }
    )
    return result


def _worker_count(
    raw: Optional[int],
    env_name: str,
    default: int,
    *,
    maximum: int,
) -> int:
    if raw is None:
        return _bounded_env_int(env_name, default, minimum=1, maximum=maximum)
    if raw < 1 or raw > maximum:
        raise Video2SpriteError(f"{env_name} workers must be between 1 and {maximum}")
    return raw


def _candidate_records(
    run_dir: Path, run: Dict[str, Any]
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for action_id in run.get("actions") or []:
        action = _load_action(run_dir, str(action_id))
        for candidate_id in action.get("candidates") or []:
            identifier = str(candidate_id)
            path = candidate_dir(run_dir, str(action_id), identifier) / "candidate.json"
            if not path.is_file():
                records.append(
                    {
                        "action_id": str(action_id),
                        "candidate_id": identifier,
                        "candidate": None,
                    }
                )
                continue
            records.append(
                {
                    "action_id": str(action_id),
                    "candidate_id": identifier,
                    "candidate": load_json(path),
                }
            )
    return records


def _advance_once(args: argparse.Namespace) -> Dict[str, Any]:
    """Make one nonblocking batch pass; never submit new provider work."""
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    network_workers = _worker_count(
        args.network_workers,
        "VIDEO2SPRITE_NETWORK_WORKERS",
        DEFAULT_NETWORK_WORKERS,
        maximum=16,
    )
    local_workers = _worker_count(
        args.local_workers,
        "VIDEO2SPRITE_LOCAL_WORKERS",
        DEFAULT_LOCAL_WORKERS,
        maximum=8,
    )
    profile = _processing_profile(args.profile)
    errors: List[Dict[str, Any]] = []
    poll_counts: Dict[str, int] = {}
    processed: List[Dict[str, Any]] = []
    process_success_count = 0
    discover_error_count = 0

    poll_targets = []
    for record in _candidate_records(run_dir, run):
        candidate = record["candidate"]
        if candidate is None:
            discover_error_count += 1
            if len(errors) < 20:
                errors.append(
                    {
                        "stage": "discover",
                        "action_id": record["action_id"],
                        "candidate_id": record["candidate_id"],
                        "error": "missing candidate.json",
                    }
                )
            continue
        source = candidate_dir(
            run_dir, record["action_id"], record["candidate_id"]
        ) / "source.mp4"
        terminal = candidate.get("status") in {
            "failed",
            "submission_failed",
            "rejected",
        }
        if (
            candidate.get("provider") == "volcengine-ark"
            and candidate.get("task_id")
            and not source.is_file()
            and not terminal
        ):
            poll_targets.append(record)

    def poll_one(record: Dict[str, Any]) -> Dict[str, Any]:
        return command_poll(
            argparse.Namespace(
                run_dir=str(run_dir),
                action_id=record["action_id"],
                candidate=record["candidate_id"],
                ffprobe=args.ffprobe,
            )
        )

    if poll_targets:
        with ThreadPoolExecutor(max_workers=network_workers) as executor:
            future_map = {
                executor.submit(poll_one, record): record for record in poll_targets
            }
            for future in as_completed(future_map):
                record = future_map[future]
                try:
                    result = future.result()
                    status = str(result.get("status") or "unknown")
                    poll_counts[status] = poll_counts.get(status, 0) + 1
                except Exception as exc:
                    poll_counts["error"] = poll_counts.get("error", 0) + 1
                    if len(errors) < 20:
                        errors.append(
                            {
                                "stage": "poll",
                                "action_id": record["action_id"],
                                "candidate_id": record["candidate_id"],
                                "error": sanitize(str(exc)),
                            }
                        )

    process_targets = []
    if args.process_ready:
        for record in _candidate_records(run_dir, run):
            candidate = record["candidate"]
            if candidate and candidate.get("status") == "ready":
                process_targets.append(record)

    def process_one(record: Dict[str, Any]) -> Dict[str, Any]:
        return command_process(
            argparse.Namespace(
                run_dir=str(run_dir),
                action_id=record["action_id"],
                candidate=record["candidate_id"],
                columns=None,
                ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,
                profile=profile,
                force=False,
            )
        )

    if process_targets:
        with ThreadPoolExecutor(max_workers=local_workers) as executor:
            future_map = {
                executor.submit(process_one, record): record
                for record in process_targets
            }
            for future in as_completed(future_map):
                record = future_map[future]
                try:
                    result = future.result()
                    process_success_count += 1
                    if len(processed) < 20:
                        processed.append(
                            {
                                "action_id": record["action_id"],
                                "candidate_id": record["candidate_id"],
                                "qc_status": result.get("status"),
                                "cached": bool(result.get("cached")),
                            }
                        )
                except Exception as exc:
                    if len(errors) < 20:
                        errors.append(
                            {
                                "stage": "process",
                                "action_id": record["action_id"],
                                "candidate_id": record["candidate_id"],
                                "error": sanitize(str(exc)),
                            }
                        )

    final_counts: Dict[str, int] = {}
    for record in _candidate_records(run_dir, run):
        candidate = record["candidate"]
        status = (
            str(candidate.get("status") or "unknown")
            if candidate
            else "missing_candidate_json"
        )
        final_counts[status] = final_counts.get(status, 0) + 1
    return {
        "run_dir": str(run_dir),
        "status": "partial" if errors else "complete",
        "submitted_tasks": 0,
        "poll": {
            "targets": len(poll_targets),
            "workers": network_workers,
            "results": poll_counts,
        },
        "process": {
            "enabled": bool(args.process_ready),
            "targets": len(process_targets),
            "workers": local_workers,
            "profile": profile,
            "completed": process_success_count,
            "sample": processed,
            "sample_truncated": process_success_count > len(processed),
        },
        "candidate_statuses": final_counts,
        "errors": errors,
        "error_count": (
            discover_error_count
            + poll_counts.get("error", 0)
            + max(0, len(process_targets) - process_success_count)
        ),
        "note": "advance never submits or creates a billed provider task",
    }


def _pending_provider_count(summary: Dict[str, Any]) -> int:
    statuses = summary.get("candidate_statuses") or {}
    return sum(
        int(statuses.get(name) or 0)
        for name in ("submitting", "submitted", "queued", "running", "unknown")
    )


def _merge_advance_passes(
    passes: Sequence[Dict[str, Any]],
    *,
    wait_requested: float,
    elapsed: float,
    stop_reason: str,
) -> Dict[str, Any]:
    final = dict(passes[-1])
    poll_results: Dict[str, int] = {}
    processed_sample: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    poll_targets = 0
    process_targets = 0
    process_completed = 0
    error_count = 0
    for result in passes:
        poll = result.get("poll") or {}
        poll_targets += int(poll.get("targets") or 0)
        for name, count in (poll.get("results") or {}).items():
            poll_results[str(name)] = poll_results.get(str(name), 0) + int(count)
        process = result.get("process") or {}
        process_targets += int(process.get("targets") or 0)
        process_completed += int(process.get("completed") or 0)
        for item in process.get("sample") or []:
            if len(processed_sample) < 20:
                processed_sample.append(item)
        for item in result.get("errors") or []:
            if len(errors) < 20:
                errors.append(item)
        error_count += int(result.get("error_count") or 0)
    final["poll"] = {
        **(final.get("poll") or {}),
        "targets": poll_targets,
        "results": poll_results,
    }
    final["process"] = {
        **(final.get("process") or {}),
        "targets": process_targets,
        "completed": process_completed,
        "sample": processed_sample,
        "sample_truncated": process_completed > len(processed_sample),
    }
    final["errors"] = errors
    final["error_count"] = error_count
    final["status"] = "partial" if error_count else "complete"
    final["wait"] = {
        "requested_seconds": round(wait_requested, 3),
        "elapsed_seconds": round(elapsed, 3),
        "passes": len(passes),
        "stop_reason": stop_reason,
        "pending_provider_tasks": _pending_provider_count(final),
    }
    return final


def command_advance(args: argparse.Namespace) -> Dict[str, Any]:
    """Advance in bounded wait windows so polling does not consume many agent turns."""
    raw_wait = getattr(args, "wait_seconds", None)
    wait_seconds = (
        float(raw_wait)
        if raw_wait is not None
        else float(os.getenv("VIDEO2SPRITE_ADVANCE_WAIT_SECONDS", "0"))
    )
    raw_interval = getattr(args, "poll_interval", None)
    poll_interval = (
        float(raw_interval)
        if raw_interval is not None
        else float(
            os.getenv(
                "VIDEO2SPRITE_POLL_INTERVAL_SECONDS",
                str(DEFAULT_POLL_INTERVAL_SECONDS),
            )
        )
    )
    if wait_seconds < 0.0 or wait_seconds > MAX_ADVANCE_WAIT_SECONDS:
        raise Video2SpriteError(
            f"Advance wait must be between 0 and {MAX_ADVANCE_WAIT_SECONDS:g} seconds"
        )
    if poll_interval < 2.0 or poll_interval > 30.0:
        raise Video2SpriteError("Poll interval must be between 2 and 30 seconds")

    started = time.monotonic()
    deadline = started + wait_seconds
    passes: List[Dict[str, Any]] = []
    stop_reason = "nonblocking_pass"
    while True:
        result = _advance_once(args)
        passes.append(result)
        pending = _pending_provider_count(result)
        if result.get("error_count"):
            stop_reason = "error"
            break
        if pending == 0:
            stop_reason = "no_pending_provider_tasks"
            break
        remaining = deadline - time.monotonic()
        if wait_seconds <= 0.0 or remaining <= 0.0:
            stop_reason = "wait_window_elapsed"
            break
        time.sleep(min(poll_interval, remaining))
    elapsed = time.monotonic() - started
    return _merge_advance_passes(
        passes,
        wait_requested=wait_seconds,
        elapsed=elapsed,
        stop_reason=stop_reason,
    )


def _approval_state(candidate_path: Path) -> Dict[str, Any]:
    approval_path = candidate_path / "approval.json"
    if not approval_path.is_file():
        return {"decision": None, "valid": False}
    approval = load_json(approval_path)
    hashes = approval.get("reviewed_hashes") or {}
    file_map = {
        "source": "source.mp4",
        "atlas": "atlas.png",
        "manifest": "manifest.json",
        "qc": "qc.json",
        "preview": "preview.mp4",
        "audio": "sfx.ogg",
        "source_receipt": LIBTV_RECEIPT_FILENAME,
    }
    required_labels = {"source", "atlas", "manifest", "qc", "preview"}
    if (candidate_path / "sfx.ogg").is_file():
        required_labels.add("audio")
    valid = isinstance(hashes, dict) and required_labels.issubset(set(hashes))
    for label, expected in hashes.items():
        filename = file_map.get(label)
        path = candidate_path / filename if filename else None
        if not path or not path.is_file() or sha256_file(path) != expected:
            valid = False
            break
    try:
        manifest = load_json(candidate_path / "manifest.json")
        action = load_json(candidate_path.parents[1] / "action.json")
        candidate = load_json(candidate_path / "candidate.json")
        source_validation = validate_candidate_source(
            candidate_path,
            candidate,
            allow_legacy=True,
        )
        if source_validation["origin"] == "libtv":
            required_labels.add("source_receipt")
            valid = valid and "source_receipt" in hashes
        master_path = candidate_path.parents[3] / "master" / "source.png"
        provenance = manifest.get("provenance") or {}
        manifest_source_origin = (provenance.get("source") or {}).get("origin")
        if source_validation["origin"] == "legacy" and manifest_source_origin is not None:
            valid = False
        valid = valid and provenance.get("action_fingerprint") == action_processing_fingerprint(action)
        valid = valid and provenance.get("model_id") == candidate.get("model_id")
        valid = valid and provenance.get("master_sha256") == sha256_file(master_path)
    except (Video2SpriteError, IndexError):
        valid = False
    return {"decision": approval.get("decision"), "valid": valid}


def command_status(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    actions_summary: List[Dict[str, Any]] = []
    for action_id in run.get("actions") or []:
        action = _load_action(run_dir, str(action_id))
        candidates_summary: List[Dict[str, Any]] = []
        for candidate_id in action.get("candidates") or []:
            path = candidate_dir(run_dir, str(action_id), str(candidate_id))
            candidate_path = path / "candidate.json"
            if not candidate_path.is_file():
                candidates_summary.append(
                    {"candidate_id": candidate_id, "status": "missing_candidate_json"}
                )
                continue
            candidate = load_json(candidate_path)
            approval = _approval_state(path)
            candidates_summary.append(
                {
                    "candidate_id": candidate_id,
                    "provider": candidate.get("provider"),
                    "model_alias": candidate.get("model_alias"),
                    "model_id": candidate.get("model_id"),
                    "purpose": candidate.get("purpose"),
                    "status": candidate.get("status"),
                    "qc_status": candidate.get("qc_status"),
                    "processing_profile": (candidate.get("artifacts") or {}).get(
                        "processing_profile"
                    ),
                    "approval": approval,
                }
            )
        actions_summary.append(
            {
                "action_id": action_id,
                "frame_count": action.get("frame_count"),
                "audio_required": action.get("audio_required"),
                "candidates": candidates_summary,
            }
        )
    result = {
        "run_dir": str(run_dir),
        "character_id": run["character_id"],
        "master_sha256": run["master"]["sha256"],
        "actions": actions_summary,
    }
    if not bool(getattr(args, "compact", False)):
        return result

    candidate_statuses: Dict[str, int] = {}
    qc_statuses: Dict[str, int] = {}
    approvals = {"approved": 0, "rejected": 0, "unreviewed": 0, "invalid": 0}
    candidate_count = 0
    for action in actions_summary:
        for candidate in action["candidates"]:
            candidate_count += 1
            status = str(candidate.get("status") or "unknown")
            candidate_statuses[status] = candidate_statuses.get(status, 0) + 1
            qc_status = str(candidate.get("qc_status") or "missing")
            qc_statuses[qc_status] = qc_statuses.get(qc_status, 0) + 1
            approval = candidate.get("approval") or {}
            decision = approval.get("decision")
            if decision in {"approved", "rejected"} and approval.get("valid"):
                approvals[str(decision)] += 1
            elif decision:
                approvals["invalid"] += 1
            else:
                approvals["unreviewed"] += 1
    remote_action_ids = set()
    approved_remote_action_ids = set()
    remote_candidate_count = 0
    for action in actions_summary:
        for candidate in action["candidates"]:
            provider = candidate.get("provider")
            if not provider or provider == "local":
                continue
            remote_candidate_count += 1
            action_id = str(action["action_id"])
            remote_action_ids.add(action_id)
            if candidate.get("approval") == {
                "decision": "approved",
                "valid": True,
            }:
                approved_remote_action_ids.add(action_id)
    pilot_gate = {
        "unlocked": (
            remote_candidate_count == 0 or bool(approved_remote_action_ids)
        ),
        "remote_candidate_count": remote_candidate_count,
        "pilot_action_ids": sorted(remote_action_ids),
        "approved_pilot_action_ids": sorted(approved_remote_action_ids),
        "requested_action_is_existing_pilot": False,
    }
    return {
        "run_dir": str(run_dir),
        "character_id": run["character_id"],
        "master_sha256": run["master"]["sha256"],
        "action_count": len(actions_summary),
        "candidate_count": candidate_count,
        "candidate_statuses": candidate_statuses,
        "qc_statuses": qc_statuses,
        "approvals": approvals,
        "pilot_gate": pilot_gate,
    }


def _elapsed_seconds(start: Any, end: Any) -> Optional[float]:
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, round((end_time - start_time).total_seconds(), 3))


def command_compare(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    action_ids = [str(item) for item in run.get("actions") or []]
    if args.action_id:
        if args.action_id not in action_ids:
            raise Video2SpriteError(f"Unknown action: {args.action_id}")
        action_ids = [args.action_id]
    groups: Dict[str, Dict[str, Any]] = {}
    for action_id in action_ids:
        action = _load_action(run_dir, action_id)
        for candidate_id in action.get("candidates") or []:
            path = candidate_dir(run_dir, action_id, str(candidate_id))
            candidate_path = path / "candidate.json"
            if not candidate_path.is_file():
                continue
            candidate = load_json(candidate_path)
            model_id = str(candidate.get("model_id") or "unknown")
            group = groups.setdefault(
                model_id,
                {
                    "provider": candidate.get("provider"),
                    "model_alias": candidate.get("model_alias"),
                    "model_id": model_id,
                    "candidates": 0,
                    "actions": set(),
                    "approved_actions": set(),
                    "qc": {"pass": 0, "review": 0, "fail": 0, "missing": 0},
                    "score_values": {name: [] for name in ("visual", "motion", "audio", "sync", "overall")},
                    "generation_seconds": [],
                    "usage_values": {},
                },
            )
            group["candidates"] += 1
            group["actions"].add(action_id)
            qc_path = path / "qc.json"
            qc_status = load_json(qc_path).get("status") if qc_path.is_file() else "missing"
            if qc_status not in group["qc"]:
                qc_status = "missing"
            group["qc"][qc_status] += 1
            approval_path = path / "approval.json"
            if approval_path.is_file():
                approval = load_json(approval_path)
                approval_state = _approval_state(path)
                if approval.get("decision") == "approved" and approval_state["valid"]:
                    group["approved_actions"].add(action_id)
                scores = approval.get("scores") or {}
                if isinstance(scores, dict) and approval_state["valid"]:
                    for name, values in group["score_values"].items():
                        if isinstance(scores.get(name), (int, float)):
                            values.append(float(scores[name]))
            elapsed = _elapsed_seconds(
                candidate.get("submitted_at"), candidate.get("downloaded_at")
            )
            if elapsed is not None:
                group["generation_seconds"].append(elapsed)
            usage = candidate.get("usage") or {}
            if isinstance(usage, dict):
                for name, value in usage.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        group["usage_values"].setdefault(str(name), []).append(float(value))

    ranking: List[Dict[str, Any]] = []
    for group in groups.values():
        score_averages = {
            name: round(sum(values) / len(values), 3)
            for name, values in group["score_values"].items()
            if values
        }
        overall = score_averages.get("overall")
        if overall is None:
            component_scores = [
                score_averages[name]
                for name in ("visual", "motion", "audio", "sync")
                if name in score_averages
            ]
            overall = (
                round(sum(component_scores) / len(component_scores), 3)
                if component_scores
                else None
            )
        generation_values = group["generation_seconds"]
        ranking.append(
            {
                "provider": group["provider"],
                "model_alias": group["model_alias"],
                "model_id": group["model_id"],
                "candidate_count": group["candidates"],
                "actions_tested": sorted(group["actions"]),
                "approved_actions": sorted(group["approved_actions"]),
                "qc": group["qc"],
                "average_scores": score_averages,
                "ranking_score": overall,
                "average_generation_seconds": (
                    round(sum(generation_values) / len(generation_values), 3)
                    if generation_values
                    else None
                ),
                "average_usage": {
                    name: round(sum(values) / len(values), 3)
                    for name, values in sorted(group["usage_values"].items())
                    if values
                },
            }
        )
    ranking.sort(
        key=lambda item: (
            item["ranking_score"] if item["ranking_score"] is not None else -1.0,
            len(item["approved_actions"]),
            item["qc"]["pass"],
            -(item["average_generation_seconds"] or float("inf")),
        ),
        reverse=True,
    )
    recommendation = None
    recommended = next(
        (
            item
            for item in ranking
            if item["ranking_score"] is not None and item["approved_actions"]
        ),
        None,
    )
    if recommended:
        top = recommended
        recommendation = {
            "model_alias": top["model_alias"],
            "model_id": top["model_id"],
            "provisional": len(top["approved_actions"]) < 4,
            "basis": "human overall score, approved-action count, QC pass count, then generation speed",
            "suggested_env": f"VIDEO2SPRITE_VIDEO_MODEL={top['model_alias']}",
        }
    return {
        "run_dir": str(run_dir),
        "scope": args.action_id or "all-actions",
        "ranking": ranking,
        "recommendation": recommendation,
        "note": "A recommendation remains provisional until representative actions and real provider costs are reviewed.",
    }


def command_review(args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    from review_server import create_run_server, create_server

    run_dir = _runtime_dir(args.run_dir)
    _load_run(run_dir)
    if bool(args.action_id) != bool(args.candidate):
        raise Video2SpriteError(
            "Provide both --action-id and --candidate for one candidate, or neither for the whole run"
        )
    candidate_id = None
    review_count = 1
    review_path = "/"
    if args.action_id:
        _load_action(run_dir, args.action_id)
        candidate_id = safe_identifier(args.candidate, "candidate ID")
        path = candidate_dir(run_dir, args.action_id, candidate_id)
        server = create_server(
            path,
            action_id=args.action_id,
            candidate_id=candidate_id,
            host=args.host,
            port=args.port,
        )
    else:
        server, review_count = create_run_server(
            run_dir,
            host=args.host,
            port=args.port,
        )
        review_path = "/review.html"
    host, port = server.server_address[:2]
    emit(
        {
            "ok": True,
            "command": "review",
            "url": f"http://{host}:{port}{review_path}",
            "action_id": args.action_id,
            "candidate_id": candidate_id,
            "review_count": review_count,
            "message": "Open this localhost URL and review audiovisual evidence without sending media through the conversation.",
        }
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return None


def _verify_approval(candidate_path: Path) -> Dict[str, Any]:
    candidate = load_json(candidate_path / "candidate.json")
    validate_candidate_source(candidate_path, candidate, allow_legacy=True)
    qc = load_json(candidate_path / "qc.json")
    approval = load_json(candidate_path / "approval.json")
    manifest = load_json(candidate_path / "manifest.json")
    if qc.get("status") == "fail":
        raise Video2SpriteError(
            f"Candidate cannot be packaged because machine QC failed: {candidate_path.name}"
        )
    if approval.get("decision") != "approved":
        raise Video2SpriteError(f"Candidate is not approved: {candidate_path.name}")
    profile = (manifest.get("provenance") or {}).get("processing_profile")
    if profile != "production":
        raise Video2SpriteError(
            f"Candidate must be rebuilt and reviewed with the production profile before packaging: {candidate_path.name}"
        )
    state = _approval_state(candidate_path)
    if not state["valid"]:
        raise Video2SpriteError(
            f"Candidate approval is stale because a reviewed file changed: {candidate_path.name}"
        )
    return approval


def _godot_sprite_frames(
    *,
    action_id: str,
    manifest: Dict[str, Any],
    texture_path: str,
) -> str:
    frames = manifest["frames"]
    lines = [
        f'[gd_resource type="SpriteFrames" load_steps={len(frames) + 2} format=3]',
        "",
        f'[ext_resource type="Texture2D" path="{texture_path}" id="1_atlas"]',
        "",
    ]
    sub_ids = []
    for frame in frames:
        sub_id = f"AtlasTexture_{int(frame['index']):04d}"
        sub_ids.append(sub_id)
        cell = frame["cell"]
        lines.extend(
            [
                f'[sub_resource type="AtlasTexture" id="{sub_id}"]',
                'atlas = ExtResource("1_atlas")',
                (
                    "region = Rect2("
                    f"{cell['x']}, {cell['y']}, {cell['width']}, {cell['height']})"
                ),
                "",
            ]
        )
    frame_rows = ",\n".join(
        (
            '{"duration": 1.0, "texture": '
            f'SubResource("{sub_id}")'
            "}"
        )
        for sub_id in sub_ids
    )
    lines.extend(
        [
            "[resource]",
            "animations = [{",
            f'"frames": [{frame_rows}],',
            f'"loop": {str(bool(manifest.get("loop"))).lower()},',
            f'"name": &"{action_id}",',
            f'"speed": {float(manifest["fps"]):.6f}',
            "}]",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_selections(raw_values: Sequence[str]) -> Dict[str, str]:
    selections: Dict[str, str] = {}
    for raw in raw_values:
        if "=" not in raw:
            raise Video2SpriteError(
                f"Invalid selection '{raw}'; expected ACTION=CANDIDATE"
            )
        action_id, candidate_id = raw.split("=", 1)
        safe_identifier(action_id, "action ID")
        safe_identifier(candidate_id, "candidate ID")
        selections[action_id] = candidate_id
    return selections


def command_package(args: argparse.Namespace) -> Dict[str, Any]:
    run_dir = _runtime_dir(args.run_dir)
    run = _load_run(run_dir)
    output_dir = ensure_runtime_outside_skill(Path(args.output_dir)).expanduser().resolve()
    if output_dir.exists():
        raise Video2SpriteError(
            f"Package output already exists: {output_dir}; choose a new directory"
        )
    selections = _parse_selections(args.select or [])
    if args.engine == "godot" and not args.godot_res_prefix.startswith("res://"):
        raise Video2SpriteError("Godot resource prefix must start with res://")
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=str(parent)))
    packaged_actions: List[Dict[str, Any]] = []
    try:
        for raw_action_id in run.get("actions") or []:
            action_id = str(raw_action_id)
            action = _load_action(run_dir, action_id)
            candidate_ids = [str(item) for item in action.get("candidates") or []]
            if action_id in selections:
                candidate_ids = [selections[action_id]]
            else:
                candidate_ids = [
                    candidate_id
                    for candidate_id in candidate_ids
                    if (candidate_dir(run_dir, str(action_id), candidate_id) / "approval.json").is_file()
                    and load_json(
                        candidate_dir(run_dir, str(action_id), candidate_id) / "approval.json"
                    ).get("decision")
                    == "approved"
                ]
                if len(candidate_ids) > 1:
                    raise Video2SpriteError(
                        f"Action {action_id} has multiple approved candidates; pass --select {action_id}=CANDIDATE"
                    )
            if not candidate_ids:
                raise Video2SpriteError(
                    f"Action {action_id} has no approved candidate to package"
                )
            candidate_id = candidate_ids[0]
            source_dir = candidate_dir(run_dir, str(action_id), candidate_id)
            _verify_approval(source_dir)
            manifest = load_json(source_dir / "manifest.json")
            candidate = load_json(source_dir / "candidate.json")
            action_output = temp_root / run["character_id"] / str(action_id)
            frames_output = action_output / "frames"
            frames_output.mkdir(parents=True, exist_ok=True)
            copy_file_atomic(source_dir / "atlas.png", action_output / "atlas.png")
            copy_file_atomic(source_dir / "manifest.json", action_output / "manifest.json")
            for frame in manifest["frames"]:
                filename = Path(str(frame["file"])).name
                copy_file_atomic(source_dir / "frames" / filename, frames_output / filename)
            if (source_dir / "sfx.ogg").is_file():
                copy_file_atomic(source_dir / "sfx.ogg", action_output / "sfx.ogg")
            if (candidate.get("source") or {}).get("origin") == "libtv":
                copy_file_atomic(
                    source_dir / LIBTV_RECEIPT_FILENAME,
                    action_output / LIBTV_RECEIPT_FILENAME,
                )
            if args.engine == "godot":
                prefix = args.godot_res_prefix.rstrip("/")
                if args.godot_res_prefix == "res://":
                    texture_path = (
                        f"res://{run['character_id']}/{action_id}/atlas.png"
                    )
                else:
                    texture_path = (
                        f"{prefix}/{run['character_id']}/{action_id}/atlas.png"
                    )
                atomic_write_bytes(
                    action_output / f"{action_id}.tres",
                    _godot_sprite_frames(
                        action_id=str(action_id),
                        manifest=manifest,
                        texture_path=texture_path,
                    ).encode("utf-8"),
                )
            packaged_actions.append(
                {
                    "action_id": action_id,
                    "candidate_id": candidate_id,
                    "model_id": manifest.get("provenance", {}).get("model_id"),
                    "atlas_sha256": sha256_file(action_output / "atlas.png"),
                    "audio": (action_output / "sfx.ogg").is_file(),
                    "source_origin": (candidate.get("source") or {}).get("origin"),
                    "source_receipt_sha256": (
                        sha256_file(action_output / LIBTV_RECEIPT_FILENAME)
                        if (action_output / LIBTV_RECEIPT_FILENAME).is_file()
                        else None
                    ),
                    "frame_count": manifest["frame_count"],
                }
            )
        package_manifest = {
            "schema_version": 1,
            "character_id": run["character_id"],
            "engine": args.engine,
            "source_run_master_sha256": run["master"]["sha256"],
            "actions": packaged_actions,
            "created_at": utc_now(),
        }
        atomic_write_json(temp_root / "package.json", package_manifest)
        os.replace(str(temp_root), str(output_dir))
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return {
        "output_dir": str(output_dir),
        "engine": args.engine,
        "character_id": run["character_id"],
        "action_count": len(packaged_actions),
        "actions": packaged_actions,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local runtime and configured defaults")
    doctor.set_defaults(handler=command_doctor)

    models = subparsers.add_parser("models", help="List bundled model aliases and effective defaults")
    models.set_defaults(handler=command_models)

    configure_key = subparsers.add_parser(
        "configure-key",
        help="Securely save a provider key in the fixed user-level credentials file",
    )
    configure_key.add_argument("--name", choices=("ark", "openai"), required=True)
    configure_key.add_argument(
        "--from-env",
        help="Read the key from this environment variable instead of hidden terminal input",
    )
    configure_key.set_defaults(handler=command_configure_key)

    generate = subparsers.add_parser("generate-master", help="Generate a canonical GPT Image master")
    _add_prompt_group(generate)
    generate.add_argument("--output", required=True)
    generate.add_argument("--provider")
    generate.add_argument("--model")
    generate.add_argument("--base-url")
    generate.add_argument("--size", default="1024x1024")
    generate.add_argument("--quality", choices=("auto", "low", "medium", "high"), default="high")
    generate.add_argument("--chroma-key", default="#3f0050")
    generate.add_argument("--overwrite", action="store_true")
    generate.set_defaults(handler=command_generate_master)

    initialize = subparsers.add_parser("init", help="Initialize a media run outside the Skill source")
    initialize.add_argument("--run-dir", required=True)
    initialize.add_argument("--character-id", required=True)
    initialize.add_argument("--master", required=True)
    initialize.add_argument("--frame-size", default="256x256")
    initialize.add_argument(
        "--pivot",
        default="bottom-center",
        help="Frame pivot as bottom-center or X,Y, for example 144,144",
    )
    initialize.add_argument(
        "--placement",
        choices=PLACEMENT_MODES,
        default="fixed",
        help="Keep the provider canvas fixed, or fit one shared foreground union",
    )
    initialize.add_argument(
        "--resampling",
        choices=RESAMPLING_MODES,
        default="lanczos",
        help="Resize filter for the shared frame transform",
    )
    initialize.add_argument("--chroma-key", default="#3f0050")
    initialize.add_argument("--chroma-mode", choices=KEY_MODES, default="border")
    initialize.add_argument("--chroma-threshold", type=float, default=12.0)
    initialize.add_argument("--chroma-softness", type=float, default=24.0)
    initialize.add_argument("--image-provider")
    initialize.add_argument("--image-model")
    initialize.add_argument("--image-base-url")
    initialize.add_argument("--video-provider")
    initialize.add_argument("--video-model")
    initialize.add_argument("--video-base-url")
    initialize.set_defaults(handler=command_init)

    add_action = subparsers.add_parser("add-action", help="Define one semantic action")
    add_action.add_argument("--run-dir", required=True)
    add_action.add_argument("--action-id", required=True)
    _add_prompt_group(add_action)
    sampling_group = add_action.add_mutually_exclusive_group(required=True)
    sampling_group.add_argument(
        "--frames",
        type=int,
        help="Exact frame count for the effective action window",
    )
    sampling_group.add_argument(
        "--fps",
        type=float,
        help="Preserve this many frames per second across the effective action window",
    )
    add_action.add_argument("--columns", type=int)
    add_action.add_argument("--duration", type=float, required=True)
    add_action.add_argument("--window-start", type=float, default=0.0)
    add_action.add_argument("--window-duration", type=float)
    add_action.add_argument("--loop", action="store_true")
    add_action.add_argument("--audio-required", action="store_true")
    add_action.add_argument("--event", action="append")
    add_action.add_argument("--chroma-key")
    add_action.add_argument("--chroma-mode", choices=KEY_MODES)
    add_action.add_argument("--chroma-threshold", type=float)
    add_action.add_argument("--chroma-softness", type=float)
    add_action.add_argument("--provider")
    add_action.add_argument("--model")
    add_action.add_argument("--base-url")
    add_action.set_defaults(handler=command_add_action)

    libtv_download = subparsers.add_parser(
        "libtv-download",
        help="Download one LibTV artifact with mandatory watermark-free VIP flags and a receipt",
    )
    libtv_download.add_argument("--node", required=True)
    libtv_download.add_argument("--output-dir", required=True)
    libtv_download.add_argument("--project")
    libtv_download.add_argument("--group")
    libtv_download.add_argument(
        "--reference-audit",
        required=True,
        choices=sorted(LIBTV_REFERENCE_AUDIT_MODES),
        help="Declare and bind LibTV-origin reference ancestry for the generating node",
    )
    libtv_download.add_argument(
        "--ancestor-source",
        action="append",
        help="Local LibTV-origin reference ancestor artifact; pair with --ancestor-receipt",
    )
    libtv_download.add_argument(
        "--ancestor-receipt",
        action="append",
        help="Receipt matching the corresponding --ancestor-source",
    )
    libtv_download.add_argument(
        "--libtv",
        help="Official LibTV CLI executable; defaults to LIBTV_BIN or libtv",
    )
    libtv_download.add_argument("--timeout", type=float, default=900.0)
    libtv_download.set_defaults(handler=command_libtv_download)

    attach = subparsers.add_parser("attach-video", help="Attach an existing local candidate video")
    attach.add_argument("--run-dir", required=True)
    attach.add_argument("--action-id", required=True)
    attach.add_argument("--candidate", default="local")
    attach.add_argument("--video", required=True)
    attach.add_argument(
        "--source-origin",
        choices=("local", "libtv"),
        required=True,
        help="Declare whether the video is ordinary local media or a LibTV download",
    )
    attach.add_argument(
        "--source-receipt",
        help="Required bounded receipt for --source-origin libtv",
    )
    attach.set_defaults(handler=command_attach_video)

    submit = subparsers.add_parser("submit", help="Submit an asynchronous image-to-video task")
    submit.add_argument("--run-dir", required=True)
    submit.add_argument("--action-id", required=True)
    reference_group = submit.add_mutually_exclusive_group()
    reference_group.add_argument("--reference-url")
    reference_group.add_argument(
        "--reference-file",
        help="Read the canonical run master locally and encode it only inside the provider worker",
    )
    reference_group.add_argument(
        "--reference-url-env",
        help="Read the provider reference URL from this environment variable",
    )
    submit.add_argument("--candidate")
    submit.add_argument("--provider")
    submit.add_argument("--model")
    submit.add_argument("--base-url")
    submit.add_argument(
        "--reference-role", choices=ARK_REFERENCE_ROLES, default="first_frame"
    )
    submit.add_argument("--resolution", choices=ARK_RESOLUTIONS, default="720p")
    submit.add_argument("--ratio", choices=ARK_RATIOS, default="adaptive")
    submit.add_argument("--seed", type=int)
    submit.add_argument("--watermark", action="store_true")
    submit.add_argument("--no-audio", action="store_true")
    submit.add_argument("--allow-silent-model", action="store_true")
    submit.add_argument(
        "--purpose",
        choices=("draft", "final", "benchmark"),
        default="draft",
        help="Record why this billed candidate is being generated",
    )
    submit.add_argument(
        "--allow-over-budget",
        action="store_true",
        help="Intentionally exceed VIDEO2SPRITE_MAX_CANDIDATES_PER_ACTION",
    )
    submit.add_argument(
        "--allow-duplicate-input",
        action="store_true",
        help="Intentionally repeat an identical billed generation fingerprint",
    )
    submit.add_argument(
        "--allow-unapproved-batch",
        action="store_true",
        help="Intentionally submit a different action before any remote pilot is approved",
    )
    submit.set_defaults(handler=command_submit)

    poll = subparsers.add_parser("poll", help="Poll and download one asynchronous video task")
    poll.add_argument("--run-dir", required=True)
    poll.add_argument("--action-id", required=True)
    poll.add_argument("--candidate", required=True)
    poll.add_argument("--ffprobe")
    poll.set_defaults(handler=command_poll)

    process = subparsers.add_parser("process", help="Extract sprite frames, audio, preview, and QC")
    process.add_argument("--run-dir", required=True)
    process.add_argument("--action-id", required=True)
    process.add_argument("--candidate", required=True)
    process.add_argument("--columns", type=int)
    process.add_argument("--ffmpeg")
    process.add_argument("--ffprobe")
    process.add_argument(
        "--profile",
        choices=PROCESS_PROFILES,
        help="Encoding profile; defaults to VIDEO2SPRITE_PROCESS_PROFILE or production",
    )
    process.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even when the processing fingerprint and artifacts match",
    )
    process.set_defaults(handler=command_process)

    advance = subparsers.add_parser(
        "advance",
        help="Poll all pending tasks once and optionally process all ready candidates",
    )
    advance.add_argument("--run-dir", required=True)
    advance.add_argument(
        "--process-ready",
        action="store_true",
        help="Also process every candidate that becomes or already is ready",
    )
    advance.add_argument("--network-workers", type=int, help="Concurrent provider polls")
    advance.add_argument("--local-workers", type=int, help="Concurrent local media jobs")
    advance.add_argument(
        "--profile",
        choices=PROCESS_PROFILES,
        help="Local encoding profile for ready candidates",
    )
    advance.add_argument("--ffmpeg")
    advance.add_argument("--ffprobe")
    advance.add_argument(
        "--wait-seconds",
        type=float,
        help="Keep polling inside one bounded command for up to 55 seconds",
    )
    advance.add_argument(
        "--poll-interval",
        type=float,
        help="Seconds between internal polling passes (2-30, default 10)",
    )
    advance.set_defaults(handler=command_advance)

    status = subparsers.add_parser("status", help="Print a bounded run summary")
    status.add_argument("--run-dir", required=True)
    status.add_argument("--compact", action="store_true")
    status.set_defaults(handler=command_status)

    compare = subparsers.add_parser(
        "compare",
        help="Summarize model candidates from choices, QC, and optional legacy scores",
    )
    compare.add_argument("--run-dir", required=True)
    compare.add_argument("--action-id")
    compare.set_defaults(handler=command_compare)

    review = subparsers.add_parser("review", help="Start the localhost audiovisual reviewer")
    review.add_argument("--run-dir", required=True)
    review.add_argument("--action-id")
    review.add_argument("--candidate")
    review.add_argument("--host", default="127.0.0.1")
    review.add_argument("--port", type=int, default=0)
    review.set_defaults(handler=command_review)

    package = subparsers.add_parser("package", help="Package approved actions")
    package.add_argument("--run-dir", required=True)
    package.add_argument("--output-dir", required=True)
    package.add_argument("--engine", choices=SUPPORTED_ENGINES, default="generic")
    package.add_argument("--select", action="append")
    package.add_argument("--godot-res-prefix", default="res://")
    package.set_defaults(handler=command_package)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
        if result is not None:
            emit({"ok": True, "command": args.command, **result})
        return 0
    except Video2SpriteError as exc:
        emit({"ok": False, "command": args.command, "error": str(exc)})
        return 2
    except KeyboardInterrupt:
        emit({"ok": False, "command": args.command, "error": "interrupted"})
        return 130
    except Exception as exc:
        emit(
            {
                "ok": False,
                "command": args.command,
                "error": f"Unexpected {exc.__class__.__name__}: {sanitize(str(exc))}",
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
