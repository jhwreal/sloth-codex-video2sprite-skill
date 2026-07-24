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


if __name__ == "__main__":
    unittest.main()
