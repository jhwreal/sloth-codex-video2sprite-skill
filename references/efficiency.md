# Efficiency and batching

## Fast default path

1. Approve one canonical master and reuse its hash for the entire character.
2. Define all known actions before starting provider work.
3. Generate one draft candidate per action with the current preferred model.
4. Submit independent jobs close together; every `submit` is an explicit billed action.
5. Run one nonblocking batch pass:

   ```bash
   python scripts/video2sprite.py advance \
     --run-dir /absolute/path/to/run \
     --process-ready \
     --profile draft
   ```

6. Repeat the pass later while submitted provider tasks remain queued or running.
7. Review every ready candidate from one run-level reviewer:

   ```bash
   python scripts/video2sprite.py review --run-dir /absolute/path/to/run
   ```

8. Regenerate only rejected actions. Reprocess selected finals with
   `--profile production`, review them again, then package.

`advance` never submits provider work and never loops until completion. Its
bounded JSON summary is safe for orchestration without placing media in the
conversation.

## Model pilot

Do not test every model on every action. Select a small pilot that covers the
hard differences:

- idle or locomotion for loop and identity stability;
- attack for fast pose change and impact audio;
- jump or dodge for large translation and framing;
- VFX-heavy action for chroma spill and transient synchronization.

Submit the same pilot inputs to candidate models, mark them with
`--purpose benchmark`, and compare them using human scores plus QC and elapsed
generation time. The default budget is two remote candidates per action. Use
`--allow-over-budget` only when the pilot intentionally needs more.

After a winner is selected, set `VIDEO2SPRITE_VIDEO_MODEL` for subsequent
actions. Do not silently change the user's environment from the Skill.

## Incremental processing cache

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
