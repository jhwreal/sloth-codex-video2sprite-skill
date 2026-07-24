from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video2sprite


class PromptGuardTests(unittest.TestCase):
    def test_master_prompt_requires_connected_prop_and_excludes_secondary_equipment(self) -> None:
        prompt = video2sprite._master_prompt(
            "Alice holding one sword",
            "#3f0050",
        )

        self.assertIn("physically connected", prompt)
        self.assertIn("handle visibly seated in the grip", prompt)
        self.assertIn("no unrelated gun, holster, scabbard", prompt)


if __name__ == "__main__":
    unittest.main()
