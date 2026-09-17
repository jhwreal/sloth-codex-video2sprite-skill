# Video action workflow

Use this for new continuous actions or existing video runs. Resolve `SKILL_DIR`
to the unified Skill root, not this references directory. Image-sheet work is
handled by [image-workflow.md](image-workflow.md); do not load it for ordinary
video processing.

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

- `efficiency.md`: action reuse, tier/duration choices and retry budget.
- `prompting.md`: concise briefs, motion flags and reference framing.
- `sprite-production.md`: engine contract, shared transforms and combos.
- `configuration.md`: dependencies, image settings and credentials.
- `provider-contracts.md`: image API and external video intake.
- `quality-gates.md`: QC, use/redo decisions and acceptance limits.
- `job-schema.md`: artifact fields and cache/review fingerprints.

## Media boundary

On this video-processing path, never use conversational `imagegen`, `view_image`,
screenshots, media-bearing subagents or `read_thread` to load generated videos
or frame batches. For a requested image/master creation or redraw, enter the
scoped image workflow and return its saved file path before continuing here. Keep Base64, data URLs,
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
When a new master is needed, follow [image-workflow.md](image-workflow.md),
save the selected reference and return here. For an explicitly selected headless
API workflow, the existing worker remains available:

```bash
python "$SKILL_DIR/scripts/video2sprite.py" generate-master \
  --prompt-file /absolute/path/to/master-brief.txt \
  --output /absolute/path/to/master.png
```

That API worker defaults to `medium`; this is not a built-in imagegen setting.
Reuse approved art. Choose the video reference matte absent from the costume
according to the project/generator contract; the existing worker defaults to
dark `#3f0050`. Review identity, equipment/grip and framing once. Plan required
poses and ending before spending; see [sprite-production.md](sprite-production.md).

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
decision through the reviewer helper described in `quality-gates.md`.
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

For modifications to existing action sprites, use the shared
[instant editing workbench](sprite-edit-workbench.md) for user interaction on
this path, preserving its native run format and acceptance.
