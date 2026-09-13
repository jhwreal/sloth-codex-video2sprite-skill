from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "video2sprite.py"


class ConfigureKeyCliTests(unittest.TestCase):
    def test_configure_key_uses_fixed_user_path_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            environment = dict(os.environ)
            environment["HOME"] = raw_temp
            environment["VIDEO2SPRITE_TEST_KEY"] = "must-never-be-printed"
            configured = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "configure-key",
                    "--name",
                    "openai",
                    "--from-env",
                    "VIDEO2SPRITE_TEST_KEY",
                ],
                cwd=str(ROOT),
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(
                configured.returncode,
                0,
                msg=f"stdout={configured.stdout}\nstderr={configured.stderr}",
            )
            self.assertNotIn("must-never-be-printed", configured.stdout)
            self.assertNotIn("must-never-be-printed", configured.stderr)
            result = json.loads(configured.stdout)
            expected = (
                Path(raw_temp)
                / ".config"
                / "sloth-codex-video2sprite"
                / "credentials.env"
            )
            self.assertEqual(Path(result["path"]), expected)
            self.assertEqual(result["credential_name"], "OPENAI_API_KEY")
            self.assertTrue(expected.is_file())
            if os.name == "posix":
                self.assertEqual(expected.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(expected.stat().st_mode & 0o777, 0o600)

            doctor_environment = dict(environment)
            doctor_environment.pop("VIDEO2SPRITE_TEST_KEY", None)
            doctor_environment.pop("OPENAI_API_KEY", None)
            checked = subprocess.run(
                [sys.executable, str(CLI), "doctor"],
                cwd=str(ROOT),
                env=doctor_environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(checked.returncode, 0)
            doctor = json.loads(checked.stdout)
            self.assertTrue(doctor["credentials"]["openai_configured"])
            self.assertEqual(
                doctor["credentials"]["openai_source"],
                "private_file",
            )


if __name__ == "__main__":
    unittest.main()
