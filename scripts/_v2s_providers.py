#!/usr/bin/env python3
"""Image provider adapter that never expose media payloads."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Any, Dict, Optional

from _v2s_common import (
    Video2SpriteError,
    atomic_write_bytes,
    credential_value,
    http_json,
    sanitize,
    sha256_file,
    utc_now,
)

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
