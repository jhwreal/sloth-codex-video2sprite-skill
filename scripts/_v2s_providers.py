#!/usr/bin/env python3
"""Image and video provider adapters that never expose media payloads."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from _v2s_common import (
    Video2SpriteError,
    atomic_write_bytes,
    choose_video_url,
    credential_value,
    download_file,
    find_first_key,
    http_json,
    sanitize,
    sha256_file,
    strip_url_query,
    utc_now,
)

ARK_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
}
ARK_MAX_REFERENCE_IMAGE_BYTES = 30 * 1024 * 1024


def generate_openai_master(
    *,
    prompt: str,
    output_path: Path,
    model_id: str,
    base_url: str,
    size: str,
    quality: str,
    output_format: str = "png",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    key = api_key or credential_value("OPENAI_API_KEY")
    if not key:
        raise Video2SpriteError("OPENAI_API_KEY is required for GPT Image generation")
    request_body = {
        "model": model_id,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "output_format": output_format,
    }
    response, headers = http_json(
        "POST",
        f"{base_url.rstrip('/')}/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        body=request_body,
    )
    data = response.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise Video2SpriteError("OpenAI image response did not contain data[0]")
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise Video2SpriteError("OpenAI image response did not contain b64_json")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise Video2SpriteError("OpenAI image response contained invalid Base64") from exc
    if len(image_bytes) < 64:
        raise Video2SpriteError("OpenAI image response was unexpectedly small")
    atomic_write_bytes(output_path, image_bytes)
    data[0]["b64_json"] = ""
    response.pop("data", None)
    encoded = ""
    image_bytes = b""
    request_id = (
        headers.get("x-request-id")
        or headers.get("X-Request-Id")
        or response.get("request_id")
    )
    usage = sanitize(response.get("usage") or {})
    return {
        "provider": "openai",
        "model_id": response.get("model") or model_id,
        "request_id": request_id,
        "created": response.get("created"),
        "usage": usage,
        "output_path": str(output_path),
        "sha256": sha256_file(output_path),
        "bytes": output_path.stat().st_size,
        "completed_at": utc_now(),
    }


def _normalized_task_status(raw: Any) -> str:
    text = str(raw or "unknown").strip().lower()
    if text in {"succeeded", "success", "completed", "complete", "done"}:
        return "succeeded"
    if text in {"failed", "error", "cancelled", "canceled", "expired"}:
        return "failed"
    if text in {"queued", "pending", "created", "submitted"}:
        return "queued"
    if text in {"running", "processing", "in_progress", "generating"}:
        return "running"
    return text or "unknown"


def _bounded_usage(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    usage: Dict[str, Any] = {}
    for key in sorted(raw, key=lambda item: str(item))[:32]:
        value = raw[key]
        if value is None or isinstance(value, (bool, int, float)):
            usage[str(key)] = value
        elif isinstance(value, str) and len(value) <= 128:
            usage[str(key)] = sanitize(value)
    return usage


def _ark_reference_payload(
    *,
    reference_url: Optional[str],
    reference_path: Optional[Path],
) -> Tuple[str, Any]:
    if bool(reference_url) == bool(reference_path):
        raise Video2SpriteError(
            "Provide exactly one Ark reference URL/asset URI or local image path"
        )
    if reference_url:
        if reference_url.lstrip().lower().startswith("data:"):
            raise Video2SpriteError(
                "Pass local references as a path so inline media cannot enter logs or run JSON"
            )
        return reference_url, strip_url_query(reference_url)

    assert reference_path is not None
    resolved = reference_path.expanduser().resolve()
    if not resolved.is_file():
        raise Video2SpriteError(f"Reference image does not exist: {resolved}")
    mime_type = ARK_IMAGE_MIME_TYPES.get(resolved.suffix.lower())
    if not mime_type:
        raise Video2SpriteError(
            "Local Ark reference must be PNG, JPEG, WebP, BMP, TIFF, or GIF"
        )
    byte_count = resolved.stat().st_size
    if byte_count <= 0 or byte_count >= ARK_MAX_REFERENCE_IMAGE_BYTES:
        raise Video2SpriteError(
            "Local Ark reference must be non-empty and smaller than 30 MiB"
        )
    try:
        from PIL import Image
    except ImportError as exc:
        raise Video2SpriteError(
            "Pillow is required to validate a local Ark reference image"
        ) from exc
    try:
        with Image.open(resolved) as image:
            width, height = image.size
            image.verify()
    except OSError as exc:
        raise Video2SpriteError(f"Cannot decode Ark reference image: {resolved}") from exc
    if width < 300 or height < 300 or width > 6000 or height > 6000:
        raise Video2SpriteError(
            "Ark reference image width and height must each be between 300 and 6000 pixels"
        )
    ratio = width / height
    if ratio < 0.4 or ratio > 2.5:
        raise Video2SpriteError(
            "Ark reference image width/height ratio must be between 0.4 and 2.5"
        )
    raw = resolved.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    payload = f"data:{mime_type};base64,{encoded}"
    raw = b""
    encoded = ""
    return payload, {
        "kind": "local_file",
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "bytes": byte_count,
        "width": width,
        "height": height,
    }


def submit_ark_video(
    *,
    base_url: str,
    model_id: str,
    prompt: str,
    reference_url: Optional[str] = None,
    reference_path: Optional[Path] = None,
    reference_role: str,
    resolution: str,
    ratio: str,
    duration: float,
    generate_audio: bool,
    seed: Optional[int],
    watermark: bool,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    key = api_key or credential_value("ARK_API_KEY")
    if not key:
        raise Video2SpriteError("ARK_API_KEY is required for Volcengine video generation")
    reference_payload, reference_summary = _ark_reference_payload(
        reference_url=reference_url,
        reference_path=reference_path,
    )
    content = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": reference_payload},
            "role": reference_role,
        },
    ]
    request_body: Dict[str, Any] = {
        "model": model_id,
        "content": content,
        "resolution": resolution,
        "ratio": ratio,
        "duration": int(duration) if float(duration).is_integer() else duration,
        "generate_audio": generate_audio,
        "watermark": watermark,
    }
    if seed is not None:
        request_body["seed"] = seed
    try:
        response, headers = http_json(
            "POST",
            f"{base_url.rstrip('/')}/contents/generations/tasks",
            headers={"Authorization": f"Bearer {key}"},
            body=request_body,
        )
    finally:
        reference_payload = ""
        content[1]["image_url"]["url"] = "[released_inline_media]"
        request_body["content"] = []
    task_id = find_first_key(response, ("id", "task_id", "taskId"))
    if not isinstance(task_id, (str, int)) or not str(task_id):
        raise Video2SpriteError("Video provider response did not contain a task ID")
    raw_status = find_first_key(response, ("status", "state"))
    request_id = (
        headers.get("x-request-id")
        or headers.get("X-Request-Id")
        or find_first_key(response, ("request_id", "requestId"))
    )
    return {
        "task_id": str(task_id),
        "status": _normalized_task_status(raw_status or "queued"),
        "request_id": request_id,
        "reference": reference_summary,
        "submitted_at": utc_now(),
    }


def poll_ark_video(
    *,
    base_url: str,
    task_id: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    key = api_key or credential_value("ARK_API_KEY")
    if not key:
        raise Video2SpriteError("ARK_API_KEY is required for Volcengine video polling")
    response, headers = http_json(
        "GET",
        f"{base_url.rstrip('/')}/contents/generations/tasks/{task_id}",
        headers={"Authorization": f"Bearer {key}"},
    )
    raw_status = find_first_key(response, ("status", "state"))
    status = _normalized_task_status(raw_status)
    error = find_first_key(response, ("error", "failure_reason", "message")) if status == "failed" else None
    usage = _bounded_usage(find_first_key(response, ("usage",)))
    return {
        "task_id": task_id,
        "status": status,
        "video_url": choose_video_url(response) if status == "succeeded" else None,
        "error": sanitize(error),
        "usage": usage,
        "request_id": (
            headers.get("x-request-id")
            or headers.get("X-Request-Id")
            or find_first_key(response, ("request_id", "requestId"))
        ),
        "polled_at": utc_now(),
    }


def download_provider_video(url: str, destination: Path) -> Dict[str, Any]:
    return download_file(url, destination)
