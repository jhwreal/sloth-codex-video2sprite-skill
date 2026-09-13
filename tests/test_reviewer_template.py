from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REVIEWER_TEMPLATE = ROOT / "assets" / "reviewer" / "run.html"


class ReviewerTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = REVIEWER_TEMPLATE.read_text(encoding="utf-8")

    def test_working_mode_uses_the_shared_action_navigation(self) -> None:
        self.assertIn('aria-label="动作名称列表"', self.template)
        self.assertNotIn('if (state.mode === "process") return;', self.template)
        self.assertIn('state.mode === "process" ? "工作中 Sprite"', self.template)
        self.assertIn('button.dataset.entryIndex = String(index);', self.template)
        self.assertIn('button.setAttribute("aria-current", "true");', self.template)
        self.assertIn('byId("action-navigation").hidden = false;', self.template)
        self.assertIn('document.querySelector("main").classList.add("library-mode");', self.template)

    def test_working_mode_only_distinguishes_confirmed_and_pending(self) -> None:
        self.assertIn(
            'const processApproved = entry.approval?.decision === "approved";',
            self.template,
        )
        self.assertNotIn("Boolean(entry.approval)", self.template)
        self.assertIn('processApproved ? "已确认" : "待确认"', self.template)
        self.assertNotIn('"已否决"', self.template)
        self.assertNotIn("process_rejected", self.template)

    def test_character_and_game_modes_share_character_sprite_numbers(self) -> None:
        self.assertIn("const characterSpriteLabel = entry => {", self.template)
        self.assertIn(
            "state.characterEntries.findIndex(candidate => candidate.action_id === entry.action_id)",
            self.template,
        )
        self.assertIn(
            "`${characterSpriteLabel(entry)} · ${entry.display_name || entry.action_id}`",
            self.template,
        )
        self.assertIn(
            "`${characterSpriteLabel(entry)} · ${entry.action_id}`",
            self.template,
        )


if __name__ == "__main__":
    unittest.main()
