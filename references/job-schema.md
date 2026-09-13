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
            └── libtv-pilot/
                ├── candidate.json
                ├── source.mp4
                ├── source.receipt.json  # required only for LibTV origin
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
- image provider/model defaults;
- action identifiers.

## Action

`action.json` contains:

- `action_id`, prompt, frame count, requested/effective FPS, source duration,
  and action window;
- loop flag and audio requirement;
- `motion`: `{ "style": "pixel-act", "root_motion": "in-place",
  "end_state": "recover" }` by default for a new non-loop action;
- matte key, border/global mode, threshold, and softness;
- optional event names;
- candidate identifiers.

One action must describe one semantic motion. Do not put several attacks or camera cuts in one action.

`motion.style` accepts `pixel-act`, `restrained`, or `natural`.
`motion.root_motion` accepts `in-place`, `planted`, or `travel`.
`motion.end_state` accepts `recover`, `hold`, or `loop`; `loop` must agree with
the existing loop flag and cannot accumulate `travel`. The CLI supplies `loop`
from `--loop`; non-loops may select `--end-state recover|hold`. The detailed
meaning and action examples are in `prompting.md`. Invalid motion settings are
rejected before creating an action or exporting a prompt.

Older actions without `motion` remain readable and keep their existing
processing/review fingerprints. A new prompt export for such an action uses the
current prompt defaults (loop ending when its loop flag is set, otherwise
recover); it does not regenerate or rewrite an existing candidate. Explicitly
adding or changing `motion` changes action/processing fingerprints and makes
old approvals stale. Updating metadata or reprocessing alone does not improve
an already-generated video's movement; a new source or explicit acceptance of
that existing source is needed. No automatic migration or paid retry occurs.

A linked multi-input combo may use one continuous paid source video, but its
deliverables remain one action per player input. Derived stages share the same
source hash, FPS, pivot, and an exact adjacent boundary frame. Middle stages do
not return to idle; early combo termination uses a separate recovery branch.

## Candidate

`candidate.json` records the attached source origin, local source path and
SHA-256, audio presence, candidate identity and timestamps. LibTV sources include
a bounded `source.receipt.json` hash and summary proving both mandatory download
flags, file identity and declared ancestry. No raw provider payload is stored.

Historical candidates may retain provider/model metadata, task IDs, request
fingerprints and timing/usage information. These remain readable for comparison,
processing and audit; the CLI does not submit, poll or download their tasks.
Keep new external generation settings, video tier, reason and any 2K approval
scope in production notes. `export-prompt` reports the effective prompt hash
and resolved motion without creating a provider task or candidate.

## Manifest

`manifest.json` is the engine-neutral delivery contract:

- atlas dimensions and cell regions;
- per-frame file, source time, duration, pivot, and alpha bounds;
- audio path, duration, peak, RMS, and suggested transient markers;
- action loop and event metadata;
- provenance hashes.

Manifest provenance includes a processing fingerprint and processing profile.
The fingerprint covers the source, master, action semantics, output geometry,
atlas columns, profile, processor schema, source origin, and LibTV receipt hash
when present. A matching fingerprint plus the required files is a reusable
processing cache entry.
Explicit action `motion` settings are included in the action fingerprint, so
the review contract cannot be changed while retaining an old approval. They
are prompt/review metadata, not a per-frame root-motion track for the engine.

## Approval

`approval.json` contains the user's use/redo decision, optional note, timestamp,
reviewed hashes, and optional edited event markers. Legacy numeric scores remain
accepted metadata but are not requested by the normal workbench. Changing a
reviewed source, LibTV receipt, atlas, audio file, prompt, or model invalidates
the decision. A packaged LibTV action retains `source.receipt.json`.

The LibTV receipt is intentionally not a visual certificate. It binds the exact
downloaded artifact to the wrapper's simultaneous
`--without-ai-watermark --vip` invocation and records only hashed upstream
ancestry. It does not assert that the pixels contain no baked watermark;
automatic provenance/hash validation and human visual review remain separate
gates.

The run-level `review-queue.json` contains only bounded metadata and relative
local media paths. It is rebuilt when the reviewer starts and is never a media
container.
