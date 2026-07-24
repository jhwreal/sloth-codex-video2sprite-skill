# Job and artifact schema

## Run layout

```text
run/
├── run.json
├── review.html
├── review-queue.json
├── master/
│   └── source.png
└── actions/
    └── attack/
        ├── action.json
        └── candidates/
            └── seedance-2.0/
                ├── candidate.json
                ├── source.mp4
                ├── frames/
                ├── atlas.png
                ├── sfx.ogg
                ├── preview.mp4
                ├── manifest.json
                ├── qc.json
                ├── review-data.json
                └── approval.json
```

Runtime media belongs in the run, never in the Skill source.

## Run

`run.json` contains:

- `schema_version`;
- `character_id`;
- local `master_path` and SHA-256;
- output `frame_size`;
- fixed-canvas placement, resampling mode, and explicit pivot;
- default extraction-matte key, mode, threshold, and softness;
- provider/model defaults;
- action identifiers.

## Action

`action.json` contains:

- `action_id`, prompt, frame count, requested/effective FPS, source duration,
  and action window;
- loop flag and audio requirement;
- matte key, border/global mode, threshold, and softness;
- optional event names;
- candidate identifiers.

One action must describe one semantic motion. Do not put several attacks or camera cuts in one action.

A linked multi-input combo may use one continuous paid source video, but its
deliverables remain one action per player input. Derived stages share the same
source hash, FPS, pivot, and an exact adjacent boundary frame. Middle stages do
not return to idle; early combo termination uses a separate recovery branch.

## Candidate

`candidate.json` records:

- provider, alias, resolved model ID, and model capabilities;
- purpose (`draft`, `final`, or `benchmark`);
- input hash and optional seed;
- a bounded request summary with reference role, resolution, ratio, duration,
  audio, and watermark flags;
- a sanitized URL/asset reference or canonical local path, never inline media;
- task ID and bounded status;
- local source path and SHA-256;
- timestamps and state transitions;
- whether the run-level paid-pilot gate was explicitly overridden;
- no raw provider payload.

## Manifest

`manifest.json` is the engine-neutral delivery contract:

- atlas dimensions and cell regions;
- per-frame file, source time, duration, pivot, and alpha bounds;
- audio path, duration, peak, RMS, and suggested transient markers;
- action loop and event metadata;
- provenance hashes.

Manifest provenance includes a processing fingerprint and processing profile.
The fingerprint covers the source, master, action semantics, output geometry,
atlas columns, profile, and processor schema. A matching fingerprint plus the
required files is a reusable processing cache entry.

## Approval

`approval.json` contains the user's use/redo decision, optional note, timestamp,
reviewed hashes, and optional edited event markers. Legacy numeric scores remain
accepted metadata but are not requested by the normal workbench. Changing a
reviewed source, atlas, audio file, prompt, or model invalidates the decision.

The run-level `review-queue.json` contains only bounded metadata and relative
local media paths. It is rebuilt when the reviewer starts and is never a media
container.
