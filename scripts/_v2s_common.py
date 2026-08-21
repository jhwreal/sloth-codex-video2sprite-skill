#!/usr/bin/env python3
"""Shared bounded-output, configuration, hashing, and HTTP helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SKILL_DIR = Path(__file__).resolve().parent.parent
PRESETS_PATH = SKILL_DIR / "assets" / "model-presets.json"
DEFAULT_LOG_MAX_CHARS = 4096
MAX_SAFE_STRING = 1024
PROCESSOR_SCHEMA_VERSION = 5
PRIVATE_CREDENTIALS_PATH = (
    Path.home() / ".config" / "sloth-codex-video2sprite" / "credentials.env"
)
PRIVATE_CREDENTIAL_NAMES = frozenset(
    {"OPENAI_API_KEY", "ARK_API_KEY", "SEEDANCE_API_KEY"}
)
MAX_PRIVATE_CREDENTIALS_BYTES = 16 * 1024
MEDIA_KEY_FRAGMENTS = (
    "b64",
    "base64",
    "binary",
    "data_url",
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "access_token",
)
HTTP_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", flags=re.IGNORECASE)
BEARER_PATTERN = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+", flags=re.IGNORECASE
)


class Video2SpriteError(RuntimeError):
    """Expected user-facing error."""


def private_credentials_path() -> Path:
    """Return the fixed user-level credentials path without creating it."""
    return PRIVATE_CREDENTIALS_PATH


def load_private_credentials(path: Optional[Path] = None) -> Dict[str, str]:
    """Read a small, permission-locked dotenv file without mutating the environment."""
    resolved = (path or private_credentials_path()).expanduser()
    try:
        metadata = resolved.lstat()
    except FileNotFoundError:
        return {}
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise Video2SpriteError(
            f"Private credentials path must be a regular file, not a link: {resolved}"
        )
    if os.name == "posix" and metadata.st_mode & 0o077:
        raise Video2SpriteError(
            f"Private credentials file permissions are too broad; run chmod 600 {resolved}"
        )
    if metadata.st_size > MAX_PRIVATE_CREDENTIALS_BYTES:
        raise Video2SpriteError(
            f"Private credentials file exceeds {MAX_PRIVATE_CREDENTIALS_BYTES} bytes"
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise Video2SpriteError(
            f"Private credentials file is not valid UTF-8: {resolved}"
        ) from exc

    credentials: Dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise Video2SpriteError(
                f"Invalid private credentials entry on line {line_number}"
            )
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in PRIVATE_CREDENTIAL_NAMES:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value:
            credentials[name] = value
    return credentials


def store_private_credential(
    name: str,
    value: str,
    *,
    path: Optional[Path] = None,
) -> Path:
    """Securely create or update one canonical user-level credential."""
    if name not in {"OPENAI_API_KEY", "ARK_API_KEY"}:
        raise Video2SpriteError(f"Unsupported credential name: {name}")
    normalized = value.strip()
    if not normalized:
        raise Video2SpriteError(f"Credential value is empty: {name}")
    if "\n" in normalized or "\r" in normalized:
        raise Video2SpriteError(f"Credential value must be one line: {name}")

    resolved = (path or private_credentials_path()).expanduser()
    directory = resolved.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_metadata = directory.lstat()
    if stat.S_ISLNK(directory_metadata.st_mode) or not stat.S_ISDIR(
        directory_metadata.st_mode
    ):
        raise Video2SpriteError(
            f"Private credentials directory must be a regular directory, not a link: {directory}"
        )
    if os.name == "posix":
        directory.chmod(0o700)

    credentials = load_private_credentials(resolved)
    credentials[name] = normalized
    if name == "ARK_API_KEY":
        credentials.pop("SEEDANCE_API_KEY", None)
    lines = [
        f"{candidate}={credentials[candidate]}"
        for candidate in ("OPENAI_API_KEY", "ARK_API_KEY", "SEEDANCE_API_KEY")
        if credentials.get(candidate)
    ]
    encoded = ("\n".join(lines) + "\n").encode("utf-8")
    if len(encoded) > MAX_PRIVATE_CREDENTIALS_BYTES:
        raise Video2SpriteError(
            f"Private credentials file exceeds {MAX_PRIVATE_CREDENTIALS_BYTES} bytes"
        )

    handle, raw_temp = tempfile.mkstemp(
        prefix=f".{resolved.name}.",
        suffix=".tmp",
        dir=str(directory),
    )
    temp_path = Path(raw_temp)
    try:
        if os.name == "posix":
            os.fchmod(handle, 0o600)
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp_path), str(resolved))
        if os.name == "posix":
            resolved.chmod(0o600)
    finally:
        normalized = ""
        encoded = b""
        if temp_path.exists():
            temp_path.unlink()
    return resolved


def credential_value(name: str, *, path: Optional[Path] = None) -> Optional[str]:
    """Resolve a credential with environment variables taking precedence."""
    if name not in {"OPENAI_API_KEY", "ARK_API_KEY"}:
        raise Video2SpriteError(f"Unsupported credential name: {name}")
    names = (name, "SEEDANCE_API_KEY") if name == "ARK_API_KEY" else (name,)
    for candidate in names:
        value = os.getenv(candidate)
        if value:
            return value
    private = load_private_credentials(path)
    for candidate in names:
        value = private.get(candidate)
        if value:
            return value
    return None


def credential_source(name: str, *, path: Optional[Path] = None) -> Optional[str]:
    """Report only where a credential came from, never its value."""
    if name not in {"OPENAI_API_KEY", "ARK_API_KEY"}:
        raise Video2SpriteError(f"Unsupported credential name: {name}")
    names = (name, "SEEDANCE_API_KEY") if name == "ARK_API_KEY" else (name,)
    if any(os.getenv(candidate) for candidate in names):
        return "environment"
    private = load_private_credentials(path)
    if any(private.get(candidate) for candidate in names):
        return "private_file"
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Video2SpriteError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise Video2SpriteError(f"Invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Video2SpriteError(f"Expected a JSON object in {path}")
    return value


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp_path), str(path))
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp_path), str(path))
    finally:
        if temp_path.exists():
            temp_path.unlink()


def copy_file_atomic(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise Video2SpriteError(f"Missing source file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    os.close(handle)
    temp_path = Path(raw_temp)
    try:
        shutil.copy2(str(source), str(temp_path))
        os.replace(str(temp_path), str(destination))
    finally:
        if temp_path.exists():
            temp_path.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise Video2SpriteError(f"Missing file for hashing: {path}") from exc
    return digest.hexdigest()


def fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def action_processing_fingerprint(action: Dict[str, Any]) -> str:
    """Hash only fields that can change deterministic processing or review meaning."""
    return fingerprint(
        {
            "prompt_sha256": action.get("prompt_sha256"),
            "frame_count": action.get("frame_count"),
            "sampling": action.get("sampling"),
            "columns": action.get("columns"),
            "duration_seconds": action.get("duration_seconds"),
            "window": action.get("window"),
            "loop": action.get("loop"),
            "audio_required": action.get("audio_required"),
            "events": action.get("events"),
            "chroma": action.get("chroma"),
            "video": action.get("video"),
        }
    )


def candidate_processing_fingerprint(
    run_spec: Dict[str, Any],
    action: Dict[str, Any],
    candidate: Dict[str, Any],
    *,
    columns: Optional[int],
    profile: str,
) -> str:
    """Hash all inputs that materially affect deterministic local processing."""
    source = candidate.get("source") or {}
    payload = {
        "processor_schema_version": PROCESSOR_SCHEMA_VERSION,
        "source_sha256": source.get("sha256"),
        "master_sha256": (run_spec.get("master") or {}).get("sha256"),
        "action_fingerprint": action_processing_fingerprint(action),
        "frame_size": run_spec.get("frame_size"),
        "pivot": run_spec.get("pivot"),
        "placement": run_spec.get("placement"),
        "resampling": run_spec.get("resampling"),
        "columns": columns or action.get("columns"),
        "profile": profile,
    }
    # Preserve the exact legacy fingerprint for already-processed candidates
    # while binding every newly attached/provider source to explicit provenance.
    if "origin" in source:
        payload["source_origin"] = source.get("origin")
        payload["source_receipt_sha256"] = (source.get("receipt") or {}).get(
            "sha256"
        )
    return fingerprint(payload)


def strip_url_query(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme not in {"http", "https"}:
        return value
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _sanitize_text_urls(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return strip_url_query(match.group(0))

    return HTTP_URL_PATTERN.sub(replace, BEARER_PATTERN.sub("Bearer [redacted]", value))


def _sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in MEDIA_KEY_FRAGMENTS)


def sanitize(value: Any, key: str = "") -> Any:
    """Recursively remove secrets, inline media, signed queries, bytes, and long strings."""
    if key and _sensitive_key(key):
        return "[redacted]"
    if isinstance(value, bytes):
        return {"redacted_bytes": len(value)}
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value[:100]]
    if isinstance(value, str):
        lowered = value.lstrip().lower()
        if lowered.startswith("data:") or ";base64," in lowered:
            return "[redacted_inline_media]"
        if "b64_json" in lowered or "base64" in lowered:
            return "[redacted_inline_media_text]"
        compact = re.sub(r"\s+", "", value)
        if (
            len(compact) >= 128
            and len(compact) % 4 == 0
            and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", compact)
        ):
            return (
                "[redacted_probable_base64 "
                f"length={len(compact)} sha256={hashlib.sha256(compact.encode('utf-8')).hexdigest()[:16]}]"
            )
        safe = _sanitize_text_urls(value)
        if len(safe) > MAX_SAFE_STRING:
            return f"[redacted_long_string length={len(safe)} sha256={hashlib.sha256(safe.encode('utf-8')).hexdigest()[:16]}]"
        return safe
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_SAFE_STRING]


def safe_json_text(value: Any, max_chars: Optional[int] = None) -> str:
    limit = max_chars or int(os.getenv("VIDEO2SPRITE_LOG_MAX_CHARS", DEFAULT_LOG_MAX_CHARS))
    safe = sanitize(value)
    text = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) <= limit:
        return text
    summary: Dict[str, Any] = {
        "ok": bool(safe.get("ok")) if isinstance(safe, dict) else False,
        "truncated": True,
        "original_chars": len(text),
    }
    if isinstance(safe, dict):
        for name in ("command", "status", "run_dir", "action_id", "candidate_id", "error"):
            if name in safe:
                summary[name] = safe[name]
        summary["keys"] = sorted(str(item) for item in safe.keys())[:50]
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def emit(value: Dict[str, Any], max_chars: Optional[int] = None) -> None:
    print(safe_json_text(value, max_chars=max_chars), flush=True)


def require_executable(name_or_path: str) -> str:
    resolved = shutil.which(name_or_path)
    if resolved:
        return resolved
    explicit = Path(name_or_path)
    if explicit.is_file() and os.access(str(explicit), os.X_OK):
        return str(explicit)
    raise Video2SpriteError(f"Required executable not found: {name_or_path}")


def run_command(
    args: Sequence[str],
    *,
    check: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    max_error_chars: int = 3000,
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            [str(item) for item in args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise Video2SpriteError(f"Command timed out: {Path(str(args[0])).name}") from exc
    except OSError as exc:
        raise Video2SpriteError(f"Cannot run {args[0]}: {exc}") from exc
    if check and result.returncode != 0:
        stderr: Any = result.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        safe_error = safe_json_text({"stderr": str(stderr)[-max_error_chars:]}, max_chars=max_error_chars)
        raise Video2SpriteError(
            f"{Path(str(args[0])).name} failed with code {result.returncode}: {safe_error}"
        )
    return result


def parse_size(raw: str) -> Tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", raw)
    if not match:
        raise Video2SpriteError(f"Invalid size '{raw}'; expected WIDTHxHEIGHT")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 16 or height < 16 or width > 8192 or height > 8192:
        raise Video2SpriteError(f"Size out of range: {width}x{height}")
    return width, height


def parse_hex_color(raw: str) -> Tuple[int, int, int]:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", raw.strip())
    if not match:
        raise Video2SpriteError(f"Invalid color '{raw}'; expected #RRGGBB")
    value = match.group(1)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def safe_identifier(raw: str, label: str = "identifier") -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}", raw):
        raise Video2SpriteError(
            f"Invalid {label} '{raw}'; use letters, numbers, dots, underscores, and hyphens"
        )
    return raw


def ensure_runtime_outside_skill(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(SKILL_DIR)
    except ValueError:
        return resolved
    raise Video2SpriteError("Runtime output must be outside the Skill source directory")


def load_presets() -> Dict[str, Any]:
    return load_json(PRESETS_PATH)


def resolve_image_settings(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    presets = load_presets()["image"]
    resolved_provider = (
        provider
        or os.getenv("VIDEO2SPRITE_IMAGE_PROVIDER")
        or presets["default_provider"]
    )
    provider_spec = presets["providers"].get(resolved_provider)
    if not provider_spec:
        raise Video2SpriteError(f"Unsupported image provider: {resolved_provider}")
    requested_model = (
        model
        or os.getenv("VIDEO2SPRITE_IMAGE_MODEL")
        or provider_spec["default_model"]
    )
    model_spec = provider_spec.get("models", {}).get(requested_model)
    model_id = model_spec.get("model_id") if model_spec else requested_model
    return {
        "provider": resolved_provider,
        "model_alias": requested_model,
        "model_id": model_id,
        "base_url": (
            base_url
            or os.getenv("VIDEO2SPRITE_IMAGE_BASE_URL")
            or provider_spec["base_url"]
        ).rstrip("/"),
        "capabilities": (
            {key: value for key, value in model_spec.items() if key != "model_id"}
            if model_spec
            else {}
        ),
    }


def resolve_video_settings(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    presets = load_presets()["video"]
    resolved_provider = (
        provider
        or os.getenv("VIDEO2SPRITE_VIDEO_PROVIDER")
        or presets["default_provider"]
    )
    provider_spec = presets["providers"].get(resolved_provider)
    if not provider_spec:
        raise Video2SpriteError(f"Unsupported video provider: {resolved_provider}")
    requested_model = (
        model
        or os.getenv("VIDEO2SPRITE_VIDEO_MODEL")
        or provider_spec["default_model"]
    )
    model_spec = provider_spec.get("models", {}).get(requested_model)
    if model_spec is None:
        for alias, candidate in provider_spec.get("models", {}).items():
            if candidate.get("model_id") == requested_model:
                requested_model = alias
                model_spec = candidate
                break
    model_id = model_spec.get("model_id") if model_spec else (model or requested_model)
    return {
        "provider": resolved_provider,
        "model_alias": requested_model,
        "model_id": model_id,
        "base_url": (
            base_url
            or os.getenv("VIDEO2SPRITE_VIDEO_BASE_URL")
            or provider_spec["base_url"]
        ).rstrip("/"),
        "capabilities": (
            {key: value for key, value in model_spec.items() if key != "model_id"}
            if model_spec
            else {
                "native_audio": None,
                "image_to_video": None,
                "tier": "custom",
            }
        ),
    }


def http_json(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    encoded = None
    request_headers = dict(headers or {})
    if body is not None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=encoded, headers=request_headers, method=method)
    resolved_timeout = timeout or float(os.getenv("VIDEO2SPRITE_HTTP_TIMEOUT", "120"))
    try:
        with urllib.request.urlopen(request, timeout=resolved_timeout) as response:
            raw = response.read()
            response_headers = {str(k): str(v) for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw_error = exc.read(8192)
        message = raw_error.decode("utf-8", errors="replace")
        raise Video2SpriteError(
            f"HTTP {exc.code} from {strip_url_query(url)}: "
            f"{safe_json_text({'provider_error': message}, max_chars=1800)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise Video2SpriteError(
            f"Network error calling {strip_url_query(url)}: {sanitize(str(exc.reason))}"
        ) from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Video2SpriteError(f"Non-JSON response from {strip_url_query(url)}") from exc
    if not isinstance(parsed, dict):
        raise Video2SpriteError(f"Unexpected JSON response from {strip_url_query(url)}")
    return parsed, response_headers


def download_file(
    url: str,
    destination: Path,
    *,
    headers: Optional[Dict[str, str]] = None,
    max_bytes: int = 1024 * 1024 * 1024,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".download", dir=str(destination.parent)
    )
    os.close(handle)
    temp_path = Path(raw_temp)
    digest = hashlib.sha256()
    total = 0
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    resolved_timeout = timeout or float(os.getenv("VIDEO2SPRITE_HTTP_TIMEOUT", "120"))
    try:
        with urllib.request.urlopen(request, timeout=resolved_timeout) as response, temp_path.open(
            "wb"
        ) as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise Video2SpriteError(
                        f"Download exceeded {max_bytes} bytes from {strip_url_query(url)}"
                    )
                output.write(chunk)
                digest.update(chunk)
        os.replace(str(temp_path), str(destination))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise Video2SpriteError(
            f"Download failed from {strip_url_query(url)}: {sanitize(str(exc))}"
        ) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {
        "path": str(destination),
        "bytes": total,
        "sha256": digest.hexdigest(),
        "source_url": strip_url_query(url),
    }


def find_first_key(value: Any, names: Iterable[str]) -> Optional[Any]:
    wanted = {name.lower() for name in names}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in wanted and item not in (None, ""):
                return item
        for item in value.values():
            found = find_first_key(item, names)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_first_key(item, names)
            if found not in (None, ""):
                return found
    return None


def collect_urls(value: Any) -> List[str]:
    urls: List[str] = []
    if isinstance(value, dict):
        for item in value.values():
            urls.extend(collect_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.extend(collect_urls(item))
    elif isinstance(value, str) and value.startswith(("http://", "https://")):
        urls.append(value)
    return urls


def choose_video_url(value: Any) -> Optional[str]:
    urls = collect_urls(value)
    for url in urls:
        path = urllib.parse.urlsplit(url).path.lower()
        if path.endswith((".mp4", ".webm", ".mov", ".m4v")):
            return url
    return urls[0] if urls else None


def candidate_dir(run_dir: Path, action_id: str, candidate_id: str) -> Path:
    safe_identifier(action_id, "action ID")
    safe_identifier(candidate_id, "candidate ID")
    return run_dir / "actions" / action_id / "candidates" / candidate_id


def action_dir(run_dir: Path, action_id: str) -> Path:
    safe_identifier(action_id, "action ID")
    return run_dir / "actions" / action_id
