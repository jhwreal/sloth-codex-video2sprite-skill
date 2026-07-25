# Quality gates

## Automatic fail

- source cannot be decoded;
- requested frame count cannot be produced;
- any frame has no foreground;
- required audio stream is absent or effectively silent;
- output atlas, frame files, audio, manifest, or hashes are missing;
- provider result or logs contain inline media payloads.

## Automatic review

- foreground touches a cell edge;
- matte corner variance suggests a non-flat background;
- alpha area or baseline varies unexpectedly;
- loop first/last difference is high;
- audio peak approaches clipping;
- transient detection cannot find a plausible event;
- model capability is unknown or native audio was requested from a silent model.

Local OGG extraction applies a deterministic `0.85` gain before lossy encoding so
provider audio that arrives at or above full scale retains codec-safe headroom.
The measured decoded output peak remains the QC authority.

Thresholds are diagnostics, not aesthetic truth. Action-specific motion can legitimately change bounds, baseline, or occupied area.

## User result decision

Review:

- identity, view, style, proportions, palette, outfit, props, and handedness;
- required hand-to-handle contact and the absence of unrelated secondary
  equipment such as guns, holsters, scabbards, sheaths, pouches, or backpacks;
- action readability, weight, anticipation, impact, recovery, and loop;
- for linked combos, exact adjacent-stage boundary continuity and no visible
  idle reset before the final stage;
- anatomy and temporal consistency;
- transparent edges on checker, light, and dark backgrounds;
- baked effects and their spatial extent;
- sound identity, cleanliness, loudness, duration, and synchronization;
- proposed gameplay event frame.

Use the localhost workbench: all extracted frames fill the left pane, the
processed action video stays at the upper right, and clicking any frame updates
an enlarged still at the lower right. Use the left and right arrow keys to step
through adjacent frames; the selected thumbnail stays focused and scrolls into
view. The page has no scoring, note, approve, or redo controls. The user
communicates “use this” or “redo” in the conversation; record that explicit
decision locally. A short rejection reason is useful but optional.

Draft-profile review may be used to reject or select a direction, but it is not
a final delivery gate. Rebuild the selected candidate with the production
profile and review the resulting hashes again. Packaging rejects draft-profile
artifacts.

## Model comparison

Use identical input hashes where possible. Record:

- provider and resolved model ID;
- generation and download time;
- objective QC status and metrics;
- retries;
- human visual, motion, audio, sync, and overall scores;
- returned usage or cost metadata when available.

Select a default after at least one representative idle, attack, damage, and transformation test. A fast model may remain the draft default while a slower model is used for final production.

Use `compare` to aggregate only bounded metadata. Ranking order is human overall
score, approved-action count, QC pass count, then generation speed. Treat fewer
than four approved representative actions as provisional, and do not change the
environment default without the user's decision.
