# Production contract

## Plan before generation

Record the game's facing, logical frame size, standing character height, pivot,
frame rate, action duration, required equipment, events and ending. Inspect
existing assets as benchmarks; do not change the controller, reach or hitboxes
to accommodate generated pixels. Apply the reuse/cost choices in `efficiency.md`.

Use one approved master on a matte distinct from the costume. Required props
must contact the correct hands. Frame at the largest constant scale that safely
contains planned poses, full weapon arcs and intended travel. Keep that actor's
scale consistent across actions. Review grip, identity and actual source detail
before generation. If an exact first-frame reference is tiny, reframe it first.

The action brief describes visible movement only. Select the matching motion and
ending flags using `prompting.md`; don't copy engine movement or pivot rules into
provider text. One asset normally represents one player-input action, with its
complete anticipation/movement/follow-through and appropriate ending.

## Preserve source movement and timing

Keep the original video unchanged. Preserve the action window at the intended
runtime rate, normally native 24fps for this workflow. Do not collapse a fast
strike to a few uniformly sampled poses. Remove redundant holds only when they
are outside useful motion; retain anticipation, contact and terminal/bridge poses.

If the game needs a lower-rate pixel animation, derive it with explicit timing
from the full-rate source. Do not delete the only full-rate version. Frame drops,
interpolation and faster playback do not create missing pose amplitude. Keep
synchronized SFX and event times aligned; put gameplay hit-stop in the engine
unless asset-level timing is specifically intended.

## Reuse continuous sources carefully

A naturally linked combo may share one continuous video and still deliver one
action per input. Decide whether this saves expected billed work before generation;
longer, more complicated clips can be harder to get right. Never mix unrelated
moves solely to claim more actions from one request.

For a linked combo:

- Specify exact hit count and a clear bridge after each middle impact. Preserve
  momentum and facing; only the final stage recovers to combat idle.
- Split so the final frame of stage N is the exact opening frame of N+1. Preserve
  source hash, FPS, pivot, body/weapon position and audio alignment.
- Each input has its own event and chain/cancel window. If the player stops early,
  use a separate recovery branch or engine blend; do not insert an idle reset
  into the linked core sequence.
- For separately generated middle stages, use `hold` with a specific bridge pose.
  Derivatives retain source receipts and need approval of their actual timing.

The CLI handles action windows and packaging, not automatic semantic combo
splitting. Verify boundaries and event mapping; don't claim derivation succeeded
from a storyboard or prompt alone.

## Matte and spatial transform

Default to a dark matte absent from the character, with `chroma-mode=border`.
It removes near-matte pixels connected to the outer background and cleans partial
edges, preserving enclosed clothing even when its color matches the matte.
Enclosed genuine background pockets can remain; check them in human review.
Do not blindly erase all enclosed matching colors to hide a background pocket.

For authored framing use `placement=fixed`: one canvas resize/pad into the target
frame, with the same pivot for every pose. Never resize each frame to its own
bounds, recenter a lunge or remove a legitimate jump. Crouches and extension
naturally change silhouette bounds. Use `fit-union` only for legacy framing; it
still applies one shared transform. Post-crop upscaling cannot recover lost detail.

Changing geometry, windows or key settings is a local processing job. Try that
before regeneration when the source itself already contains the required pixels.

## Review and engine verification

Machine QC reports decode/frame/audio failures, clipping and matte diagnostics,
bounds/baseline variation, loop difference, geometry and hashes. It cannot prove
anatomical scale stability, root correctness, expressiveness or visual watermark
absence. Judge those against the move at actual game size and playback speed.

Use one run-level localhost review. Record explicit use/redo decisions for current
artifacts; see `quality-gates.md`. Ordinary candidates may go directly through
production processing and one final review. Only selected drafts need rebuilding.

Package current approved production artifacts. Test target-engine playback,
filtering, pivot, contact events and transitions. Keep VFX and collision logic in
separate engine layers. Report untested engine behavior or pending approvals
without presenting them as complete.
