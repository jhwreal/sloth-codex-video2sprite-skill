# Efficiency and batching

## Fast default path

1. Approve one canonical master and reuse its hash for the entire character.
2. Define all known actions before starting provider work.
3. Submit one draft candidate for the hardest representative pilot action.
4. Advance and process that pilot in bounded polling windows:

   ```bash
   python scripts/video2sprite.py advance \
     --run-dir /absolute/path/to/run \
     --process-ready \
     --profile draft \
     --wait-seconds 50
   ```

5. Review the pilot from the localhost workbench. Do not use `view_image`,
   screenshots, `read_thread`, or a vision subagent.
6. Only after the user adopts a remote pilot, submit one draft candidate per
   remaining action close together. Every `submit` is an explicit billed action.
7. Repeat the bounded pass later while submitted provider tasks remain queued or running.
8. Review every ready candidate from one run-level reviewer:

   ```bash
   python scripts/video2sprite.py review --run-dir /absolute/path/to/run
   ```

9. Regenerate only rejected actions. Reprocess selected finals with
   `--profile production`, review them again, then package.

`advance` never submits provider work. Without `--wait-seconds` it makes one
nonblocking pass; with it, the command polls internally for at most 55 seconds
and emits one final bounded JSON summary. This replaces dozens of conversational
poll turns without hiding an indefinitely running worker.

The CLI blocks a different remote action while the paid pilot gate is locked.
Retries or model comparisons on the same pilot action remain possible.
`--allow-unapproved-batch` is an explicit billed-risk override, not a normal
fast path.

## Model pilot

Do not test every model on every action. Select a small pilot that covers the
hard differences:

- idle or locomotion for loop and identity stability;
- attack for fast pose change and impact audio;
- jump or dodge for large translation and framing;
- an action with wide weapon reach and moving hair/cloth for matte-edge
  contamination and action-sound synchronization, without added VFX or BGM.

Submit the same pilot inputs to candidate models, mark them with
`--purpose benchmark`, and compare them using the user's use/redo decision,
optional legacy score metadata, QC, and elapsed generation time. The default
budget is two remote candidates per action. Use
`--allow-over-budget` only when the pilot intentionally needs more.

After a winner is selected, set `VIDEO2SPRITE_VIDEO_MODEL` for subsequent
actions. Do not silently change the user's environment from the Skill.

## Incremental processing cache

`generate-master` also has a billed-input cache. If the output PNG, its hash,
prompt, model, size, quality, and matte match the provenance sidecar, an
identical invocation returns `cached: true` without calling GPT Image 2.

The processing fingerprint covers:

- source video SHA-256;
- canonical master SHA-256;
- action processing fingerprint;
- output frame size and atlas columns;
- draft or production profile;
- processor schema version.

When the fingerprint and required artifacts match, `process` returns
`cached: true`. It does not decode media, rewrite files, or archive an existing
approval. `--force` bypasses the cache and therefore invalidates prior review.

Changing from draft to production is an intentional cache miss. Production
must be reviewed after rebuilding; the packager rejects draft artifacts.

## Concurrency

- Network workers only perform independent provider status/download work.
- Local workers run independent FFmpeg/Pillow pipelines in separate candidate
  directories.
- Fixed-placement decoding scales and pads to the logical sprite canvas inside
  FFmpeg before temporary PNG extraction. A 1152×704 source targeting 288×176
  therefore writes and keys one-sixteenth as many pixels per frame.
- Defaults are four network workers and two local workers.
- Increasing local concurrency can reduce throughput when PNG compression,
  memory bandwidth, or storage is saturated. Measure before raising it.

## Retry budget

Regenerate only for a source-level failure: identity drift, wrong action,
camera movement, unusable background, missing required sound, or failed human
review. Do not regenerate for a deterministic extraction failure until the
local configuration or source window has been corrected.

Keep one normal candidate and at most one retry per action. Additional
candidates require an explicit benchmark rationale. An exact generation
fingerprint match is blocked even under the candidate budget; use
`--allow-duplicate-input` only when repeating those inputs is intentional.

## Conversation context

The worker boundary alone is not enough if a task later reloads its media:

- conversational `imagegen` returns encoded image results;
- `view_image` and screenshots return image payloads;
- `read_thread`, including calls configured with `includeOutputs=false`, may
  still rehydrate structured image-generation results;
- subagents and monitoring tasks can duplicate those payloads again.

Use only local paths, hashes, `status --compact`, bounded `advance` output, the
localhost reviewer, and small approval JSON. Never inspect generated media
inside the agent conversation.
