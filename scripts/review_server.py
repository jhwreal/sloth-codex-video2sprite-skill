#!/usr/bin/env python3
"""Local-only audiovisual reviewer and hash-bound approval writer."""

from __future__ import annotations

import argparse
import json
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from _v2s_common import (
    SKILL_DIR,
    Video2SpriteError,
    atomic_write_json,
    copy_file_atomic,
    load_json,
    safe_identifier,
    sha256_file,
    utc_now,
)
from _v2s_receipts import LIBTV_RECEIPT_FILENAME, validate_candidate_source


MAX_DECISION_BYTES = 64 * 1024
MAX_NOTE_CHARS = 4000
SCORE_NAMES = ("visual", "motion", "audio", "sync", "overall")


def write_decision(
    candidate_dir: Path,
    *,
    action_id: str,
    candidate_id: str,
    decision: str,
    note: str = "",
    edited_events: Optional[Sequence[Dict[str, Any]]] = None,
    scores: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    safe_identifier(action_id, "action ID")
    safe_identifier(candidate_id, "candidate ID")
    if decision not in {"approved", "rejected"}:
        raise Video2SpriteError("Decision must be approved or rejected")
    if len(note) > MAX_NOTE_CHARS:
        raise Video2SpriteError(f"Decision note exceeds {MAX_NOTE_CHARS} characters")
    candidate = load_json(candidate_dir / "candidate.json")
    source_validation = validate_candidate_source(
        candidate_dir,
        candidate,
        allow_legacy=True,
    )
    manifest = load_json(candidate_dir / "manifest.json")
    qc = load_json(candidate_dir / "qc.json")
    manifest_origin = ((manifest.get("provenance") or {}).get("source") or {}).get(
        "origin"
    )
    if source_validation["origin"] == "legacy" and manifest_origin is not None:
        raise Video2SpriteError(
            "Candidate source origin was removed after processing; reattach the source"
        )
    if manifest.get("action_id") != action_id or manifest.get("candidate_id") != candidate_id:
        raise Video2SpriteError("Review target does not match the processed manifest")
    if decision == "approved" and qc.get("status") == "fail":
        raise Video2SpriteError("A candidate with failing machine QC cannot be approved")

    reviewed_paths = {
        "source": candidate_dir / "source.mp4",
        "atlas": candidate_dir / "atlas.png",
        "manifest": candidate_dir / "manifest.json",
        "qc": candidate_dir / "qc.json",
        "preview": candidate_dir / "preview.mp4",
    }
    audio_path = candidate_dir / "sfx.ogg"
    if audio_path.is_file():
        reviewed_paths["audio"] = audio_path
    if source_validation["origin"] == "libtv":
        reviewed_paths["source_receipt"] = candidate_dir / LIBTV_RECEIPT_FILENAME
    hashes: Dict[str, str] = {}
    for label, path in reviewed_paths.items():
        if not path.is_file():
            raise Video2SpriteError(f"Cannot record decision; reviewed file is missing: {path.name}")
        hashes[label] = sha256_file(path)

    events: Sequence[Dict[str, Any]] = edited_events or []
    if len(events) > 64:
        raise Video2SpriteError("At most 64 edited event markers are allowed")
    normalized_events = []
    for event in events:
        if not isinstance(event, dict):
            raise Video2SpriteError("Edited event markers must be objects")
        name = str(event.get("event") or "")[:96]
        try:
            frame = int(event["frame"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Video2SpriteError("Each edited event marker requires an integer frame") from exc
        if frame < 0 or frame >= int(manifest.get("frame_count") or 0):
            raise Video2SpriteError(f"Edited event frame is out of range: {frame}")
        normalized_events.append({"event": name, "frame": frame})

    normalized_scores: Dict[str, float] = {}
    if scores is not None:
        if not isinstance(scores, dict):
            raise Video2SpriteError("Review scores must be an object")
        for name in SCORE_NAMES:
            if name not in scores:
                continue
            try:
                score = float(scores[name])
            except (TypeError, ValueError) as exc:
                raise Video2SpriteError(f"Review score '{name}' must be numeric") from exc
            if score < 1.0 or score > 5.0:
                raise Video2SpriteError(f"Review score '{name}' must be between 1 and 5")
            normalized_scores[name] = round(score, 2)

    approval = {
        "schema_version": 1,
        "action_id": action_id,
        "candidate_id": candidate_id,
        "decision": decision,
        "note": note,
        "edited_events": normalized_events,
        "scores": normalized_scores,
        "qc_status": qc.get("status"),
        "reviewed_hashes": hashes,
        "reviewed_at": utc_now(),
    }
    atomic_write_json(candidate_dir / "approval.json", approval)
    return approval


def build_review_queue(run_dir: Path) -> Dict[str, Any]:
    run = load_json(run_dir / "run.json")
    entries = []
    targets: Dict[str, str] = {}
    for raw_action_id in run.get("actions") or []:
        action_id = safe_identifier(str(raw_action_id), "action ID")
        action_path = run_dir / "actions" / action_id
        action = load_json(action_path / "action.json")
        for raw_candidate_id in action.get("candidates") or []:
            candidate_id = safe_identifier(str(raw_candidate_id), "candidate ID")
            candidate_path = action_path / "candidates" / candidate_id
            review_path = candidate_path / "review-data.json"
            if not review_path.is_file():
                continue
            review = load_json(review_path)
            relative_root = candidate_path.relative_to(run_dir).as_posix()
            review_paths = review.get("paths") or {}
            paths = {
                name: (
                    f"{relative_root}/{relative}"
                    if isinstance(relative, str) and relative
                    else None
                )
                for name, relative in review_paths.items()
            }
            approval_summary = None
            approval_path = candidate_path / "approval.json"
            if approval_path.is_file():
                approval = load_json(approval_path)
                approval_summary = {
                    "decision": approval.get("decision"),
                    "reviewed_at": approval.get("reviewed_at"),
                }
            entries.append(
                {
                    "action_id": action_id,
                    "candidate_id": candidate_id,
                    "provider": review.get("provider"),
                    "model_id": review.get("model_id"),
                    "paths": paths,
                    "qc": review.get("qc") or {},
                    "manifest_summary": review.get("manifest_summary") or {},
                    "approval": approval_summary,
                }
            )
            targets[f"{action_id}\0{candidate_id}"] = str(candidate_path)
    queue = {
        "schema_version": 1,
        "character_id": run.get("character_id"),
        "entries": entries,
        "generated_at": utc_now(),
    }
    atomic_write_json(run_dir / "review-queue.json", queue)
    copy_file_atomic(
        SKILL_DIR / "assets" / "reviewer" / "run.html",
        run_dir / "review.html",
    )
    return {"queue": queue, "targets": targets}


def _update_queue_approval(
    queue_path: Path,
    *,
    action_id: str,
    candidate_id: str,
    approval: Dict[str, Any],
) -> None:
    if not queue_path.is_file():
        return
    queue = load_json(queue_path)
    for entry in queue.get("entries") or []:
        if (
            isinstance(entry, dict)
            and entry.get("action_id") == action_id
            and entry.get("candidate_id") == candidate_id
        ):
            entry["approval"] = {
                "decision": approval.get("decision"),
                "reviewed_at": approval.get("reviewed_at"),
            }
            break
    atomic_write_json(queue_path, queue)


class ReviewHandler(SimpleHTTPRequestHandler):
    server_version = "Video2SpriteReview/1"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
        super().end_headers()

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _json_response(self, status: int, body: Dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.path != "/api/decision":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return
        if length < 1 or length > MAX_DECISION_BYTES:
            self._json_response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_body_size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        if not isinstance(body, dict):
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "expected_object"})
            return
        server = self.server
        requested_action = str(body.get("action_id") or "")
        requested_candidate = str(body.get("candidate_id") or "")
        targets = getattr(server, "review_targets", None)
        if isinstance(targets, dict):
            try:
                expected_action = safe_identifier(requested_action, "action ID")
                expected_candidate = safe_identifier(requested_candidate, "candidate ID")
            except Video2SpriteError:
                self._json_response(HTTPStatus.CONFLICT, {"error": "review_target_mismatch"})
                return
            resolved = targets.get(f"{expected_action}\0{expected_candidate}")
            if not resolved:
                self._json_response(HTTPStatus.CONFLICT, {"error": "review_target_mismatch"})
                return
            candidate_dir = Path(resolved)
        else:
            candidate_dir = Path(getattr(server, "candidate_dir"))
            expected_action = str(getattr(server, "action_id"))
            expected_candidate = str(getattr(server, "candidate_id"))
            if requested_action != expected_action or requested_candidate != expected_candidate:
                self._json_response(HTTPStatus.CONFLICT, {"error": "review_target_mismatch"})
                return
        try:
            approval = write_decision(
                candidate_dir,
                action_id=expected_action,
                candidate_id=expected_candidate,
                decision=str(body.get("decision") or ""),
                note=str(body.get("note") or ""),
                edited_events=body.get("edited_events"),
                scores=body.get("scores"),
            )
        except Video2SpriteError as exc:
            self._json_response(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        queue_path = getattr(server, "review_queue_path", None)
        if queue_path:
            _update_queue_approval(
                Path(queue_path),
                action_id=expected_action,
                candidate_id=expected_candidate,
                approval=approval,
            )
        self._json_response(
            HTTPStatus.OK,
            {
                "ok": True,
                "decision": approval["decision"],
                "reviewed_at": approval["reviewed_at"],
            },
        )


def create_server(
    candidate_dir: Path,
    *,
    action_id: str,
    candidate_id: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise Video2SpriteError("Reviewer may bind only to localhost")
    if not (candidate_dir / "review-data.json").is_file():
        raise Video2SpriteError("Process the candidate before starting the reviewer")
    handler = partial(ReviewHandler, directory=str(candidate_dir))
    server = ThreadingHTTPServer((host, port), handler)
    setattr(server, "candidate_dir", str(candidate_dir))
    setattr(server, "action_id", action_id)
    setattr(server, "candidate_id", candidate_id)
    return server


def create_run_server(
    run_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, int]:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise Video2SpriteError("Reviewer may bind only to localhost")
    built = build_review_queue(run_dir)
    entries = built["queue"]["entries"]
    if not entries:
        raise Video2SpriteError("No processed candidates are available for review")
    handler = partial(ReviewHandler, directory=str(run_dir))
    server = ThreadingHTTPServer((host, port), handler)
    setattr(server, "review_targets", built["targets"])
    setattr(server, "review_queue_path", str(run_dir / "review-queue.json"))
    return server, len(entries)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        server = create_server(
            args.candidate_dir.expanduser().resolve(),
            action_id=args.action_id,
            candidate_id=args.candidate_id,
            host=args.host,
            port=args.port,
        )
    except Video2SpriteError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    host, port = server.server_address[:2]
    print(json.dumps({"ok": True, "url": f"http://{host}:{port}/"}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
