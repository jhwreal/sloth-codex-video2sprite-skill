# Provider contracts

## GPT Image 2

For an explicitly selected headless API workflow, retain the existing one-shot
canonical-master worker. Normal built-in imagegen uses the scoped
[image workflow](image-workflow.md); this API contract does not apply to it.

- Default model: `gpt-image-2`.
- Credential: `OPENAI_API_KEY`, resolved from the environment first and then
  the fixed private store documented in `configuration.md`.
- Default endpoint: `POST /v1/images/generations`.
- The API returns Base64 image data. Decode it inside the worker and discard the encoded string before emitting any status.
- This pipeline requests a flat extraction matte absent from the character.
  Default image quality is `medium`; reuse a suitable approved master.
- Do not enable streaming or partial images; they multiply media payloads without helping this workflow.
- Retry only when the provider clearly reports a retry-safe failure. Do not automatically
  repeat an ambiguous generation request, because that can create duplicate billed work.
  Never retry user or moderation errors unchanged.

The worker may store request ID, model, usage numbers, output path, size, and hash. It must not store or print `b64_json`.

The adjacent provenance sidecar includes a generation fingerprint over the
prompt, provider, model, size, quality, and matte. A verified identical output
is reused without another API request. Any changed input or mismatched output
hash requires an intentional `--overwrite`.

## External video intake

Generate videos through LibTV or the user's external tool, using the canonical
master and `export-prompt` output. The Skill has no direct video-provider adapter.
Select 768 by default. Explain why 2K is needed and obtain explicit user approval
before generation. Review a representative pilot before expanding to other actions.

For LibTV, use `libtv-download` with the upstream-reference audit. The wrapper
always supplies `--without-ai-watermark --vip` and emits a bounded receipt.
Use `attach-video --source-origin libtv --source-receipt ...` for those artifacts.
Ordinary supplied local videos use `--source-origin local`. Retain source hashes
and receipts; a download receipt cannot replace visual watermark review.

Existing downloaded source videos and legacy candidate metadata remain readable.
Pending remote task records are historical evidence only. `advance` cannot poll
or download them; obtain the missing video externally before local processing.

## Official image reference

- OpenAI image generation: `https://developers.openai.com/api/docs/guides/image-generation`

Re-check the official reference before changing image API request fields.
