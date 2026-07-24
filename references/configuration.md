# Configuration

## Precedence

Resolve every setting in this order:

1. CLI argument.
2. Candidate, action, or run JSON.
3. Environment variable.
4. `assets/model-presets.json`.

Do not silently replace an explicitly selected provider or model.

## Credentials

Use environment variables only:

```text
OPENAI_API_KEY
ARK_API_KEY
```

Never place credentials in a run, `.env` committed to Git, prompt, command output, or approval file. A local uncommitted `.env` may be used by the shell, but the Skill does not parse it automatically.

## Model and endpoint settings

```text
VIDEO2SPRITE_IMAGE_PROVIDER=openai
VIDEO2SPRITE_IMAGE_MODEL=gpt-image-2
VIDEO2SPRITE_IMAGE_BASE_URL=https://api.openai.com/v1

VIDEO2SPRITE_VIDEO_PROVIDER=volcengine-ark
VIDEO2SPRITE_VIDEO_MODEL=seedance-2.0
VIDEO2SPRITE_VIDEO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VIDEO2SPRITE_REFERENCE_URL=
```

`VIDEO2SPRITE_VIDEO_MODEL` accepts a bundled alias or a full provider model ID. Availability is account-specific. Run `video2sprite.py models` to inspect aliases, then verify live availability with the user's provider account.

Use `--model` for a one-off override. Use environment configuration only after a model comparison establishes a preferred default.

The CLI does not rewrite `.env` or shell configuration. `compare` prints a
suggested environment assignment, and the user decides whether to adopt it.

## Runtime settings

```text
VIDEO2SPRITE_FFMPEG=ffmpeg
VIDEO2SPRITE_FFPROBE=ffprobe
VIDEO2SPRITE_LOG_MAX_CHARS=4096
VIDEO2SPRITE_HTTP_TIMEOUT=120
VIDEO2SPRITE_PROCESS_PROFILE=production
VIDEO2SPRITE_NETWORK_WORKERS=4
VIDEO2SPRITE_LOCAL_WORKERS=2
VIDEO2SPRITE_MAX_CANDIDATES_PER_ACTION=2
VIDEO2SPRITE_ADVANCE_WAIT_SECONDS=0
VIDEO2SPRITE_POLL_INTERVAL_SECONDS=10
```

The CLI must remain useful without credentials for `doctor`, `models`, `init`, `add-action`, `attach-video`, `process`, `status`, `review`, and `package`.

`VIDEO2SPRITE_PROCESS_PROFILE` accepts `draft` or `production`. Draft keeps the same frame selection, matte removal, geometry, audio extraction, QC, and manifest semantics, but uses faster PNG compression and preview encoding. Packaging rejects draft artifacts.

New runs default to a dark `#3f0050` matte with border-connected removal,
fixed-canvas placement, and Lanczos resizing. Pixel-art projects should usually
pass `--resampling nearest` and an explicit in-cell foot pivot such as
`--pivot 144,144`. Legacy footage may opt into `--placement fit-union` and
`--chroma-mode global`.

`advance` uses the network and local worker limits. Four network workers are suitable for lightweight asynchronous status calls. Keep local workers at two unless the machine has enough CPU, memory, and storage bandwidth for concurrent FFmpeg/Pillow jobs.

`VIDEO2SPRITE_ADVANCE_WAIT_SECONDS` defaults to `0` for a single nonblocking
pass and is capped at `55`. Set it to `50`, or pass `--wait-seconds 50`, to
collapse several provider polls into one bounded command result. Poll intervals
must remain between 2 and 30 seconds.

The candidate budget counts remote candidates already registered for an action, including failed attempts that may still have incurred provider work. Local attached videos do not consume the remote budget. `submit --allow-over-budget` is the explicit escape hatch for a planned representative benchmark.

The CLI also rejects a new candidate whose generation fingerprint exactly
matches an existing candidate. Use `--allow-duplicate-input` only for an
intentional provider retry; it does not bypass the separate candidate budget.

The first remote action in a run becomes its paid pilot. Until one remote pilot
candidate has a valid “approved” decision, `submit` rejects a different action.
The same pilot action can still receive a retry or model comparison.
`--allow-unapproved-batch` bypasses this run-level gate only when the user has
explicitly authorized that billed batch.

## Provider-readable references

The preferred path for Ark is the canonical master already copied into the run:

```bash
python scripts/video2sprite.py submit \
  --run-dir /absolute/path/to/run \
  --action-id attack \
  --reference-file /absolute/path/to/run/master/source.png
```

The worker requires the local file hash to equal `run.json`'s master hash, validates Ark's image size and dimensions locally, and encodes the image only inside the provider request. The data URL is released after the request and never enters stdout, run JSON, or persisted logs.

Provider-readable references remain available when a local file is unsuitable. Supply one of:

- a stable HTTPS object URL;
- a short-lived signed URL, kept out of logs;
- a provider asset URI such as `asset://...`.

Do not paste signed URLs into agent messages. Pass them directly as a CLI argument or environment-sourced value. The worker redacts URL query strings from persisted summaries.

For a short-lived signed reference, prefer `VIDEO2SPRITE_REFERENCE_URL` or
`--reference-url-env YOUR_VARIABLE_NAME`; this keeps the signed URL out of CLI
arguments and bounded command output.

Direct `data:` URLs are rejected at the CLI and provider boundaries. Use
`--reference-file` so the media firewall can keep encoded bytes inside the
worker.
