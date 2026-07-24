from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "video2sprite.py"
sys.path.insert(0, str(SCRIPTS))

import video2sprite
from review_server import build_review_queue, create_run_server, write_decision


class OfflineEndToEndTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg or FFprobe is unavailable")
        try:
            from PIL import Image, ImageDraw
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("Pillow or NumPy is unavailable")
        self.Image = Image
        self.ImageDraw = ImageDraw
        self.temp = tempfile.TemporaryDirectory(prefix="video2sprite-e2e-")
        self.root = Path(self.temp.name)
        self.run_dir = self.root / "run"
        self.package_dir = self.root / "package"
        self.master = self.root / "master.png"
        self.video = self.root / "source.mp4"
        self._make_synthetic_media()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _make_synthetic_media(self) -> None:
        master = self.Image.new("RGB", (160, 120), (0, 255, 0))
        draw = self.ImageDraw.Draw(master)
        draw.rectangle((52, 28, 82, 96), fill=(235, 25, 35))
        master.save(self.master, format="PNG")

        raw_frames = self.root / "raw-frames"
        raw_frames.mkdir()
        for index in range(60):
            image = self.Image.new("RGB", (160, 120), (0, 255, 0))
            draw = self.ImageDraw.Draw(image)
            x = 20 + int(round(55 * index / 59))
            draw.rectangle((x, 34, x + 26, 96), fill=(235, 25, 35))
            image.save(raw_frames / f"frame_{index:04d}.png", format="PNG")
        command = [
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "30",
            "-i",
            str(raw_frames / "frame_%04d.png"),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=48000:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(self.video),
        ]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _cli(self, *args: str) -> Dict[str, Any]:
        environment = dict(os.environ)
        environment["VIDEO2SPRITE_LOG_MAX_CHARS"] = "4096"
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(ROOT),
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertLessEqual(len(result.stdout), 4097)
        lowered = result.stdout.lower()
        self.assertNotIn("base64", lowered)
        self.assertNotIn("data:image", lowered)
        self.assertNotIn("bearer ", lowered)
        return json.loads(result.stdout)

    def test_offline_run_review_and_godot_package(self) -> None:
        initialized = self._cli(
            "init",
            "--run-dir",
            str(self.run_dir),
            "--character-id",
            "test-hero",
            "--master",
            str(self.master),
            "--frame-size",
            "128x128",
        )
        self.assertEqual(initialized["video_default"]["model_alias"], "seedance-2.0")

        self._cli(
            "add-action",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--prompt",
            "A concise side-view attack",
            "--frames",
            "8",
            "--duration",
            "2",
            "--audio-required",
        )
        attached = self._cli(
            "attach-video",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--candidate",
            "local",
            "--video",
            str(self.video),
        )
        self.assertTrue(attached["audio_present"])

        first_process_started = time.perf_counter()
        processed = self._cli(
            "process",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--candidate",
            "local",
        )
        first_process_elapsed = time.perf_counter() - first_process_started
        self.assertEqual(processed["status"], "pass")
        self.assertEqual(processed["frame_count"], 8)
        self.assertFalse(processed["cached"])

        candidate = self.run_dir / "actions" / "attack" / "candidates" / "local"
        manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        qc = json.loads((candidate / "qc.json").read_text(encoding="utf-8"))
        self.assertEqual(qc["status"], "pass")
        self.assertEqual(manifest["frame_count"], 8)
        self.assertTrue((candidate / "atlas.png").is_file())
        self.assertTrue((candidate / "sfx.ogg").is_file())
        self.assertTrue((candidate / "preview.mp4").is_file())
        x_positions = [frame["alpha_bounds"]["x"] for frame in manifest["frames"]]
        self.assertGreater(max(x_positions) - min(x_positions), 10)

        with self.Image.open(candidate / "atlas.png") as atlas:
            self.assertEqual(atlas.mode, "RGBA")
            self.assertLess(atlas.getextrema()[3][0], atlas.getextrema()[3][1])

        approval = write_decision(
            candidate,
            action_id="attack",
            candidate_id="local",
            decision="approved",
            note="Synthetic regression fixture is correct.",
            scores={
                "visual": 4,
                "motion": 5,
                "audio": 4,
                "sync": 5,
                "overall": 4.5,
            },
        )
        self.assertEqual(approval["decision"], "approved")
        atlas_mtime = (candidate / "atlas.png").stat().st_mtime_ns
        preview_mtime = (candidate / "preview.mp4").stat().st_mtime_ns
        approval_mtime = (candidate / "approval.json").stat().st_mtime_ns
        cache_started = time.perf_counter()
        cached = self._cli(
            "process",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--candidate",
            "local",
        )
        cache_elapsed = time.perf_counter() - cache_started
        self.assertTrue(cached["cached"])
        self.assertFalse(cached["review_required"])
        self.assertIsNone(cached["approval_archived"])
        self.assertLess(cache_elapsed, 1.0)
        self.assertLess(cache_elapsed, first_process_elapsed * 0.75)
        self.assertEqual((candidate / "atlas.png").stat().st_mtime_ns, atlas_mtime)
        self.assertEqual((candidate / "preview.mp4").stat().st_mtime_ns, preview_mtime)
        self.assertEqual((candidate / "approval.json").stat().st_mtime_ns, approval_mtime)
        status = self._cli("status", "--run-dir", str(self.run_dir), "--compact")
        approval_state = status["actions"][0]["candidates"][0]["approval"]
        self.assertEqual(approval_state, {"decision": "approved", "valid": True})
        comparison = self._cli("compare", "--run-dir", str(self.run_dir))
        self.assertEqual(comparison["ranking"][0]["ranking_score"], 4.5)
        self.assertTrue(comparison["recommendation"]["provisional"])

        packaged = self._cli(
            "package",
            "--run-dir",
            str(self.run_dir),
            "--output-dir",
            str(self.package_dir),
            "--engine",
            "godot",
        )
        self.assertEqual(packaged["action_count"], 1)
        action_package = self.package_dir / "test-hero" / "attack"
        self.assertTrue((action_package / "atlas.png").is_file())
        self.assertTrue((action_package / "sfx.ogg").is_file())
        tres = (action_package / "attack.tres").read_text(encoding="utf-8")
        self.assertIn('path="res://test-hero/attack/atlas.png"', tres)
        self.assertIn('"name": &"attack"', tres)

        (candidate / "frames" / "frame_0000.png").write_bytes(b"corrupted")
        rebuilt = self._cli(
            "process",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--candidate",
            "local",
        )
        self.assertFalse(rebuilt["cached"])
        self.assertIsNotNone(rebuilt["approval_archived"])
        self.assertFalse((candidate / "approval.json").exists())
        with self.Image.open(candidate / "frames" / "frame_0000.png") as repaired:
            repaired.verify()

        for action_id in ("idle", "jump"):
            self._cli(
                "add-action",
                "--run-dir",
                str(self.run_dir),
                "--action-id",
                action_id,
                "--prompt",
                f"A concise side-view {action_id}",
                "--frames",
                "4",
                "--duration",
                "2",
            )
            self._cli(
                "attach-video",
                "--run-dir",
                str(self.run_dir),
                "--action-id",
                action_id,
                "--candidate",
                "local",
                "--video",
                str(self.video),
            )
        advanced = self._cli(
            "advance",
            "--run-dir",
            str(self.run_dir),
            "--process-ready",
            "--profile",
            "draft",
            "--local-workers",
            "2",
        )
        self.assertEqual(advanced["submitted_tasks"], 0)
        self.assertEqual(advanced["process"]["targets"], 2)
        self.assertEqual(advanced["process"]["completed"], 2)
        self.assertEqual(advanced["error_count"], 0)
        for action_id in ("idle", "jump"):
            manifest_path = (
                self.run_dir
                / "actions"
                / action_id
                / "candidates"
                / "local"
                / "manifest.json"
            )
            draft_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                draft_manifest["provenance"]["processing_profile"], "draft"
            )
        idle_candidate = (
            self.run_dir / "actions" / "idle" / "candidates" / "local"
        )
        write_decision(
            idle_candidate,
            action_id="idle",
            candidate_id="local",
            decision="approved",
        )
        with self.assertRaisesRegex(
            video2sprite.Video2SpriteError, "production profile"
        ):
            video2sprite._verify_approval(idle_candidate)
        no_op_advance = self._cli(
            "advance",
            "--run-dir",
            str(self.run_dir),
            "--process-ready",
        )
        self.assertEqual(no_op_advance["process"]["targets"], 0)
        queue = build_review_queue(self.run_dir)["queue"]
        self.assertEqual(len(queue["entries"]), 3)
        self.assertTrue((self.run_dir / "review.html").is_file())
        try:
            server, review_count = create_run_server(self.run_dir)
        except PermissionError:
            server = None
        if server is not None:
            self.assertEqual(review_count, 3)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address[:2]
                with urllib.request.urlopen(
                    f"http://{host}:{port}/review.html", timeout=3
                ) as response:
                    self.assertEqual(response.status, 200)
                decision_body = json.dumps(
                    {
                        "action_id": "jump",
                        "candidate_id": "local",
                        "decision": "rejected",
                        "note": "Synthetic run-level review test.",
                        "scores": {"overall": 2},
                    }
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"http://{host}:{port}/api/decision",
                    data=decision_body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertTrue(result["ok"])
                jump_approval = json.loads(
                    (
                        self.run_dir
                        / "actions"
                        / "jump"
                        / "candidates"
                        / "local"
                        / "approval.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(jump_approval["decision"], "rejected")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

        for json_path in self.run_dir.rglob("*.json"):
            serialized = json_path.read_text(encoding="utf-8").lower()
            self.assertNotIn("data:image", serialized, msg=str(json_path))
            self.assertNotIn('"b64_json"', serialized, msg=str(json_path))
            self.assertNotIn("bearer ", serialized, msg=str(json_path))


if __name__ == "__main__":
    unittest.main()
