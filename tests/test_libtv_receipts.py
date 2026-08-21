from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video2sprite
from _v2s_common import Video2SpriteError
from _v2s_receipts import (
    LIBTV_PROOF_SCOPE,
    validate_candidate_source,
    validate_libtv_receipt,
    validate_libtv_reference_ancestors,
    write_libtv_receipt,
)


class LibTVReceiptTests(unittest.TestCase):
    def _fake_libtv(self, directory: Path) -> tuple[Path, Path]:
        executable = directory / "fake-libtv"
        log_path = directory / "argv.json"
        executable.write_text(
            """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

if sys.argv[1:] == ["--version"]:
    print("libtv 1.1.1-test")
    raise SystemExit(0)
args = sys.argv[1:]
pathlib.Path(os.environ["FAKE_LIBTV_LOG"]).write_text(json.dumps(args))
output = pathlib.Path(args[args.index("-o") + 1])
output.mkdir(parents=True, exist_ok=True)
(output / "member.mp4").write_bytes(b"synthetic-libtv-video")
""",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable, log_path

    def _download_args(
        self,
        *,
        executable: Path,
        output_dir: Path,
        reference_audit: str = "no-libtv-ancestors",
        ancestor_sources: Optional[List[str]] = None,
        ancestor_receipts: Optional[List[str]] = None,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            node="opaque-node-value",
            output_dir=str(output_dir),
            project="opaque-project-value",
            group=None,
            reference_audit=reference_audit,
            ancestor_source=ancestor_sources,
            ancestor_receipt=ancestor_receipts,
            libtv=str(executable),
            timeout=30.0,
        )

    def test_wrapper_always_passes_both_flags_and_writes_bounded_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-receipt-") as raw_temp:
            root = Path(raw_temp)
            executable, log_path = self._fake_libtv(root)
            output_dir = root / "download"
            with mock.patch.dict(os.environ, {"FAKE_LIBTV_LOG": str(log_path)}):
                result = video2sprite.command_libtv_download(
                    self._download_args(executable=executable, output_dir=output_dir)
                )
            argv = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(argv.count("--without-ai-watermark"), 1)
            self.assertEqual(argv.count("--vip"), 1)
            self.assertNotIn("opaque-node-value", json.dumps(result))
            receipt = Path(result["receipt"])
            artifact = Path(result["artifact"])
            self.assertLessEqual(receipt.stat().st_size, 64 * 1024)
            validated = validate_libtv_receipt(receipt, artifact)
            self.assertEqual(validated["required_flags"], {
                "without_ai_watermark": True,
                "vip": True,
            })
            self.assertEqual(validated["proof_scope"], LIBTV_PROOF_SCOPE)
            self.assertFalse(validated["proof_scope"]["visual_watermark_absence"])
            self.assertEqual(
                validated["reference_audit"],
                {"status": "no-libtv-ancestors", "ancestor_count": 0},
            )

    def test_receipt_rejects_a_missing_flag_or_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-receipt-") as raw_temp:
            root = Path(raw_temp)
            artifact = root / "member.mp4"
            receipt = root / "member.receipt.json"
            artifact.write_bytes(b"first")
            write_libtv_receipt(
                artifact,
                receipt,
                libtv_version="libtv 1.1.1",
                node="node",
                reference_audit="no-libtv-ancestors",
            )
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["required_flags"]["vip"] = False
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(Video2SpriteError, "both"):
                validate_libtv_receipt(receipt, artifact)
            write_libtv_receipt(
                artifact,
                receipt,
                libtv_version="libtv 1.1.1",
                node="node",
                reference_audit="no-libtv-ancestors",
            )
            artifact.write_bytes(b"changed")
            with self.assertRaisesRegex(Video2SpriteError, "hash and size"):
                validate_libtv_receipt(receipt, artifact)

    def test_verified_lineage_requires_matching_clean_ancestor_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-lineage-") as raw_temp:
            root = Path(raw_temp)
            ancestor = root / "ancestor.png"
            ancestor_receipt = root / "ancestor.receipt.json"
            ancestor.write_bytes(b"synthetic-reference-image")
            write_libtv_receipt(
                ancestor,
                ancestor_receipt,
                libtv_version="libtv 1.1.1",
                node="ancestor-node",
                reference_audit="no-libtv-ancestors",
            )
            ancestors = validate_libtv_reference_ancestors(
                [ancestor],
                [ancestor_receipt],
            )
            self.assertEqual(len(ancestors), 1)
            self.assertEqual(
                set(ancestors[0]),
                {"artifact_sha256", "receipt_sha256"},
            )
            with self.assertRaisesRegex(Video2SpriteError, "matching receipt"):
                validate_libtv_reference_ancestors([ancestor], [])

    def test_wrapper_rejects_unproved_libtv_ancestry_before_download(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-lineage-") as raw_temp:
            root = Path(raw_temp)
            executable, _ = self._fake_libtv(root)
            output_dir = root / "must-not-be-created"
            with self.assertRaisesRegex(Video2SpriteError, "requires at least one"):
                video2sprite.command_libtv_download(
                    self._download_args(
                        executable=executable,
                        output_dir=output_dir,
                        reference_audit="verified-libtv-ancestors",
                    )
                )
            self.assertFalse(output_dir.exists())

    def test_attach_rejects_libtv_without_receipt_before_media_probe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-attach-") as raw_temp:
            root = Path(raw_temp)
            video = root / "source.mp4"
            video.write_bytes(b"not-probed")
            args = argparse.Namespace(
                run_dir=str(root / "run"),
                action_id="attack",
                candidate="libtv",
                video=str(video),
                source_origin="libtv",
                source_receipt=None,
            )
            with mock.patch.object(video2sprite, "_load_run", return_value={}), mock.patch.object(
                video2sprite, "_load_action", return_value={}
            ), mock.patch.object(video2sprite, "probe_media") as probe:
                with self.assertRaisesRegex(Video2SpriteError, "requires --source-receipt"):
                    video2sprite.command_attach_video(args)
            probe.assert_not_called()

    def test_attach_forbids_receipt_on_local_origin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-attach-") as raw_temp:
            root = Path(raw_temp)
            video = root / "source.mp4"
            receipt = root / "receipt.json"
            video.write_bytes(b"not-probed")
            receipt.write_text("{}", encoding="utf-8")
            args = argparse.Namespace(
                run_dir=str(root / "run"),
                action_id="attack",
                candidate="local",
                video=str(video),
                source_origin="local",
                source_receipt=str(receipt),
            )
            with mock.patch.object(video2sprite, "_load_run", return_value={}), mock.patch.object(
                video2sprite, "_load_action", return_value={}
            ), mock.patch.object(video2sprite, "probe_media") as probe:
                with self.assertRaisesRegex(Video2SpriteError, "only"):
                    video2sprite.command_attach_video(args)
            probe.assert_not_called()

    def test_removing_libtv_origin_does_not_turn_receipted_source_into_legacy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="libtv-origin-") as raw_temp:
            candidate_dir = Path(raw_temp)
            source = candidate_dir / "source.mp4"
            receipt = candidate_dir / "source.receipt.json"
            source.write_bytes(b"synthetic-source")
            summary = write_libtv_receipt(
                source,
                receipt,
                libtv_version="libtv 1.1.1",
                node="node",
                reference_audit="no-libtv-ancestors",
            )
            candidate = {
                "source": {
                    "path": "source.mp4",
                    "sha256": summary["artifact_sha256"],
                    "bytes": summary["artifact_bytes"],
                    "receipt": {"sha256": summary["receipt_sha256"]},
                }
            }
            with self.assertRaisesRegex(Video2SpriteError, "origin is missing"):
                validate_candidate_source(
                    candidate_dir,
                    candidate,
                    allow_legacy=True,
                )


if __name__ == "__main__":
    unittest.main()
