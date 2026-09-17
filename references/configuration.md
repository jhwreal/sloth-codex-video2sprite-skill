# Configuration

## Explicit headless image API settings and credentials

These settings apply only to the existing `generate-master` CLI worker when
that API path is explicitly selected. Normal imagegen work follows
[image-workflow.md](image-workflow.md) and needs no CLI API key.

Image configuration resolves as CLI argument, environment variable, then
`assets/model-presets.json`. Video generation is external; configure its model
in LibTV or the selected tool. Follow the 768 default and prior 2K approval rule
in [video-workflow.md](video-workflow.md).

```text
OPENAI_API_KEY=
VIDEO2SPRITE_IMAGE_PROVIDER=openai
VIDEO2SPRITE_IMAGE_MODEL=gpt-image-2
VIDEO2SPRITE_IMAGE_BASE_URL=https://api.openai.com/v1
```

New master generation defaults to `1024x1024` and `--quality medium`;
`--size` and `--quality` can be overridden for a concrete output requirement.
Reuse an approved master instead of calling generation again to adopt new defaults.

The only credential managed by this CLI is `OPENAI_API_KEY`. The environment
wins over the fixed machine-local store:
`~/.config/sloth-codex-video2sprite/credentials.env`. Keep it outside the source,
Skill installation and all run directories. Never print it or commit it.

```bash
python scripts/video2sprite.py configure-key --name openai
# Or copy a key already set in the local environment:
python scripts/video2sprite.py configure-key --name openai --from-env OPENAI_API_KEY
```

The command uses hidden terminal input or an environment variable, never a raw
key argument. It creates a `700` directory and atomically writes a `600` file.
The loader rejects symlinks and broad permissions, never executes shell syntax,
and ignores unrecognized credential names. `doctor` reports configuration status
and source only. Do not ask the user to paste keys into the conversation.

## Runtime settings

```text
VIDEO2SPRITE_FFMPEG=ffmpeg
VIDEO2SPRITE_FFPROBE=ffprobe
VIDEO2SPRITE_LOG_MAX_CHARS=4096
VIDEO2SPRITE_HTTP_TIMEOUT=120
VIDEO2SPRITE_PROCESS_PROFILE=production
VIDEO2SPRITE_LOCAL_WORKERS=2
LIBTV_BIN=libtv
```

`doctor` starts FFmpeg and FFprobe with a bounded `-version` probe; a broken
executable or timeout is reported as unavailable before production work.

`doctor`, `models`, `init`, `add-action`, `export-prompt`, `attach-video`,
`process`, `advance`, `status`, `review`, and `package` work without API keys.
`libtv-download` uses the separately authenticated official LibTV CLI and always
passes `--without-ai-watermark --vip`; it does not manage LibTV credentials.

New runs default to a dark `#3f0050` matte with border-connected removal,
fixed-canvas placement, and Lanczos resizing. Pixel art should usually use
`--resampling nearest` and an explicit foot pivot such as `--pivot 144,144`.
Legacy footage may use `--placement fit-union` and `--chroma-mode global`.

`VIDEO2SPRITE_PROCESS_PROFILE` accepts `draft` or `production`. Draft changes
encoding speed only; frame selection, geometry, audio and QC remain the same.
Normal single-candidate work can use production directly and be reviewed once.
Only selected drafts need a production rebuild. Packaging requires production
processing and current user approval.

`advance --process-ready` processes ready local candidates in one pass using
at most the selected local worker count (default two). It has no provider
submission, polling, download, network-worker or wait-window options. Missing
local sources are reported without modifying historical candidate records.
Already downloaded historical videos remain eligible for processing and review.

## Motion and external generation

`add-action --motion-style`, `--root-motion`, and `--end-state` are action-local.
Defaults are `pixel-act`, `in-place`, and `recover` (`loop` when `--loop` is set).
See `prompting.md` and `job-schema.md` for motion and fingerprint semantics.

`export-prompt` writes the effective visual prompt to a new local text file,
with bounded metadata and its fingerprint on stdout. It never calls a provider
or overwrites an existing output. Use that prompt with the canonical master in
the external generator, retaining the selected video tier and any 2K approval
in production notes. Pilot review, generation budgets, duplicate avoidance and
2K approval are agent workflow requirements, not enforced by this local CLI.
