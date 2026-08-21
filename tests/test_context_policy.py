from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ContextPolicyTests(unittest.TestCase):
    def test_skill_forbids_media_rehydration_tools(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for forbidden_tool in ("view_image", "read_thread", "imagegen"):
            self.assertIn(forbidden_tool, skill)
        self.assertIn("status --compact", skill)
        self.assertIn("--wait-seconds", skill)

    def test_skill_requires_libtv_receipts_without_overclaiming_visual_proof(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        quality = (ROOT / "references" / "quality-gates.md").read_text(
            encoding="utf-8"
        )
        combined = f"{skill}\n{quality}"
        for required in (
            "--without-ai-watermark",
            "--vip",
            "source.receipt.json",
            "上游",
            "视觉",
        ):
            self.assertIn(required, combined)
        self.assertIn("receipt 只证明", combined)
        self.assertIn("不得", combined)


if __name__ == "__main__":
    unittest.main()
