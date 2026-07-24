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
- default chroma key;
- provider/model defaults;
- action identifiers.

## Action

`action.json` contains:

- `action_id`, prompt, frame count, source duration, action window;
- loop flag and audio requirement;
- chroma key and threshold;
- optional event names;
- candidate identifiers.

One action must describe one semantic motion. Do not put several attacks or camera cuts in one action.

## Candidate

`candidate.json` records:

- provider, alias, resolved model ID, and model capabilities;
- purpose (`draft`, `final`, or `benchmark`);
- input hash and optional seed;
- task ID and bounded status;
- local source path and SHA-256;
- timestamps and state transitions;
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

`approval.json` contains the human decision, note, optional visual/motion/audio/
sync/overall scores, timestamp, reviewed hashes, and optional edited event
markers. Changing a reviewed source, atlas, audio file, prompt, or model
invalidates approval.

The run-level `review-queue.json` contains only bounded metadata and relative
local media paths. It is rebuilt when the reviewer starts and is never a media
container.
