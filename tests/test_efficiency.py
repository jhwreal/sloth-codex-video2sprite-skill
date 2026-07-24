from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video2sprite
from _v2s_common import Video2SpriteError, resolve_video_settings


class CandidateBudgetTests(unittest.TestCase):
    def _fixture(
        self, root: Path, existing_candidates: tuple[str, ...] = ("first", "second")
    ) -> argparse.Namespace:
        run_dir = root / "run"
        action_dir = run_dir / "actions" / "attack"
        action_dir.mkdir(parents=True)
        master_path = run_dir / "master" / "source.png"
        master_path.parent.mkdir(parents=True)
        master_bytes = b"synthetic-canonical-master"
        master_path.write_bytes(master_bytes)
        master_sha = hashlib.sha256(master_bytes).hexdigest()
        settings = resolve_video_settings(model="seedance-2.0")
        run = {
            "schema_version": 1,
            "character_id": "hero",
            "master": {"path": "master/source.png", "sha256": master_sha},
            "defaults": {"video": settings},
            "actions": ["attack"],
        }
        action = {
            "schema_version": 1,
            "action_id": "attack",
            "prompt": "One attack",
            "prompt_sha256": "prompt-sha",
            "frame_count": 8,
            "columns": 4,
            "duration_seconds": 4,
            "window": {"start_seconds": 0, "duration_seconds": 4},
            "loop": False,
            "audio_required": False,
            "events": [],
            "chroma": {"key": "#00ff00", "threshold": 42, "softness": 36},
            "video": {},
            "candidates": list(existing_candidates),
        }
        (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
        (action_dir / "action.json").write_text(json.dumps(action), encoding="utf-8")
        for candidate_id in action["candidates"]:
            candidate_dir = action_dir / "candidates" / candidate_id
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "candidate.json").write_text(
                json.dumps(
                    {
                        "candidate_id": candidate_id,
                        "provider": "volcengine-ark",
                        "status": "queued",
                    }
                ),
                encoding="utf-8",
            )
        return argparse.Namespace(
            run_dir=str(run_dir),
            action_id="attack",
            reference_url="https://assets.example/master.png",
            reference_url_env=None,
            reference_file=None,
            provider=None,
            model=None,
            base_url=None,
            no_audio=False,
            allow_silent_model=False,
            candidate="third",
            purpose="benchmark",
            allow_over_budget=False,
            allow_duplicate_input=False,
            reference_role="first_frame",
            resolution="720p",
            ratio="adaptive",
            seed=None,
            watermark=False,
        )

    def test_budget_blocks_accidental_third_billed_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-budget-") as raw_temp:
            args = self._fixture(Path(raw_temp))
            with mock.patch.dict(
                "os.environ",
                {"VIDEO2SPRITE_MAX_CANDIDATES_PER_ACTION": "2"},
                clear=False,
            ):
                with self.assertRaisesRegex(Video2SpriteError, "Candidate budget reached"):
                    video2sprite.command_submit(args)

    def test_explicit_override_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-budget-") as raw_temp:
            args = self._fixture(Path(raw_temp))
            args.allow_over_budget = True
            provider_result = {
                "task_id": "task-3",
                "request_id": "request-3",
                "status": "queued",
                "submitted_at": "2026-07-24T00:00:00Z",
            }
            with mock.patch.dict(
                "os.environ",
                {"VIDEO2SPRITE_MAX_CANDIDATES_PER_ACTION": "2"},
                clear=False,
            ), mock.patch(
                "video2sprite.submit_ark_video", return_value=provider_result
            ) as submit:
                result = video2sprite.command_submit(args)
            submit.assert_called_once()
            self.assertEqual(result["candidate_budget"], 2)
            candidate_path = (
                Path(args.run_dir)
                / "actions"
                / "attack"
                / "candidates"
                / "third"
                / "candidate.json"
            )
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate["purpose"], "benchmark")

    def test_local_reference_persists_no_inline_media(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-budget-") as raw_temp:
            args = self._fixture(Path(raw_temp), existing_candidates=())
            args.reference_url = None
            args.reference_file = str(Path(args.run_dir) / "master" / "source.png")
            args.candidate = "local-master"
            provider_result = {
                "task_id": "task-local",
                "request_id": "request-local",
                "status": "queued",
                "submitted_at": "2026-07-24T00:00:00Z",
            }
            with mock.patch(
                "video2sprite.submit_ark_video", return_value=provider_result
            ) as submit:
                video2sprite.command_submit(args)
            call = submit.call_args.kwargs
            self.assertIsNone(call["reference_url"])
            self.assertEqual(
                call["reference_path"],
                Path(args.reference_file).resolve(),
            )
            candidate_path = (
                Path(args.run_dir)
                / "actions"
                / "attack"
                / "candidates"
                / "local-master"
                / "candidate.json"
            )
            serialized = candidate_path.read_text(encoding="utf-8")
            lowered = serialized.lower()
            self.assertNotIn("data:image", lowered)
            self.assertNotIn(";base64,", lowered)
            self.assertNotIn('"b64_json"', lowered)
            candidate = json.loads(serialized)
            self.assertEqual(candidate["reference"], str(Path(args.reference_file).resolve()))

    def test_seedance_2_rejects_seed_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-budget-") as raw_temp:
            args = self._fixture(Path(raw_temp), existing_candidates=())
            args.seed = 42
            with mock.patch("video2sprite.submit_ark_video") as submit:
                with self.assertRaisesRegex(Video2SpriteError, "does not support"):
                    video2sprite.command_submit(args)
            submit.assert_not_called()

    def test_identical_generation_is_blocked_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-budget-") as raw_temp:
            args = self._fixture(Path(raw_temp), existing_candidates=())
            args.candidate = "first"
            provider_result = {
                "task_id": "task-1",
                "request_id": "request-1",
                "status": "queued",
                "submitted_at": "2026-07-24T00:00:00Z",
            }
            with mock.patch.dict(
                "os.environ",
                {"VIDEO2SPRITE_MAX_CANDIDATES_PER_ACTION": "3"},
                clear=False,
            ), mock.patch(
                "video2sprite.submit_ark_video", return_value=provider_result
            ) as submit:
                video2sprite.command_submit(args)
                submit.reset_mock()
                args.candidate = "second"
                with self.assertRaisesRegex(
                    Video2SpriteError, "same generation fingerprint"
                ):
                    video2sprite.command_submit(args)
                submit.assert_not_called()

    def test_compact_status_returns_counts_without_candidate_listing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-status-") as raw_temp:
            args = self._fixture(Path(raw_temp), existing_candidates=("pilot",))
            result = video2sprite.command_status(
                argparse.Namespace(run_dir=args.run_dir, compact=True)
            )
            self.assertNotIn("actions", result)
            self.assertEqual(result["action_count"], 1)
            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["candidate_statuses"], {"queued": 1})
            self.assertFalse(result["pilot_gate"]["unlocked"])

    def test_different_action_is_blocked_until_remote_pilot_is_approved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-pilot-") as raw_temp:
            args = self._fixture(Path(raw_temp), existing_candidates=("pilot",))
            run_dir = Path(args.run_dir)
            run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            run["actions"].append("jump")
            (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
            jump_dir = run_dir / "actions" / "jump"
            jump_dir.mkdir()
            attack = json.loads(
                (run_dir / "actions" / "attack" / "action.json").read_text(
                    encoding="utf-8"
                )
            )
            attack.update(
                {
                    "action_id": "jump",
                    "prompt": "One jump",
                    "prompt_sha256": "jump-prompt-sha",
                    "candidates": [],
                }
            )
            (jump_dir / "action.json").write_text(
                json.dumps(attack), encoding="utf-8"
            )
            args.action_id = "jump"
            args.candidate = "jump-first"
            with mock.patch("video2sprite.submit_ark_video") as submit:
                with self.assertRaisesRegex(Video2SpriteError, "pilot gate is locked"):
                    video2sprite.command_submit(args)
            submit.assert_not_called()

    def test_explicit_unapproved_batch_override_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-pilot-") as raw_temp:
            args = self._fixture(Path(raw_temp), existing_candidates=("pilot",))
            run_dir = Path(args.run_dir)
            run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            run["actions"].append("jump")
            (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
            attack = json.loads(
                (run_dir / "actions" / "attack" / "action.json").read_text(
                    encoding="utf-8"
                )
            )
            attack.update(
                {
                    "action_id": "jump",
                    "prompt": "One jump",
                    "prompt_sha256": "jump-prompt-sha",
                    "candidates": [],
                }
            )
            jump_dir = run_dir / "actions" / "jump"
            jump_dir.mkdir()
            (jump_dir / "action.json").write_text(
                json.dumps(attack), encoding="utf-8"
            )
            args.action_id = "jump"
            args.candidate = "jump-first"
            args.allow_unapproved_batch = True
            provider_result = {
                "task_id": "task-jump",
                "request_id": "request-jump",
                "status": "queued",
                "submitted_at": "2026-07-24T00:00:00Z",
            }
            with mock.patch(
                "video2sprite.submit_ark_video", return_value=provider_result
            ):
                result = video2sprite.command_submit(args)
            self.assertTrue(result["pilot_gate"]["override_used"])
            candidate = json.loads(
                (
                    jump_dir
                    / "candidates"
                    / "jump-first"
                    / "candidate.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(candidate["pilot_gate_override"])


class MasterCacheTests(unittest.TestCase):
    def test_identical_master_request_reuses_verified_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="video2sprite-master-") as raw_temp:
            output = Path(raw_temp) / "master.png"
            args = argparse.Namespace(
                output=str(output),
                overwrite=False,
                chroma_key="#3f0050",
                provider=None,
                model=None,
                base_url=None,
                prompt="One test hero",
                prompt_file=None,
                size="1024x1024",
                quality="high",
            )

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
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            generate.assert_called_once()


class BoundedAdvanceTests(unittest.TestCase):
    def test_wait_window_aggregates_passes_without_streaming_status(self) -> None:
        first = {
            "run_dir": "/tmp/run",
            "status": "complete",
            "submitted_tasks": 0,
            "poll": {"targets": 1, "workers": 1, "results": {"running": 1}},
            "process": {
                "enabled": True,
                "targets": 0,
                "workers": 1,
                "profile": "draft",
                "completed": 0,
                "sample": [],
                "sample_truncated": False,
            },
            "candidate_statuses": {"running": 1},
            "errors": [],
            "error_count": 0,
            "note": "no billing",
        }
        second = {
            **first,
            "poll": {"targets": 1, "workers": 1, "results": {"ready": 1}},
            "process": {
                **first["process"],
                "targets": 1,
                "completed": 1,
                "sample": [
                    {
                        "action_id": "attack",
                        "candidate_id": "pilot",
                        "qc_status": "pass",
                        "cached": False,
                    }
                ],
            },
            "candidate_statuses": {"processed": 1},
        }
        args = argparse.Namespace(wait_seconds=20, poll_interval=5)
        with mock.patch(
            "video2sprite._advance_once", side_effect=[first, second]
        ), mock.patch(
            "video2sprite.time.monotonic", side_effect=[0.0, 0.0, 5.0]
        ), mock.patch(
            "video2sprite.time.sleep"
        ) as sleep:
            result = video2sprite.command_advance(args)
        sleep.assert_called_once_with(5.0)
        self.assertEqual(result["wait"]["passes"], 2)
        self.assertEqual(result["wait"]["stop_reason"], "no_pending_provider_tasks")
        self.assertEqual(result["poll"]["targets"], 2)
        self.assertEqual(result["process"]["completed"], 1)


if __name__ == "__main__":
    unittest.main()
