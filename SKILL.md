---
name: sloth-codex-video2sprite-skill
description: Create game-ready 2D sprite animations with synchronized sound by generating a canonical still with GPT Image 2, animating one action per clip through a selectable video model such as Volcengine Seedance, and deterministically extracting, keying, aligning, validating, reviewing, and packaging local frames and audio without putting media payloads in Codex context. Use for video-to-sprite, image-to-video-to-sprite, character action clips, sprite atlases, Godot export, native SFX extraction, video-model comparisons, or workflows where image and Base64 context growth must be avoided.
---

# Sloth Codex Video2Sprite Skill

## Overview

Produce one isolated, fixed-camera action video with synchronized sound, then let local scripts turn it into transparent frames, an atlas, timing metadata, an audio clip, QC evidence, and a local review page. Keep every image, video, audio payload, and provider response out of the agent conversation.

Use GPT Image 2 for canonical still generation. Select the video provider and model independently; do not treat Seedance 2.0 as mandatory. Resolve configuration in this order: CLI override, run/action configuration, environment, bundled preset.

## Non-negotiable media firewall

1. Never call the conversational `$imagegen` flow for production batches. Invoke GPT Image 2 through `scripts/video2sprite.py generate-master`; the worker decodes Base64 internally and prints only bounded metadata.
2. Never print, paste, return, summarize, or persist raw Base64, data URLs, image bytes, audio bytes, video bytes, signed query strings, full provider responses, or secrets.
3. Pass media between stages only as absolute local paths, HTTPS URLs, provider asset IDs, hashes, and bounded JSON summaries.
4. Do not open generated media automatically. Run machine QC first, then give the user the localhost review URL. Read `approval.json` after the user reviews.
5. Do not claim an action is approved because processing or QC passed. Human audiovisual review remains required.
6. Keep runtime runs outside this Skill source directory. Never commit generated media, credentials, caches, or private references.

## Runtime setup

Use Python 3.9 or newer with Pillow and NumPy, plus `ffmpeg` and `ffprobe`. Prefer the Codex bundled Python when the system Python lacks the image packages. Do not install dependencies without approval.

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/sloth-codex-video2sprite-skill"
python3 "$SKILL_DIR/scripts/video2sprite.py" doctor
```

Read only the reference needed for the current step:

- `references/configuration.md`: environment variables, precedence, model selection, and credentials.
- `references/efficiency.md`: batch orchestration, pilot strategy, cache behavior, and retry budgets.
- `references/job-schema.md`: run, action, candidate, manifest, and approval contracts.
- `references/provider-contracts.md`: GPT Image 2 and selectable video-provider behavior.
- `references/prompting.md`: fixed-camera chroma action and dry-SFX prompting.
- `references/quality-gates.md`: automatic QC and human approval requirements.

## Workflow

### 1. Inspect available models

```bash
python "$SKILL_DIR/scripts/video2sprite.py" models
```

Treat bundled aliases as conveniences, not account entitlements. Prefer a native-audio video model for the final goal. Let the user override the default with `VIDEO2SPRITE_VIDEO_MODEL` or `--model`.

### 2. Generate or attach one approved master

Generate through the worker when an approved character master does not already exist:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" generate-master \
  --prompt-file /absolute/path/to/master-prompt.txt \
  --output /absolute/path/to/master.png
```

GPT Image 2 does not provide transparent output. Request a flat removable chroma background, full body, fixed view, no scenery, no text, and no shadow. Review the master once outside the agent context before using it for actions.

### 3. Initialize a run and define actions

```bash
python "$SKILL_DIR/scripts/video2sprite.py" init \
  --run-dir /absolute/path/to/video2sprite-run \
  --character-id hero \
  --master /absolute/path/to/master.png \
  --frame-size 256x256

python "$SKILL_DIR/scripts/video2sprite.py" add-action \
  --run-dir /absolute/path/to/video2sprite-run \
  --action-id attack \
  --prompt-file /absolute/path/to/attack-prompt.txt \
  --frames 12 \
  --duration 5 \
  --audio-required
```

Define one semantic action per video. Submit independent asynchronous jobs close together, then advance the whole run in batches instead of making one long blocking agent turn.

### 4. Submit or attach candidate videos

For remote generation, provide a provider-readable reference URL or asset URI in addition to the local master. Use one candidate for normal work. Benchmark more models only on representative pilot actions:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" submit \
  --run-dir /absolute/path/to/video2sprite-run \
  --action-id attack \
  --reference-url 'https://example.invalid/master.png' \
  --model seedance-2.0 \
  --purpose draft
```

After submitting the intended actions, make one nonblocking pass across the run:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" advance \
  --run-dir /absolute/path/to/video2sprite-run \
  --process-ready \
  --profile draft
```

`advance` concurrently polls every pending provider task once, downloads completed videos, and optionally processes every ready candidate. It never waits in a loop and never submits or creates a billed task. Run it again later until all submitted work is ready. Use the single-candidate `poll` command only for diagnosis.

Alternatively attach existing local MP4 files with `attach-video`, then run the same `advance --process-ready` command. The default budget permits at most two remote candidates per action. Exceed it only for a deliberate representative benchmark with `--allow-over-budget`.

### 5. Process and QC locally

```bash
python "$SKILL_DIR/scripts/video2sprite.py" process \
  --run-dir /absolute/path/to/video2sprite-run \
  --action-id attack \
  --candidate seedance-2.0 \
  --profile production
```

The processor selects evenly timed frames from the declared action window, removes the chroma background, applies one shared crop and scale, preserves source-relative motion, packs the atlas, extracts synchronized OGG audio, suggests transient event markers, renders a review preview, and writes bounded manifests.

Processing is incremental. When the source hash, action, geometry, columns, and profile have not changed, `process` returns `cached: true` without decoding the video, rewriting artifacts, or invalidating approval. Use `--force` only for an intentional rebuild. `draft` uses fast PNG and preview encoding; rerun the accepted candidate with `--profile production` before final approval and packaging.

Do not rescale each frame independently. Do not use a vision model to repair individual frames. Regenerate the candidate when the source video fails identity, action, camera, background, or sound requirements.

### 6. Review without loading media into Codex

```bash
python "$SKILL_DIR/scripts/video2sprite.py" review \
  --run-dir /absolute/path/to/video2sprite-run
```

The run-level reviewer queues every processed candidate in one localhost page with previous, next, and next-unreviewed controls. Give its URL to the user. Let the user compare the raw video, transparent preview, atlas, audio, metrics, and model provenance, then approve or reject without uploading media into Codex. After review, read only the small approval records. Add `--action-id` and `--candidate` only when isolating one candidate.

When evaluating providers, score visual identity, motion, audio, synchronization,
and overall quality in the reviewer. Summarize without opening media:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" compare \
  --run-dir /absolute/path/to/video2sprite-run
```

Treat a recommendation as provisional until representative actions are approved.
The command never changes environment defaults automatically.

### 7. Package approved actions

```bash
python "$SKILL_DIR/scripts/video2sprite.py" package \
  --run-dir /absolute/path/to/video2sprite-run \
  --output-dir /absolute/path/to/final-assets \
  --engine generic
```

Package only candidates whose QC is not `fail` and whose approval decision is `approved`. Keep gameplay projectiles, hitboxes, and persistent particles in engine code unless the user explicitly wants baked visual-only effects.

## Efficiency rules

- Submit all already-approved actions first, then use one `advance --process-ready` call per progress check. Never serialize polling and processing into dozens of conversational turns.
- Use `draft` during motion/model selection and `production` only for accepted finals.
- Reuse the master by hash, provider task ID, downloaded source hash, and processing fingerprint. A cache hit must not rewrite artifacts or archive approval.
- Reuse a candidate when its generation fingerprint matches. Repeat identical provider inputs only with the explicit `--allow-duplicate-input` billed-retry override.
- Default to one remote candidate per action; the hard guard is two. Test several models only on a small representative pilot, promote the winner, then generate the remaining action set with that model.
- Use the run-level reviewer instead of one server and one conversation round-trip per candidate.
- Keep network and local worker counts bounded. More local workers can slow the machine through FFmpeg and PNG contention.
- Use `status --compact` or `advance` summaries for orchestration; do not enumerate media files or provider payloads.
- Compare models with identical prompt, reference, duration, resolution, and seed when the provider supports a seed.
- Measure generation time, objective QC, human score, retry count, and any returned usage. Select the default only after a real pilot.
- Keep secrets in environment variables. Never ask the user to paste API keys into prompts or commit them to files.

## Acceptance criteria

Accept a final action only when:

- the requested frame count, atlas geometry, timing, pivot, and hashes are complete;
- no frame is empty, clipped, or contaminated by the chroma background;
- one shared spatial transform preserves motion without per-frame scale pumping;
- required audio exists, is not silent or clipped, and remains synchronized with the frame timings;
- loop seams and event markers are reviewed when relevant;
- identity, view, style, action readability, VFX, and sound pass human review;
- the packaged action is tested in the target engine.
