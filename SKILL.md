---
name: sloth-codex-video2sprite-skill
description: Produce game-ready 2D sprite actions with synchronized sound from a canonical still and externally generated or supplied video. Use for LibTV video intake, video-to-sprite extraction, action editing, QC, local review, atlases and Godot packaging, with media kept out of Codex context.
---

# Sloth Video to Sprite

Optimize total cost per accepted gameplay action. At the intended game size and
speed, preserve identity, readable motion, clean edges, consistent scale and
required action sound. Use GPT Image 2 only when a suitable master is missing;
generate videos externally through LibTV or use supplied local files. This Skill
is self-contained and has no direct video submission or polling adapter.

## Production defaults

- **768 video tier.** Use the shortest supported duration that fits the complete
  action. A lower tier is useful only if the representative pilot still meets the
  target sprite detail. Before **2K**, explain why it is needed and obtain explicit
  user approval for that scope; a preset or general generation request is not
  approval. Record the chosen tier and any approval in production notes.
- **Large subject, complete motion.** Fill the source frame at one constant scale
  with only necessary safety margins for the body, props and travel. No clipping,
  camera zoom, per-frame resizing or reduced action reach. A tiny exact first
  frame needs a better-framed, reviewed reference before generation. Keep actor
  scale consistent across its actions. Correct framing before raising resolution.
- **Short prompts.** Describe this action's visible poses, direction, timing and
  ending in a few sentences. `export-prompt` adds compact shared constraints once.
  Do not paste whole checklists, unrelated action examples, engine/pivot notes or
  duplicate exported text into the brief. Add one specific correction when needed.
- **Reuse before paying.** Reuse approved masters, videos and processing caches.
  Generate one representative pilot, review it at gameplay size, then expand the
  successful recipe. Normal budget: one candidate plus one targeted retry per
  action; persistent failure needs diagnosis before another paid attempt.
- **One local pass when possible.** For a normal candidate use `production`
  processing and one final review. Use `draft` only when it saves local selection
  time; selected draft artifacts must be rebuilt and reviewed before packaging.

Read only what the current step needs:

- `references/efficiency.md`: action reuse, tier/duration choices and retry budget.
- `references/prompting.md`: concise briefs, motion flags and reference framing.
- `references/sprite-production.md`: engine contract, shared transforms and combos.
- `references/configuration.md`: dependencies, image settings and credentials.
- `references/provider-contracts.md`: image API and external video intake.
- `references/quality-gates.md`: QC, use/redo decisions and acceptance limits.
- `references/job-schema.md`: artifact fields and cache/review fingerprints.

## Media boundary

Never use conversational `imagegen`, `view_image`, screenshots, media-bearing
subagents or `read_thread` on generated-media tasks. Keep Base64, data URLs,
media bytes, signed query strings, full provider responses and secrets out of
conversation and logs. Workers write media to disk and emit bounded summaries.
Use paths, hashes, `status --compact`, small QC/manifest/approval JSON and the
localhost reviewer. Never infer human approval from machine QC.
Keep runs outside the Skill source. Do not commit media, private references,
credentials or generated output. This boundary also applies to LibTV ancestors.

## Workflow

### 1. Prepare the character and action set

Use Python with Pillow/NumPy and FFmpeg/FFprobe. Prefer the bundled runtime;
do not install dependencies without approval. `doctor` checks availability and
`models` lists image models. Reuse the game's existing master when suitable.
Only when a new master is needed:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" generate-master \
  --prompt-file /absolute/path/to/master-brief.txt \
  --output /absolute/path/to/master.png
```

`SKILL_DIR` is this Skill's installed directory. Image quality defaults to
`medium`; keep a usable approved image instead of regenerating it at `high`.
Choose a flat matte absent from the costume; the default is dark `#3f0050`.
Review identity, equipment/grip and framing once. Plan each action's required
poses and ending before spending; see `references/sprite-production.md`.

### 2. Define and generate one pilot

Match the game's canvas, foot pivot, facing and frame rate. Example values are
not universal defaults:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" init \
  --run-dir /absolute/path/to/run --character-id hero \
  --master /absolute/path/to/master.png \
  --frame-size 288x176 --pivot 144,144 --resampling nearest

python "$SKILL_DIR/scripts/video2sprite.py" add-action \
  --run-dir /absolute/path/to/run --action-id attack \
  --prompt-file /absolute/path/to/attack-brief.txt \
  --fps 24 --duration 4 --window-duration 1.5 --audio-required

python "$SKILL_DIR/scripts/video2sprite.py" export-prompt \
  --run-dir /absolute/path/to/run --action-id attack \
  --output /absolute/path/to/attack-video-prompt.txt
```

Default motion is `pixel-act`, `in-place`, `recover`. Use `--end-state hold` for
terminal/bridge poses, `--loop` for a loop, and `--root-motion travel` only for
intentional movement across the picture. Write the matching visible motion in
the brief; do not change gameplay movement or hitboxes to fit a weak result.
Generate externally with the master and exported prompt. Keep resolution and
other provider settings in the tool, not repeated in the prompt. Require clean
character/prop motion without added VFX or BGM, with synchronized dry SFX when
required. The local CLI does not enforce external billing or approval gates.

### 3. Attach, process and review

LibTV artifacts must pass the wrapper; it always uses
`--without-ai-watermark --vip` and writes `source.receipt.json` on attachment:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" libtv-download \
  --node <node> --output-dir /absolute/path/to/empty-download \
  --reference-audit no-libtv-ancestors

python "$SKILL_DIR/scripts/video2sprite.py" attach-video \
  --run-dir /absolute/path/to/run --action-id attack --candidate pilot \
  --video /absolute/path/to/empty-download/member.mp4 \
  --source-origin libtv \
  --source-receipt /absolute/path/to/empty-download/member.mp4.libtv-receipt.json
```

Declare `no-libtv-ancestors` only when true. For LibTV-origin 上游 references, use
`verified-libtv-ancestors` with paired `--ancestor-source`/`--ancestor-receipt`.
不得 reuse unreceipted or visibly watermarked frames as new references.
receipt 只证明 download flags and file identity; it does not prove 视觉无水印.
Ordinary local videos use `attach-video --source-origin local` without a receipt.
Never label LibTV output as ordinary local media to bypass its provenance check.

Use `advance --process-ready` for all ready local candidates or `process` for one:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" advance \
  --run-dir /absolute/path/to/run --process-ready --profile production
python "$SKILL_DIR/scripts/video2sprite.py" review --run-dir /absolute/path/to/run
```

Keep the source unchanged, preserve the effective action's frame rate and use one
shared spatial transform. Border-connected matte removal preserves enclosed
costume pixels; review edges and enclosed background pockets. Fix window/matte/
placement errors locally before paying for a replacement source.
Give the localhost URL to the user; record their explicit “use this” or “redo”
decision through the reviewer helper described in `references/quality-gates.md`.
After the pilot is adopted, reuse its model/framing recipe for remaining actions.

### 4. Deliver approved assets

```bash
python "$SKILL_DIR/scripts/video2sprite.py" package \
  --run-dir /absolute/path/to/run \
  --output-dir /absolute/path/to/final-assets --engine godot
```

Use `generic` when appropriate. Packaging requires current approval, production
artifacts and QC other than `fail`. Verify playback, pivot and event timing in
the target engine; keep game VFX and collision logic separate. Report accepted
versus pending actions, known spend/retries and any unresolved quality issue.
Offline prompt tests prove routing and contracts, not a provider's visual quality.

## Editing existing sprites

Use the 工作中 → 已确认 → 游戏绑定 workbench by default. Read
`references/sprite-edit-workbench.md` and adapt `assets/sprite-edit-workbench/`;
reuse the project's instance when available. Preserve originals, create new
unconfirmed versions for edits, and keep confirmation separate from game binding.
Explicit user workflow choices override this default.
