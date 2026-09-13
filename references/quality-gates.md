# Quality and acceptance

## Machine checks

Fail on undecodable source, missing/empty frames, missing required audio, missing
artifacts or invalid hashes. A LibTV source also requires a valid source receipt,
both download flags and verified declared ancestry. Reject media-bearing logs.

Review warnings about edge contact, matte variation, bounds/baseline changes,
loop difference, near-clipping audio or uncertain event detection. They are
diagnostics, not aesthetic decisions: a lunge, crouch or collapse legitimately
changes bounds. QC does not measure every aspect of action quality or prove
anatomical scale stability. Extracted OGG uses `0.85` pre-encode gain; the decoded
output peak is the audio QC authority.

LibTV receipt 只证明双参数调用与文件身份，不证明视觉无水印。上游参考和最终
画面都要检查；不得用错误来源标签、无凭据抽帧或裁切水印绕过检查。

## Review only what makes the action usable

At actual gameplay size and speed, check:

- identity, facing, proportions, equipment and grip;
- sufficiently large/clear subject, complete body/weapon path and consistent scale;
- requested pose contrast, timing, amplitude and correct recovery/terminal/loop;
- transparent edges and enclosed background pockets without missing costume;
- no added VFX, BGM or watermarks; required SFX remains synchronized;
- event frame, pivot and transitions in the target engine.

Choose “use this” when the action meets its target. Optional cosmetic refinements
are not a reason to buy more candidates by default. A short failure-specific
reason for “redo” helps; numeric scoring is optional legacy metadata.

## Record the user's decision

The normal generation reviewer shows a filmstrip on the left, video at upper
right and an enlarged clicked frame below. Arrow keys step frames. The header
identifies the current Sprite, action and candidate. It is observation-only;
the user gives the use/redo decision in conversation. Sprite editing may instead
use the explicit confirmation UI described in `sprite-edit-workbench.md`.

Only after that decision, call the bounded local helper from `scripts/review_server.py`:

```python
write_decision(candidate_dir, action_id="attack", candidate_id="pilot",
               decision="approved", note="<the user's actual decision>")
```

Import `write_decision` with the Skill's `scripts` directory on the Python path;
`candidate_dir` is its resolved local Path. Use `rejected` for redo. Do not invent
notes about checks the user did not make. The helper writes `approval.json` bound
to current hashes and rejects approval when machine QC fails.

Packaging requires current approval and `production` artifacts. Source, timing,
atlas, receipt or processing changes invalidate the old decision. Selected
`draft` candidates need a production rebuild and review; direct-production
candidates already follow the final review path.

## Optional model comparison

`compare` summarizes existing candidate metadata, approvals, QC, time/usage and
optional historical scores without opening media or changing defaults. Its
recommendation is provisional; score or action count alone does not establish
cost effectiveness. Do not generate extra test actions to satisfy an arbitrary
count. Use the actual action mix, accepted quality and known cost as described in
`efficiency.md`; missing price information remains unknown.
