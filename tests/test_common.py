from __future__ import annotations

import json
import sys
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _v2s_common import (
    candidate_processing_fingerprint,
    resolve_video_settings,
    safe_json_text,
    sanitize,
)


class MediaFirewallTests(unittest.TestCase):
    def test_sanitize_removes_inline_media_secrets_queries_and_bytes(self) -> None:
        value = {
            "b64_json": "aGVsbG8=",
            "Authorization": "not-a-real-credential",
            "preview": "data:image/png;base64,aGVsbG8=",
            "download": "https://media.example/video.mp4?token=secret&expires=1",
            "error": (
                "download https://media.example/video.mp4?token=secret failed; "
                "Authorization: Bearer fake"
            ),
            "payload": b"\x89PNG\r\n",
            "unknown_encoded": "QUJD" * 64,
            "long": "x" * 5000,
        }
        result = sanitize(value)
        self.assertEqual(result["b64_json"], "[redacted]")
        self.assertEqual(result["Authorization"], "[redacted]")
        self.assertEqual(result["preview"], "[redacted_inline_media]")
        self.assertEqual(result["download"], "https://media.example/video.mp4")
        self.assertNotIn("token=", result["error"])
        self.assertNotIn("Bearer fake", result["error"])
        self.assertEqual(result["payload"], {"redacted_bytes": 6})
        self.assertIn("redacted_probable_base64", result["unknown_encoded"])
        self.assertTrue(result["long"].startswith("[redacted_"))

    def test_safe_json_is_bounded(self) -> None:
        text = safe_json_text(
            {
                "ok": True,
                "command": "test",
                "rows": [{"value": "y" * 2000} for _ in range(100)],
            },
            max_chars=700,
        )
        self.assertLessEqual(len(text), 700)
        payload = json.loads(text)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["command"], "test")


class ModelSelectionTests(unittest.TestCase):
    def test_environment_default_and_cli_override(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"VIDEO2SPRITE_VIDEO_MODEL": "seedance-2.0-fast"},
            clear=False,
        ):
            environment_default = resolve_video_settings()
            explicit = resolve_video_settings(model="seedance-1.5-pro")
        self.assertEqual(environment_default["model_alias"], "seedance-2.0-fast")
        self.assertEqual(
            environment_default["model_id"], "doubao-seedance-2-0-fast-260128"
        )
        self.assertEqual(explicit["model_alias"], "seedance-1.5-pro")

    def test_full_model_id_is_accepted(self) -> None:
        settings = resolve_video_settings(model="account-specific-model-123")
        self.assertEqual(settings["model_id"], "account-specific-model-123")
        self.assertEqual(settings["capabilities"]["tier"], "custom")


class ProcessingFingerprintTests(unittest.TestCase):
    def test_profile_and_source_are_cache_keys(self) -> None:
        run = {
            "master": {"sha256": "master"},
            "frame_size": {"width": 128, "height": 128},
        }
        action = {
            "prompt_sha256": "prompt",
            "frame_count": 8,
            "columns": 4,
            "duration_seconds": 2,
            "window": {"start_seconds": 0, "duration_seconds": 2},
            "loop": False,
            "audio_required": True,
            "events": [],
            "chroma": {"key": "#00ff00", "threshold": 42, "softness": 36},
            "video": {},
        }
        candidate = {"source": {"sha256": "video-a"}}
        production = candidate_processing_fingerprint(
            run, action, candidate, columns=None, profile="production"
        )
        draft = candidate_processing_fingerprint(
            run, action, candidate, columns=None, profile="draft"
        )
        changed_source = candidate_processing_fingerprint(
            run,
            action,
            {"source": {"sha256": "video-b"}},
            columns=None,
            profile="production",
        )
        self.assertNotEqual(production, draft)
        self.assertNotEqual(production, changed_source)


if __name__ == "__main__":
    unittest.main()
