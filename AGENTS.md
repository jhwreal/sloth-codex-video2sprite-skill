# AGENTS.md

## Scope

This directory is the source of truth for the `sloth-codex-video2sprite-skill` Codex Skill.

- Source: `/Users/john/Documents/slothsunolyric/sloth-codex-video2sprite-skill`
- Git remote: `git@github.com:jhwreal/sloth-codex-video2sprite-skill.git`
- Codex install: `~/.codex/skills/sloth-codex-video2sprite-skill`
- Keep the directory name, `SKILL.md` name, install directory, and `$sloth-codex-video2sprite-skill` invocation identical.
- Commit or push only when the user explicitly requests it.

## Purpose and boundaries

Create high-quality 2D game sprite animations with synchronized sound from a canonical still and one generated or supplied action video. Use GPT Image 2 for optional master generation, external generation through LibTV or supplied local action clips, and deterministic local processing for frames, transparency, audio, QC, review, and packaging.

Do not depend on or modify `my-codex-sprite-skill`. Do not make a conversational image tool part of the production path. Do not infer gameplay hitboxes, projectile behavior, or approval from pixels alone.

## Cost and motion policy

Optimize total cost per accepted gameplay action. Reuse approved sources, start
videos at 768 with a large complete subject, use short sufficient durations and
concise action-specific briefs. Require a reason and explicit approval before
2K. Validate a representative pilot before expansion; stop repeating a failure
without diagnosis. Ordinary candidates can be processed as production directly.

Preserve the requested pose contrast, timing, scale, root and ending. Translate
internal engine/pivot settings into visible movement for provider prompts. The
exporter adds only the selected motion/ending and shared constraints; do not add
unrelated action catalogues. Clean visuals, no BGM and required dry SFX remain.
Keep legacy processing caches valid; offline prompt tests do not prove visual
improvement. Production specifics belong in the references, not duplicated here.

## Media firewall

- Never print or return Base64, data URLs, media bytes, signed URL query strings, full provider payloads, credentials, or unbounded logs.
- Decode provider media inside the worker and write it directly to disk.
- Limit CLI stdout to compact JSON summaries. Redact all debug and error output through the same safe serializer.
- Keep generated runs, raw media, caches, review decisions, and private references outside the Skill source.
- Review media through the localhost reviewer; agents use the bounded `status` or
  `compare` command and read only small `qc.json`, `manifest.json`, and
  `approval.json` files.

Any change that can expose media payloads must add a regression test proving stdout and persisted logs remain bounded and contain no Base64 or data URL.

## Dependencies

- Python 3.9 or newer.
- Pillow and NumPy.
- FFmpeg and FFprobe.
- Network access and provider credentials only for real API calls.

Do not install packages without user approval. Prefer the Codex bundled Python when the system runtime lacks Pillow or NumPy.

## Change workflow

Before changing behavior, read `SKILL.md`, the relevant reference, and every affected script. Keep CLI help, schemas, references, tests, and Skill instructions synchronized.

Validate at minimum:

1. `skill-creator` `quick_validate.py`.
2. Python bytecode compilation for all scripts and tests.
3. `--help`, `doctor`, and `models` CLI smoke checks.
4. Unit tests, including the media-firewall test.
5. A synthetic offline end-to-end video-to-sprite run with audio.
6. `git diff --check` and a scan for secrets, absolute runtime paths, Base64 fixtures, caches, and generated media.

Run paid or live-provider tests only after credentials are configured and the user has authorized the call. Install only after source validation passes, and exclude `.git`, tests, caches, environments, and runtime outputs from the installed copy.

## Provider and model rules

- Image settings resolve as CLI override, environment, then bundled preset. Video model selection belongs to the external generator.
- Keep model IDs configurable; presets are not proof that a model is enabled on the user's account.
- Preserve provider task IDs and input hashes so interrupted work resumes without accidental duplicate billing.
- `advance` processes local candidates only. Do not restore direct video-provider submission or polling; preserve historical media and metadata.
- A valid processing-cache hit must not rewrite artifacts or invalidate approval.
- Apply pilot review and retry budgets in the agent workflow before external generation; the local CLI has no billed-task guard.
- Draft processing is for selection only; packaging requires production processing followed by a current approval.
- Compare models using the same reference, prompt, duration, resolution, and seed where possible.
- Require native audio for the default production goal unless the user explicitly accepts a silent model or adds a separate audio provider.
- Route every LibTV artifact through `libtv-download`; it must always pass
  `--without-ai-watermark --vip`, issue a bounded receipt, and require an
  explicit upstream-reference audit. Never classify LibTV output as ordinary
  local media to bypass the gate.
- If a LibTV generation reference came from LibTV, require its matching clean
  artifact/receipt ancestor. Never re-upload frames from unreceipted or visibly
  watermarked candidates. A receipt proves invocation and file identity only;
  it cannot replace machine and human visual watermark review.

## Privacy and release

Never commit API keys, `.env` files, private image URLs, signed URLs, user media, generated outputs, or provider responses. Store only reusable source, sanitized fixtures, and programmatically generated test media. Do not claim commercial rights or provider availability; preserve provenance and require the user to verify provider terms for their assets.
