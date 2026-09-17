import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('create_workbench', ROOT / 'scripts/create_sprite_workbench.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorkbenchCreationTests(unittest.TestCase):
    def test_boss_and_enemy_use_identical_template_and_keep_plan(self):
        for character in ('boss', 'enemy'):
            with self.subTest(character=character), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                plan = {'title': character, 'actions': [{'action': 'idle', 'candidates': [
                    {'manifest': 'idle/v1/manifest.json', 'label': 'v1'}]}]}
                content = json.dumps(plan).encode()
                (root / 'production-plan.json').write_bytes(content)
                module.create(root)
                self.assertEqual((root / 'production-plan.json').read_bytes(), content)
                for name in module.FILES:
                    self.assertEqual((root / name).read_bytes(), (module.TEMPLATE / name).read_bytes())
                self.assertFalse(list(root.rglob('*.mp4')))

    def test_existing_instance_is_not_partially_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'production-plan.json').write_text(json.dumps({'actions': [
                {'action': 'idle', 'frames': ['frame.png']}]}))
            (root / 'app.js').write_text('custom game adapter')
            with self.assertRaises(ValueError):
                module.create(root)
            self.assertEqual((root / 'app.js').read_text(), 'custom game adapter')
            self.assertFalse((root / 'index.html').exists())

    def test_invalid_plan_creates_no_editor(self):
        for actions in ([], [{'action': 'idle'}], [{'action': 'idle', 'candidates': [{'id': 'v1'}]}],
                        [{'action': 'idle', 'frames': ['a']}, {'action': 'idle', 'frames': ['b']}]):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'production-plan.json').write_text(json.dumps({'actions': actions}))
                with self.assertRaises(ValueError):
                    module.create(root)
                self.assertFalse((root / 'index.html').exists())
