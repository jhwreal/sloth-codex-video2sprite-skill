# Cost and throughput

Optimize **total billed cost per accepted gameplay action**. Record known spend,
accepted action count, retries and unresolved failures. If cost is unavailable,
record tier, billed duration and attempt count as proxies; do not invent prices
or claim that a shorter prompt itself reduces provider billing.

## Plan free reuse first

Map the requested action set to existing approved sources before generation:

| Source | Reuse when |
| --- | --- |
| Approved master | Identity, view, equipment and framing still fit. No new image per action. |
| Existing action video | Its motion/ending fit; a new window, matte setting or target atlas can be processed locally. |
| Shared action asset | Two gameplay uses truly need the same visible motion; reuse pixels and set game events separately. |
| Continuous combo | The requested sequence is naturally continuous and each input can be split at a clear bridge pose. |
| Mirrored direction | Handedness, asymmetric design, lighting and gameplay allow it; verify in the engine. |

Do not reverse attacks/death/audio, call a static hold a new animation, or bundle
unrelated moves into one clip just to increase the count. Linked sequences can
reduce separate requests, but may cost more per attempt or be harder to get right;
compare the actual provider's duration/billing unit before batching. Preserve
source, provenance, complete movement and all existing approved versions.

## Use the least sufficient generation settings

1. Start at **768**, with the subject large enough for target sprite detail.
   Fix composition before increasing pixel count. A lower supported tier may be
   tried on the pilot when it can still satisfy the target; don't regenerate a
   whole usable batch merely to benchmark settings.
2. Choose the shortest supported clip that contains the action and its ending.
   Do not stretch a quick strike to fill the provider minimum. Longer clips are
   justified only by motion/continuity needs, not extra idle padding.
3. Prefer a compatible economical model already proven for this visual style and
   required sound. No compulsory multi-model or four-action benchmark. Use a
   representative pilot covering the main risk (e.g. full weapon reach), then add
   a different pilot only if the remaining actions have a materially new risk.
4. A higher tier needs a specific unresolved source-detail problem. **2K always
   requires a reason and explicit user approval for its scope.** Do not infer
   approval from production mode or from a retry request.
5. Use a suitable existing master; new image quality defaults to `medium`.
   Smaller/cheaper settings only help if the identity and prop grip remain clear.
   Reuse a successful image; a quality setting change is a new paid request.

Provider model, resolution, reference role and audio must be supported by the
selected tool. Do not silently relabel tiers or invent an unsupported parameter.
Keep source/anatomical scale and final game scale consistent when comparing.

## Generate, verify, expand

Generate one pilot and process at `production` for normal final-ready review.
Review at actual gameplay size and speed. Once the user adopts it, generate the
remaining independent actions with that recipe and use one run-level reviewer.
Don't regenerate selected draft source videos as a mandatory final step.

Use `draft` only for meaningful local selection savings on large/multiple
candidates. It changes local encoding, not provider tier or source detail.
Chosen drafts need one production rebuild and current approval; ordinary
production candidates do not need this extra pass.

`advance --process-ready` processes attached local videos concurrently (default
two workers). It cannot submit, poll or download provider tasks. More workers can
lose time to CPU/PNG contention. `status --compact` gives bounded progress.

## Retry decision

- **Local issue:** wrong window, matte tolerance, placement, event or export;
  adjust and reprocess existing source before buying another video.
- **Source issue:** wrong identity, inadequate detail, clipped action, unwanted
  motion/VFX/music or incorrect ending; make one specific correction.
- **Ambiguous provider result:** check the existing task/node before retrying to
  avoid duplicate billing. Keep its ID and input hashes in production notes.

Default to one candidate plus one targeted retry per action within the user's
budget. Stop expansion after repeated failure; diagnose and explain a revised
approach before further paid attempts. An attractive optional refinement is not
required when the accepted action already meets the game's target.

## Local reuse and provenance

Verified identical `generate-master` inputs reuse the output without another
image request. Changed/unverifiable inputs require explicit `--overwrite`.
Prompt/default updates do not authorize regenerating an approved master.
`process` caches source/master/action/geometry/profile/receipt fingerprints.
A hit must not rewrite output or invalidate approval; `--force` does both.
Preserve original media and LibTV source/ancestor receipts for all derived uses.
