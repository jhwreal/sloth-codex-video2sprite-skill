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
- chroma corner variance suggests a non-flat background;
- alpha area or baseline varies unexpectedly;
- loop first/last difference is high;
- audio peak approaches clipping;
- transient detection cannot find a plausible event;
- model capability is unknown or native audio was requested from a silent model.

Thresholds are diagnostics, not aesthetic truth. Action-specific motion can legitimately change bounds, baseline, or occupied area.

## Human audiovisual review

Review:

- identity, view, style, proportions, palette, outfit, props, and handedness;
- action readability, weight, anticipation, impact, recovery, and loop;
- anatomy and temporal consistency;
- transparent edges on checker, light, and dark backgrounds;
- baked effects and their spatial extent;
- sound identity, cleanliness, loudness, duration, and synchronization;
- proposed gameplay event frame.

Approve only through the local reviewer. Record notes for every rejection.

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
