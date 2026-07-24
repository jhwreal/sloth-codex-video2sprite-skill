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
```

The CLI must remain useful without credentials for `doctor`, `models`, `init`, `add-action`, `attach-video`, `process`, `status`, `review`, and `package`.

`VIDEO2SPRITE_PROCESS_PROFILE` accepts `draft` or `production`. Draft keeps the same frame selection, chroma removal, geometry, audio extraction, QC, and manifest semantics, but uses faster PNG compression and preview encoding. Packaging rejects draft artifacts.

`advance` uses the network and local worker limits. Four network workers are suitable for lightweight asynchronous status calls. Keep local workers at two unless the machine has enough CPU, memory, and storage bandwidth for concurrent FFmpeg/Pillow jobs.

The candidate budget counts remote candidates already registered for an action, including failed attempts that may still have incurred provider work. Local attached videos do not consume the remote budget. `submit --allow-over-budget` is the explicit escape hatch for a planned representative benchmark.

The CLI also rejects a new candidate whose generation fingerprint exactly
matches an existing candidate. Use `--allow-duplicate-input` only for an
intentional provider retry; it does not bypass the separate candidate budget.

## Provider-readable references

Video APIs usually require an HTTPS URL or provider asset URI for reference media. Store the local approved master in the run and supply one of:

- a stable HTTPS object URL;
- a short-lived signed URL, kept out of logs;
- a provider asset URI such as `asset://...`.

Do not paste signed URLs into agent messages. Pass them directly as a CLI argument or environment-sourced value. The worker redacts URL query strings from persisted summaries.

For a short-lived signed reference, prefer `VIDEO2SPRITE_REFERENCE_URL` or
`--reference-url-env YOUR_VARIABLE_NAME`; this keeps the signed URL out of CLI
arguments and bounded command output.
