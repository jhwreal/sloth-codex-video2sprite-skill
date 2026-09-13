from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video2sprite
from _v2s_common import Video2SpriteError, atomic_write_json, credential_value, load_private_credentials


class RemovedArkIntegrationTests(unittest.TestCase):
    def test_removed_commands_and_options_are_rejected_without_network(self):
        parser = video2sprite._build_parser()
        cases = (
            ["submit"], ["poll"], ["configure-key", "--name", "ark"],
            ["advance", "--run-dir", "/tmp/unused", "--wait-seconds", "50"],
            ["advance", "--run-dir", "/tmp/unused", "--network-workers", "4"],
        )
        with mock.patch("urllib.request.urlopen") as network:
            for args in cases:
                with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        parser.parse_args(args)
                    self.assertEqual(raised.exception.code, 2)
            network.assert_not_called()

    def test_legacy_video_environment_cannot_restore_adapter(self):
        with mock.patch.dict(os.environ, {
            "VIDEO2SPRITE_VIDEO_PROVIDER": "volcengine-ark",
            "VIDEO2SPRITE_VIDEO_MODEL": "obsolete-model",
            "VIDEO2SPRITE_VIDEO_BASE_URL": "https://invalid.example",
            "ARK_API_KEY": "obsolete-key",
        }), mock.patch("urllib.request.urlopen") as network:
            args = video2sprite._build_parser().parse_args(["models"])
            result = args.handler(args)
            self.assertNotIn("video_default", result)
            self.assertNotIn("video_models", result)
            self.assertNotIn("obsolete", json.dumps(result))
            with self.assertRaises(Video2SpriteError):
                credential_value("ARK_API_KEY")
            network.assert_not_called()

    def test_legacy_private_keys_are_ignored_without_rewriting_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.env"
            path.write_text("ARK_API_KEY=old-key\nSEEDANCE_API_KEY=old-alias\nOPENAI_API_KEY=image-key\n")
            path.chmod(0o600)
            original = path.read_bytes()
            self.assertEqual(load_private_credentials(path), {"OPENAI_API_KEY": "image-key"})
            self.assertEqual(path.read_bytes(), original)

    def test_advance_preserves_pending_legacy_record_and_processes_local_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_write_json(root / "run.json", {
                "schema_version": 1, "character_id": "hero", "master": {"sha256": "master"},
                "actions": ["attack"],
            })
            action = root / "actions" / "attack"
            atomic_write_json(action / "action.json", {"action_id": "attack", "candidates": ["old", "local"]})
            old = action / "candidates" / "old" / "candidate.json"
            atomic_write_json(old, {"provider": "volcengine-ark", "task_id": "legacy-task", "status": "queued"})
            original = old.read_bytes()
            local = action / "candidates" / "local"
            atomic_write_json(local / "candidate.json", {"provider": "local", "status": "ready"})
            (local / "source.mp4").write_bytes(b"synthetic-placeholder-not-decoded")
            args = video2sprite._build_parser().parse_args([
                "advance", "--run-dir", str(root), "--process-ready",
            ])
            with mock.patch("urllib.request.urlopen") as network, mock.patch(
                "video2sprite.command_process", return_value={"status": "pass", "cached": False}
            ) as process:
                result = args.handler(args)
                network.assert_not_called()
                process.assert_called_once()
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["error_count"], 1)
            self.assertEqual(result["process"]["completed"], 1)
            self.assertIn("Remote polling is unavailable", result["errors"][0]["error"])
            self.assertEqual(old.read_bytes(), original)
            self.assertEqual(result["submitted_tasks"], 0)
            status_args = video2sprite._build_parser().parse_args(["status", "--run-dir", str(root), "--compact"])
            summary = status_args.handler(status_args)
            self.assertEqual(summary["candidate_count"], 2)
            self.assertNotIn("actions", summary)
            self.assertNotIn("pilot_gate", summary)


if __name__ == "__main__":
    unittest.main()
