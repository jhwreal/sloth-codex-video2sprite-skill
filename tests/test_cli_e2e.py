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
from _v2s_media import (
    _key_rgba,
    analyze_audio,
    extract_audio,
    extract_video_frames,
    probe_media,
)
from review_server import build_review_queue, create_run_server, write_decision
from _v2s_receipts import write_libtv_receipt


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

    def _cli_failure(self, *args: str) -> Dict[str, Any]:
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
        self.assertEqual(result.returncode, 2, msg=result.stderr)
        self.assertLessEqual(len(result.stdout), 4097)
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
            "--placement",
            "fit-union",
            "--chroma-key",
            "#00ff00",
            "--chroma-mode",
            "global",
            "--chroma-threshold",
            "42",
            "--chroma-softness",
            "36",
        )
        self.assertNotIn("video_default", initialized)

        self._cli(
            "add-action",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--prompt",
            "A concise side-view attack",
            "--fps",
            "4",
            "--duration",
            "2",
            "--audio-required",
        )
        libtv_receipt = self.root / "source.mp4.libtv-receipt.json"
        write_libtv_receipt(
            self.video,
            libtv_receipt,
            libtv_version="libtv test-1.0",
            node="synthetic-node",
            reference_audit="no-libtv-ancestors",
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
            "--source-origin",
            "libtv",
            "--source-receipt",
            str(libtv_receipt),
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
        self.assertEqual(processed["status"], "review")
        self.assertEqual(processed["frame_count"], 8)
        self.assertFalse(processed["cached"])

        candidate = self.run_dir / "actions" / "attack" / "candidates" / "local"
        manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        qc = json.loads((candidate / "qc.json").read_text(encoding="utf-8"))
        self.assertEqual(qc["status"], "review")
        self.assertIn(
            "libtv_visual_watermark_review_required",
            [issue["code"] for issue in qc["issues"]],
        )
        self.assertEqual(manifest["frame_count"], 8)
        self.assertTrue((candidate / "atlas.png").is_file())
        self.assertTrue((candidate / "sfx.ogg").is_file())
        self.assertTrue((candidate / "preview.mp4").is_file())
        self.assertTrue((candidate / "source.receipt.json").is_file())
        x_positions = [frame["alpha_bounds"]["x"] for frame in manifest["frames"]]
        self.assertGreater(max(x_positions) - min(x_positions), 10)

        with self.Image.open(candidate / "atlas.png") as atlas:
            self.assertEqual(atlas.mode, "RGBA")
            self.assertLess(atlas.getextrema()[3][0], atlas.getextrema()[3][1])

        copied_receipt = candidate / "source.receipt.json"
        clean_receipt_bytes = copied_receipt.read_bytes()
        copied_receipt.write_text("{}", encoding="utf-8")
        process_failure = self._cli_failure(
            "process",
            "--run-dir",
            str(self.run_dir),
            "--action-id",
            "attack",
            "--candidate",
            "local",
        )
        self.assertIn("LibTV receipt", process_failure["error"])
        with self.assertRaisesRegex(video2sprite.Video2SpriteError, "LibTV receipt"):
            write_decision(
                candidate,
                action_id="attack",
                candidate_id="local",
                decision="approved",
            )
        copied_receipt.write_bytes(clean_receipt_bytes)

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
        self.assertIn("source_receipt", approval["reviewed_hashes"])
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
        status = self._cli("status", "--run-dir", str(self.run_dir))
        approval_state = status["actions"][0]["candidates"][0]["approval"]
        self.assertEqual(approval_state, {"decision": "approved", "valid": True})
        compact_status = self._cli(
            "status", "--run-dir", str(self.run_dir), "--compact"
        )
        self.assertNotIn("actions", compact_status)
        self.assertEqual(compact_status["approvals"]["approved"], 1)
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
        self.assertTrue((action_package / "source.receipt.json").is_file())
        tres = (action_package / "attack.tres").read_text(encoding="utf-8")
        self.assertIn('path="res://test-hero/attack/atlas.png"', tres)
        self.assertIn('"name": &"attack"', tres)
        copied_receipt.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(video2sprite.Video2SpriteError, "LibTV receipt"):
            video2sprite._verify_approval(candidate)
        copied_receipt.write_bytes(clean_receipt_bytes)

        action_path = candidate.parents[1] / "action.json"
        original_action = action_path.read_text(encoding="utf-8")
        changed_action = json.loads(original_action)
        changed_action["motion"]["style"] = "restrained"
        action_path.write_text(json.dumps(changed_action), encoding="utf-8")
        self.assertFalse(video2sprite._approval_state(candidate)["valid"])
        with self.assertRaisesRegex(video2sprite.Video2SpriteError, "approval is stale"):
            video2sprite._verify_approval(candidate)
        action_path.write_text(original_action, encoding="utf-8")
        self.assertTrue(video2sprite._approval_state(candidate)["valid"])

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
                "--source-origin",
                "local",
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
        reviewer_html = (self.run_dir / "review.html").read_text(encoding="utf-8")
        self.assertIn("全部关键帧", reviewer_html)
        self.assertIn('id="selected-frame"', reviewer_html)
        self.assertIn(
            'id="counter" aria-label="当前 Sprite 和总 Sprite 数"',
            reviewer_html,
        )
        self.assertIn('id="title">动作资产工作台</h1>', reviewer_html)
        self.assertLess(
            reviewer_html.index('id="counter"'),
            reviewer_html.index("<main>"),
        )
        self.assertLess(
            reviewer_html.index('id="title"'),
            reviewer_html.index("<main>"),
        )
        self.assertIn('id="mode-process"', reviewer_html)
        self.assertIn('id="mode-character"', reviewer_html)
        self.assertIn('id="mode-game"', reviewer_html)
        self.assertIn('id="game-select"', reviewer_html)
        self.assertIn('id="action-navigation"', reviewer_html)
        self.assertIn('fetch("character-action-queue.json"', reviewer_html)
        self.assertIn("indices: {process: 0, character: 0}", reviewer_html)
        self.assertIn("game.is_default", reviewer_html)
        self.assertIn(
            "`工作中（${state.processEntries.length}）`",
            reviewer_html,
        )
        self.assertIn(
            "`角色动作（${state.characterEntries.length}）`",
            reviewer_html,
        )
        self.assertIn("`游戏动作（${game.display_name} · ${game.bound_action_ids.length}）`", reviewer_html)
        self.assertNotIn('id="confirmed-toggle"', reviewer_html)
        self.assertNotIn('fetch("confirmed-bound-queue.json"', reviewer_html)
        self.assertNotIn('<aside>\n      <h1 id="title">', reviewer_html)
        self.assertIn("selectFrame(frame, manifestPath, figure)", reviewer_html)
        self.assertIn('event.key === "ArrowLeft"', reviewer_html)
        self.assertIn('"ArrowRight"', reviewer_html)
        self.assertIn("moveSelectedFrame", reviewer_html)
        self.assertIn('scrollIntoView({block: "nearest", inline: "nearest"})', reviewer_html)
        self.assertNotIn('id="note"', reviewer_html)
        self.assertNotIn('id="use"', reviewer_html)
        self.assertNotIn('id="redo"', reviewer_html)
        self.assertNotIn("人工评分", reviewer_html)
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

    def test_dark_border_matte_preserves_enclosed_dark_costume_pixels(self) -> None:
        import numpy as np

        matte = (63, 0, 80)
        rgb = np.empty((64, 64, 3), dtype=np.uint8)
        rgb[:] = matte
        rgb[14:54, 18:46] = (220, 176, 92)
        rgb[24:44, 25:39] = matte
        rgba, _ = _key_rgba(
            np,
            rgb,
            matte,
            threshold=8.0,
            softness=16.0,
            mode="border",
        )
        self.assertEqual(int(rgba[0, 0, 3]), 0)
        self.assertEqual(int(rgba[32, 32, 3]), 255)
        self.assertEqual(tuple(int(value) for value in rgba[32, 32, :3]), matte)

    def test_fixed_decode_writes_only_target_canvas_pixels(self) -> None:
        output = self.root / "scaled-decode"
        paths, _ = extract_video_frames(
            self.video,
            output,
            frame_count=8,
            start_seconds=0,
            duration_seconds=2,
            fixed_source_size=(160, 120),
            fixed_target_size=(80, 64),
            fixed_pad_color="#3f0050",
            resampling="lanczos",
        )
        self.assertEqual(len(paths), 8)
        with self.Image.open(paths[0]) as frame:
            self.assertEqual(frame.size, (80, 64))

    def test_fixed_dark_24fps_action_preserves_full_window(self) -> None:
        matte = (63, 0, 80)
        run_dir = self.root / "dark-run"
        master = self.root / "dark-master.png"
        video = self.root / "dark-source.mp4"
        raw_frames = self.root / "dark-frames"
        raw_frames.mkdir()
        master_image = self.Image.new("RGB", (160, 96), matte)
        master_draw = self.ImageDraw.Draw(master_image)
        master_draw.rectangle((62, 18, 88, 80), fill=(235, 195, 112))
        master_image.save(master, format="PNG")
        for index in range(48):
            image = self.Image.new("RGB", (160, 96), matte)
            draw = self.ImageDraw.Draw(image)
            x = 52 + int(round(24 * index / 47))
            # A deep crouch/wide extension must survive fixed-canvas processing;
            # matching every frame's bounding height would erase this pose change.
            extension = 20 if 12 <= index < 36 else 0
            draw.rectangle((x, 18 + extension, x + 26 + extension, 80), fill=(235, 195, 112))
            draw.rectangle((x + 9, 44, x + 17, 60), fill=matte)
            image.save(raw_frames / f"frame_{index:04d}.png", format="PNG")
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                "24",
                "-i",
                str(raw_frames / "frame_%04d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(video),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._cli(
            "init",
            "--run-dir",
            str(run_dir),
            "--character-id",
            "dark-hero",
            "--master",
            str(master),
            "--frame-size",
            "160x96",
            "--pivot",
            "80,80",
            "--placement",
            "fixed",
            "--resampling",
            "nearest",
        )
        self._cli(
            "add-action",
            "--run-dir",
            str(run_dir),
            "--action-id",
            "slash",
            "--prompt",
            "One right-facing slash",
            "--fps",
            "24",
            "--duration",
            "2",
        )
        self._cli(
            "attach-video",
            "--run-dir",
            str(run_dir),
            "--action-id",
            "slash",
            "--candidate",
            "local",
            "--video",
            str(video),
            "--source-origin",
            "local",
        )
        processed = self._cli(
            "process",
            "--run-dir",
            str(run_dir),
            "--action-id",
            "slash",
            "--candidate",
            "local",
        )
        self.assertEqual(processed["frame_count"], 48)
        candidate = run_dir / "actions" / "slash" / "candidates" / "local"
        manifest = json.loads(
            (candidate / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["fps"], 24.0)
        self.assertEqual(manifest["sampling"]["requested_fps"], 24.0)
        self.assertEqual(manifest["transform"]["placement"], "fixed")
        self.assertEqual(
            manifest["frames"][0]["pivot"],
            {"x": 80.0, "y": 80.0, "normalized": [0.5, 0.83333333]},
        )
        self.assertEqual(len(list((candidate / "frames").glob("frame_*.png"))), 48)
        bounds = [frame["alpha_bounds"] for frame in manifest["frames"]]
        self.assertAlmostEqual(bounds[-1]["x"] - bounds[0]["x"], 24, delta=2)
        self.assertGreater(bounds[20]["width"] - bounds[0]["width"], 15)
        self.assertGreater(bounds[0]["height"] - bounds[20]["height"], 15)
        self.assertTrue(all(frame["pivot"] == manifest["frames"][0]["pivot"] for frame in manifest["frames"]))


class AudioHeadroomTests(unittest.TestCase):
    def test_hot_source_is_exported_with_codec_safe_headroom(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("FFmpeg or FFprobe is unavailable")
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow or NumPy is unavailable")

        with tempfile.TemporaryDirectory(prefix="video2sprite-audio-") as raw_temp:
            temp = Path(raw_temp)
            source = temp / "hot.wav"
            destination = temp / "headroom.ogg"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:sample_rate=48000:duration=1",
                    "-af",
                    "volume=8",
                    "-c:a",
                    "pcm_s16le",
                    str(source),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            source_metrics = analyze_audio(
                source,
                frame_count=4,
                action_duration=1.0,
                event_names=[],
                ffmpeg=ffmpeg,
            )
            self.assertGreaterEqual(source_metrics["peak"], 0.99)

            result = extract_audio(
                source,
                destination,
                start_seconds=0.0,
                duration_seconds=1.0,
                source_probe=probe_media(source, ffprobe=ffprobe),
                ffmpeg=ffmpeg,
            )
            output_metrics = analyze_audio(
                destination,
                frame_count=4,
                action_duration=1.0,
                event_names=[],
                ffmpeg=ffmpeg,
            )
            self.assertTrue(result["present"])
            self.assertEqual(result["gain"], 0.85)
            self.assertGreater(output_metrics["peak"], 0.70)
            self.assertLess(output_metrics["peak"], 0.98)


if __name__ == "__main__":
    unittest.main()
