# Default sprite modification workbench

For **every existing sprite modification**, whether Boss, enemy, player, NPC,
video-derived, image-sheet or loose frames, load the asset into the instant editor
and return its localhost URL to the user. Reuse a project instance where possible;
otherwise install `assets/sprite-edit-workbench/instant/`. Keep the selected
backend, originals, provenance and acceptance rules. A review-only request or
standalone master drawing does not require creating an action editor.

One workbench represents one Sprite/character. Its left navigation lists that
Sprite's actions (for example Boss Action 1 / Action 2, or idle / attack), not
character categories such as Boss / Enemy. Each action has its own versions.

## Create or update an instance

The default is the reusable frame-and-audio editor extracted from the tested
instant-edit workbench. It has no character IDs, generation budget or engine
binding built in. Prepare `production-plan.json` in an output directory outside
Skill sources, then run:

```bash
python "$SKILL_DIR/scripts/create_sprite_workbench.py" --output-dir /path/to/workbench
python -m http.server 8795 --bind 127.0.0.1 --directory /path/to/project
```

Serve a root containing the workbench and its local media, then give the user the
corresponding `/path/to/workbench/index.html` URL. The helper copies only three
editor files and refuses to overwrite an existing instance. For an existing
instance, merge the template behavior into its project adapter; preserve its plan,
media, decisions, custom controls and runtime binding.

Minimal project plan (paths are examples, not bundled media):

```json
{
  "title": "Sprite 即时编辑工作台 · Character",
  "workbench": {"canvasWidth": 320, "canvasHeight": 240},
  "actions": [{
    "action": "idle", "name": "待机", "fps": 12, "loop": true,
    "candidates": [
      {"id": "idle-v1", "label": "待机 v1", "manifest": "idle/v1/manifest.json"},
      {"id": "idle-v2", "label": "待机 v2", "manifest": "idle/v2/manifest.json"}
    ]
  }]
}
```

Each candidate has a distinct immutable manifest path. Append every new version,
including H3 retries, image edits and locally trimmed derivatives, to the end of
`candidates`; never replace older entries. Arrays define chronological order.
The editor polls the plan every ten seconds, defaults to the latest version, and
preserves a user's explicit choice separately for each action. Optional `frames`
is an ordered array of reference image paths, not a claim of approval. `prompt`
and `opening` are optional local resource links.

Manifest paths are relative to the plan/page; frame, atlas and audio paths are
relative to their manifest. Use a presentation manifest for image-sheet backends
without rewriting their native run schema. A manifest needs `fps` and ordered
`frames`, each with `file` or an atlas `cell: {x,y,width,height}`. Optional fields:

- `duration_ticks` (or `duration_seconds`) on each frame, `loop` on the manifest.
- `atlas: {path,width,height,sha256}` and `canvas: {width,height}` for atlas playback.
- `audio: {present:true,path:"sfx.ogg"}` for a separate audio file.
- `derivation.crop: [x,y,width,height]` with `derivation.canvas_width` and
  `canvas_height` for restoring cropped cells to the original canvas.

Keep uniform geometry, root and scale. Supply actual dimensions, especially for
cropped and non-square sprites. Preserve backend source/receipt/hash metadata in
the presentation manifest; do not copy private URLs or provider payloads into it.

## Instant editing contract

- 工作中 shows actions, oldest-to-newest versions, a canvas preview, full numbered
  filmstrip, timeline, range, FPS, speed, timing mode and loop controls.
- Every card has ✓ at top left and × at top right. All frames start included.
  Exclusion changes only the draft; playback immediately skips excluded frames
  in original order. Clicking an excluded image still inspects it. Empty selection
  disables playback; all-keep restores the checkmarks (range still applies).
- Left/Right arrows inspect adjacent cards in the complete bottom filmstrip,
  including excluded and out-of-range frames; inspection pauses playback and
  scrolls/focuses the selected card into view without changing inclusion. This
  also works after clicking a frame, its keep/remove button or playback controls.
  Text/number inputs, selects and editable text retain their normal arrow keys.
  Toolbar previous/next still step through retained playback frames.
- UI frame numbers and exported selections are one-based and inclusive. Internal
  indices are zero-based. Remaining frame holds are preserved by default; equal
  timing is an explicit option. Do not normalize frames to individual bounds.
- **No preview video is generated or loaded for these edits.** Canvas frames and
  an independent audio element provide immediate playback. Do not rerun FFmpeg or
  a video build script merely because a user changes frame selection or timing.
  Existing generation CLI artifacts remain compatible; source videos stay intact.
- Audio starts at the selected retained playback frame, restarts on loops and
  stops on pause, action/version/tab change, animation end or hidden page. FPS and
  speed affect its rate. Removing picture frames does not splice corresponding
  audio segments; verify sound alignment with the user before final delivery.
- Drafts and explicit choices persist in localStorage, scoped to page directory,
  browser and origin. Different ports/browsers do not share them. Export JSON to
  preserve a decision outside browser storage. New manifest content creates a
  fresh draft; keep version paths immutable.

## Confirmation, binding and final delivery

Export downloads `sprite-edit-decision.v1`: source manifest/snapshot, atlas hash
when available, selected frame numbers, compressed timeline, timing and audio cue.
It is a **pending edit recipe**, not an atlas, approval or game binding. Validate
source hashes/snapshot before applying it through the current backend's derived
candidate adapter; preserve unchanged pixels, frame mapping, receipts and sound.
Build a new unconfirmed version and add it back to 工作中. Materialize final atlas,
metadata and required sound after the selection is settled; preview video remains
optional unless a separately requested export/backend contract requires it.

已确认 and 游戏绑定 are read-only views. A project adapter may populate each
action's `confirmed` or `binding` with `{label,manifest}` only after verifying the
actual human approval or runtime record against the current media and timing.
Their manifests describe the exact final selection and sound. Without these
records, display an empty state; never relabel reference frames as approved.
Edits do not approve or bind anything. Use the backend's existing acceptance and
game adapter for writes, require user intent for binding, invalidate acceptance
when content/timing changes, and retain per-action rollback.

The older top-level `.template` files are **legacy project-specific examples**
for server writes and Godot binding, not the default editor or a drop-in API for
this frontend. Only consult them when adapting an existing integration. Adapt
ROOT/RUN/HERE, namespace, identity, scale and engine paths; remove example budgets
and hardcoded audiovisual approval claims. Preserve localhost token/origin checks,
path bounds, receipt origin branching and hash validation. Never apply the sample
768/552 scale, action list or LibTV-only receipt copy to another character.

## Verification

Run `node --test tests/test_editor_model.mjs` and the Python helper tests. Use
synthetic local images/audio for a browser smoke test: exclude final five of ten
frames, verify five-frame playback/timing, all-excluded protection, restore,
refresh persistence, two actions' remembered versions, latest-version fallback,
audio cue/pause and empty confirmed/binding states. Confirm no video element or
preview-video request. Actual animation aesthetics, audio sync and any engine
binding still require asset-specific user/engine review.
