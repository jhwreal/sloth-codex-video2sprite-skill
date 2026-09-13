from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video2sprite
from _v2s_common import Video2SpriteError


class RuntimeReadinessTests(unittest.TestCase):
    def test_existing_but_broken_media_tool_is_not_reported_ready(self):
        with mock.patch("video2sprite.require_executable", return_value="/tmp/fake-ffmpeg"):
            for code in (0, -6, 1):
                with self.subTest(returncode=code), mock.patch(
                    "video2sprite.run_command", return_value=mock.Mock(returncode=code)
                ) as run:
                    self.assertEqual(video2sprite._executable_ready("ffmpeg"), code == 0)
                    run.assert_called_once_with(["/tmp/fake-ffmpeg", "-version"], check=False, timeout=5)
            with mock.patch("video2sprite.run_command", side_effect=Video2SpriteError("Command timed out")):
                self.assertFalse(video2sprite._executable_ready("ffmpeg"))
        with mock.patch("video2sprite.require_executable", side_effect=Video2SpriteError("Missing")):
            self.assertFalse(video2sprite._executable_ready("ffmpeg"))


class MasterCacheTests(unittest.TestCase):
    def test_identical_master_request_reuses_verified_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-master-") as raw_temp:
            output = Path(raw_temp) / "master.png"
            args = video2sprite._build_parser().parse_args([
                "generate-master", "--output", str(output), "--prompt", "One test hero",
            ])

            def fake_generate(**kwargs):
                kwargs["output_path"].write_bytes(b"synthetic-png")
                return {
                    "provider": "openai",
                    "model_id": "gpt-image-2",
                    "request_id": "req-master",
                    "created": 1,
                    "usage": {"total_tokens": 7},
                    "sha256": hashlib.sha256(b"synthetic-png").hexdigest(),
                    "bytes": len(b"synthetic-png"),
                    "completed_at": "2026-07-24T00:00:00Z",
                }

            with mock.patch(
                "video2sprite.generate_openai_master", side_effect=fake_generate
            ) as generate:
                first = video2sprite.command_generate_master(args)
                second = video2sprite.command_generate_master(args)
                self.assertEqual(generate.call_args.kwargs["quality"], "medium")
                args.quality = "high"
                with self.assertRaisesRegex(Video2SpriteError, "reuse the existing approved master"):
                    video2sprite.command_generate_master(args)
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
