#!/usr/bin/env python3
"""Deterministic local video-to-sprite, audio, preview, and QC processing."""

from __future__ import annotations

import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _v2s_common import (
    SKILL_DIR,
    Video2SpriteError,
    action_processing_fingerprint,
    atomic_write_json,
    candidate_processing_fingerprint,
    copy_file_atomic,
    parse_hex_color,
    require_executable,
    run_command,
    sha256_file,
    utc_now,
)


_AUDIO_ENCODER_CACHE: Dict[str, List[str]] = {}
AUDIO_OUTPUT_GAIN = 0.85


def _image_dependencies() -> Tuple[Any, Any]:
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise Video2SpriteError(
            "Pillow and NumPy are required; use the Codex bundled Python or install requirements.txt"
        ) from exc
    return Image, np


def _parse_fraction(raw: Any) -> Optional[float]:
    if raw in (None, "", "N/A"):
        return None
    text = str(raw)
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            divisor = float(denominator)
            return float(numerator) / divisor if divisor else None
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def probe_media(path: Path, ffprobe: str = "ffprobe") -> Dict[str, Any]:
    if not path.is_file():
        raise Video2SpriteError(f"Missing media file: {path}")
    executable = require_executable(ffprobe)
    result = run_command(
        [
            executable,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Video2SpriteError(f"ffprobe returned invalid JSON for {path}") from exc
    streams = payload.get("streams") if isinstance(payload, dict) else []
    streams = streams if isinstance(streams, list) else []
    video = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    audio = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"),
        None,
    )
    format_spec = payload.get("format") if isinstance(payload, dict) else {}
    format_spec = format_spec if isinstance(format_spec, dict) else {}
    duration = _parse_fraction(format_spec.get("duration"))
    if duration is None and video:
        duration = _parse_fraction(video.get("duration"))
    return {
        "duration_seconds": round(duration or 0.0, 6),
        "video": {
            "present": bool(video),
            "codec": video.get("codec_name") if video else None,
            "width": int(video.get("width") or 0) if video else 0,
            "height": int(video.get("height") or 0) if video else 0,
            "fps": (
                _parse_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate"))
                if video
                else None
            ),
        },
        "audio": {
            "present": bool(audio),
            "codec": audio.get("codec_name") if audio else None,
            "channels": int(audio.get("channels") or 0) if audio else 0,
            "sample_rate": int(audio.get("sample_rate") or 0) if audio else 0,
        },
    }


def _clear_numbered_pngs(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("frame_*.png"):
        if path.is_file():
            path.unlink()


def _fixed_canvas_geometry(
    source_size: Tuple[int, int],
    target_size: Tuple[int, int],
) -> Dict[str, Any]:
    source_width, source_height = source_size
    target_width, target_height = target_size
    if min(source_width, source_height, target_width, target_height) <= 0:
        raise Video2SpriteError("Fixed-canvas source and target sizes must be positive")
    scale = min(target_width / source_width, target_height / source_height)
    scaled_width = max(1, int(round(source_width * scale)))
    scaled_height = max(1, int(round(source_height * scale)))
    return {
        "scale": scale,
        "scaled_width": scaled_width,
        "scaled_height": scaled_height,
        "offset_x": (target_width - scaled_width) // 2,
        "offset_y": (target_height - scaled_height) // 2,
    }


def extract_video_frames(
    source: Path,
    output_dir: Path,
    *,
    frame_count: int,
    start_seconds: float,
    duration_seconds: float,
    ffmpeg: str = "ffmpeg",
    fixed_source_size: Optional[Tuple[int, int]] = None,
    fixed_target_size: Optional[Tuple[int, int]] = None,
    fixed_pad_color: str = "#000000",
    resampling: str = "lanczos",
) -> Tuple[List[Path], List[float]]:
    if frame_count < 1 or frame_count > 512:
        raise Video2SpriteError("Frame count must be between 1 and 512")
    if start_seconds < 0 or duration_seconds <= 0:
        raise Video2SpriteError("Action window start must be non-negative and duration must be positive")
    executable = require_executable(ffmpeg)
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_numbered_pngs(output_dir)
    fps = frame_count / duration_seconds
    filters = [f"fps={fps:.12f}:round=near"]
    if bool(fixed_source_size) != bool(fixed_target_size):
        raise Video2SpriteError(
            "Fixed-canvas decode requires both source and target sizes"
        )
    if fixed_source_size and fixed_target_size:
        geometry = _fixed_canvas_geometry(fixed_source_size, fixed_target_size)
        color = "".join(
            f"{component:02x}" for component in parse_hex_color(fixed_pad_color)
        )
        if resampling not in {"nearest", "lanczos"}:
            raise Video2SpriteError("Resampling must be nearest or lanczos")
        ffmpeg_filter = "neighbor" if resampling == "nearest" else "lanczos"
        filters.extend(
            [
                (
                    f"scale={geometry['scaled_width']}:{geometry['scaled_height']}"
                    f":flags={ffmpeg_filter}"
                ),
                (
                    f"pad={fixed_target_size[0]}:{fixed_target_size[1]}"
                    f":{geometry['offset_x']}:{geometry['offset_y']}:color=0x{color}"
                ),
            ]
        )
    filters.append("format=rgb24")
    run_command(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start_seconds:.6f}",
            "-i",
            str(source),
            "-t",
            f"{duration_seconds:.6f}",
            "-vf",
            ",".join(filters),
            "-frames:v",
            str(frame_count),
            str(output_dir / "frame_%04d.png"),
        ],
        timeout=max(120.0, duration_seconds * 20.0),
    )
    paths = sorted(output_dir.glob("frame_*.png"))
    if len(paths) != frame_count:
        raise Video2SpriteError(
            f"Requested {frame_count} frames but ffmpeg produced {len(paths)} from the action window"
        )
    times = [
        round(start_seconds + ((index + 0.5) * duration_seconds / frame_count), 6)
        for index in range(frame_count)
    ]
    return paths, times


def _alpha_bounds(np: Any, rgba: Any, threshold: int = 12) -> Optional[Tuple[int, int, int, int]]:
    ys, xs = np.nonzero(rgba[..., 3] >= threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _corner_metrics(np: Any, rgb: Any, key: Any) -> Dict[str, float]:
    height, width = rgb.shape[:2]
    patch = max(2, min(width, height) // 20)
    samples = np.concatenate(
        [
            rgb[:patch, :patch].reshape(-1, 3),
            rgb[:patch, -patch:].reshape(-1, 3),
            rgb[-patch:, :patch].reshape(-1, 3),
            rgb[-patch:, -patch:].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.float32)
    distances = np.linalg.norm(samples - key.reshape(1, 3), axis=1)
    return {
        "rgb_std": float(samples.std(axis=0).mean()),
        "distance_from_key_mean": float(distances.mean()),
        "distance_from_key_p95": float(np.percentile(distances, 95)),
    }


def _key_rgba(
    np: Any,
    rgb_u8: Any,
    key_rgb: Tuple[int, int, int],
    threshold: float,
    softness: float,
    mode: str = "global",
) -> Tuple[Any, Dict[str, float]]:
    rgb = rgb_u8.astype(np.float32)
    key = np.asarray(key_rgb, dtype=np.float32)
    distance = np.linalg.norm(rgb - key.reshape(1, 1, 3), axis=2)
    if mode == "global":
        alpha = np.clip(
            (distance - threshold) / max(softness, 1.0), 0.0, 1.0
        )
        dominant = int(np.argmax(key))
        other_channels = [index for index in range(3) if index != dominant]
        if (
            key[dominant]
            - max(key[other_channels[0]], key[other_channels[1]])
            >= 32
        ):
            other_max = np.maximum(
                rgb[..., other_channels[0]], rgb[..., other_channels[1]]
            )
            excess = np.maximum(rgb[..., dominant] - other_max, 0.0)
            edge_weight = (1.0 - alpha) * (alpha > 0.0)
            rgb[..., dominant] = np.maximum(
                0.0, rgb[..., dominant] - (excess * edge_weight * 0.85)
            )
    elif mode == "border":
        from PIL import Image, ImageDraw

        near_matte = distance <= threshold + softness
        binary = np.where(near_matte, 0, 255).astype(np.uint8)
        connectivity = Image.fromarray(
            np.repeat(binary[..., None], 3, axis=2), mode="RGB"
        )
        width, height = connectivity.size
        seeds = (
            (0, 0),
            (max(0, width - 1), 0),
            (0, max(0, height - 1)),
            (max(0, width - 1), max(0, height - 1)),
        )
        for seed in seeds:
            if connectivity.getpixel(seed) == (0, 0, 0):
                ImageDraw.floodfill(
                    connectivity, seed, (128, 0, 0), thresh=0
                )
        connectivity_array = np.asarray(connectivity, dtype=np.uint8)
        connected = (
            (connectivity_array[..., 0] == 128)
            & (connectivity_array[..., 1] == 0)
            & (connectivity_array[..., 2] == 0)
        )
        alpha = np.ones(distance.shape, dtype=np.float32)
        alpha[connected] = np.clip(
            (distance[connected] - threshold) / max(softness, 1.0),
            0.0,
            1.0,
        )
        edge = connected & (alpha > 0.0) & (alpha < 1.0)
        if np.any(edge):
            edge_alpha = alpha[edge].reshape(-1, 1)
            observed = rgb[edge]
            cleaned = (
                observed - key.reshape(1, 3) * (1.0 - edge_alpha)
            ) / np.maximum(edge_alpha, 0.20)
            rgb[edge] = np.clip(cleaned, 0.0, 255.0)
    else:
        raise Video2SpriteError(f"Unsupported matte key mode: {mode}")

    alpha_u8 = np.rint(alpha * 255.0).astype(np.uint8)
    rgb_u8_clean = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)
    rgb_u8_clean[alpha_u8 == 0] = 0
    rgba = np.dstack([rgb_u8_clean, alpha_u8])
    return rgba, _corner_metrics(np, rgb_u8, key)


def key_and_pack_frames(
    raw_paths: Sequence[Path],
    output_dir: Path,
    atlas_path: Path,
    *,
    target_size: Tuple[int, int],
    key_color: str,
    threshold: float,
    softness: float,
    key_mode: str,
    placement: str,
    pivot: Dict[str, Any],
    resampling: str,
    columns: Optional[int],
    source_times: Sequence[float],
    frame_duration: float,
    png_optimize: bool = True,
    fixed_source_size: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    Image, np = _image_dependencies()
    if not raw_paths:
        raise Video2SpriteError("No source frames were provided")
    if len(raw_paths) != len(source_times):
        raise Video2SpriteError("Frame path and timestamp counts do not match")
    if threshold < 0.0 or threshold > 442.0:
        raise Video2SpriteError("Chroma threshold must be between 0 and 442")
    if softness <= 0.0 or softness > 442.0:
        raise Video2SpriteError("Chroma softness must be greater than 0 and no more than 442")
    if key_mode not in {"border", "global"}:
        raise Video2SpriteError("Matte key mode must be border or global")
    if placement not in {"fixed", "fit-union"}:
        raise Video2SpriteError("Placement must be fixed or fit-union")
    if resampling not in {"nearest", "lanczos"}:
        raise Video2SpriteError("Resampling must be nearest or lanczos")
    target_width, target_height = target_size
    key_rgb = parse_hex_color(key_color)
    raw_bounds: List[Optional[Tuple[int, int, int, int]]] = []
    corner_metrics: List[Dict[str, float]] = []
    source_shape: Optional[Tuple[int, int]] = None

    for path in raw_paths:
        with Image.open(path) as image:
            image_size = image.size
            rgb = (
                np.asarray(image.convert("RGB"), dtype=np.uint8)
                if placement == "fit-union"
                else None
            )
        if source_shape is None:
            source_shape = (int(image_size[0]), int(image_size[1]))
        elif source_shape != (int(image_size[0]), int(image_size[1])):
            raise Video2SpriteError("Decoded source frames do not share one size")
        if rgb is not None:
            rgba, corner = _key_rgba(
                np, rgb, key_rgb, threshold, softness, key_mode
            )
            raw_bounds.append(_alpha_bounds(np, rgba))
            corner_metrics.append(corner)

    assert source_shape is not None
    if placement == "fit-union":
        empty_indices = [
            index for index, bounds in enumerate(raw_bounds) if bounds is None
        ]
        if empty_indices:
            raise Video2SpriteError(
                "Matte key removed all foreground from frame(s): "
                + ", ".join(str(index) for index in empty_indices)
            )
    decoded_width, decoded_height = source_shape
    if fixed_source_size:
        if placement != "fixed":
            raise Video2SpriteError(
                "A pre-scaled fixed source can only use fixed placement"
            )
        if source_shape != (target_width, target_height):
            raise Video2SpriteError(
                "Pre-scaled fixed frames must already match the target canvas"
            )
        source_width, source_height = fixed_source_size
    else:
        source_width, source_height = decoded_width, decoded_height
    if placement == "fixed":
        union = (0, 0, source_width, source_height)
    else:
        union = (
            min(bounds[0] for bounds in raw_bounds if bounds),
            min(bounds[1] for bounds in raw_bounds if bounds),
            max(bounds[2] for bounds in raw_bounds if bounds),
            max(bounds[3] for bounds in raw_bounds if bounds),
        )
        source_margin = max(
            2, int(round(max(source_width, source_height) * 0.015))
        )
        union = (
            max(0, union[0] - source_margin),
            max(0, union[1] - source_margin),
            min(source_width, union[2] + source_margin),
            min(source_height, union[3] + source_margin),
        )
    union_width, union_height = union[2] - union[0], union[3] - union[1]
    target_padding = (
        0
        if placement == "fixed"
        else max(2, int(round(min(target_width, target_height) * 0.035)))
    )
    available_width = max(1, target_width - 2 * target_padding)
    available_height = max(1, target_height - 2 * target_padding)
    if placement == "fixed":
        geometry = _fixed_canvas_geometry(
            (source_width, source_height),
            (target_width, target_height),
        )
        scale = float(geometry["scale"])
        scaled_width = int(geometry["scaled_width"])
        scaled_height = int(geometry["scaled_height"])
        offset_x = int(geometry["offset_x"])
        offset_y = int(geometry["offset_y"])
    else:
        scale = min(available_width / union_width, available_height / union_height)
        scaled_width = max(1, int(round(union_width * scale)))
        scaled_height = max(1, int(round(union_height * scale)))
        offset_x = (target_width - scaled_width) // 2
        offset_y = (target_height - scaled_height) // 2

    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_numbered_pngs(output_dir)
    processed_paths: List[Path] = []
    first_processed: Optional[Any] = None
    last_processed: Optional[Any] = None
    processed_bounds: List[Tuple[int, int, int, int]] = []
    alpha_areas: List[float] = []
    baselines: List[float] = []
    edge_touch = False
    frame_entries: List[Dict[str, Any]] = []
    resize_filter = (
        Image.Resampling.NEAREST
        if resampling == "nearest"
        else Image.Resampling.LANCZOS
    )
    resolved_columns = columns or int(math.ceil(math.sqrt(len(raw_paths))))
    if resolved_columns < 1 or resolved_columns > len(raw_paths):
        raise Video2SpriteError("Atlas columns must be between 1 and the frame count")
    rows = int(math.ceil(len(raw_paths) / resolved_columns))
    atlas = Image.new(
        "RGBA",
        (resolved_columns * target_width, rows * target_height),
        (0, 0, 0, 0),
    )

    for index, raw_path in enumerate(raw_paths):
        with Image.open(raw_path) as image:
            source_image = image.convert("RGB")
        if placement == "fixed":
            if fixed_source_size:
                transformed_rgb = np.asarray(source_image, dtype=np.uint8)
            else:
                resized_rgb = source_image.resize(
                    (scaled_width, scaled_height), resize_filter
                )
                matte_cell = Image.new(
                    "RGB", (target_width, target_height), key_rgb
                )
                matte_cell.paste(resized_rgb, (offset_x, offset_y))
                transformed_rgb = np.asarray(matte_cell, dtype=np.uint8)
            rgba, corner = _key_rgba(
                np,
                transformed_rgb,
                key_rgb,
                threshold,
                softness,
                key_mode,
            )
            corner_metrics.append(corner)
            cell = Image.fromarray(rgba, mode="RGBA")
        else:
            source_rgb = np.asarray(source_image, dtype=np.uint8)
            rgba, _ = _key_rgba(
                np, source_rgb, key_rgb, threshold, softness, key_mode
            )
            crop = Image.fromarray(rgba, mode="RGBA").crop(union)
            resized = crop.resize(
                (scaled_width, scaled_height), resize_filter
            )
            cell = Image.new(
                "RGBA", (target_width, target_height), (0, 0, 0, 0)
            )
            cell.alpha_composite(resized, (offset_x, offset_y))
        processed = np.asarray(cell, dtype=np.uint8)
        bounds = _alpha_bounds(np, processed)
        if bounds is None:
            raise Video2SpriteError(f"Processed frame {index} has no foreground")
        touches = (
            bounds[0] <= 0
            or bounds[1] <= 0
            or bounds[2] >= target_width
            or bounds[3] >= target_height
        )
        edge_touch = edge_touch or touches
        alpha_area = float((processed[..., 3] >= 12).sum()) / float(target_width * target_height)
        processed_bounds.append(bounds)
        alpha_areas.append(alpha_area)
        baselines.append(float(bounds[3]) / target_height)
        output_path = output_dir / f"frame_{index:04d}.png"
        cell.save(
            output_path,
            format="PNG",
            optimize=png_optimize,
            compress_level=9 if png_optimize else 1,
        )
        processed_paths.append(output_path)
        atlas.alpha_composite(
            cell,
            (
                (index % resolved_columns) * target_width,
                (index // resolved_columns) * target_height,
            ),
        )
        if index == 0:
            first_processed = processed.copy()
        if index == len(raw_paths) - 1:
            last_processed = processed.copy()

    for index, path in enumerate(processed_paths):
        bounds = processed_bounds[index]
        frame_entries.append(
            {
                "index": index,
                "file": f"frames/{path.name}",
                "sha256": sha256_file(path),
                "source_time_seconds": source_times[index],
                "duration_seconds": round(frame_duration, 6),
                "cell": {
                    "x": (index % resolved_columns) * target_width,
                    "y": (index // resolved_columns) * target_height,
                    "width": target_width,
                    "height": target_height,
                },
                "alpha_bounds": {
                    "x": bounds[0],
                    "y": bounds[1],
                    "width": bounds[2] - bounds[0],
                    "height": bounds[3] - bounds[1],
                },
                "pivot": {
                    "x": float(pivot["x"]),
                    "y": float(pivot["y"]),
                    "normalized": [
                        float(pivot["normalized"][0]),
                        float(pivot["normalized"][1]),
                    ],
                },
            }
        )
    atlas_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(
        atlas_path,
        format="PNG",
        optimize=png_optimize,
        compress_level=9 if png_optimize else 1,
    )

    area_mean = float(np.mean(alpha_areas))
    area_cv = float(np.std(alpha_areas) / area_mean) if area_mean else 0.0
    baseline_span = float(max(baselines) - min(baselines))
    loop_seam = (
        float(
            np.mean(
                np.abs(
                    first_processed.astype(np.float32)
                    - last_processed.astype(np.float32)
                )
            )
            / 255.0
        )
        if len(raw_paths) > 1 and first_processed is not None and last_processed is not None
        else 0.0
    )
    return {
        "paths": processed_paths,
        "frames": frame_entries,
        "atlas": {
            "path": atlas_path.name,
            "sha256": sha256_file(atlas_path),
            "width": atlas.width,
            "height": atlas.height,
            "columns": resolved_columns,
            "rows": rows,
            "cell_width": target_width,
            "cell_height": target_height,
        },
        "transform": {
            "source_size": [source_width, source_height],
            "shared_crop": {
                "x": union[0],
                "y": union[1],
                "width": union_width,
                "height": union_height,
            },
            "shared_scale": round(scale, 8),
            "target_offset": [offset_x, offset_y],
            "placement": placement,
            "resampling": resampling,
            "matte_key_mode": key_mode,
            "pivot": pivot,
        },
        "metrics": {
            "empty_frames": [],
            "edge_touch": edge_touch,
            "alpha_area_mean": round(area_mean, 6),
            "alpha_area_cv": round(area_cv, 6),
            "baseline_span": round(baseline_span, 6),
            "loop_seam_mean_abs": round(loop_seam, 6),
            "corner_rgb_std_mean": round(
                float(np.mean([metric["rgb_std"] for metric in corner_metrics])), 6
            ),
            "corner_distance_from_key_mean": round(
                float(
                    np.mean(
                        [metric["distance_from_key_mean"] for metric in corner_metrics]
                    )
                ),
                6,
            ),
        },
    }


def extract_audio(
    source: Path,
    destination: Path,
    *,
    start_seconds: float,
    duration_seconds: float,
    source_probe: Dict[str, Any],
    ffmpeg: str = "ffmpeg",
) -> Dict[str, Any]:
    if destination.exists():
        destination.unlink()
    if not source_probe.get("audio", {}).get("present"):
        return {"present": False, "path": None, "reason": "source_has_no_audio"}
    executable = require_executable(ffmpeg)
    encoder_args = _AUDIO_ENCODER_CACHE.get(executable)
    if encoder_args is None:
        encoders = run_command(
            [executable, "-hide_banner", "-encoders"],
            check=True,
        )
        listing = f"{encoders.stdout}\n{encoders.stderr}"
        if re.search(r"^\s*A\S*\s+libvorbis\s", listing, flags=re.MULTILINE):
            encoder_args = ["-c:a", "libvorbis", "-q:a", "5"]
        elif re.search(r"^\s*A\S*\s+vorbis\s", listing, flags=re.MULTILINE):
            encoder_args = [
                "-ac",
                "2",
                "-c:a",
                "vorbis",
                "-strict",
                "experimental",
                "-q:a",
                "5",
            ]
        elif re.search(r"^\s*A\S*\s+libopus\s", listing, flags=re.MULTILINE):
            encoder_args = ["-c:a", "libopus", "-b:a", "160k"]
        else:
            raise Video2SpriteError(
                "ffmpeg has no usable Ogg encoder (libvorbis, vorbis, or libopus)"
            )
        _AUDIO_ENCODER_CACHE[executable] = encoder_args
    run_command(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start_seconds:.6f}",
            "-i",
            str(source),
            "-t",
            f"{duration_seconds:.6f}",
            "-vn",
            "-map",
            "0:a:0",
            "-af",
            f"volume={AUDIO_OUTPUT_GAIN:.2f},asetpts=PTS-STARTPTS",
            *encoder_args,
            str(destination),
        ],
        timeout=max(120.0, duration_seconds * 20.0),
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        return {"present": False, "path": None, "reason": "audio_extraction_empty"}
    return {
        "present": True,
        "path": destination.name,
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "gain": AUDIO_OUTPUT_GAIN,
    }


def analyze_audio(
    audio_path: Path,
    *,
    frame_count: int,
    action_duration: float,
    event_names: Sequence[str],
    ffmpeg: str = "ffmpeg",
) -> Dict[str, Any]:
    _, np = _image_dependencies()
    executable = require_executable(ffmpeg)
    sample_rate = 48000
    result = run_command(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "f32le",
            "pipe:1",
        ],
        text=False,
        timeout=max(120.0, action_duration * 20.0),
    )
    samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float32)
    if samples.size == 0:
        return {
            "duration_seconds": 0.0,
            "peak": 0.0,
            "rms": 0.0,
            "non_silent_fraction": 0.0,
            "suggested_markers": [],
        }
    finite = samples[np.isfinite(samples)]
    if finite.size != samples.size:
        samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
    absolute = np.abs(samples)
    peak = float(absolute.max())
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    non_silent_fraction = float(np.mean(absolute >= 0.01))

    hop = 512
    window = 1024
    envelope: List[float] = []
    positions: List[int] = []
    for start in range(0, max(1, samples.size - window + 1), hop):
        chunk = samples[start : start + window]
        if chunk.size:
            envelope.append(float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64)))))
            positions.append(start)
    onset_candidates: List[Tuple[float, float]] = []
    if len(envelope) >= 3:
        env = np.asarray(envelope, dtype=np.float64)
        novelty = np.maximum(np.diff(env, prepend=env[0]), 0.0)
        positive = novelty[novelty > 0]
        threshold = (
            max(float(np.percentile(positive, 75)), float(novelty.max()) * 0.20, 0.002)
            if positive.size
            else 1.0
        )
        minimum_gap = int(round(0.08 * sample_rate / hop))
        last_index = -minimum_gap
        for index in range(1, len(novelty) - 1):
            if (
                novelty[index] >= threshold
                and novelty[index] >= novelty[index - 1]
                and novelty[index] >= novelty[index + 1]
                and index - last_index >= minimum_gap
            ):
                onset_candidates.append(
                    (positions[index] / sample_rate, float(novelty[index]))
                )
                last_index = index
    strongest = sorted(onset_candidates, key=lambda item: item[1], reverse=True)[:8]
    selected_count = max(1, len(event_names)) if strongest else 0
    selected = sorted(strongest[:selected_count], key=lambda item: item[0])
    markers: List[Dict[str, Any]] = []
    for index, (time_seconds, strength) in enumerate(selected):
        local_time = min(max(time_seconds, 0.0), max(action_duration, 0.0))
        frame_index = min(
            frame_count - 1,
            max(0, int(math.floor(local_time / max(action_duration, 1e-6) * frame_count))),
        )
        marker: Dict[str, Any] = {
            "time_seconds": round(local_time, 6),
            "frame": frame_index,
            "strength": round(strength, 6),
        }
        if index < len(event_names):
            marker["event"] = event_names[index]
        markers.append(marker)
    return {
        "duration_seconds": round(samples.size / sample_rate, 6),
        "sample_rate": sample_rate,
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "non_silent_fraction": round(non_silent_fraction, 6),
        "suggested_markers": markers,
    }


def render_preview(
    frame_paths: Sequence[Path],
    destination: Path,
    *,
    duration_seconds: float,
    audio_path: Optional[Path],
    ffmpeg: str = "ffmpeg",
    png_optimize: bool = True,
    video_preset: str = "veryfast",
    video_crf: int = 20,
) -> Dict[str, Any]:
    Image, np = _image_dependencies()
    executable = require_executable(ffmpeg)
    if not frame_paths:
        raise Video2SpriteError("No processed frames are available for preview")
    with tempfile.TemporaryDirectory(prefix="video2sprite-preview-") as raw_temp:
        temp_dir = Path(raw_temp)
        for index, path in enumerate(frame_paths):
            with Image.open(path) as raw:
                frame = raw.convert("RGBA")
            width, height = frame.size
            tile = max(8, min(width, height) // 12)
            yy, xx = np.indices((height, width))
            light = ((xx // tile) + (yy // tile)) % 2 == 1
            checker_array = np.empty((height, width, 4), dtype=np.uint8)
            checker_array[:] = (38, 45, 58, 255)
            checker_array[light] = (75, 86, 102, 255)
            checker = Image.fromarray(checker_array, mode="RGBA")
            checker.alpha_composite(frame)
            checker.save(
                temp_dir / f"frame_{index:04d}.png",
                format="PNG",
                optimize=png_optimize,
                compress_level=9 if png_optimize else 1,
            )
        fps = len(frame_paths) / duration_seconds
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            f"{fps:.12f}",
            "-i",
            str(temp_dir / "frame_%04d.png"),
        ]
        if audio_path and audio_path.is_file():
            command.extend(["-i", str(audio_path)])
        command.extend(
            [
                "-t",
                f"{duration_seconds:.6f}",
                "-c:v",
                "libx264",
                "-preset",
                video_preset,
                "-crf",
                str(video_crf),
                "-pix_fmt",
                "yuv420p",
            ]
        )
        if audio_path and audio_path.is_file():
            command.extend(["-c:a", "aac", "-b:a", "160k", "-shortest"])
        else:
            command.append("-an")
        command.append(str(destination))
        run_command(command, timeout=max(120.0, duration_seconds * 20.0))
    return {
        "path": destination.name,
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
    }


def _qc_report(
    *,
    action: Dict[str, Any],
    candidate: Dict[str, Any],
    frame_result: Dict[str, Any],
    audio_result: Dict[str, Any],
    required_paths: Sequence[Path],
) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []

    def add(code: str, severity: str, message: str) -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    for path in required_paths:
        if not path.is_file() or path.stat().st_size == 0:
            add("missing_output", "fail", f"Required output is missing: {path.name}")
    if (candidate.get("source") or {}).get("origin") == "libtv":
        add(
            "libtv_visual_watermark_review_required",
            "review",
            "LibTV receipt and hashes passed; visually confirm that no watermark is baked into the frames",
        )
    metrics = frame_result["metrics"]
    if metrics["edge_touch"]:
        add("foreground_touches_edge", "review", "Foreground alpha touches a cell edge")
    if metrics["corner_rgb_std_mean"] > 14.0:
        add(
            "background_not_flat",
            "review",
            "Source corner color variance suggests a non-flat background",
        )
    chroma = action.get("chroma") or {}
    matte_tolerance = max(
        18.0,
        float(chroma.get("threshold", 42.0))
        + float(chroma.get("softness", 36.0)) * 0.5,
    )
    if metrics["corner_distance_from_key_mean"] > matte_tolerance:
        add(
            "background_key_mismatch",
            "review",
            "Source corners differ materially from the configured matte key",
        )
    if metrics["alpha_area_cv"] > 0.55:
        add("alpha_area_variation", "review", "Foreground area changes substantially")
    if metrics["baseline_span"] > 0.35:
        add("baseline_variation", "review", "Foreground baseline moves substantially")
    if action.get("loop") and metrics["loop_seam_mean_abs"] > 0.12:
        add("loop_seam", "review", "First and last processed frames differ substantially")

    audio_required = bool(action.get("audio_required"))
    if audio_required and not audio_result.get("present"):
        add("required_audio_missing", "fail", "This action requires audio but none was extracted")
    audio_metrics = audio_result.get("metrics") or {}
    if audio_required and audio_metrics:
        if audio_metrics.get("rms", 0.0) < 0.001 or audio_metrics.get("non_silent_fraction", 0.0) < 0.005:
            add("required_audio_silent", "fail", "Extracted audio is effectively silent")
    if audio_metrics.get("peak", 0.0) >= 0.98:
        add("audio_near_clipping", "review", "Audio peak is close to digital clipping")
    if action.get("events") and audio_result.get("present") and not audio_metrics.get("suggested_markers"):
        add("no_transient_marker", "review", "No plausible audio transient was detected for the requested event")
    native_audio = (candidate.get("capabilities") or {}).get("native_audio")
    if audio_required and native_audio is None:
        add(
            "unknown_native_audio_capability",
            "review",
            "The selected custom model has unknown native-audio capability",
        )

    severities = {issue["severity"] for issue in issues}
    status = "fail" if "fail" in severities else ("review" if "review" in severities else "pass")
    return {
        "schema_version": 1,
        "status": status,
        "issues": issues,
        "metrics": {
            "frames": metrics,
            "audio": audio_metrics,
        },
        "generated_at": utc_now(),
    }


def process_candidate_media(
    *,
    run_dir: Path,
    action_id: str,
    candidate_id: str,
    run_spec: Dict[str, Any],
    action: Dict[str, Any],
    candidate: Dict[str, Any],
    columns: Optional[int] = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    profile: str = "production",
) -> Dict[str, Any]:
    if profile not in {"production", "draft"}:
        raise Video2SpriteError("Processing profile must be production or draft")
    png_optimize = profile == "production"
    preview_preset = "veryfast" if profile == "production" else "ultrafast"
    preview_crf = 20 if profile == "production" else 28
    candidate_path = run_dir / "actions" / action_id / "candidates" / candidate_id
    source = candidate_path / "source.mp4"
    if not source.is_file():
        raise Video2SpriteError(f"Candidate source video is missing: {source}")
    source_probe = probe_media(source, ffprobe=ffprobe)
    if not source_probe["video"]["present"]:
        raise Video2SpriteError("Candidate source has no video stream")
    window = action.get("window") or {}
    start_seconds = float(window.get("start_seconds", 0.0))
    duration_seconds = float(window.get("duration_seconds") or action.get("duration_seconds") or 0.0)
    if duration_seconds <= 0:
        raise Video2SpriteError("Action duration must be positive")
    if source_probe["duration_seconds"] and start_seconds + duration_seconds > source_probe["duration_seconds"] + 0.08:
        raise Video2SpriteError(
            "Action window exceeds source duration "
            f"({start_seconds + duration_seconds:.3f}s > {source_probe['duration_seconds']:.3f}s)"
        )
    frame_count = int(action["frame_count"])
    frame_size = run_spec.get("frame_size") or {}
    target_size = (int(frame_size["width"]), int(frame_size["height"]))
    chroma = action.get("chroma") or run_spec.get("chroma") or {}
    key_color = str(chroma.get("key") or "#00ff00")
    threshold = float(chroma.get("threshold", 42.0))
    softness = float(chroma.get("softness", 36.0))
    key_mode = str(chroma.get("mode") or "global")
    placement = str(run_spec.get("placement") or "fit-union")
    resampling = str(run_spec.get("resampling") or "lanczos")
    pivot = run_spec.get("pivot") or {
        "x": target_size[0] / 2.0,
        "y": float(target_size[1]),
        "normalized": [0.5, 1.0],
    }
    frame_duration = duration_seconds / frame_count
    fixed_source_size = (
        (
            int(source_probe["video"]["width"]),
            int(source_probe["video"]["height"]),
        )
        if placement == "fixed"
        else None
    )

    with tempfile.TemporaryDirectory(prefix="video2sprite-frames-") as raw_temp:
        raw_paths, source_times = extract_video_frames(
            source,
            Path(raw_temp),
            frame_count=frame_count,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            ffmpeg=ffmpeg,
            fixed_source_size=fixed_source_size,
            fixed_target_size=target_size if fixed_source_size else None,
            fixed_pad_color=key_color,
            resampling=resampling,
        )
        frame_result = key_and_pack_frames(
            raw_paths,
            candidate_path / "frames",
            candidate_path / "atlas.png",
            target_size=target_size,
            key_color=key_color,
            threshold=threshold,
            softness=softness,
            key_mode=key_mode,
            placement=placement,
            pivot=pivot,
            resampling=resampling,
            columns=columns or action.get("columns"),
            source_times=source_times,
            frame_duration=frame_duration,
            png_optimize=png_optimize,
            fixed_source_size=fixed_source_size,
        )

    audio_result = extract_audio(
        source,
        candidate_path / "sfx.ogg",
        start_seconds=start_seconds,
        duration_seconds=duration_seconds,
        source_probe=source_probe,
        ffmpeg=ffmpeg,
    )
    if audio_result.get("present"):
        audio_result["metrics"] = analyze_audio(
            candidate_path / "sfx.ogg",
            frame_count=frame_count,
            action_duration=duration_seconds,
            event_names=[str(item) for item in action.get("events") or []],
            ffmpeg=ffmpeg,
        )
    else:
        audio_result["metrics"] = {}

    preview_result = render_preview(
        frame_result["paths"],
        candidate_path / "preview.mp4",
        duration_seconds=duration_seconds,
        audio_path=(candidate_path / "sfx.ogg") if audio_result.get("present") else None,
        ffmpeg=ffmpeg,
        png_optimize=png_optimize,
        video_preset=preview_preset,
        video_crf=preview_crf,
    )
    processing_fingerprint = candidate_processing_fingerprint(
        run_spec,
        action,
        candidate,
        columns=columns,
        profile=profile,
    )
    source_metadata = candidate.get("source") or {}
    source_provenance: Dict[str, Any] = {
        "path": "source.mp4",
        "sha256": sha256_file(source),
    }
    if "origin" in source_metadata:
        source_provenance["origin"] = source_metadata.get("origin")
    receipt = source_metadata.get("receipt")
    if isinstance(receipt, dict):
        source_provenance["receipt"] = {
            "path": receipt.get("path"),
            "sha256": receipt.get("sha256"),
            "receipt_type": receipt.get("receipt_type"),
            "required_flags": receipt.get("required_flags"),
            "proof_scope": receipt.get("proof_scope"),
            "reference_audit": receipt.get("reference_audit"),
        }
    manifest = {
        "schema_version": 1,
        "character_id": run_spec["character_id"],
        "action_id": action_id,
        "candidate_id": candidate_id,
        "loop": bool(action.get("loop")),
        "duration_seconds": round(duration_seconds, 6),
        "fps": round(frame_count / duration_seconds, 6),
        "frame_count": frame_count,
        "sampling": action.get("sampling")
        or {
            "mode": "count",
            "fps": round(frame_count / duration_seconds, 6),
        },
        "atlas": frame_result["atlas"],
        "frames": frame_result["frames"],
        "audio": audio_result,
        "events": {
            "requested": [str(item) for item in action.get("events") or []],
            "suggested": (audio_result.get("metrics") or {}).get("suggested_markers") or [],
        },
        "transform": frame_result["transform"],
        "provenance": {
            "source": source_provenance,
            "master_sha256": run_spec["master"]["sha256"],
            "provider": candidate.get("provider"),
            "model_alias": candidate.get("model_alias"),
            "model_id": candidate.get("model_id"),
            "prompt_sha256": action.get("prompt_sha256"),
            "action_fingerprint": action_processing_fingerprint(action),
            "processing_fingerprint": processing_fingerprint,
            "processing_profile": profile,
        },
        "generated_at": utc_now(),
    }
    atomic_write_json(candidate_path / "manifest.json", manifest)
    required_paths = [
        candidate_path / "atlas.png",
        candidate_path / "preview.mp4",
        candidate_path / "manifest.json",
    ] + list(frame_result["paths"])
    if action.get("audio_required"):
        required_paths.append(candidate_path / "sfx.ogg")
    qc = _qc_report(
        action=action,
        candidate=candidate,
        frame_result=frame_result,
        audio_result=audio_result,
        required_paths=required_paths,
    )
    atomic_write_json(candidate_path / "qc.json", qc)
    review_data = {
        "schema_version": 1,
        "action_id": action_id,
        "candidate_id": candidate_id,
        "provider": candidate.get("provider") or "local",
        "model_id": candidate.get("model_id") or "attached-video",
        "paths": {
            "source": "source.mp4",
            "preview": "preview.mp4",
            "atlas": "atlas.png",
            "manifest": "manifest.json",
            "audio": "sfx.ogg" if audio_result.get("present") else None,
        },
        "qc": qc,
        "manifest_summary": {
            "frame_count": manifest["frame_count"],
            "duration_seconds": manifest["duration_seconds"],
            "fps": manifest["fps"],
            "atlas": manifest["atlas"],
            "audio": manifest["audio"],
            "events": manifest["events"],
            "provenance": manifest["provenance"],
        },
    }
    atomic_write_json(candidate_path / "review-data.json", review_data)
    copy_file_atomic(SKILL_DIR / "assets" / "reviewer" / "index.html", candidate_path / "index.html")
    return {
        "status": qc["status"],
        "candidate_dir": str(candidate_path),
        "frame_count": frame_count,
        "atlas_sha256": frame_result["atlas"]["sha256"],
        "audio_present": bool(audio_result.get("present")),
        "preview_sha256": preview_result["sha256"],
        "qc_issue_codes": [issue["code"] for issue in qc["issues"]],
        "processing_fingerprint": processing_fingerprint,
        "processing_profile": profile,
    }
