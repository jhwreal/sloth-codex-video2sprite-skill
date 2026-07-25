from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _v2s_common import (
    Video2SpriteError,
    candidate_processing_fingerprint,
    credential_source,
    credential_value,
    load_private_credentials,
    resolve_video_settings,
    safe_json_text,
    sanitize,
    store_private_credential,
)
from _v2s_media import _fixed_canvas_geometry


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


class PrivateCredentialsTests(unittest.TestCase):
    def _credentials_file(self, directory: str, text: str) -> Path:
        path = Path(directory) / "credentials.env"
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_legacy_seedance_key_is_available_to_ark_without_mutating_env(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = self._credentials_file(
                raw_temp,
                "# local only\nSEEDANCE_API_KEY=file-secret\n",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    credential_value("ARK_API_KEY", path=path),
                    "file-secret",
                )
                self.assertEqual(
                    credential_source("ARK_API_KEY", path=path),
                    "private_file",
                )
                self.assertNotIn("ARK_API_KEY", os.environ)
                self.assertNotIn("SEEDANCE_API_KEY", os.environ)

    def test_environment_beats_private_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = self._credentials_file(
                raw_temp,
                "ARK_API_KEY=file-secret\nSEEDANCE_API_KEY=legacy-secret\n",
            )
            with mock.patch.dict(
                os.environ,
                {"ARK_API_KEY": "environment-secret"},
                clear=True,
            ):
                self.assertEqual(
                    credential_value("ARK_API_KEY", path=path),
                    "environment-secret",
                )
                self.assertEqual(
                    credential_source("ARK_API_KEY", path=path),
                    "environment",
                )

    def test_exact_private_ark_key_beats_legacy_alias(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = self._credentials_file(
                raw_temp,
                "SEEDANCE_API_KEY=legacy-secret\nARK_API_KEY=exact-secret\n",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    credential_value("ARK_API_KEY", path=path),
                    "exact-secret",
                )

    def test_unrelated_entries_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = self._credentials_file(
                raw_temp,
                "UNRELATED=value\nexport OPENAI_API_KEY='openai-secret'\n",
            )
            self.assertEqual(
                load_private_credentials(path),
                {"OPENAI_API_KEY": "openai-secret"},
            )

    def test_store_creates_fixed_permissions_and_preserves_other_provider(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = Path(raw_temp) / "private" / "credentials.env"
            store_private_credential(
                "OPENAI_API_KEY",
                "openai-secret",
                path=path,
            )
            store_private_credential(
                "ARK_API_KEY",
                "ark-secret",
                path=path,
            )
            self.assertEqual(
                load_private_credentials(path),
                {
                    "OPENAI_API_KEY": "openai-secret",
                    "ARK_API_KEY": "ark-secret",
                },
            )
            if os.name == "posix":
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_store_canonicalizes_legacy_seedance_name(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = self._credentials_file(
                raw_temp,
                "SEEDANCE_API_KEY=legacy-secret\n",
            )
            store_private_credential(
                "ARK_API_KEY",
                "ark-secret",
                path=path,
            )
            self.assertEqual(
                load_private_credentials(path),
                {"ARK_API_KEY": "ark-secret"},
            )

    def test_store_rejects_multiline_value_without_exposing_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = Path(raw_temp) / "credentials.env"
            with self.assertRaises(Video2SpriteError) as captured:
                store_private_credential(
                    "ARK_API_KEY",
                    "first-line\nmust-never-appear-in-error",
                    path=path,
                )
            self.assertNotIn("must-never-appear-in-error", str(captured.exception))

    @unittest.skipUnless(os.name == "posix", "POSIX permission check")
    def test_group_or_world_access_is_rejected_without_exposing_value(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            path = self._credentials_file(
                raw_temp,
                "ARK_API_KEY=must-never-appear-in-error\n",
            )
            path.chmod(0o644)
            with self.assertRaises(Video2SpriteError) as captured:
                load_private_credentials(path)
            self.assertNotIn("must-never-appear-in-error", str(captured.exception))
            self.assertIn("chmod 600", str(captured.exception))


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
            "pivot": {"x": 64, "y": 112, "normalized": [0.5, 0.875]},
            "placement": "fixed",
            "resampling": "nearest",
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
        changed_pivot = candidate_processing_fingerprint(
            {
                **run,
                "pivot": {"x": 64, "y": 128, "normalized": [0.5, 1.0]},
            },
            action,
            candidate,
            columns=None,
            profile="production",
        )
        self.assertNotEqual(production, draft)
        self.assertNotEqual(production, changed_source)
        self.assertNotEqual(production, changed_pivot)


class FixedCanvasGeometryTests(unittest.TestCase):
    def test_large_provider_canvas_is_reduced_before_png_extraction(self) -> None:
        geometry = _fixed_canvas_geometry((1152, 704), (288, 176))
        self.assertEqual(geometry["scaled_width"], 288)
        self.assertEqual(geometry["scaled_height"], 176)
        self.assertEqual(geometry["offset_x"], 0)
        self.assertEqual(geometry["offset_y"], 0)
        self.assertEqual(geometry["scale"], 0.25)


if __name__ == "__main__":
    unittest.main()
