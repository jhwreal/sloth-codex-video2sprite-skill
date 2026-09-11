from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video2sprite
from _v2s_common import (
    Video2SpriteError,
    action_processing_fingerprint,
    atomic_write_json,
    fingerprint,
    load_json,
)


class PromptGuardTests(unittest.TestCase):
    def test_master_prompt_requires_connected_prop_and_excludes_secondary_equipment(self) -> None:
        prompt = video2sprite._master_prompt(
            "Alice holding one sword",
            "#3f0050",
        )

        self.assertIn("physically connected", prompt)
        self.assertIn("handle visibly seated in the grip", prompt)
        self.assertIn("no unrelated gun, holster, scabbard", prompt)


class MotionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="video2sprite-motion-")
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name) / "run"
        atomic_write_json(
            self.run_dir / "run.json",
            {
                "schema_version": 1,
                "master": {"sha256": "synthetic-master"},
                "defaults": {},
                "actions": [],
                "chroma": {"key": "#3f0050", "mode": "border"},
            },
        )
        self.parser = video2sprite._build_parser()

    def _add(self, action_id: str, *flags: str, prompt: str = "One heavy slash"):
        args = self.parser.parse_args(
            [
                "add-action", "--run-dir", str(self.run_dir),
                "--action-id", action_id, "--prompt", prompt,
                "--fps", "24", "--duration", "4",
                "--window-start", "0.25", "--window-duration", "0.75",
                *flags,
            ]
        )
        result = args.handler(args)
        action = load_json(self.run_dir / "actions" / action_id / "action.json")
        self.assertEqual(result["motion"], action["motion"])
        return action

    def _submit_args(self, action_id: str, candidate: str):
        return self.parser.parse_args(
            [
                "submit", "--run-dir", str(self.run_dir),
                "--action-id", action_id, "--candidate", candidate,
                "--reference-url", "https://assets.example/master.png",
            ]
        )

    def _provider_result(self):
        return {
            "task_id": "synthetic-task", "status": "queued",
            "submitted_at": "2026-09-11T00:00:00Z",
        }

    def test_defaults_and_explicit_action_endings_survive_save_load(self) -> None:
        cases = (
            ("heavy", (), ("pixel-act", "in-place", "recover")),
            ("idle", ("--loop", "--root-motion", "planted", "--motion-style", "restrained"),
             ("restrained", "planted", "loop")),
            ("death", ("--end-state", "hold"), ("pixel-act", "in-place", "hold")),
            ("combo-middle", ("--end-state", "hold"), ("pixel-act", "in-place", "hold")),
            ("dash", ("--root-motion", "travel", "--motion-style", "natural"),
             ("natural", "travel", "recover")),
        )
        for action_id, flags, expected in cases:
            with self.subTest(action=action_id):
                action = self._add(action_id, *flags)
                self.assertEqual(
                    video2sprite._motion_settings(action),
                    dict(zip(("style", "root_motion", "end_state"), expected)),
                )
                self.assertEqual(action["frame_count"], 18)
                self.assertEqual(action["sampling"]["fps"], 24)

    def test_profile_is_not_guessed_from_action_id_or_prompt_language(self) -> None:
        first = self._add("death-by-name-only", prompt="呼吸待机")
        second = self._add("idle-by-name-only", prompt="一次重斩")
        self.assertEqual(first["motion"], second["motion"])

    def test_invalid_loop_contract_fails_without_creating_action(self) -> None:
        for flags in (
            ("--loop", "--root-motion", "travel"),
            ("--loop", "--end-state", "hold"),
            ("--loop", "--end-state", "recover"),
        ):
            with self.subTest(flags=flags), self.assertRaises(Video2SpriteError):
                self._add("invalid", *flags)
            self.assertFalse((self.run_dir / "actions" / "invalid").exists())
            self.assertEqual(load_json(self.run_dir / "run.json")["actions"], [])

    def test_invalid_stored_settings_never_reach_provider(self) -> None:
        action = self._add("attack")
        path = self.run_dir / "actions" / "attack" / "action.json"
        for invalid in (
            None, [], {"style": "typo"}, {"root_motion": "frozen"},
            {"end_state": "loop"}, {"end_state": "unknown"}, {"amplitude": 2},
        ):
            with self.subTest(motion=invalid):
                atomic_write_json(path, {**action, "motion": invalid})
                with mock.patch("video2sprite.submit_ark_video") as submit:
                    with self.assertRaises(Video2SpriteError):
                        video2sprite.command_submit(self._submit_args("attack", "bad"))
                    submit.assert_not_called()
                self.assertFalse((path.parent / "candidates" / "bad").exists())

    def test_provider_receives_direction_and_window_with_auditable_fingerprint(self) -> None:
        action = self._add("heavy")
        with mock.patch(
            "video2sprite.submit_ark_video", return_value=self._provider_result()
        ) as submit:
            video2sprite.command_submit(self._submit_args("heavy", "pilot"))
        kwargs = submit.call_args.kwargs
        sent_prompt = kwargs["prompt"]
        # Regress the contradictory all-frame foot lock and omitted runtime window.
        self.assertNotIn("Keep the foot-root at one fixed image coordinate", sent_prompt)
        self.assertIn("bounded pose displacement", sent_prompt)
        self.assertIn("0.25s to 1s", sent_prompt)
        self.assertEqual(kwargs["duration"], 4)
        candidate_path = self.run_dir / "actions" / "heavy" / "candidates" / "pilot" / "candidate.json"
        candidate = load_json(candidate_path)
        self.assertEqual(candidate["request"]["motion"], action["motion"])
        self.assertEqual(candidate["request"]["prompt_sha256"], fingerprint(sent_prompt))
        serialized = candidate_path.read_text(encoding="utf-8")
        self.assertNotIn(sent_prompt, serialized)
        self.assertLess(len(serialized), 4096)

    def test_motion_changes_generation_input_and_duplicate_guard_still_works(self) -> None:
        action = self._add("attack")
        path = self.run_dir / "actions" / "attack" / "action.json"
        with mock.patch(
            "video2sprite.submit_ark_video", return_value=self._provider_result()
        ) as submit:
            video2sprite.command_submit(self._submit_args("attack", "pixel"))
            updated = load_json(path)
            updated["motion"]["style"] = "restrained"
            atomic_write_json(path, updated)
            video2sprite.command_submit(self._submit_args("attack", "quiet"))
            self.assertEqual(submit.call_count, 2)
            self.assertNotEqual(
                submit.call_args_list[0].kwargs["prompt"],
                submit.call_args_list[1].kwargs["prompt"],
            )
            with self.assertRaisesRegex(Video2SpriteError, "same generation fingerprint"):
                video2sprite.command_submit(self._submit_args("attack", "duplicate"))
            self.assertEqual(submit.call_count, 2)
        candidates = path.parent / "candidates"
        first = load_json(candidates / "pixel" / "candidate.json")
        second = load_json(candidates / "quiet" / "candidate.json")
        self.assertNotEqual(first["input_fingerprint"], second["input_fingerprint"])
        self.assertEqual(first["request"]["motion"], action["motion"])
        self.assertEqual(load_json(path)["prompt_sha256"], action["prompt_sha256"])

    def test_terminal_and_travel_endings_do_not_force_original_root_reset(self) -> None:
        terminal = self._add("death", "--end-state", "hold", prompt="Fall and remain fallen")
        travel = self._add("dash", "--root-motion", "travel")
        loop = self._add("run", "--loop")
        terminal_prompt = video2sprite._video_prompt(terminal)
        travel_prompt = video2sprite._video_prompt(travel)
        loop_prompt = video2sprite._video_prompt(loop)
        self.assertNotIn("matching ready pose at the original root", terminal_prompt)
        self.assertNotIn("matching ready pose at the original root", travel_prompt)
        self.assertIn("terminal or combo bridge pose", terminal_prompt)
        self.assertIn("matching ready pose at the destination root", travel_prompt)
        self.assertNotIn("Use a brief readable end hold", loop_prompt)

    def test_legacy_hash_is_unchanged_and_each_explicit_motion_field_affects_review(self) -> None:
        legacy = {"prompt_sha256": "fixture", "frame_count": 24, "loop": False}
        self.assertEqual(
            action_processing_fingerprint(legacy),
            "6bb23e663e09b73746fb4df287ca93f20cf0a45be49ae52fa88abc5e6ea3a285",
        )
        before = json.dumps(legacy, sort_keys=True)
        video2sprite._motion_settings(legacy)
        self.assertEqual(json.dumps(legacy, sort_keys=True), before)
        explicit = {**legacy, "motion": video2sprite._motion_settings(legacy)}
        base = action_processing_fingerprint(explicit)
        self.assertNotEqual(base, action_processing_fingerprint(legacy))
        for field, value in (("style", "natural"), ("root_motion", "travel"), ("end_state", "hold")):
            changed = {**explicit, "motion": {**explicit["motion"], field: value}}
            self.assertNotEqual(base, action_processing_fingerprint(changed))
        self.assertEqual(base, action_processing_fingerprint({**explicit, "candidates": ["new"]}))


if __name__ == "__main__":
    unittest.main()
