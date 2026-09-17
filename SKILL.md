---
name: sloth-codex-video2sprite-skill
description: Create, repair, review and package 2D game sprites. Use as the unified sprite entry point; route video actions, imagegen artwork and image-sheet work according to the requested asset.
---

# Sloth Sprite Production

One entry point for sprite work. Reuse existing assets and preserve the game's
identity, facing, scale, pivot, timing and requested sound. Keep the public Skill
name and existing video CLI stable for current projects.

## Choose one path

Use the requested method first. Otherwise inspect existing project/run metadata
and choose by the actual asset and change; do not infer a backend from the word
"sprite", "frame", "repair", or a `run.json` filename alone.

| Request or input | Path |
| --- | --- |
| New continuous action or supplied action video | [Video workflow](references/video-workflow.md), the default for new motion |
| Draw/edit one master, character image or a specific image/frame | [Image workflow](references/image-workflow.md), using the installed `imagegen` skill |
| Explicit imagegen action-sheet request, supplied sprite sheet, or an existing image-sheet run | [Image workflow](references/image-workflow.md), then load `my-codex-sprite-skill` on demand |
| Timing, trim, placement, alpha-processing or export fix in a video run | Keep the video backend and existing sources; use the shared [editing workbench](references/sprite-edit-workbench.md) |
| Existing image-sheet run or image-sheet processing/export fix | Keep its image-sheet backend; do not generate new art unless requested |
| Review/diagnosis only | Inspect the relevant path and report findings; do not generate or overwrite |

Image-sheet work may be routed internally without asking the user to name the
image-sheet skill. That skill is independently usable; some personal installations
make it explicit-only to prefer this unified entry point. Either policy permits
this scoped handoff. Load its body only when image-sheet processing needs it.
Ordinary video tasks do not depend on that installation.

Missing a master does not turn a video action into an image-sheet task: use
imagegen for the master, save the chosen local asset, then return to video.
If the user explicitly selects the existing headless `generate-master` API
worker, retain that path and its credential/billing contract; do not silently
switch a built-in image request to it.

## Sprite modification workbench

For existing sprite edits, always load the affected actions into the
[instant editing workbench](references/sprite-edit-workbench.md) and give the user
its localhost URL. This applies equally to Bosses, enemies and other characters,
for both video and image-sheet paths. Reuse a project instance or install the
bundled `assets/sprite-edit-workbench/instant/` template. Append new versions,
preserve explicit per-action choices, and preview frame selection with canvas
frames plus independent audio; do not regenerate preview video for draft edits.
Keep final approval and game binding with the existing backend adapters.

## Shared boundaries

- Keep runs outside Skill sources. Preserve originals and already accepted work;
  create new candidates for changes and invalidate affected acceptance.
- Never print Base64, data URLs, signed URL query strings, credentials or full
  provider payloads. Local workers keep bounded, redacted status and logs.
- Video processing/review uses local media and the localhost reviewer, with
  `status --compact` for agent inspection. Do not load videos or batches of
  extracted frames into the conversation with `view_image`, screenshots,
  media-bearing subagents or `read_thread`.
- Image work permits the necessary reference/target/output images through the
  supported imagegen and image-view tools. This is not permission to rehydrate
  an entire video run or export raw payloads. Follow the current tool schema.
- Retain source provenance across paths. LibTV-derived inputs keep their receipt
  ancestry; an image edit cannot relabel them as ordinary local media.
- Preserve user decisions and scope. Do not expand paid retries, change providers,
  drop required sound or claim human approval from machine QC.
- An image-sheet output has no synchronized audio by itself. If sound is required,
  deliver a separately authorized sound path or report it pending.

## Complete the selected task

For video actions, follow [video quality gates](references/quality-gates.md):
preserve required audio, source receipts, production processing and the user's
current use/redo decision before packaging. For image sheets, use that backend's
QC, visual selection and atlas export; do not copy approval files between formats.

A standalone image task ends with the saved image and relevant visual checks.
An action task ends with the requested frames/atlas, timing/pivot metadata,
preview and backend-specific acceptance. Verify engine playback when integration
is requested; mark unavailable or pending checks honestly. Do not create a full
action set, video or game binding for an image-only request.

Load only the selected workflow and its needed references. Command examples use
`SKILL_DIR` for the directory containing the relevant backend's `SKILL.md`;
keep the unified and image-sheet backend paths distinct.
