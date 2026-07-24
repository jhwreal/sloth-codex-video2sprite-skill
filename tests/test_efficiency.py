from __future__ import annotations

import argparse
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
        settings = resolve_video_settings(model="seedance-2.0")
        run = {
            "schema_version": 1,
            "character_id": "hero",
            "master": {"sha256": "master-sha"},
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
            "duration_seconds": 2,
            "window": {"start_seconds": 0, "duration_seconds": 2},
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


if __name__ == "__main__":
    unittest.main()
