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

from _v2s_providers import generate_openai_master, poll_ark_video, submit_ark_video


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

    def test_ark_submit_result_is_bounded_and_strips_signed_reference(self) -> None:
        provider_response = {
            "id": "task_123",
            "status": "queued",
            "debug_blob": "z" * 20_000,
        }
        with mock.patch(
            "_v2s_providers.http_json",
            return_value=(provider_response, {"x-request-id": "req_ark"}),
        ):
            result = submit_ark_video(
                base_url="https://ark.example/api/v3",
                model_id="model-id",
                prompt="one action",
                reference_url="https://assets.example/master.png?token=signed",
                reference_role="first_frame",
                resolution="720p",
                ratio="adaptive",
                duration=5,
                generate_audio=True,
                seed=42,
                watermark=False,
                api_key="not-a-real-key",
            )
        self.assertEqual(result["task_id"], "task_123")
        self.assertEqual(result["reference"], "https://assets.example/master.png")
        self.assertNotIn("provider_summary", result)
        self.assertLess(len(json.dumps(result)), 1000)

    def test_ark_local_reference_base64_never_leaves_provider_result(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is unavailable")
        with tempfile.TemporaryDirectory() as raw_temp:
            reference = Path(raw_temp) / "master.png"
            Image.new("RGB", (320, 320), (0, 255, 0)).save(reference)
            captured = {}

            def fake_http_json(method, url, *, headers, body):
                captured["reference"] = body["content"][1]["image_url"]["url"]
                return {"id": "task_local", "status": "queued"}, {
                    "x-request-id": "req_local"
                }

            with mock.patch(
                "_v2s_providers.http_json",
                side_effect=fake_http_json,
            ):
                result = submit_ark_video(
                    base_url="https://ark.example/api/v3",
                    model_id="model-id",
                    prompt="one action",
                    reference_path=reference,
                    reference_role="first_frame",
                    resolution="480p",
                    ratio="1:1",
                    duration=4,
                    generate_audio=True,
                    seed=None,
                    watermark=False,
                    api_key="not-a-real-key",
                )
            self.assertTrue(captured["reference"].startswith("data:image/png;base64,"))
            serialized = json.dumps(result)
            self.assertNotIn("data:image", serialized)
            self.assertNotIn(";base64,", serialized)
            self.assertEqual(result["reference"]["kind"], "local_file")
            self.assertEqual(result["reference"]["path"], str(reference.resolve()))
            captured.clear()

    def test_ark_poll_keeps_only_bounded_usage_and_in_memory_video_url(self) -> None:
        provider_response = {
            "id": "task_123",
            "status": "succeeded",
            "content": {
                "video_url": "https://media.example/result.mp4?token=short-lived"
            },
            "usage": {
                "completion_tokens": 123,
                "billing_unit": "tokens",
                "nested_debug": {"raw": "not retained"},
            },
        }
        with mock.patch(
            "_v2s_providers.http_json",
            return_value=(provider_response, {"x-request-id": "req_poll"}),
        ):
            result = poll_ark_video(
                base_url="https://ark.example/api/v3",
                task_id="task_123",
                api_key="not-a-real-key",
            )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["usage"]["completion_tokens"], 123)
        self.assertNotIn("nested_debug", result["usage"])
        self.assertNotIn("provider_summary", result)


if __name__ == "__main__":
    unittest.main()
