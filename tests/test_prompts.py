from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


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

        self.assertIn("held props must meet the correct hands at the grip", prompt)
        self.assertIn("No extra equipment or characters", prompt)
        self.assertIn("No added visual effects (VFX)", prompt)
        self.assertIn("largest practical subject scale with small safety margins", prompt)
        self.assertNotIn("comfortable margins", prompt)


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


    def _export(self, action_id, filename="prompt.txt"):
        output = self.run_dir / action_id / filename
        args = self.parser.parse_args([
            "export-prompt", "--run-dir", str(self.run_dir),
            "--action-id", action_id, "--output", str(output),
        ])
        result = args.handler(args)
        return output.read_text(), result

    def test_invalid_stored_motion_prevents_prompt_export(self):
        action = self._add("attack")
        path = self.run_dir / "actions" / "attack" / "action.json"
        for invalid in (None, [], {"style": "typo"}, {"root_motion": "frozen"},
                        {"end_state": "loop"}, {"end_state": "unknown"}, {"amplitude": 2}):
            with self.subTest(motion=invalid):
                atomic_write_json(path, {**action, "motion": invalid})
                with self.assertRaises(Video2SpriteError):
                    self._export("attack")
                self.assertFalse((self.run_dir / "attack" / "prompt.txt").exists())

    def test_export_preserves_window_motion_and_bounded_fingerprint(self):
        action = self._add("heavy")
        sent, result = self._export("heavy")
        self.assertNotIn("Keep the foot-root at one fixed image coordinate", sent)
        self.assertIn("lifted feet, weight shifts and full body articulation", sent)
        self.assertIn("at the starting spot", sent)
        self.assertIn("0.25s to 1s", sent)
        self.assertEqual(result["duration_seconds"], 4)
        self.assertEqual(result["motion"], action["motion"])
        self.assertEqual(result["prompt_sha256"], fingerprint(sent))
        self.assertNotIn(sent, json.dumps(result))
        self.assertLess(len(json.dumps(result)), 4096)
        with self.assertRaisesRegex(Video2SpriteError, "already exists"):
            self._export("heavy")

    def test_framing_direction_reaches_both_reference_modes_without_rewriting_action(self):
        self._add("wide-attack", "--root-motion", "travel", prompt="Lunge right with a wide sword swing")
        action_path = self.run_dir / "actions" / "wide-attack" / "action.json"
        original = action_path.read_bytes()
        exported = {}
        for role in ("first_frame", "reference_image"):
            with self.subTest(role=role):
                output = self.run_dir / f"{role}.txt"
                args = self.parser.parse_args([
                    "export-prompt", "--run-dir", str(self.run_dir),
                    "--action-id", "wide-attack", "--reference-role", role,
                    "--output", str(output),
                ])
                result = args.handler(args)
                prompt = output.read_text()
                exported[role] = prompt
                self.assertIn("Maximize subject size with a small safety margin", prompt)
                self.assertIn("constant character scale throughout", prompt)
                self.assertIn("complete body, weapon path and intended travel", prompt)
                self.assertIn("No tiny distant subject", prompt)
                self.assertIn("clipped extremities or reduced action reach", prompt)
                self.assertIn("no zoom, pan or cuts", prompt)
                self.assertIn("at the destination", prompt)
                self.assertEqual(result["prompt_sha256"], fingerprint(prompt))
                self.assertEqual(action_path.read_bytes(), original)
        self.assertIn("exact opening frame", exported["first_frame"])
        self.assertNotIn("exact opening frame", exported["reference_image"])
        self.assertIn("do not inherit its empty margins", exported["reference_image"])

    def test_motion_changes_exported_prompt_and_fingerprint(self):
        action = self._add("attack")
        first, metadata = self._export("attack", "first.txt")
        action["motion"]["style"] = "restrained"
        atomic_write_json(self.run_dir / "actions" / "attack" / "action.json", action)
        second, updated = self._export("attack", "second.txt")
        self.assertNotEqual(first, second)
        self.assertNotEqual(metadata["prompt_sha256"], updated["prompt_sha256"])

    def test_clean_visuals_and_action_sound_survive_local_export(self):
        for style in video2sprite.MOTION_STYLES:
            for audio in (False, True):
                with self.subTest(style=style, audio=audio):
                    name = f"{style}-{audio}"
                    flags = ("--audio-required",) if audio else ()
                    self._add(name, "--motion-style", style, *flags)
                    sent, result = self._export(name)
                    self.assertIn("no background music (BGM)", sent)
                    self.assertIn("No added visual effects (VFX)", sent)
                    self.assertIn("no slash trails, particles, glow or motion blur", sent)
                    self.assertEqual(result["audio_required"], audio)
                    self.assertIn("Synchronized dry action SFX only" if audio
                                  else "Silent clip", sent)

    def test_spatial_and_ending_choices_export_as_visible_motion(self):
        cases = (
            ("death", ("--end-state", "hold"), "Fall and remain fallen",
             "specified terminal or next-action pose", "at the starting spot"),
            ("dash", ("--root-motion", "travel"), "Dash screen-right and stop",
             "at the destination", "at the starting spot"),
            ("run", ("--loop",), "Run facing screen-right with full alternating strides",
             "full alternating strides", "Use a brief readable end hold"),
            ("planted", ("--root-motion", "planted", "--loop"),
             "Keep the left foot supporting the body while gently breathing",
             "named support contact", "recover to the ready pose"),
        )
        for action_id, flags, brief, required, forbidden in cases:
            with self.subTest(action=action_id):
                self._add(action_id, *flags, prompt=brief)
                sent, result = self._export(action_id)
                self.assertTrue(sent.startswith(brief))
                self.assertIn(required, sent)
                self.assertNotIn(forbidden, sent)
                for note in ("root", "pivot", "registration", "engine", "stage anchor"):
                    self.assertNotIn(note, sent.lower())
                self.assertEqual(result["prompt_sha256"], fingerprint(sent))

    def test_shared_suffix_has_no_unrelated_action_catalog_and_keeps_selected_ending(self):
        cases = (
            ("idle", ("--loop", "--motion-style", "restrained"), "Breathe quietly", "Loop seamlessly", "recover to the ready pose"),
            ("death", ("--end-state", "hold"), "Collapse forward", "terminal or next-action pose", "Loop seamlessly"),
            ("attack", (), "Slash forward", "recover to the ready pose", "Loop seamlessly"),
        )
        for action_id, flags, brief, required, forbidden in cases:
            with self.subTest(action=action_id):
                self._add(action_id, *flags, prompt=brief)
                sent, _ = self._export(action_id)
                self.assertTrue(sent.startswith(brief + "\n\n"))
                suffix = sent.split("\n\n", 1)[1]
                self.assertIn(required, suffix)
                self.assertNotIn(forbidden, suffix)
                for unrelated in ("For attacks", "For idle", "For locomotion", "for death"):
                    self.assertNotIn(unrelated, suffix)
                # Bounds the automatic English suffix, not user-authored brief length.
                self.assertLess(len(suffix.split()), 300)
                self.assertEqual(suffix.count("No added visual effects"), 1)
                self.assertEqual(suffix.count("no background music"), 1)

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
