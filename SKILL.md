---
name: sloth-codex-video2sprite-skill
description: Independently produce game-ready 2D sprite animations with synchronized sound from a canonical still and one action video, including Volcengine Seedance calls, full-rate frame extraction, dark-matte removal, fixed-pivot alignment, QC, a local keyframe/video workbench, atlases, and Godot packaging without media payloads entering Codex context. Use for video-to-sprite, image-to-video-to-sprite, side-view combat actions, sprite atlases, Godot export, native SFX extraction, or a complete result-owned sprite pipeline that must not depend on another sprite Skill.
---

# Sloth Codex Video2Sprite Skill

## Overview

Own the result end to end: turn one isolated, fixed-camera action video with synchronized sound into transparent frames, an atlas, timing metadata, an audio clip, QC evidence, a local keyframe/video workbench, and a target-engine package. Keep every image, video, audio payload, and provider response out of the agent conversation.

Use GPT Image 2 for canonical still generation. Select the video provider and model independently; do not treat Seedance 2.0 as mandatory. Resolve configuration in this order: CLI override, run/action configuration, environment, bundled preset.

This Skill is self-contained. Do not invoke, import, or require
`my-codex-sprite-skill` or any other sprite Skill. Existing project sprites may
serve as visual and motion benchmarks only. Read
`references/sprite-production.md` before defining a production action.

## Non-negotiable media firewall

1. Never call conversational `imagegen` or `$imagegen` for this workflow. Invoke GPT Image 2 through `scripts/video2sprite.py generate-master`; the worker decodes Base64 internally and prints only bounded metadata.
2. Never print, paste, return, summarize, or persist raw Base64, data URLs, image bytes, audio bytes, video bytes, signed query strings, full provider responses, or secrets.
3. Pass media between stages only as absolute local paths, HTTPS URLs, provider asset IDs, hashes, and bounded JSON summaries.
4. Never call `view_image`, a screenshot tool, or a vision subagent on generated media. Run machine QC, give the user the localhost review URL, and read only the resulting small `approval.json`.
5. Never call `read_thread` on a task that may contain image generation or image viewing. `includeOutputs=false` is not a media firewall because structured image-generation results can still be rehydrated. Use local `status --compact` instead.
6. Do not copy a media task into another task for monitoring and do not delegate visual inspection to subagents; either action duplicates payloads and context.
7. Do not claim an action is approved because processing or QC passed. Human audiovisual review remains required.
8. Keep runtime runs outside this Skill source directory. Never commit generated media, credentials, caches, or private references.

## Runtime setup

Use Python 3.9 or newer with Pillow and NumPy, plus `ffmpeg` and `ffprobe`. Prefer the Codex bundled Python when the system Python lacks the image packages. Do not install dependencies without approval.

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/sloth-codex-video2sprite-skill"
python3 "$SKILL_DIR/scripts/video2sprite.py" doctor
```

The one canonical persistent key store is
`~/.config/sloth-codex-video2sprite/credentials.env`. It is machine-local,
outside both the source repository and installed Skill, and must never be
tracked by Git. Environment variables still take priority. When `doctor` shows
a missing provider key, save it through the bounded CLI instead of writing a
repository `.env`:

```bash
# Hidden interactive entry in a user-controlled terminal:
python3 "$SKILL_DIR/scripts/video2sprite.py" configure-key --name ark

# Or copy from an already-set environment variable without putting the value on argv:
python3 "$SKILL_DIR/scripts/video2sprite.py" configure-key \
  --name ark \
  --from-env SEEDANCE_API_KEY
```

Use `--name openai` for GPT Image. The command creates the parent directory as
`700`, writes the file atomically as `600`, preserves the other provider key,
and never prints the value. It deliberately has no raw `--key` argument. If a
user has not configured a key, ask them to enter it through the hidden prompt or
make it available through a local environment variable; do not ask them to
paste a credential into the Codex conversation. Once securely supplied, store
it at this fixed path by default so later Codex sessions do not depend on
conversation context.

Read only the reference needed for the current step:

- `references/configuration.md`: environment variables, precedence, model selection, and credentials.
- `references/efficiency.md`: batch orchestration, pilot strategy, cache behavior, and retry budgets.
- `references/job-schema.md`: run, action, candidate, manifest, and approval contracts.
- `references/provider-contracts.md`: GPT Image 2 and selectable video-provider behavior.
- `references/prompting.md`: fixed-camera game-action, dark-matte, and dry-SFX prompting.
- `references/sprite-production.md`: canonical master, motion beats, frame-rate, pivot, atlas, and engine acceptance rules.
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

GPT Image 2 does not provide transparent output. Request a flat removable matte,
full body, fixed view, no scenery, no text, and no shadow. Default to a dark
non-green hue that is absent from the character. Review the master once outside
the agent context before using it for actions. Repeating the same command against
the same verified output is a free cache hit; changing the prompt, model, size,
quality, or matte requires an explicit `--overwrite` and creates a new billed
image.

### 3. Initialize a run and define actions

```bash
python "$SKILL_DIR/scripts/video2sprite.py" init \
  --run-dir /absolute/path/to/video2sprite-run \
  --character-id hero \
  --master /absolute/path/to/master.png \
  --frame-size 288x176 \
  --pivot 144,144 \
  --placement fixed \
  --resampling nearest \
  --chroma-key '#3f0050' \
  --chroma-mode border

python "$SKILL_DIR/scripts/video2sprite.py" add-action \
  --run-dir /absolute/path/to/video2sprite-run \
  --action-id attack \
  --prompt-file /absolute/path/to/attack-prompt.txt \
  --fps 24 \
  --duration 4 \
  --window-start 0 \
  --window-duration 1.75 \
  --audio-required
```

Define one semantic action per video. `--fps 24` preserves every 24fps source
frame inside the effective action window; it does not sparsely sample a few
poses. Keep the full provider video as evidence, but exclude only deliberate
pre/post-action holds from the runtime atlas.

### 4. Submit or attach candidate videos

For remote generation, prefer the canonical local master copied into the run. The worker verifies its hash and dimensions, converts it to the provider's inline request form only in memory, and never prints or persists the encoded media:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" submit \
  --run-dir /absolute/path/to/video2sprite-run \
  --action-id attack \
  --reference-file /absolute/path/to/video2sprite-run/master/source.png \
  --model seedance-2.0 \
  --purpose draft
```

Stable HTTPS URLs, environment-sourced signed URLs, and provider asset URIs remain supported when the provider must fetch the reference itself. Use one candidate for normal work. Submit and review one representative paid pilot before expanding to other actions. The CLI permits retries or model comparison on that same pilot action, but blocks a different action until a remote pilot is validly approved. `--allow-unapproved-batch` is only for a user-authorized billed batch.

Advance submitted work in a bounded polling window:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" advance \
  --run-dir /absolute/path/to/video2sprite-run \
  --process-ready \
  --profile draft \
  --wait-seconds 50
```

`advance` concurrently polls pending provider tasks, downloads completed videos,
and optionally processes ready candidates. The default is one nonblocking pass;
`--wait-seconds` performs several internal passes but is hard-capped at 55
seconds and emits only one final bounded summary. It never submits or creates a
billed task. Use the single-candidate `poll` command only for diagnosis.

After the user adopts the pilot, submit the remaining independent actions close
together and advance the whole run in batches. Alternatively attach existing
local MP4 files with `attach-video`, then run the same
`advance --process-ready` command. When an existing candidate comes from a
LibTV node, download the watermark-free member artifact with both explicit
flags before attaching it:

```bash
libtv download -n <node> -o <dedicated-output-directory> \
  --without-ai-watermark --vip
```

The default budget permits at most two remote candidates per action. Exceed it
only for a deliberate representative benchmark with `--allow-over-budget`.

### 5. Process and QC locally

```bash
python "$SKILL_DIR/scripts/video2sprite.py" process \
  --run-dir /absolute/path/to/video2sprite-run \
  --action-id attack \
  --candidate seedance-2.0 \
  --profile production
```

The processor preserves the declared frame rate across the action window. For
fixed placement, FFmpeg scales and pads decoded frames directly to the target
canvas before temporary PNGs are written, avoiding a full-resolution frame
intermediate. It then removes only matte pixels connected to the canvas border, applies one shared
fixed-canvas transform, preserves source-relative motion and the configured
pivot, packs the atlas, extracts synchronized OGG audio with codec-safe output
headroom, suggests transient event markers, renders a preview, and writes
bounded manifests. Use `fit-union` only for legacy footage whose source framing
was not authored as the target sprite canvas.

Processing is incremental. When the source hash, action, geometry, columns, and profile have not changed, `process` returns `cached: true` without decoding the video, rewriting artifacts, or invalidating approval. Use `--force` only for an intentional rebuild. `draft` uses fast PNG and preview encoding; rerun the accepted candidate with `--profile production` before final approval and packaging.

Do not rescale each frame independently. Do not use a vision model to repair individual frames. Regenerate the candidate when the source video fails identity, action, camera, background, or sound requirements.

### 6. Review without loading media into Codex

```bash
python "$SKILL_DIR/scripts/video2sprite.py" review \
  --run-dir /absolute/path/to/video2sprite-run
```

The localhost workbench puts all extracted frames on the large left pane, keeps
the processed action video playing at the upper right, and shows one enlarged
still at the lower right. Its header keeps the current Sprite position and total
in an explicit localized form (`第 3 个 / 共 5 个`) beside the current action and
candidate name, so screenshots remain attributable. Clicking a left-side frame
or pressing the left and right arrow keys updates only the still viewer, so the
video can continue playing for motion comparison. Keyboard selection stays
focused and scrolls into view. The workbench is intentionally observation-only:
it has no score, note, approve, or redo controls. Give its URL to the user,
receive the user's “use this” or “redo” decision in the conversation, then
record that explicit decision locally before packaging. Add `--action-id` and
`--candidate` only when isolating one candidate.

When deliberately evaluating several providers, optional legacy score metadata
may still be aggregated without opening media:

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

- Submit one paid pilot action first. Expand to other actions only after its remote candidate is processed and the user chooses “use this”; the CLI enforces this unless `--allow-unapproved-batch` is explicit.
- Use `advance --process-ready --wait-seconds 50` for progress. Never serialize polling and processing into dozens of conversational turns.
- Use `draft` during motion/model selection and `production` only for accepted finals.
- Reuse the master by hash, provider task ID, downloaded source hash, and processing fingerprint. A cache hit must not rewrite artifacts or archive approval.
- Reuse a candidate when its generation fingerprint matches. Repeat identical provider inputs only with the explicit `--allow-duplicate-input` billed-retry override.
- Default to one remote candidate per action; the hard guard is two. Test several models only on a small representative pilot, promote the winner, then generate the remaining action set with that model.
- Use the run-level reviewer instead of one server and one conversation round-trip per candidate.
- Keep network and local worker counts bounded. More local workers can slow the machine through FFmpeg and PNG contention.
- Use `status --compact` or one bounded `advance` summary for orchestration. Never inspect a media task through `read_thread`, `view_image`, screenshots, or media-bearing subagent messages.
- Compare models with identical prompt, reference, duration, resolution, and seed when the provider supports a seed.
- Measure generation time, objective QC, the user's use/redo decision, retry count, and any returned usage. Select the default only after a real pilot.
- Keep secrets in environment variables or the permission-locked user-level
  file at `~/.config/sloth-codex-video2sprite/credentials.env`, as documented
  in `references/configuration.md`. Environment variables take priority. Never
  ask the user to paste API keys into prompts or place credentials in a
  repository, Skill installation, run, or output.

## Acceptance criteria

Accept a final action only when:

- the requested frame count, atlas geometry, timing, pivot, and hashes are complete;
- no frame is empty, clipped, or contaminated by the extraction matte;
- one shared spatial transform preserves motion without per-frame scale pumping;
- the first and final ready poses share the configured foot-root, and a
  one-shot action returns to its starting place;
- fast anticipation, contact, follow-through, and recovery retain their full
  requested frame rate; only redundant holds may be omitted;
- required audio exists, is not silent or clipped, and remains synchronized with the frame timings;
- loop seams and event markers are reviewed when relevant;
- identity, view, style, action readability, coherent VFX direction, and sound
  earn the user's “use this” decision;
- the packaged action is tested in the target engine.
