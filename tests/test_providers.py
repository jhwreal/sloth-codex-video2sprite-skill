from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _v2s_providers import generate_openai_master


class ProviderFirewallTests(unittest.TestCase):
    def test_openai_image_base64_never_leaves_worker_result(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is unavailable")
        image = Image.new("RGB", (32, 32), (0, 255, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        response = {
            "created": 123,
            "data": [{"b64_json": encoded}],
            "usage": {"total_tokens": 7},
        }
        with tempfile.TemporaryDirectory() as raw_temp:
            output = Path(raw_temp) / "master.png"
            with mock.patch(
                "_v2s_providers.http_json",
                return_value=(response, {"x-request-id": "req_test"}),
            ):
                result = generate_openai_master(
                    prompt="test",
                    output_path=output,
                    model_id="gpt-image-2",
                    base_url="https://api.openai.com/v1",
                    size="1024x1024",
                    quality="high",
                    api_key="not-a-real-key",
                )
            self.assertTrue(output.is_file())
            self.assertEqual(result["request_id"], "req_test")
            serialized = json.dumps(result)
            self.assertNotIn(encoded, serialized)
            self.assertNotIn("b64_json", serialized)
            self.assertNotIn("data", response)


if __name__ == "__main__":
    unittest.main()
